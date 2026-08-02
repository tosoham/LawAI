"""
RAG (Retrieval-Augmented Generation) Service for LawAI
Combines vector search with LLM for contextual legal responses
"""
import logging
from typing import List, Dict, Any, Optional
from .vector_service import get_vector_service
from .llm_service import llm_service

logger = logging.getLogger(__name__)


class RAGService:
    """Service for RAG-based legal question answering"""
    
    def __init__(self):
        """Initialize RAG service with vector and LLM services"""
        self.vector_service = get_vector_service()
        self.llm_service = llm_service
    
    def _format_context(self, search_results: Dict[str, Any]) -> str:
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
        for i, (doc, meta) in enumerate(zip(documents, metadatas), 1):
            # Format based on document type
            if 'section_number' in meta:
                # Legal section
                header = f"[{i}] {meta.get('act', 'Unknown Act')}, Section {meta.get('section_number', 'N/A')}"
                if 'title' in meta:
                    header += f" - {meta['title']}"
            elif 'case_name' in meta:
                # Court judgement
                header = f"[{i}] {meta.get('case_name', 'Unknown Case')}"
                if 'citation' in meta:
                    header += f" {meta['citation']}"
            else:
                header = f"[{i}] Legal Document"
            
            context_parts.append(f"{header}\n{doc}\n")
        
        return "\n".join(context_parts)
    
    def _format_sources(self, search_results: Dict[str, Any]) -> List[Dict[str, Any]]:
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
        for doc, meta, distance, doc_id in zip(documents, metadatas, distances, ids):
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
    
    def _create_prompt(self, query: str, context: str) -> str:
        """
        Create prompt for LLM with query and context
        
        Args:
            query: User's question
            context: Retrieved legal context
            
        Returns:
            Formatted prompt
        """
        prompt = f"""You are a legal AI assistant specializing in Indian law. Answer the following question based on the provided legal context.

LEGAL CONTEXT:
{context}

USER QUESTION:
{query}

INSTRUCTIONS:
1. Provide a clear, accurate answer based on the legal context provided
2. Cite specific sections, cases, or provisions when relevant
3. Use proper legal terminology and citation format
4. If the context doesn't fully answer the question, acknowledge limitations
5. Always include a disclaimer that this is AI-generated legal information

ANSWER:"""
        return prompt
    
    def search_and_generate(
        self,
        query: str,
        collection: str,
        top_k: int = 5
    ) -> Dict[str, Any]:
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
            
            # Step 2: Format context
            context = self._format_context(search_results)
            
            # Step 3: Create prompt
            prompt = self._create_prompt(query, context)
            
            # Step 4: Generate response with LLM
            llm_response = self.llm_service.generate(prompt=prompt)
            
            # Step 5: Format sources
            sources = self._format_sources(search_results)
            
            # Step 6: Add disclaimer
            answer = llm_response + "\n\n**DISCLAIMER**: This is AI-generated legal information for educational purposes only. Please consult a qualified lawyer for legal advice specific to your situation."
            
            result = {
                'answer': answer,
                'sources': sources,
                'query': query,
                'collection': collection,
                'num_sources': len(sources)
            }
            
            logger.info(f"RAG search completed: {len(sources)} sources, answer length={len(answer)}")
            return result
            
        except Exception as e:
            logger.error(f"Error in RAG search: {e}")
            raise
    
    def multi_collection_search(
        self,
        query: str,
        collections: List[str],
        top_k_per_collection: int = 3
    ) -> Dict[str, Any]:
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
            answer = llm_response + "\n\n**DISCLAIMER**: This is AI-generated legal information for educational purposes only. Please consult a qualified lawyer for legal advice specific to your situation."
            
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
_rag_service: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """Get or create the global RAG service instance"""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service

# Made with Bob
