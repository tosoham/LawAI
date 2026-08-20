"""
RAG (Retrieval-Augmented Generation) Service for LawAI
Combines vector search with LLM for contextual legal responses
"""
import logging
from typing import Any

from agents.citations import primary_citation

from .legal_graph import GraphContext, get_legal_graph, section_key
from .llm_service import llm_service
from .retrieval.offence_lookup import find_offences
from .vector_service import get_vector_service

logger = logging.getLogger(__name__)

# How many retrieved chunks seed graph expansion. Expansion is only worth
# anything if the seeds are right, and a low-ranked chunk drags in material
# about something the user did not ask about.
GRAPH_SEED_DEPTH = 3

# The one canonical disclaimer. Every generated answer carries it, and the marker
# is stable so a client that renders its own styled version can strip this copy
# instead of showing the warning twice — see stripDisclaimer in frontend/lib/api.ts.
DISCLAIMER_MARKER = "**DISCLAIMER**"
DISCLAIMER = (
    f"{DISCLAIMER_MARKER}: This is AI-generated legal information for educational "
    "purposes only. Please consult a qualified lawyer for legal advice specific to "
    "your situation."
)


def with_disclaimer(answer: str) -> str:
    """Append the canonical disclaimer, without duplicating one already present."""
    if DISCLAIMER_MARKER in answer:
        return answer
    return f"{answer}\n\n{DISCLAIMER}"


class RAGService:
    """Service for RAG-based legal question answering"""

    def __init__(self):
        """Initialize RAG service with vector and LLM services"""
        self.vector_service = get_vector_service()
        self.llm_service = llm_service

    def _format_context(self, search_results: dict[str, Any]) -> str:
        """
        Format search results into context for LLM

        Args:
            search_results: Results from vector search

        Returns:
            Formatted context string
        """
        documents = search_results.get('documents', [])
        metadatas = search_results.get('metadatas', [])

        if not documents:
            return "No relevant legal provisions found."

        context_parts = []
        for i, (doc, meta) in enumerate(zip(documents, metadatas, strict=True), 1):
            # Format based on document type
            if 'section_number' in meta:
                # Legal section
                header = f"[{i}] {meta.get('act', 'Unknown Act')}, Section {meta.get('section_number', 'N/A')}"
                if 'title' in meta:
                    header += f" - {meta['title']}"
            elif 'case_name' in meta:
                # Court judgement.
                #
                # The id is part of the header because a holding or
                # interpretation claim is verified by looking its judgement up
                # by id -- `SourceKind.JUDGEMENT` only recognises a ref shaped
                # `sc_...`, and the synthesis prompt tells the model to cite
                # "the judgement id exactly as given". It was never given. The
                # model saw a case name, cited a case name, and the verifier
                # classified that as `UNKNOWN` and rejected every such claim
                # for naming no judgement. Measured over the golden set before
                # this line existed: 40 rejected claims from this one cause,
                # and all 12 judgement queries driven to abstention -- the
                # `holding` and `interpretation` classes were unreachable.
                #
                # The citation is trimmed to the leading report for the reason
                # `primary_citation` exists: Indian Kanoon lists every parallel
                # reporter, and Siddharam Mhetre's run past 900 characters of
                # header before a word of the judgement is reached.
                header = f"[{i}] {meta.get('case_name', 'Unknown Case')}"
                reported = primary_citation(meta.get('citation'))
                if reported:
                    header += f" {reported}"
                if meta.get('parent_id'):
                    header += f" [id: {meta['parent_id']}]"
            else:
                header = f"[{i}] Legal Document"

            context_parts.append(f"{header}\n{doc}\n")

        return "\n".join(context_parts)

    def _format_sources(self, search_results: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Format search results into source citations

        Args:
            search_results: Results from vector search

        Returns:
            List of source dicts
        """
        documents = search_results.get('documents', [])
        metadatas = search_results.get('metadatas', [])
        distances = search_results.get('distances', [])
        ids = search_results.get('ids', [])

        sources = []
        for doc, meta, distance, doc_id in zip(
            documents, metadatas, distances, ids, strict=True
        ):
            source = {
                'id': doc_id,
                'text': doc[:200] + "..." if len(doc) > 200 else doc,  # Truncate for response
                'metadata': meta,
                # Cosine distance -> similarity. Must test for None, not truthiness:
                # a distance of 0.0 is a *perfect* match and would otherwise score 0.0.
                'relevance_score': float(1 - distance) if distance is not None else 0.0
            }
            sources.append(source)

        return sources

    def _expand_over_graph(
        self, search_results: dict[str, Any], query: str = ""
    ) -> GraphContext:
        """
        Ask the graph what the top retrieved sections connect to.

        This closes a gap embedding distance cannot: the five judgements
        construing BNSS 482 never use the words someone asking about
        anticipatory bail would, so they are unreachable by similarity no
        matter how the query is phrased.

        A classification question seeds the offence it names as well, ahead of
        anything retrieved. "Bailable" and "cognizable" are First Schedule
        words that appear nowhere in the BNS, so "is murder bailable" ranks BNS
        103 sixth and it never reaches the model -- see
        ``services.retrieval.offence_lookup``.
        """
        seeds: list[str] = list(find_offences(query))
        for metadata in search_results.get("metadatas", [])[:GRAPH_SEED_DEPTH]:
            act = metadata.get("short_name")
            section = metadata.get("section_number")
            if act and section:
                seeds.append(section_key(act, section))
        if not seeds:
            return GraphContext((), (), (), (), (), ())
        return get_legal_graph().expand(seeds)

    def _format_graph_context(self, graph: GraphContext) -> str:
        """
        Render graph material for the prompt, keeping its kinds apart.

        The separation is not cosmetic. Related sections and judgements are
        *pointers*: the graph holds their titles and one-line subjects, not
        their text, so the model must be able to name them without being
        licensed to say what they provide. Doctrine summaries and offence
        attributes are real content and can be stated. Flattening these into
        one "related material" block is how a pointer becomes a fabricated
        holding.
        """
        if graph.is_empty:
            return ""

        blocks: list[str] = []
        if graph.classification:
            rows = []
            for row in graph.classification:
                cognizable = row["cognizable_text"].rstrip(".")
                bailable = row["bailable_text"].rstrip(".")
                rows.append(
                    f"- {row['short_name']} {row['section']} ({row['offence']}) — "
                    f"{cognizable}; {bailable}; triable by {row['triable_by'].rstrip('.')}"
                )
            blocks.append(
                "OFFENCE CLASSIFICATION (from the First Schedule to the BNSS; these "
                "are facts and may be stated). Cite the section shown here for any "
                "classification: it is the section that punishes the offence, which "
                "is not always the one that defines it:\n" + "\n".join(rows)
            )

        if graph.doctrines:
            rows = [f"- {d.name}: {d.summary}" for d in graph.doctrines]
            blocks.append(
                "DOCTRINE (curated; may be stated, attributed to the cases below):\n"
                + "\n".join(rows)
            )

        if graph.judgements:
            # The id is given for the same reason as in `_format_context`: a
            # claim citing this case is checked by looking the id up, so a
            # pointer the model can name but not cite verifiably is a pointer
            # it can only use unverifiably.
            rows = [
                f"- {j.case_name}"
                + (f", {j.citation}" if j.citation else "")
                + (f" — {j.subject}" if j.subject else "")
                + f" [id: {j.id}]"
                for j in graph.judgements
            ]
            blocks.append(
                "JUDGEMENTS RECORDED AS INTERPRETING THESE PROVISIONS. Only the case "
                "name and a one-line subject are given here, not the judgement text. "
                "You may say that a case bears on the provision and cite it, but you "
                "must NOT state what it held:\n" + "\n".join(rows)
            )

        if graph.related_sections:
            rows = [
                f"- {s.act} {s.section}" + (f" — {s.title}" if s.title else "")
                for s in graph.related_sections
            ]
            blocks.append(
                "CROSS-REFERENCED PROVISIONS. Titles only; their text is not before "
                "you. You may point the reader to them by number and title, but you "
                "must NOT state what they provide:\n" + "\n".join(rows)
            )

        if graph.contested:
            rows = [f"- {d.name}: {d.contest_note}" for d in graph.contested]
            blocks.append(
                "CONTESTED. This question touches a provision on which the "
                "authorities differ. Say so plainly and set out both positions; do "
                "not present one of them as the answer:\n" + "\n".join(rows)
            )

        return "\n\n".join(blocks)

    def _create_prompt(self, query: str, context: str, graph_context: str = "") -> str:
        """
        Create prompt for LLM with query and context

        Args:
            query: User's question
            context: Retrieved legal context
            graph_context: Connected material from the legal graph, already
                rendered with its own use restrictions (see
                ``_format_graph_context``)

        Returns:
            Formatted prompt
        """
        # The instruction lives with the block, and the list is numbered here
        # rather than in the template: an instruction about a section that is
        # not in the prompt is noise, and a gap in the numbering reads as one
        # that went missing.
        connected = f"\n\nCONNECTED MATERIAL:\n{graph_context}" if graph_context else ""
        rules = [
            "Provide a clear, accurate answer based on the legal context provided",
            "Cite specific sections, cases, or provisions when relevant",
            "Use proper legal terminology and citation format",
            "If the context doesn't fully answer the question, acknowledge limitations",
        ]
        if graph_context:
            rules.append(
                "Observe the use restrictions stated inside CONNECTED MATERIAL. Where "
                "it gives you only a title or a one-line subject, you know the "
                "provision or the case is connected and nothing more — cite it, and "
                "say that it bears on the question, but do not describe what it says "
                "or what it held."
            )
        rules.append(
            "Do NOT write your own disclaimer. One canonical disclaimer is appended "
            "to every answer by this service; a second one written here means the "
            "user sees the same warning twice, which trains them to skip past it."
        )
        instructions = "\n".join(f"{n}. {rule}" for n, rule in enumerate(rules, 1))
        prompt = f"""You are a legal AI assistant specializing in Indian law. Answer the following question based on the provided legal context.

THE APPLICABLE CODES (use these names exactly; do not mix them up):
- BNS = Bharatiya Nyaya Sanhita, 2023 — offences. Replaces the Indian Penal Code.
- BNSS = Bharatiya Nagarik Suraksha Sanhita, 2023 — procedure. Replaces the CrPC.
- BSA = Bharatiya Sakshya Adhiniyam, 2023 — evidence. Replaces the Evidence Act.
Never expand BNSS as "Bharatiya Nyaya Sanhita"; they are different statutes with
different section numbering, and confusing them misstates the law.

LEGAL CONTEXT:
{context}{connected}

USER QUESTION:
{query}

INSTRUCTIONS:
{instructions}

ANSWER:"""
        return prompt

    def search_and_generate(
        self,
        query: str,
        collection: str,
        top_k: int = 5
    ) -> dict[str, Any]:
        """
        Perform RAG search and generate response

        Args:
            query: User's search query
            collection: Collection name to search
            top_k: Number of documents to retrieve

        Returns:
            Dict with 'answer', 'sources', 'query'
        """
        try:
            logger.info(f"RAG search: query='{query}', collection='{collection}', top_k={top_k}")

            # Step 1: Vector search
            search_results = self.vector_service.search(
                collection_name=collection,
                query=query,
                top_k=top_k
            )

            if not search_results.get('documents'):
                return {
                    'answer': "I couldn't find relevant legal provisions for your query. Please try rephrasing or provide more specific details.",
                    'sources': [],
                    'query': query,
                    'collection': collection
                }

            # Step 2: Format context, and walk one step out over the graph
            context = self._format_context(search_results)
            graph = self._expand_over_graph(search_results, query)

            # Step 3: Create prompt
            prompt = self._create_prompt(query, context, self._format_graph_context(graph))

            # Step 4: Generate response with LLM
            llm_response = self.llm_service.generate(prompt=prompt)

            # Step 5: Format sources
            sources = self._format_sources(search_results)

            # Step 6: Add disclaimer
            answer = with_disclaimer(llm_response)

            result = {
                'answer': answer,
                'sources': sources,
                'query': query,
                'collection': collection,
                'num_sources': len(sources),
                # Kept out of `sources`: this material was reached by an edge,
                # not retrieved by relevance, and the two must stay
                # distinguishable all the way to the UI.
                'graph_context': {
                    'seeds': list(graph.seeds),
                    'related_sections': [
                        {'key': s.key, 'act': s.act, 'section': s.section, 'title': s.title}
                        for s in graph.related_sections
                    ],
                    'judgements': [
                        {
                            'id': j.id,
                            'case_name': j.case_name,
                            'citation': j.citation,
                            'year': j.year,
                            'subject': j.subject,
                            'source_url': j.source_url,
                        }
                        for j in graph.judgements
                    ],
                    'doctrines': [
                        {
                            'id': d.id,
                            'name': d.name,
                            'summary': d.summary,
                            'contested': d.contested,
                            'contest_note': d.contest_note,
                        }
                        for d in graph.doctrines
                    ],
                    'classification': list(graph.classification),
                },
            }

            logger.info(f"RAG search completed: {len(sources)} sources, answer length={len(answer)}")
            return result

        except Exception as e:
            logger.error(f"Error in RAG search: {e}")
            raise

    def multi_collection_search(
        self,
        query: str,
        collections: list[str],
        top_k_per_collection: int = 3
    ) -> dict[str, Any]:
        """
        Search across multiple collections and generate unified response

        Args:
            query: User's search query
            collections: List of collection names
            top_k_per_collection: Number of docs per collection

        Returns:
            Dict with 'answer', 'sources', 'query'
        """
        try:
            logger.info(f"Multi-collection RAG search: query='{query}', collections={collections}")

            all_documents = []
            all_metadatas = []
            all_distances = []
            all_ids = []

            # Search each collection
            for collection in collections:
                try:
                    results = self.vector_service.search(
                        collection_name=collection,
                        query=query,
                        top_k=top_k_per_collection
                    )

                    all_documents.extend(results.get('documents', []))
                    all_metadatas.extend(results.get('metadatas', []))
                    all_distances.extend(results.get('distances', []))
                    all_ids.extend(results.get('ids', []))
                except Exception as e:
                    logger.warning(f"Error searching collection {collection}: {e}")
                    continue

            if not all_documents:
                return {
                    'answer': "I couldn't find relevant legal provisions across the searched collections. Please try rephrasing your query.",
                    'sources': [],
                    'query': query,
                    'collections': collections
                }

            # Sort by relevance (distance)
            sorted_indices = sorted(range(len(all_distances)), key=lambda i: all_distances[i])
            top_k = min(5, len(sorted_indices))

            filtered_results = {
                'documents': [all_documents[i] for i in sorted_indices[:top_k]],
                'metadatas': [all_metadatas[i] for i in sorted_indices[:top_k]],
                'distances': [all_distances[i] for i in sorted_indices[:top_k]],
                'ids': [all_ids[i] for i in sorted_indices[:top_k]]
            }

            # Generate response
            context = self._format_context(filtered_results)
            prompt = self._create_prompt(query, context)

            llm_response = self.llm_service.generate(prompt=prompt)

            sources = self._format_sources(filtered_results)
            answer = with_disclaimer(llm_response)

            result = {
                'answer': answer,
                'sources': sources,
                'query': query,
                'collections': collections,
                'num_sources': len(sources)
            }

            logger.info(f"Multi-collection RAG search completed: {len(sources)} sources")
            return result

        except Exception as e:
            logger.error(f"Error in multi-collection RAG search: {e}")
            raise


# Global instance
_rag_service: RAGService | None = None


def get_rag_service() -> RAGService:
    """Get or create the global RAG service instance"""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service
