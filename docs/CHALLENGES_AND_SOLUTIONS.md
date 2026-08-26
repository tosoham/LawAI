# Challenges and Solutions

**Every non-obvious problem in this project, what caused it, how it was fixed, and how it is
prevented from returning.**

This is the skimmable catalogue. Narrative context is in
[`ENGINEERING_DEEP_DIVE.md`](ENGINEERING_DEEP_DIVE.md).

Each entry follows the same shape: **Symptom → Cause → Fix → Guard.** Entries marked
**⚑ high-value** are the ones with the most transferable lesson.

**Index**

| § | Area | Entries |
|---|---|---|
| [1](#1-data-ingestion) | Data ingestion & parsing | 12 |
| [2](#2-chunking-embedding-and-indexing) | Chunking, embedding, indexing | 10 |
| [3](#3-retrieval) | Retrieval | 7 |
| [4](#4-grounding-and-verification) | Grounding & verification | 12 |
| [5](#5-the-legal-graph) | Legal graph | 4 |
| [6](#6-agent-orchestration) | Agent orchestration | 4 |
| [7](#7-llm-integration) | LLM integration | 5 |
| [8](#8-containers-and-deployment) | Containers & deployment | 6 |
| [9](#9-frontend) | Frontend | 6 |
| [10](#10-process-and-tooling) | Process & tooling | 4 |

---

## 1. Data ingestion

### 1.1 pdfplumber glues words together ⚑

**Symptom.** Extracted text reads `"isdoubtfulof"`.
**Cause.** pdfplumber's default `x_tolerance=3` is too loose for the gazette's font.
**Fix.** `x_tolerance=1.0`.
**Why not pypdf.** pypdf spaces correctly but returns **no coordinates** — and coordinates
are required to bind titles (1.2). So: pdfplumber with a tuned tolerance, for both.
**Guard.** `tests/unit/test_ingestion.py`.

### 1.2 Section titles extract out of order ⚑

**Symptom.** Section 11's title appeared after section 14's.
**Cause.** Titles are gazette **marginal notes** in a narrow side column — left on even
pages, right on odd. Linear extraction emits them in visual, not logical, order.
**Fix.** Bind notes to sections by **vertical position**, not reading order.
**Detail.** A note sits ~1.5pt below its section's first line but can sit a few points
*above* — tolerance is **6pt**, found because BNS 78 ("Stalking") sat 3.3pt above.

### 1.3 Clustering notes by vertical gap merges them

**Symptom.** BNS 103 — the most-queried section in the corpus — came out **untitled**, and
"Punishment for murder" was absorbed into the previous note.
**Cause.** Intra-note line spacing is ~9.6pt; the gap between two *different* notes can be as
little as 14.9pt. A 16pt threshold cannot separate them.
**Fix.** Segment by section position, never by gap size.

### 1.4 `CHAPTERV`

**Symptom.** Chapter V (offences against woman and child) vanished entirely.
**Cause.** Chapter headings lose their internal space in extraction.
**Fix.** Make the space optional in the regex.

### 1.5 The margin column carries non-title text

**Symptom.** Titles polluted with `"45 of 1860."` and, on the last page, a binary blob.
**Cause.** Act citations share a typeset line with title words; the final page carries the
PDF's **digital-signature blob**.
**Fix.** Citation substring removal, plus line-length and digit-ratio caps.

### 1.6 The last section of each act swallowed the schedules ⚑

**Symptom.** BNSS 531 was **129,022 characters**. It should be **1,873**.
**Cause.** Nothing terminated the final section, so it absorbed the entire First Schedule and
all statutory forms.
**Impact.** Distorted the chunk count (3,320 → 3,184 after the fix) and poisoned retrieval
for every procedural query.
**Fix.** Explicit terminator for the last section of each act.
**The lesson.** *Invisible in aggregate counts* — 358/531/170 were all correct. It only
surfaced from looking at the **distribution of section lengths**. Check distributions, not
just totals.

### 1.7 First Schedule: column edges move between pages ⚑

**Symptom.** Page 188 read `"2 Non-cognizable."` in the cognizable column and resolved to
nothing.
**Cause.** The gazette re-flows the table per page. Column 4 starts at x0 **285** on page 158
and **304** on page 163. A single set of edges pushed "2 years" out of the punishment column.
**Fix.** Measure edges **per page**, recovered from the closed vocabulary each column opens
with (`PUNISHMENT_OPENERS`, `COGNIZABLE_OPENERS`, …).

### 1.8 First Schedule: wrapped text escapes its column

**Symptom.** Continuation words landed in the next column.
**Cause.** Wrapped text drifts right — `"...person aggrieved by the"` puts "the" at x0 367,
two points *inside* column 5's tolerance.
**Fix.** Group words into **runs**; place a run by its **leading** word only.
**Detail.** A run breaks on a wide gap *or* where a word reaches the next anchor outright —
both tests needed, because adjacent columns can be a single space apart (`"...7 years"` ends
at x1 283, `"According"` begins at 286).

### 1.9 First Schedule: rows cannot be found by gaps or by section number ⚑

**Symptom.** Rows merged; wrong court reported for BNS 356(2).
**Cause, twice over.**
- Not gaps: most pages set rows 15.6pt apart and lines 9.6pt, but **page 161 sets both at
  10.2pt**.
- Not the section column: BNS 356(2) is classified **twice** — once for defamation of the
  President (Court of Session) and once "in any other case" (Magistrate) — with **column 1
  blank on the second row**.
**Fix.** A row opens when a line **refills a cell that is already filled**.

### 1.10 A conditional cell must never become a boolean ⚑

**Symptom.** 27 rows (of 465) leave `cognizable` or `bailable` unresolved — 25 of them
reading *"According as offence abetted is cognizable or non-cognizable"*.
**Fix.** Keep `cognizable`/`bailable` as `null`, preserving the Schedule's own wording in
`cognizable_text`/`bailable_text`. The UI renders **"Not stated"** with that wording.
**Why it matters.** *A guessed "bailable" is the most dangerous single value this system can
emit.*
**Guard.** `test_offence_schedule.py` — 21 offences transcribed by eye, invariants over the
other 444.

### 1.11 Concordance: a parser slipping a row is silent ⚑

**Symptom.** None — that is the problem. A 38-page table mis-pairs sections invisibly.
**Fix.** Cross-check the whole extraction against a **second, independently typeset table**
(the comparative chart in the same publisher's handbook), **failing the run** if they
disagree beyond 5%. Currently **117/117 agree**.
**The lesson.** The cross-check tests the thing most likely to break, which was **not the
source but my parser**.

### 1.12 Concordance: a title filter would have discarded good data ⚑

**Symptom.** `title_agreement` scored 58 rows below one third.
**Investigation.** All 58 were **correct** — IPC 501/502 → BNS 356 (titled simply
"Defamation"); forty definitional rows → BNS 2 ("Definitions").
**Fix.** Demoted from a **gate** to a **recorded signal**.
**The lesson.** A plausible quality heuristic, validated against reality, turned out to have
**zero precision**. Check your filters before trusting them.

### 1.13 Judgements cannot be resolved by name ⚑

**Symptom.** Searching `"Selvi vs State of Karnataka"` returns the unrelated Jayalalitha
appeal. Several landmark searches return a later *order*, not the judgement.
**Fix.** Pin each judgement by **document id**, re-verified on fetch against `expect` tokens.

### 1.14 Title tokens are not enough either

**Symptom.** The first Bhajan Lal id matched "bhajanlal" and "haryana" — and was a **1992
contempt petition between the same parties**.
**Fix.** `expect_text` asserts a phrase from the actual **holding** appears in the body.
**Recorded limitation.** Indian Kanoon serves Bhajan Lal abridged (~27k chars); its famous
seven-category list at paragraph 102 is **not in the corpus**, and the entry's `subject` says
what is actually stored.

### 1.15 Gazette line-break hyphens break punishment parsing ⚑

**Symptom.** A murder timeline showed the 60-day branch instead of 90.
**Cause.** `"imprison- ment for life"` survives into the Schedule, so **a life sentence reads
as no sentence at all**.
**Fix.** Normalise line-break hyphens before parsing.

---

## 2. Chunking, embedding and indexing

### 2.1 The embedder truncates silently ⚑

**Symptom.** Long judgements never matched queries about their holdings. No error anywhere.
**Cause.** `all-MiniLM-L6-v2` has a **~256 token window** and truncates past it — a
60,000-char judgement is indexed by its first paragraph.
**Fix.** Chunk before embedding: 1,200 chars, 150 overlap, structure-aware.
**The lesson.** This is *the* silent RAG failure. It presents as "retrieval isn't very good"
with a clean log.

### 2.2 Naive splitting produces unusable chunks

**Cause.** A pure paragraph splitter yields a 40-char proviso next to a 1,100-char
sub-section, and short chunks embed poorly — too little context to place them in vector
space.
**Fix.** Hierarchical split (paragraph → sentence → hard cut) **then re-pack greedily** so
chunks are near-uniform.
**Detail.** Sentence splitting includes `;` and `:` — statutory drafting uses
semicolon-separated clauses far more than full stops.

### 2.3 A retrieved chunk must be citable ⚑

**Fix.** Every chunk carries `parent_id`, `chunk_index`, `chunk_count`.
**Pays off three times.** Citation in the answer; **verification against the whole section**
(4.7); graph expansion keying on the parent node.

### 2.4 Embedding 3,184 chunks at once exhausts memory

**Fix.** `BATCH_SIZE = 256`, with per-batch progress logging.
**Also.** `EmbeddingService` is a singleton — the model is ~90 MB and takes seconds to load.

### 2.5 Re-seeding silently kept the stale text ⚑

**Symptom.** None visible — the seed logs success and the counts are right.
**Cause.** `add_documents` used `collection.add`. ChromaDB **silently discards** a write whose
id already exists: no exception, no warning, and the **previous** document is what stays
indexed.

```python
c.add(documents=["alpha"],        ids=["x1"], ...)
c.add(documents=["BETA-CHANGED"], ids=["x1"], ...)   # does not raise
c.get(ids=["x1"])["documents"]                       # -> ['alpha']   ← stale
```

**Blast radius.** The default seed path deletes each collection first (`reset=True`), so it
was safe **by destruction**. But `init_vector_db.py --keep` — the documented way to add to an
existing index — kept stale text for every id already present.
**The failure it would have caused.** BNSS 531 held **129,022 characters** until the parser
stopped it swallowing the First Schedule (1.6). Re-seeding with `--keep` after that fix would
have reported success and **kept serving the 129k version** — silent staleness in the corpus
that is supposed to be the guarantee.
**Fix.** `collection.upsert`. Ids are deterministic (`bns_103`, `bns_103__c2`), so re-seeding
the same corpus is a true no-op and re-seeding a corrected one replaces exactly the chunks
that changed. Idempotent **in content**, not merely in count.
**Guard.** `TestAddDocuments` — against a **real** ChromaDB, because a mocked collection
asserts only that we called what we meant to call, which was the thing that was wrong.
`add_documents` previously had **zero coverage**.
**The lesson.** Found by *asking whether the batching was idempotent*, not by any test. "It
inserts fine" and "re-running it converges" are different claims, and only the second is
worth anything when the corpus is the guarantee.

### 2.6 A length guard that only fired when all three lengths differed

**Cause.** Written `len(a) != len(b) != len(c)`, which Python reads as
`(a != b) and (b != c)` — **False whenever two of the three match**, i.e. the likeliest
mismatch of all.
**Precise consequence** (the obvious guess is wrong): **chromadb validates lengths itself**,
so nothing was ever mis-paired. What was lost was the **diagnosis** — a caller passing 3
documents and 2 ids got `Unequal lengths for fields: ids: 2, ..., embeddings: 3`, naming a
list it never supplied, from two calls down inside the library.
**Fix.** `if not (len(documents) == len(metadatas) == len(ids))`, with the actual lengths in
the message.

---

### 2.7 A crashed seed left a partial index reporting itself healthy ⚑

**Symptom.** Retrieval quietly stops finding things. No error anywhere.
**Cause.** ChromaDB has no transactions, so a multi-batch write cannot be rolled back. A seed
that died on batch 7 of 13 left a collection holding a prefix of the corpus — and **nothing
downstream can distinguish a partial index from a small one.**
**Fix.** Rebuild into a **staging** collection and rename it into place only after every batch
lands and the row count is verified. `collection.modify(name=…)` is a metadata-only operation,
so the swap is two renames rather than a copy:

```
build   bns_sections__staging       ← readers see the old index throughout
verify  count == expected
swap    bns_sections → __retired ;  __staging → bns_sections
drop    __retired
```

Two renames because chromadb refuses to rename onto an existing name (`UNIQUE constraint
failed: collections.name`).
**Crash recovery.** `repair_interrupted_rebuild()` handles both reachable states and invents
nothing: retired-exists-but-live-does-not means the swap was interrupted, so restore the
previous index and discard the rebuild; live-exists-plus-debris means it completed, so drop
the debris.
**Bonus.** Because staging starts empty, a document removed from the source now disappears
from the index. Upsert alone never deletes.
**Guard.** `TestAtomicRebuild`, `TestRepairInterruptedRebuild` — against a real ChromaDB.

### 2.8 Nothing recorded which model built the index ⚑

**Symptom.** None available. That is the entire problem.
**Cause.** A vector index is derived data and the derivation is invisible once written: 3,184
rows of 384 floats look identical whichever model produced them. **Swapping the embedding
model against an existing store is silent and total** — the query is embedded by one model and
compared against vectors written by another, so distances are meaningless while remaining
well-formed numbers. No assertion downstream could catch it; by then the only evidence is that
answers got slightly worse.
**Fix.** `services/index_manifest.py` writes `index_manifest.json` **inside** the Chroma
directory so provenance travels with the volume. The seed refuses to append across a model,
dimension or chunk-parameter change and rebuilds instead, with a readable reason:
*"index was built with embedding model 'bge-small-en', this run uses 'all-MiniLM-L6-v2' —
their vectors are not comparable"*.
**Two hashes, two remedies.** The *build fingerprint* (model + dimension + chunk params)
excludes the corpus — a mismatch means rebuild everything. The *content hash* per collection
answers whether contents are current — a mismatch means re-seed that collection only.
**Guard.** `tests/unit/test_index_manifest.py`.

### 2.9 The content hash was self-referential ⚑

**Symptom.** `525 embedded, 0 reused` on a corpus where exactly **one** chunk had changed.
**Cause.** Each chunk's hash is stored in its own metadata so the next run can tell what
changed. The hash covered that key, so its value depended on whether it had been written yet —
the first pass hashes metadata *without* it, the second hashes metadata *with* it, and the two
never agree. Every chunk looks changed, forever.
**Why it is worth recording.** **Nothing broke.** The index stayed correct, the seed still
succeeded, every test passed. The optimisation simply never fired, and the only evidence was a
surprising number in a log line.
**Fix.** Exclude `content_hash` from the hash it is stored under. After: `1 embedded, 524
reused, 1.9s` — down from ~85s.
**Guard.** `test_stamping_a_chunk_with_its_own_hash_does_not_change_its_hash`, plus
`test_a_stamped_chunk_still_detects_a_real_change` so the exclusion cannot blind the hash to
something that matters.

### 2.10 The seed marker answered the wrong question ⚑

**Cause.** `docker-entrypoint.sh` gated on a `.lawai-seeded` marker — *"has a seed ever
finished here?"* — when the question worth asking is *"does this store match this image?"*
Those come apart every time the corpus is updated: a new image with new data finds the old
marker and serves **the old corpus, silently and indefinitely.**
**Fix.** Run the seed on every start. It now answers the real question itself (manifest
comparison + content hashing) and is a no-op when nothing changed, so it is cheap enough to
run unconditionally and correct in the cases the marker got wrong — corpus updated, model
swapped, previous seed crashed.
**Note.** This supersedes 8.2, which fixed the marker's *other* failure. The marker was doing
two jobs badly; deleting it does both properly.

## 3. Retrieval

### 3.1 A section number carries almost no semantic signal ⚑

**Symptom.** `"section 482 BNSS"` did not surface BNSS 482 **anywhere in the top 20**.
recall@3 for the citation class: **0.250**.
**Cause.** "482" and "483" embed to nearly the same point; a section's text rarely repeats
its own number. **Reranking cannot fix it** — a reranker works from the same signal.
**Fix.** Stop treating it as a search. Parse the citation, fetch by exact metadata key at
`distance = 0.0`, rank first, **keep vector hits behind it**.
**Result.** **0.250 → 1.000**, no other class moved.

### 3.2 A term of art is absent from the statute governing it ⚑

**Symptom.** "anticipatory bail" ranks BNSS 480/483 above BNSS 482, which actually governs
it.
**Cause.** BNSS 482 is titled *"Direction for grant of bail to person apprehending arrest"* —
the word **"anticipatory" appears nowhere in its 1,948 characters.**
**Fix.** A curated alias table appends the statutory phrasing before embedding.
**The key insight.** **BM25 would not fix this** — the term is absent from the text, so there
is nothing to match lexically. It is a **vocabulary** problem, not semantic-vs-lexical.
**Safety.** Expansion is **additive** (a working query cannot be made worse) and **only the
embedded text changes** (the model still sees the user's own wording).
**Result.** `term_of_art` recall@3 **0.500 → 0.875**.

### 3.3 Repealed code numbers must be translated, never assumed ⚑

**Cause.** "CrPC 438" means BNSS 482 — but **BNSS also has a section 438**, about something
else. Returning the same number turns a miss into a **confident wrong answer**.
**Fix.** Refuse outright until a sourced concordance existed; now translate through it, and
**still refuse** anything the concordance does not cover.
**Also refused:** lettered sections ("41A", "65B") — no section of the 2023 codes carries a
letter, so the letter signals a repealed provision quoted from memory.
**Result.** `repealed_code` recall@3 **0.375 → 1.000**.

### 3.4 Classification vocabulary is absent from the BNS ⚑

**Symptom.** "is murder bailable" ranks **BNS 103 sixth** — it never reaches the model at
`top_k=5`. "is theft bailable" does not surface BNS 303 in the top 8.
**Cause.** "bailable", "cognizable", "triable by" appear nowhere in the BNS. They are in the
**BNSS First Schedule**.
**Fix.** The Schedule names every offence in its own column, so match exactly and fetch the
section directly.

### 3.5 A verifier working correctly surfaced a retrieval bug ⚑

**Symptom.** *"What is the punishment for theft?"* abstained about **one time in three**.
**Cause.** Dense retrieval ranked BNS 305 (theft in a dwelling house) and BNS 304 (snatching)
above BNS 303 (theft). The model cited them, the verifier correctly rejected the claims, and
a basic question came back as "I cannot answer this."
**Root cause.** The offence-lookup trigger fired only on *classification* vocabulary, not on
general punishment questions.
**Fix.** Widen the trigger (`is_offence_question`) and fetch the named section exactly.
**The lesson ⚑.** Without verification, the system would have **confidently cited BNS 304 for
theft and nobody would have noticed**. A safety mechanism made a retrieval bug *visible* —
the inverse of the usual relationship, where safety layers hide problems by smoothing them.

### 3.6 A regex suffix ate part of a valid citation

**Symptom.** *"section 111 of the Bharatiya Nyaya Sanhita"* was refused.
**Cause.** The section-suffix pattern allowed whitespace, so it read **"of"** as a suffix.
**Fix.** Set the suffix tight against the digits.

### 3.7 Distance-relevance inversion

**Symptom.** Perfect matches ranked **worst**.
**Cause.** `rag_service` scored distance `0.0` as relevance `0.0` — a falsy check on a value
where zero is the best possible score.
**Fix.** Explicit `is None` handling.
**The lesson.** Classic Python truthiness bug, in the one place where `0.0` is the *ideal*
value.

---

### 3.8 A reranker made retrieval worse, on the class it was meant to help ⚑

**Symptom.** The cross-encoder was added to close a measured precision gap (recall@1 0.812
against recall@10 0.986 — in ~19% of queries the right chunk was retrieved and ranked below
first). It gained on `judgement` (+0.083 R@3) and `plain` (+0.040), and lost **0.250 of
recall@3 and 0.306 of MRR on `term_of_art`** — a net **−0.029** overall.
**Cause.** It was scored on the **raw** query. The reasoning had been that query expansion is
a crutch for a bi-encoder which never sees the chunk, while a cross-encoder does — so the
appended statutory phrasing was noise to score around. But `term_of_art` is exactly the class
where the term is *absent from the section governing it*: "anticipatory" occurs nowhere in
BNSS 482. Shown "grounds for anticipatory bail", the cross-encoder reads a chunk that never
says the word and demotes what expansion had just surfaced.
**Fix.** Score on the expanded text. `term_of_art` went from −0.250 to **+0.062**, overall
from −0.029 to **+0.043**, no class regressed, recall@1 0.812 → 0.870 with recall@10 unmoved.
**Guard.** `eval_retrieval.py --rerank`, reported **per class** — the overall mean alone read
as a small loss and would have hidden a large regression inside a modest set of gains.
**The lesson.** *Seeing two texts together does not tell a model they mean the same thing.*
The alias table is what says so, and no amount of joint encoding substitutes for it.

### 3.9 A documented limitation stopped being true for the wrong reason ⚑

**Symptom.** `test_bnss_482_is_unreachable_without_expansion` began failing once reranking
was on. Its own docstring said this meant the alias had become redundant.
**Reality.** 482 was not ranking *unaided* — it was ranking with a **different** aid. The
embedder puts it at rank 18 unexpanded; the cross-encoder lifts it into the top 6. The eval
says the alias is still load-bearing: reranking on the unexpanded query costs `term_of_art`
0.250 of recall@3.
**Fix.** The test holds *both* aids off, since the claim under test is what the embedder can
reach. A second test records the new fact — that the reranker recovers 482 from rank 18 —
and states why the two layers are not alternatives: reranking reorders what was retrieved and
can never add to it.
**The lesson.** *A test that tells you what to conclude when it fails is worth writing, and
still worth re-deriving.* The instruction was right about the trigger and wrong about the
cause.

---

## 4. Grounding and verification

### 4.1 Post-hoc labelling is a guess about a guess ⚑

**Cause.** A classifier reading *"Section 103 provides for the death penalty in the rarest of
rare cases"* **cannot tell which half came from the statute and which from Bachan Singh.**
**Fix.** Synthesis **emits** typed claims as JSON; prose is rendered from them. The class is
constitutive, not annotated.

### 4.2 A model cannot grade itself ⚑

**Cause.** **The prior that invented BNS 999 will confirm BNS 999** — same prior, both
outputs.
**Fix.** Every check is a lookup against committed data or a structural property of the
claim. A failure is a *fact*, not an opinion, and is therefore deterministic and unit
testable.

### 4.3 A relevance threshold cannot separate answerable from unanswerable ⚑

**Measured.** 69 answerable queries: worst best-distance **0.577**. 6 adversarial queries: as
low as **0.423**. **The distributions overlap.**
**Consequence.** Any cutoff either refuses real questions or admits invented answers.
**Fix.** Abstention falls out of **verification** — the gate is whether one claim survives,
and the threshold is one.
**The lesson.** The obvious design was built as a measurement and **rejected on the numbers**
rather than on intuition.

### 4.4 A right classification cited to the wrong section ⚑

**Symptom.** A live answer said correctly that theft is non-bailable and cited **BNS 304** —
which is *snatching* (its text opens "Theft is snatching if…"). It **passed**, because
snatching carries the same attributes.
**Why it matters.** Right facts, wrong provision — **and the citation is what the reader
follows.**
**Fix.** `match_offences` binds the claim to the section the First Schedule keys that offence
to.

### 4.5 A section's Schedule rows can disagree with each other ⚑

**Symptom.** *"Theft is bailable"* passed verification.
**Cause.** BNS 303 has two rows: "Theft" (non-bailable) and "Where value of property is less
than 5,000 rupees" (bailable). Checking against the **union** let the false claim match the
petty-theft row.
**Fix.** `_rows_the_claim_is_about` picks the row by its own offence wording appearing in the
claim, and **rejects when candidates disagree**.

### 4.6 Classification attaches to the punishing section, not the defining one

**Symptom.** The model reliably cited BNS 101 (defines murder) instead of BNS 103 (punishes
it).
**Fix.** The prompt, the graph block **and the verifier's failure message** all say so.
**Detail worth keeping.** Without fixing the *failure message* too, the model returned
`{"claims": []}` on regeneration instead of re-citing correctly. **A verifier's error text is
part of the prompt.**

### 4.7 A true quotation rejected because its chunk did not rank ⚑

**Symptom.** The model quoted BNS 303 correctly and the claim was rejected.
**Cause.** Retrieval had returned that section's **fifth** chunk; the quotation came from a
different piece. Checking only the retrieved chunk **rejected a true statement of the law.**
**Fix.** Check against the **whole section** — `SectionNode.text` carries it. (This is what
`parent_id` buys.)

### 4.8 Trailing punctuation broke exact-match quoting

**Symptom.** Quoting *"or with both."* was rejected as a misquote.
**Cause.** BNS 303 reads "…or with both and in case of second conviction…" — a quotation
ending mid-sentence still closes with a full stop.
**Fix.** Strip trailing punctuation **from the span only**. Interior punctuation is untouched
— that would be the model rewriting the provision.

### 4.9 A real case cited for a section it never mentions ⚑

**The subtlest failure in the set.** Both halves check out separately: the case is real, the
section is real.
**Fix.** Only the **graph edge** catches it — `judgement --interprets--> section` must exist.
**Tested with.** "Explain how Bachan Singh governs anticipatory bail under BNSS 482."

### 4.10 Models wrap JSON in prose ⚑

**Symptom.** Answerable questions abstained **intermittently — four runs in five** on one
query, for a reason with nothing to do with the law.
**Cause.** A response prefaced with a sentence was treated as a malformed generation.
**Fix.** `_extract_json()` pulls the object out of whatever surrounds it.
**Also.** A malformed response yields an **empty answer**, not an exception — the caller then
abstains, which is correct. Raising would turn a bad generation into a 500.

### 4.11 Token cap truncation loses the entire answer

**Cause.** The default cap truncated a structured answer mid-object, and **a truncated JSON
object is a total parse failure**, not a partial answer.
**Fix.** `SYNTHESIS_MAX_TOKENS = 2048`.

### 4.12 Metrics that can be gamed by not trying ⚑

**Two traps, both closed:**
- `verbatim_fidelity` is measured over **every** statute claim, not just quoted ones —
  otherwise **a model that stops quoting to avoid being checked** shows an unchanged score
  over a shrinking denominator.
- Metrics are computed over the answer **as synthesis emitted it**, before failures are
  rewritten — otherwise scoring **deletes every failure from the record and reports a perfect
  1.0 for having caught them.**
- `unsupported` is **totalled**, never averaged: one bad claim in fifty answers is one too
  many, and a mean rounds it away.

### 4.13 Verification does not check that the answer answers the question ⚑

**Symptom, twice.**
- *"What does **BNSS** 103 say about murder?"* answered from **BNS** 103. **Every claim
  verified, because every claim was true — of a different provision than the one named.**
- *"Since IPC 302 still applies…"* answered correctly from BNS 103 **without noting the IPC
  is repealed**, leaving the false premise standing.
**Fix.** `citation_note()` — computed **from the parsed citation and the corpus, not by the
model**, so the correction cannot itself be wrong or be argued away.

### 4.14 Regeneration that drops the point entirely

**Symptom.** An answerable question came back as an abstention because a quotation was a few
words out.
**Fix.** Where a *quotation* failed, the feedback explicitly tells the model it may **keep
the point and paraphrase**. A paraphrase is still checked — the cited section must exist and
be the right one.

---

### 4.15 The pre-check ran the old section number against the new act ⚑

**Symptom.** *"What replaced IPC section 420?"* was refused, before retrieval and with no
model call, with **"There is no section 420 of the BNS."** True, unrelated, and unrecoverable
— nothing downstream runs after the pre-check refuses.
**Cause.** The check read `citation.section` — the number the query wrote down — instead of
`citation.sections`, the numbers that will actually be looked up. For a current citation they
are the same. For a repealed one they are not: IPC 420 is answered by BNS 318, and the BNS
runs to 358.
**Why it hid.** *"IPC 302"* passed — because BNS 302 happens to exist (it is about snatching).
An equally meaningless check, giving the right answer by luck.
**Fix.** Check what will be looked up. A repealed provision that became several (IPC 498A →
BNS 85 **and** 86) passes if any target exists.
**Guard.** Tests for both directions, including the one that used to pass for the wrong reason.
**The lesson.** *The most dangerous checks are the ones that usually pass.* Six of eight
`repealed_code` queries were abstaining; two remain.

### 4.16 Seven correct statements deleted for naming the wrong act ⚑

**Symptom.** Answers stating BNSS law correctly were cited to **BNS** and rejected: arrest
without warrant checked against the right of private defence (BNSS 35 vs BNS 35), the right
to meet an advocate against private defence causing death (38), maintenance of wives and
children against exploitation of a trafficked person (144). Every claim was true of the
provision it described and false of the provision it named.
**Cause.** The retrieved-context header gave the act's **full name**. All three begin
"Bharatiya", and a model shown *"Bharatiya Nagarik Suraksha Sanhita, Section 35"* writes BNS.
`short_name: "BNSS"` sat unused in the metadata.
**Why the prompt did not save it.** The synthesis prompt already said *"BNS 103 and BNSS 103
are unrelated provisions."* It could not have been enough: **a warning cannot supply a string
the context never contains.**
**Fix.** The header leads with the citation key — `[1] BNSS 35 (Bharatiya Nagarik Suraksha
Sanhita) - When police may arrest without warrant`.
**Measured.** Unsupported claims 35 → 20, abstentions 14 → 9, verbatim fidelity +0.135,
`plain` class 17 → 2 unsupported; adversarial abstention unchanged at 6/6.
**The lesson.** *Give the model the key it is checked against, not something it must
translate into one.* Identical in shape to the judgement-id bug that had made the `holding`
and `interpretation` classes unreachable — the same mistake, found twice, because the fix the
first time was treated as specific to judgements rather than as a rule.

---

### 4.17 A grounding number that moved on its own ⚑

**Symptom.** Turning reranking on appeared to take the `plain` class from **2 unsupported
claims to 18** while `judgement` went from 13 to 3. A clear, large, contradictory signal.
**Check before believing it.** The same configuration was run twice with **no code change**:
overall unsupported 20 → 18, abstentions 9 → 6, `judgement` **13 → 6**, `plain` **2 → 7**.
**Cause.** Synthesis is a sampled model call, the classes are small (12 judgement queries, 25
plain), each answer carries several claims, and one answer flipping between attempting and
abstaining moves its whole class.
**Consequence.** A per-class swing under ~7 is not evidence. A single A/B run of the grounding
harness **cannot settle a retrieval change** — the deterministic `eval_retrieval.py` decides
those, because embedding and ranking involve no sampling and its diffs are exact.
**Fix.** The noise floor is written into the harness docstring beside the gate, with the two
runs that measured it, so the next person reads a diff at the right resolution.
**The lesson.** *Measure your instrument before you trust a reading off it.* The gated
invariants were fine — they are properties of the deterministic verifier. It was the
*reported means and counts*, the numbers most likely to be quoted, that needed an error bar.

---

## 5. The legal graph

### 5.1 An inferred edge is invisible once it exists ⚑

**Rule.** **No LLM-inferred edges, ever.** A false relation propagates into every answer
touching either endpoint, with nothing in the output to show it was invented.
**So:** cross-references are mechanical (regex), judgement edges are transcribed metadata,
doctrine edges are curated by hand.

### 5.2 A foreign statute reference must be dropped, not redirected

**Symptom risk.** *"section 2 of the Dowry Prohibition Act"* becoming an edge to BNS 2.
**Fix.** **28 of 2,038** references are foreign and are dropped; a named act redirects
instead.

### 5.3 Precedential status is the highest-harm field

**Rule.** `doctrines.json` carries **no** `overruled_by`, no `still_good_law`. Not something
to infer, and not something to freeze into a file that ages.
**Where authority genuinely splits**, the doctrine is marked `contested` with both sides
named and **neither declared the winner**.

### 5.4 Sub-section keys do not match corpus keys

**Cause.** Offence rows key `103(1)`; the corpus keys `103`.
**Fix.** Attach to the parent so either lookup works.

### 5.5 Flattening the prompt turns a pointer into a fabricated holding ⚑

**Cause.** Given a case name adjacent to a section, with no indication that **only the name**
is available, a model writes what the case "held".
**Fix.** Render the four kinds **separately**, each with explicit permissions — judgements
may be **cited** but **must not** be described as holding anything; cross-referenced sections
are **titles only**.
**Same reasoning** drives `graph_context` being returned separately from `sources`: one was
reached by an **edge**, the other by **relevance**.

---

## 6. Agent orchestration

### 6.1 "Tell me about bail" produced a drafted bail application ⚑

**Cause.** Draft/analyse intents matched on **ordinary legal vocabulary** — "bail",
"petition", "contract", "risks" — which appears just as often in questions *about* the law.
**Fix.** `REQUIRED_TRIGGERS` — those intents score nothing without an **action verb**.

### 6.2 "Current case law on BNS 111" answered from the snapshot

**Cause.** RAG_SEARCH and LIVE_RESEARCH deliberately share case-law vocabulary; recency is
the only discriminator, and a single shared keyword outweighed it.
**Fix.** `TRIGGER_WEIGHT = 2` for live research, so the recency trigger outweighs a shared
keyword.

### 6.3 Ties resolved in enum order

**Symptom.** "What can you help me with?" went to vector search.
**Fix.** Explicit `_TIE_BREAK_ORDER` with **RAG_SEARCH last** — it is the documented
fallback, so it must *lose* ties to narrower intents.

### 6.4 Whether a question needs live data is not keyword-decidable

**Fix.** `live_research` is the one node that does **not** call a predetermined tool. The
model is given tool schemas and **chooses** between the local corpus and live sources.
**Observed** calling *both* for "what does BNS say about organised crime, and any recent
rulings?".

---

## 7. LLM integration

### 7.1 A missing API key crashed the whole app at import ⚑

**Cause.** The module-level singleton raised in `__init__`.
**Fix.** Build clients **lazily** — a missing key does not raise until a generation is
actually attempted, so the app starts and `/health` stays up.
**Do not "fix" this back.**

### 7.2 Unrecognised generation kwargs became provider 400s

**Fix.** Standardise on OpenAI names (`max_tokens`, `temperature`); accept `max_new_tokens`
as a legacy alias; **drop** unrecognised kwargs rather than forwarding them.

### 7.3 `generate_stream` blocked the event loop

**Cause.** A synchronous call inside an `async def`.
**Fix.** Real `stream=True`. Draft/analyse tools had the same bug.

### 7.4 Two streaming endpoints spoke different SSE dialects ⚑

**Symptom.** Streaming chat rendered nothing.
**Cause.** `/chat` emitted `{"type":"token","content":…}`; the agent emitted `{"token":…}`;
the frontend parser understood only the latter.
**Fix.** Unified on `{"token":…}` + `data: [DONE]`.

### 7.5 Live source access failed **open** ⚑

**Symptom.** `is_allowed()` logged "proceeding cautiously" and then **allowed everything**
when robots.txt could not be read.
**Cause.** Exactly backwards. The disallow list names several thousand documents
individually — **not knowing is not permission.**
**Fix.** Fail **closed**. The failure is not cached, since it is usually transient.
**Found when** the whole site went behind a challenge and robots.txt started 403-ing with it.

---

## 8. Containers and deployment

### 8.1 A container that passed its health check and 500-ed on every question ⚑

**Cause.** The image copied `data/processed` but **not `data/curated`**. `legal_graph`
refuses to build without `doctrines.json`, taking the grounded path and every `/offences`
response down with it.
**Why the health check missed it.** It does not exercise the graph.
**Fix.** `COPY data/curated /app/data/curated`.
**The lesson.** **A health check that doesn't exercise the real path is a green light on a
broken system.**

### 8.2 A half-finished seed looked complete on restart ⚑

**Cause.** The entrypoint gated on `chroma.sqlite3` — which **chromadb creates the moment a
client connects.** A crashed seed looked done and the API served an **empty corpus**,
silently.
**Fix.** Gate on a `.lawai-seeded` marker written **only after `init_vector_db.py` exits 0**.

### 8.3 The default torch wheel adds ~2.5 GB for nothing

**Fix.** Install **CPU-only torch first** (`--index-url .../whl/cpu`) so pip treats the
dependency as satisfied.

### 8.4 sentence-transformers phones home on every start

**Symptom.** ~20 HTTP round trips to huggingface.co per container start; hard failure when
offline or rate-limited.
**Fix.** Bake the model into the image **and set `HF_HUB_OFFLINE=1`** — baking alone is not
enough, it still revalidates.

### 8.5 `.dockerignore` silently ignored

**Cause.** BuildKit looks for **`<dockerfile>.dockerignore`** within the context. Since the
context is the repo root, a `backend/.dockerignore` is never read.
**Fix.** `backend/Dockerfile.dockerignore`.

### 8.6 `NEXT_PUBLIC_*` is inlined at build time

**Consequence.** `NEXT_PUBLIC_API_URL` must be the address the **browser** uses — never the
compose service name — and changing it requires `--build`, not a restart.

---

## 9. Frontend

### 9.1 A payload-shape mismatch crashed every answer ⚑

**Symptom.** `TypeError: Cannot read properties of undefined (reading 'match')` → Next.js
error screen, on **every answer** through the primary UI path.
**Cause.** The agent emitted claim `sources` as **bare strings**; `/search/grounded` emitted
typed **`{ref, kind}` objects**. `ClaimList` reads `source.ref`.
**Why every test passed.** Component tests used the endpoint's (correct) shape; agent tests
checked the agent's own self-consistent contract. **Nothing compared the two.**
**Fix.** `_grounded_payload()` emits typed objects. **Guard:** `TestPayloadShapesAgree`
compares both payloads directly.
**Follow-on.** The fix broke `_cited_sources()` (`unhashable type: 'dict'`) — caught by a
pre-existing test.
**The lesson ⚑.** **Two independent surfaces can each satisfy their own tests and still
disagree with each other.** Test the *relationship*, not just each side.

### 9.2 SVG labels clipped outside the viewBox

**Symptom.** "**rrest** without warrant", "Investigatio".
**Cause.** Labels are centred on their node; the first and last nodes sat half a label width
outside the `viewBox`.
**Fix.** `PADDING` 28 → 62.
**Only findable by looking** — hand-rolled SVG has no layout to assert against.

### 9.3 The API client was never committed ⚑

**Symptom.** A fresh clone could not build.
**Cause.** An unanchored `lib/` rule in `.gitignore` (meant for Python distutils output) also
matched `frontend/lib/`, silently excluding the module every frontend file imports.
**Fix.** Anchor to `/lib/`. **Do not re-broaden it.**

### 9.4 Search was broken end-to-end in three independent ways

Frontend called `/search/rag` while the backend served `/search/` (404); sent
`collection="bns_sections"` while the model accepted only short aliases (422); and read
`results.results[].content` while the API returns `answer` + `sources[].text`.
**All three** were invisible until the app was actually driven.

### 9.5 Dark-mode users got a white flash

**Cause.** React cannot hydrate before the browser paints.
**Fix.** `pages/_document.tsx` exists **solely** to apply the stored theme before first
paint.

### 9.6 The disclaimer and citations rendered twice

**Cause.** The backend appends `**Sources:**` and `**DISCLAIMER**` to `response` for
plain-text consumers; the UI renders both itself.
**Fix.** `stripAppendedBlocks` in `lib/api.ts`.

---

## 10. Process and tooling

### 10.1 Lint findings depended on the linter version ⚑

**Symptom.** ruff 0.1.14 flagged a handful; **0.16 flagged ~1,300 on identical code.**
**Cause.** ruff widens its defaults every release.
**Fix.** Pin the rule set in `backend/pyproject.toml`.
**The lesson.** **An unpinned linter is a test whose meaning changes under you.**

### 10.2 Tests imported the same modules under two names ⚑

**Cause.** Tests imported `backend.*` while the app imported `services.*`.
**Consequence.** Would have **duplicated every singleton** — two vector services, two
graphs, two LLM clients.
**Fix.** `pytest.ini` sets `pythonpath = .`; everything is on the `services.*` convention.

### 10.3 51 MB of binaries were tracked in git

**Fix.** `backend/chroma_db/` untracked and ignored; regenerate with `init_vector_db.py`.
**Also.** `data/raw/*.pdf` did not match subdirectories — now `data/raw/`.

### 10.4 A test asserted the wrong thing ⚑

**Symptom.** `test_it_does_not_invent` expected **abstention** on "the right to a phone call
after arrest".
**Reality.** The system answered with **BNSS 38** — the right to meet an advocate during
interrogation — quoted verbatim and verified. **Responsive and true.**
**Fix.** Rewrote the **test**, not the working code, to assert what actually matters: no
phone-call right is invented, and whatever *is* said checks out.
**The lesson.** *Abstention is not the goal — honesty is.* An over-abstaining system is also
a failure.

---

## The five lessons worth carrying elsewhere

1. **A safety layer that works makes other bugs visible.** The verifier turned a silent
   wrong-citation into a loud abstention (3.5). Systems that hide failures by smoothing them
   are worse than systems that fail loudly.
2. **Measure the obvious design before building it.** The relevance threshold was intuitive,
   universal in RAG writeups, and **provably wrong here** (4.3).
3. **Aggregates hide the bugs that matter.** Correct section counts hid a 129k-char section
   (1.6); a 0.652 mean hid a 0.250 class (§3).
4. **Green tests are a claim about what you wrote down.** Containers and browsers found four
   real bugs that 755 passing tests did not (9.1, 8.1, 8.2, 9.2).
5. **Validate your quality heuristics before you gate on them.** The title filter would have
   discarded 58 correct mappings and caught nothing (1.12).

---

*See also: [`ENGINEERING_DEEP_DIVE.md`](ENGINEERING_DEEP_DIVE.md) ·
[`RAG_PIPELINE.md`](RAG_PIPELINE.md) ·
[`EVALUATION_AND_TESTING.md`](EVALUATION_AND_TESTING.md)*
