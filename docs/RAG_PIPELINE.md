# The RAG Pipeline

**Chunking, batching, embedding, retrieval, and the four-layer retrieval stack — with the
measurements that justify each layer.**

This document covers the retrieval half of LawAI in depth. The generation and verification
half is in [`ENGINEERING_DEEP_DIVE.md`](ENGINEERING_DEEP_DIVE.md) §8; evaluation methodology
is in [`EVALUATION_AND_TESTING.md`](EVALUATION_AND_TESTING.md).

---

## 1. The corpus

| Source | Format | Records | Notes |
|---|---|---|---|
| BNS gazette PDF | `bns_sections.json` | 358 | complete act |
| BNSS gazette PDF | `bnss_sections.json` | 531 | complete act |
| BSA gazette PDF | `bsa_sections.json` | 170 | complete act |
| Indian Kanoon | `sc_judgements.json` | 30 | id-pinned, verified on fetch |
| BNSS First Schedule | `offence_classification.json` | 465 | **not** a vector collection |
| BPR&D tables | `repealed_concordance.json` | 1,195 | **not** a vector collection |

**1,089 embedded documents → 3,184 chunks** across four ChromaDB collections
(`bns_sections`, `bnss_sections`, `bsa_sections`, `sc_judgements`).

The last two are deliberately **not** vector collections. They answer questions by exact key,
and putting them in an embedding index would replace a lookup that is always right with a
similarity search that is sometimes right. See §6 and §7.

---

## 2. Chunking

### 2.1 Why

`all-MiniLM-L6-v2` has a **~256 word-piece token window** and **truncates silently** past
it. A 60,000-character judgement indexed whole is represented by its first paragraph and can
never match a query about its holding.

There is no error and no warning. This is the RAG failure that presents as *"retrieval just
isn't very good"* with nothing in the logs.

### 2.2 Parameters

```python
# scripts/init_vector_db.py
MAX_CHUNK_CHARS     = 1200   # ≈ the 256-token window, with headroom
CHUNK_OVERLAP_CHARS = 150    # a passage split across a boundary stays retrievable
BATCH_SIZE          = 256    # bounds peak memory during seeding
```

1200 characters is roughly 250–300 word-piece tokens for this corpus's register — legal
English is token-dense (long words, heavy punctuation), so the ratio is worse than the ~4
chars/token rule of thumb. The headroom is deliberate.

### 2.3 The splitting strategy — structure first, width last

`split_text()` is hierarchical and falls back only as far as it must:

| Step | Rule | Why |
|---|---|---|
| 1 | Whole document fits → **one chunk** | Do not fragment a 400-char section for nothing |
| 2 | Split on **paragraphs** (`\n\s*\n`) | Statutory sub-clauses are paragraphs; they are the natural semantic unit |
| 3 | Oversized paragraph → **sentences** (`(?<=[.;:])\s+`) | Note `;` and `:` — statutory drafting uses semicolon-separated clauses far more than full stops |
| 4 | Oversized sentence → hard cut with overlap | Last resort |
| 5 | **Re-pack** units greedily up to the limit | Chunks end up near-uniform instead of one-per-paragraph |

Step 5 matters: a naive paragraph splitter produces wildly uneven chunks (a 40-char proviso
next to a 1,100-char sub-section), and short chunks embed poorly — too little context to
place them in vector space.

**That most sections fit whole is why 1,089 documents produce only 3,184 chunks.** The
expansion is concentrated in the 30 judgements.

### 2.4 Chunk metadata — the most important decision here

```python
metadata["parent_id"]   = record["id"]   # the section or case this came from
metadata["chunk_index"] = index
metadata["chunk_count"] = len(parts)
```

IDs are stable and meaningful: a single-chunk document keeps its own id; a split one becomes
`{id}__c{index}`. Re-seeding is idempotent.

`parent_id` is what makes a retrieved fragment **citable back to its source**, and it pays
off twice more downstream:

- **The verifier checks a quotation against the whole section, not the retrieved chunk.** A
  section is indexed in pieces; a true quotation from a piece that did not rank is still
  true. Asked for the punishment for theft, the model quoted BNS 303 correctly while
  retrieval had returned that section's *fifth* chunk — checking only the chunk **rejected a
  true statement of the law**.
- **The graph keys on parent, not chunk**, so graph expansion from a mid-section chunk
  reaches the right node.

> Interview-relevant framing: chunking is usually discussed as a retrieval-quality knob. In
> this system it is also a **citation-integrity** problem — a chunk you cannot attribute is
> a chunk you cannot use in a legal answer, whatever its similarity score.

---

## 3. Batching

```python
for start in range(0, len(chunks), BATCH_SIZE):
    batch = chunks[start:start + BATCH_SIZE]
    vector_service.add_documents(...)
    logger.info(f"  {collection_name}: {min(start+BATCH_SIZE, len(chunks))}/{len(chunks)}")
```

Three reasons, in order of importance:

- **Peak memory.** `SentenceTransformer.encode()` over 3,184 texts at once materialises the
  whole activation set. Batching bounds it — which is what lets the seed run inside a
  memory-limited container rather than being OOM-killed halfway.
- **Failure isolation and progress.** A failure names the batch instead of losing a
  five-minute run with no indication of where.
- **ChromaDB write efficiency.** Per-document `add()` calls dominate on transaction
  overhead; 256 is comfortably inside Chroma's batch limits while large enough to amortise
  it.

`EmbeddingService` is a **singleton** — the model is ~90 MB and takes seconds to load.
Constructing it per request would dominate query latency.

---

## 4. The embedding model

**`all-MiniLM-L6-v2`** — 384 dimensions, ~90 MB, CPU-fast.

**Why this one:**

| Requirement | How it is met |
|---|---|
| No per-query cost | Local model, not an embedding API |
| No data leaving the machine | Matters for a legal tool handling case facts |
| Works offline | Baked into the Docker image with `HF_HUB_OFFLINE=1` |
| Fast on CPU | No GPU in the deployment target |

**Its limitation is real, and measured rather than assumed:** it is general-purpose with no
Indian-legal training. That is exactly *why* the retrieval stack needed three non-vector
layers on top. Rather than papering over it with prompt engineering, each gap was measured
and given a targeted fix (§5–§7).

An embedding upgrade (BGE/GTE class) is designed but not built, and is gated on **beating
the committed baseline**, not on sounding better.

> **A trap I designed for and would flag in review:** swapping the embedder against an
> existing Chroma volume silently serves an index built by a *different* model. Everything
> still works; every answer is slightly wrong. The fix (a manifest of model + chunk params
> in the volume, reseeding on mismatch) is specified in the plan and not yet implemented.

---

## 5. Retrieval, layer by layer

Four strategies feed one merged ranking inside `VectorService.search`.

```
query
  ├─ parse_citation()      →  exact metadata fetch, distance 0.0   (§6)
  ├─ find_offences()       →  exact metadata fetch, distance 0.0   (§7)
  ├─ expand_query()        →  appended statutory phrasing          (§8)
  └─ dense vector search over 1–3 collections
        └─ merge by distance, exact hits sort to the front for free
```

### The measured ablation

69-query golden set. Reports committed in `backend/eval/`.

| Stage | recall@1 | recall@3 | recall@5 | MRR | nDCG@10 |
|---|---|---|---|---|---|
| Dense vector only | 0.536 | 0.652 | 0.725 | 0.618 | 0.639 |
| + query expansion | 0.638 | 0.768 | 0.841 | 0.719 | 0.733 |
| + structured citation lookup | 0.725 | 0.855 | 0.928 | 0.802 | 0.815 |
| + concordance | **0.812** | **0.928** | **0.986** | **0.879** | **0.890** |

**recall@3 per class — the diagnostic view:**

| Class | n | Dense | +expand | +structured | +concordance | Δ |
|---|---|---|---|---|---|---|
| `plain` | 25 | 0.960 | 0.960 | 0.960 | 0.960 | — |
| `term_of_art` | 16 | 0.500 | **0.875** | 0.875 | 0.875 | **+0.375** |
| `citation` | 8 | 0.250 | 0.250 | **1.000** | 1.000 | **+0.750** |
| `repealed_code` | 8 | 0.125 | 0.375 | 0.375 | **1.000** | **+0.875** |
| `judgement` | 12 | 0.833 | 0.833 | 0.833 | 0.833 | — |

**Read the diagonal.** Each layer moved exactly the class it targeted, and no layer degraded
another. `plain` never moves — every layer is additive by construction. That pattern is the
evidence that these are three distinct problems with three distinct fixes, not one
general-purpose tuning effort.

---

## 6. Structured citation lookup — a citation is not a search

`services/retrieval/structured_filter.py`

### The problem

Citation was the worst class in the baseline by a wide margin: **recall@3 of 0.250** against
0.960 for plain questions. `"section 482 BNSS"` did not surface BNSS 482 **anywhere in the
top 20**.

### The diagnosis

Not a tuning problem. **A section number carries almost no semantic signal.**

- "482" and "483" embed to nearly the same point.
- A section's text rarely repeats its own number.
- **Reranking cannot fix this**, because a reranker works from the same signal.

### The solution

A citation *names one document*. The store already holds it under an exact metadata key.

```python
citation = parse_citation(query)       # "section 482 BNSS" → BNSS, 482
# fetched via ChromaDB `where={"section_number": "482"}`
# ranked at EXACT_MATCH_DISTANCE = 0.0
```

Vector hits are **kept behind it**, not replaced — a citation is usually only *part* of what
was asked ("what does section 482 BNSS say about conditions?").

**Result: 0.250 → 1.000, with no other class moving.**

### Two deliberate refusals

These are the interesting part, because both trade recall for correctness on purpose.

**A repealed code's number is translated, never assumed.** "CrPC 438" means BNSS 482 — but
**BNSS also has a section 438**, about something else entirely. Returning the same number in
the new act turns a miss into a **confident wrong answer**. Before a sourced concordance
existed, the number was refused outright and only the *act* resolved. Now it is translated
through `repealed_concordance.json`; a citation the concordance does not cover is **still
refused**, on the original reasoning.

**A lettered section ("41A", "65B") is refused.** No section of the 2023 codes carries a
letter suffix, so the letter is a reliable signal that the user is citing a repealed
provision from memory.

### A parsing trap

The suffix pattern must be set **tight against the digits**. With any whitespace allowed,
*"section 111 of the Bharatiya Nyaya Sanhita"* reads **"of"** as a section suffix and
refuses a perfectly valid citation.

---

## 7. Offence lookup — classification vocabulary is absent from the statute

`services/retrieval/offence_lookup.py`

### The problem

*"Is murder bailable?"*

The words **"bailable", "cognizable", "triable by" appear nowhere in the BNS.** They live in
the *BNSS First Schedule*, a different act. So the query pulls the embedder toward whatever
prose is nearest:

- **BNS 103 ranks sixth** for "is murder bailable" and never reaches the model at `top_k=5`.
- **BNS 303 does not appear in the top 8** for "is theft bailable".

### The solution

The First Schedule names every offence in a column of its own, so the match is **exact**.
`find_offences()` maps the offence name to its section, which is then fetched by metadata.

Two guards keep it from firing wrongly:

- It only fires on an offence/classification question (`is_offence_question()`).
- It returns nothing for a phrase generic enough to match the whole table.

### The extension — a bug found by adversarial testing

*"What is the punishment for theft?"* was **abstaining about one time in three.**

Not a hallucination — the opposite. Dense retrieval ranked **BNS 305** (theft in a dwelling
house) and **BNS 304** (snatching) above **BNS 303** (theft). The model quoted and cited
those sections, the verifier correctly rejected the claims as not matching the offence asked
about, and a basic question came back as *"I cannot answer this."*

The trigger regex only fired on *classification* vocabulary ("bailable", "cognizable"), not
on general punishment questions. Widening it:

```python
_OFFENCE_QUESTION = re.compile(
    r"\b(punishment|punishable|sentence|penalty|imprisonment|fine|"
    r"what\s+(is|are|does)|which\s+section|defined?)\b"
)
```

…and fetching the named section exactly (`_add_named_section`) fixed it.

> **This is the most instructive bug in the project.** The verifier was working *perfectly*,
> and that is precisely what made the failure visible. Without verification, the system would
> have confidently cited BNS 304 for theft and nobody would ever have noticed. **A safety
> mechanism surfaced a retrieval bug** — the inverse of the usual relationship, where safety
> layers hide problems by smoothing over them.

---

## 8. Query expansion — the vocabulary gap

`services/query_expansion.py`

### The problem

**A term of art often does not appear in the statute that governs it.**

The worked example: **BNSS 482 governs anticipatory bail.** The section is titled *"Direction
for grant of bail to person apprehending arrest"* and the word **"anticipatory" appears
nowhere in its 1,948 characters.** Searching the phrase ranks BNSS 480 and 483 above the
section that actually applies.

Second class: repealed-code names. **"IPC", "CrPC" and "Evidence Act" appear nowhere in the
post-2023 corpus at all** — the acts were repealed and the new text does not mention them.

### The key insight

> **A hybrid BM25 retriever would not fix this class of miss.**
>
> The term is *absent from the text*. There is nothing to match lexically either. This is a
> **vocabulary** problem, not a semantic-versus-lexical one, and the fix has to be a
> vocabulary layer.

This is worth stating carefully because "add hybrid search" is the reflex answer to a
retrieval gap, and here it is wrong — for a reason you can only see by actually reading the
source text and confirming the term is not in it.

### The solution

A curated alias table appends the statutory phrasing before embedding:

```python
LEGAL_ALIASES = {
    "anticipatory bail":  "direction for grant of bail to person apprehending arrest",
    "default bail":       "release on bail on failure to complete investigation within "
                          "the prescribed period of detention",
    "dying declaration":  "statement by person who cannot be called as witness as to "
                          "cause of death",
    "double jeopardy":    "person once convicted or acquitted not to be tried for same offence",
    "quashing":           "power of High Court to prevent abuse of process",
    "zero fir":           "first information report recorded irrespective of the area "
                          "where the offence is committed",
    # ...
}
```

Three properties make it safe:

- **Additive, never substitutive.** The alias is *appended* to the query. A query that
  already worked cannot be made worse — which is why `plain` recall does not move.
- **Only the embedded text changes.** The generation prompt still carries **the user's own
  wording**, so the model never sees a rephrased question and never answers a question the
  user did not ask.
- **Curated, not generated.** A wrong entry silently misdirects retrieval, which is worse
  than the gap it closes. Each entry is a phrase whose *statutory* wording genuinely differs
  — it is not a thesaurus.

`expand=False` measures unexpanded behaviour, which is how the ablation was produced.

**Result: `term_of_art` recall@3 0.500 → 0.875; `repealed_code` 0.125 → 0.375.**

---

## 9. Multi-collection search

The agent does not know in advance whether a question concerns offences (BNS), procedure
(BNSS) or evidence (BSA). `rag_search` therefore searches **all three together** and merges
by distance:

```python
for name in collections:
    results = self.vector_service.search(collection_name=name, query=query, top_k=top_k)
    # extend merged lists
order = sorted(range(len(merged["ids"])), key=lambda i: merged["distances"][i])[:top_k]
```

Because exact-match hits carry `distance = 0.0`, **citation and offence hits sort to the
front for free** — no special-casing in the merge.

The direct `/search/rag` endpoint still takes a single named collection, for callers that
know which act they want.

---

## 10. Graph expansion after retrieval

Retrieval finds *what matches*. The graph finds *what bears on it*.

`RAGService._expand_over_graph()` seeds from the **top 3** chunks only — a low-ranked chunk
drags in material about something the user did not ask about — and walks one step out:
cross-referenced sections, interpreting judgements, doctrines, First Schedule attributes.

**It does not change retrieval ranking.** The eval is byte-identical with expansion on and
off. It only adds material to the prompt.

The rendered `CONNECTED MATERIAL` block keeps the four kinds **separate**, and that
separation is load-bearing:

| Kind | Prompt permits |
|---|---|
| Offence classification | **may be stated** (First Schedule facts) |
| Doctrine | **may be stated**, attributed to its cases |
| Judgements | name + one-line subject; may be **cited**, **must not** be described as holding anything |
| Cross-referenced sections | **titles only**; may be pointed to, **must not** be described |
| Contested | both positions required; neither presented as the answer |

> **Flattening pointers and content into one "related material" block is exactly how a
> pointer becomes a fabricated holding.** Given a case name adjacent to a section, with no
> indication that only the name is available, a model will write what the case "held".

`graph_context` is returned **separately from `sources`** in the API for the same reason: one
was reached by an **edge**, the other retrieved by **relevance**, and the UI must be able to
tell them apart.

---

## 11. What is deliberately *not* in this pipeline

| Not built | Why not / status |
|---|---|
| **Hybrid BM25 + RRF** | Would not fix the term-of-art class (§8). Still worth it for exact-phrase work the structured filter does not cover — designed, not built. |
| **Cross-encoder reranking** | Designed, behind a flag, gated on beating `eval/concordance.json`. Becomes load-bearing at 10:1 judgement-to-statute chunk imbalance, i.e. at 300 judgements. |
| **Small-to-big retrieval** | Chunks already carry `parent_id`, so the plumbing exists. Not built. |
| **A relevance-score abstention threshold** | **Built as a measurement and rejected on the numbers** — answerable and unanswerable query distributions overlap (0.577 vs 0.423). See deep dive §8.3. |
| **LLM-generated query rewriting** | An unbounded rewrite can change the question. Expansion is additive and curated for exactly this reason. |
| **Vector storage of the offence table or concordance** | Both answer by exact key. Embedding them replaces an always-right lookup with a sometimes-right similarity search. |

---

## 12. Reproducing the numbers

```bash
cd backend

# Full eval, current configuration → writes eval/latest.json
python scripts/eval_retrieval.py

# Ablations
python scripts/eval_retrieval.py --no-expand          # dense-only vocabulary behaviour
python scripts/eval_retrieval.py --class citation     # score one failure class only
python scripts/eval_retrieval.py --top-k 10

# Diff against a committed report. --compare takes the report's *label*
# (its filename without .json), not a path.
python scripts/eval_retrieval.py --compare concordance

# Name this run's report file
python scripts/eval_retrieval.py --label my_experiment --compare concordance
```

`--compare` prints a per-class delta table for `recall@3`, `mrr` and `ndcg@10`, **and names
every individual query whose first correct hit moved to a worse rank.** That per-query
regression list is the useful part: an aggregate can improve while a specific class of
question silently breaks.

Committed reports, in the order they were produced:

| File | What it captures |
|---|---|
| `eval/baseline_no_expand.json` | dense vector retrieval alone |
| `eval/baseline.json` | + query expansion |
| `eval/structured.json` | + structured citation lookup |
| `eval/concordance.json` | + concordance translation — **current** |

---

*See also: [`ENGINEERING_DEEP_DIVE.md`](ENGINEERING_DEEP_DIVE.md) ·
[`EVALUATION_AND_TESTING.md`](EVALUATION_AND_TESTING.md) ·
[`CHALLENGES_AND_SOLUTIONS.md`](CHALLENGES_AND_SOLUTIONS.md)*
