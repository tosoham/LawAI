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

IDs are stable and deterministic: a single-chunk document keeps its own id; a split one
becomes `{id}__c{index}`. Combined with `upsert`, re-seeding is idempotent **in content, not
merely in count** — see §3.2.

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

### 3.1 Why batch, and how it is sized

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

### 3.2 Upsert, not insert — and why it matters here

`add_documents` calls `collection.upsert`, not `collection.add`.

**This was a real bug, found by asking the question rather than by any test.** ChromaDB's
`add()` with an id that already exists **silently discards the write** — no exception, no
warning — and **keeps the previous text**:

```python
c.add(documents=["alpha"],         ids=["x1"], ...)
c.add(documents=["BETA-CHANGED"],  ids=["x1"], ...)   # no error raised
c.get(ids=["x1"])["documents"]                        # -> ['alpha']   ← stale
```

Because the seed script deletes each collection before filling it (`reset=True` by default),
the **default path was safe by destruction**. But `init_vector_db.py --keep` — the documented
way to add to an existing index — silently kept stale text for any id it had seen before.

**The concrete failure this would have caused:** BNSS 531 held **129,022 characters** until
the parser stopped it swallowing the First Schedule. Re-seeding with `--keep` after that fix
would have reported success and **continued serving the 129k version.** Exactly the silent
staleness this project exists to prevent — in the corpus that is supposed to be the
guarantee.

With deterministic ids plus `upsert`, re-seeding the same corpus is a genuine no-op, and
re-seeding a *corrected* corpus replaces precisely the chunks that changed.

> **Why no test caught it:** `add_documents` had **zero coverage**. And a mocked collection
> could not have caught it anyway — it would assert only that we called what we meant to
> call, which was the thing that was wrong. The regression tests run against a real ChromaDB
> for that reason.

**A related smaller bug in the same function:** the length guard was written
`len(a) != len(b) != len(c)`, which Python reads as `(a != b) and (b != c)` — False whenever
two of the three match, i.e. the likeliest mismatch of all. To be precise about the
consequence, since the obvious guess is wrong: **chromadb validates lengths itself**, so
nothing was ever mis-paired. What the broken guard cost was the *diagnosis* — a caller
passing 3 documents and 2 ids got an error naming `embeddings`, a list it never supplied,
from two calls down inside the library.

### 3.3 The rebuild is atomic

**ChromaDB has no transactions**, so a multi-batch write cannot be rolled back. A seed that
died on batch 7 of 13 left a collection holding a prefix of the corpus and **reporting itself
healthy** — nothing downstream can tell a partial index from a small one, and retrieval simply
stops finding things.

What ChromaDB *does* offer is `collection.modify(name=...)`, a metadata-only rename. So a
rebuild is written into a **staging collection** and becomes visible only by renaming it into
place:

```
build   bns_sections__staging          ← readers still see the old index throughout
verify  count == expected chunks       ← a short build is refused, not promoted
swap    bns_sections → bns_sections__retired     (metadata write)
        bns_sections__staging → bns_sections     (metadata write)
drop    bns_sections__retired
```

Two renames rather than one, because ChromaDB refuses to rename onto an existing name
(`UNIQUE constraint failed: collections.name`). The uncovered window is those two metadata
writes instead of a whole collection delete.

**Crash recovery.** `repair_interrupted_rebuild()` runs before planning and handles both
reachable states, inventing nothing:

| State found | Meaning | Action |
|---|---|---|
| `__retired` exists, live name does not | died between the renames | rename retired back; the previous index is restored and the rebuild discarded |
| live name exists, plus `__retired`/`__staging` | swap completed | drop the debris |

**Verification before promotion matters.** The staging count is checked against the expected
chunk count *before* anything swaps, so a staging collection that silently lost writes cannot
be promoted over a good index — the same silent-truncation failure as §3.2, one level up.

**A rebuild also handles deletion.** Upsert alone never removes. Because staging starts empty,
a document dropped from the source disappears from the index rather than lingering.

### 3.4 Change detection: the manifest and content hashes

`services/index_manifest.py` writes `index_manifest.json` **inside** the Chroma directory, so
provenance travels with the volume it describes:

```json
{
  "embedding_model": "all-MiniLM-L6-v2",
  "embedding_dimension": 384,
  "chunk_max_chars": 1200,
  "chunk_overlap_chars": 150,
  "collections": {
    "bns_sections": { "documents": 358, "chunks": 525, "content_hash": "dd6cfa7f…" }
  },
  "build_fingerprint": "5f494645f5627a05"
}
```

**This closes the highest-risk gap in the system.** Swapping the embedding model against an
existing store is **silent and total**: the vectors are well-formed, the distances are
numbers, and every answer is subtly wrong. No assertion downstream could catch it, because by
then the only evidence is that answers got slightly worse. The seed now refuses to append
across a model, dimension or chunk-parameter change and rebuilds instead — with a readable
reason, not "manifest mismatch":

> `index was built with embedding model 'bge-small-en', this run uses 'all-MiniLM-L6-v2' —
> their vectors are not comparable`

**Two hashes, two different remedies.** The *build fingerprint* (model + dimension + chunk
params) deliberately excludes the corpus: a match means the index is one this code could have
written, and a mismatch means rebuild everything. The *content hash* per collection answers
whether the contents are current, and a mismatch means re-seed just that collection.

**Measured effect** on the real corpus:

| Scenario | Embedded | Reused | Time |
|---|---|---|---|
| First build | 3,184 | 0 | ~85s |
| Re-run, nothing changed | 0 | 0 | ~16s (model load only, all four collections skipped) |
| One section edited | **1** | **524** | **1.9s** |
| `--force` on an unchanged corpus | 0 | 525 | 1.5s |

Chunk-level reuse works because each chunk's hash is stored **in its own metadata**, so the
next run can tell what changed without re-reading the corpus, and unchanged chunks have their
vectors copied from the live index rather than recomputed.

> **A bug worth recording, because it was silent.** The stored hash must *exclude* the
> `content_hash` key it is stored under. It did not at first, so the value depended on whether
> it had been written yet — the first pass hashes metadata without it, the second hashes
> metadata with it, and the two never agree. Nothing broke: the index stayed correct and the
> seed still succeeded. The optimisation just never fired, and the only evidence was a
> surprising log line — `525 embedded, 0 reused` on a corpus where one chunk had moved.
> Pinned by `test_stamping_a_chunk_with_its_own_hash_does_not_change_its_hash`.

### 3.5 The container entrypoint asks a better question

`docker-entrypoint.sh` used to gate on a `.lawai-seeded` marker: seed if absent, skip if
present. That answers *"has a seed ever finished here?"* when the question worth asking is
*"does this store match this image?"* — and the two come apart every time the corpus is
updated, because a new image with new data finds the old marker and serves **the old corpus,
silently and indefinitely**.

The entrypoint now just runs the seed on every start, because the seed answers the real
question itself and costs nothing when the answer is "nothing changed":

| Situation | Result |
|---|---|
| fresh volume | full build |
| unchanged image | no-op |
| corpus updated | rebuild only the collections that moved |
| embedding model swapped | full rebuild — the vectors are not comparable |
| previous seed crashed | partial build discarded, rebuilt |

`SKIP_DB_INIT=true` still bypasses it entirely.

### 3.6 Other production concerns handled

| Concern | How |
|---|---|
| **Transient write failures** | Up to 3 attempts per batch with widening backoff, so a five-minute pass is not lost to a 100 ms problem |
| **Progress visibility** | Per-batch throughput and ETA (`525/805 chunks (312/s, ~1s left)`), so a stall looks like one |
| **Plan before write** | `--dry-run` reports what would rebuild and why, touching nothing |
| **Partial runs** | `--collection <name>`, repeatable |
| **Atomic manifest write** | Written to a temp file and `os.replace`d — a manifest truncated by a crash would claim provenance the index does not have |

### 3.7 What is still missing

| | |
|---|---|
| **No resume within a collection** | A failed rebuild restarts that collection from scratch rather than continuing from batch 7. Acceptable at 3,184 chunks with vector reuse making the retry cheap; it would not be at 300 judgements. |
| **Single-writer assumption** | Two concurrent seeds against one store would race on the staging name. There is no lock file. Not a real scenario today (one entrypoint, one operator) but it is an assumption, not a guarantee. |
| **Reuse trusts the stored hash** | If a row's `content_hash` were corrupted to match while its vector did not, reuse would copy a wrong vector. The hash is written by the same pass that writes the vector, so this needs external tampering. |

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
