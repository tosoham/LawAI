# Interview Brief

**Talking points for LawAI, anchored on what was actually built and measured.**

Written for screening conversations about **RAG, chunking, batching, LLM evaluation, testing
and retrieval**. Every number here is reproducible from this repository; every story is a
real bug with a real fix and, in most cases, a test that pins it.

> **The rule for using this document:** do not memorise it. Understand the *reasoning*.
> Interviewers probe, and a memorised answer collapses on the second question. Each section
> below gives the claim, the evidence, and the follow-up you should expect.

---

## 1. The 60-second project summary

> "LawAI answers questions about Indian criminal law under the 2023 codes — BNS, BNSS and
> BSA, which replaced the IPC, CrPC and Evidence Act. It's a FastAPI backend, Next.js
> frontend, ChromaDB with local MiniLM embeddings, and a LangGraph agent over an LLM.
>
> The corpus isn't downloaded — it's parsed from official government gazette PDFs, because
> no dataset of the 2023 codes exists. 1,059 statutory sections, 30 Supreme Court judgements,
> plus two structured tables: the offence classification schedule and a concordance mapping
> old code sections to new ones.
>
> The part I'd actually want to talk about is that **it's built to refuse.** An answer isn't
> prose — it's a list of typed claims, each labelled as statute, classification, a court's
> holding, or the model's own inference. Each type gets checked by a rule appropriate to it,
> deterministically, against committed data. Anything that fails is deleted, not hedged. If
> nothing survives, it abstains and says so.
>
> On retrieval I got recall@3 from 0.65 to 0.93 on a 69-query golden set — but the
> interesting part isn't the number, it's that I split the eval into failure classes, and
> each fix moved exactly one class."

**Have ready:** why the 2023 codes matter (the domain is *new*, so the model's training data
is actively wrong about it — it will cite IPC 302 for murder, which is repealed).

---

## 2. The strongest stories, ranked

Lead with these. Each has a measurement, a decision, and a consequence.

### 2.1 "I measured the obvious design and rejected it" — abstention ⭐

**The setup.** Everyone builds "know when you don't know" as a **relevance threshold**: score
retrieval, refuse below a cutoff.

**What I measured.**

| | best cosine distance |
|---|---|
| 69 answerable queries | worst case **0.577** |
| 6 known-unanswerable queries | as low as **0.423** |

**The distributions overlap.** Any threshold either refuses real questions or admits invented
answers.

**Why they overlap** — this is the part that shows understanding: *"How many days of parole
under the BNSS?"* retrieves genuinely similar text — prison-adjacent procedural sections — at
a good distance. **"The corpus contains something that looks like this" and "the corpus can
answer this" are different questions**, and vector distance only measures the first.

**What I did instead.** Abstention falls out of **verification**: the gate is whether one
claim survives checking, and the threshold is one. It cannot be mis-tuned, because there is
no parameter.

**Expect:** *"Couldn't you have used a reranker score instead?"* → Same problem, one layer
up. A reranker also measures similarity, not answerability. The distinguishing signal is
whether a specific factual assertion can be grounded, which is a different kind of check.

### 2.2 "Each retrieval layer moved exactly one failure class" ⭐

**The ablation:**

| Class | n | Dense | +expansion | +structured | +concordance |
|---|---|---|---|---|---|
| `plain` | 25 | 0.960 | 0.960 | 0.960 | 0.960 |
| `term_of_art` | 16 | 0.500 | **0.875** | 0.875 | 0.875 |
| `citation` | 8 | 0.250 | 0.250 | **1.000** | 1.000 |
| `repealed_code` | 8 | 0.125 | 0.375 | 0.375 | **1.000** |
| `judgement` | 12 | 0.833 | 0.833 | 0.833 | 0.833 |

Overall recall@3: **0.652 → 0.928**.

**The point to make:** the diagonal is the evidence. Three distinct problems, three targeted
fixes, no collateral damage, `plain` never moves. If I had only reported the aggregate, I
couldn't tell you whether any individual fix worked or whether one had broken something else.

**Expect:** *"Why is `judgement` flat?"* → Be honest: no layer targeted it, and 12 queries
over 30 judgements is a thin sample. It's a known gap, not a success.

### 2.3 "BM25 would not have fixed it" ⭐

**The problem.** BNSS 482 governs anticipatory bail. The section is titled *"Direction for
grant of bail to person apprehending arrest"*, and **the word "anticipatory" appears nowhere
in its 1,948 characters.**

**Why this is the good answer:** "add hybrid search" is the reflex fix for a retrieval gap.
It is wrong here, and you can only know that by **reading the source text and confirming the
term is absent**.

> The term isn't in the document. There's nothing for BM25 to match either. It's a
> **vocabulary** problem, not a semantic-versus-lexical one — so the fix has to be a
> vocabulary layer.

**The fix.** A curated alias table appending statutory phrasing before embedding. Additive
(a working query can't get worse), and **only the embedded text changes** — the model still
sees the user's own wording.

**Expect:** *"Doesn't a curated table not scale?"* → Correct, and I'd say so. It covers ~30
high-value terms of art. The scalable version is a learned alias layer or a domain-tuned
embedder, and I'd gate that on beating the committed baseline. Curation was the right call
for a corpus where a wrong alias silently misdirects retrieval.

### 2.4 "A citation is not a search" ⭐

**Symptom.** `"section 482 BNSS"` did not surface BNSS 482 **anywhere in the top 20**.
Citation was the worst class at recall@3 **0.250**.

**Diagnosis.** **A section number carries almost no semantic signal.** "482" and "483" embed
to nearly the same point, and a section's text rarely repeats its own number. **Reranking
cannot fix this** — a reranker works from the same signal.

**Fix.** Stop treating it as retrieval. A citation *names one document*; fetch it by exact
metadata key at distance 0.0 and rank it first, keeping vector hits behind it (a citation is
usually only part of what was asked).

**0.250 → 1.000.**

**The refusal that shows judgement:** "CrPC 438" means BNSS 482 — but **BNSS also has a
section 438**, about something else. Mapping the number across would turn a *miss* into a
*confident wrong answer*. So it was refused outright until I had a sourced concordance, and
anything the concordance doesn't cover is **still** refused.

### 2.5 "A working safety layer surfaced a retrieval bug" ⭐

*"What is the punishment for theft?"* was abstaining **one time in three**.

Dense retrieval ranked BNS 305 (theft in a dwelling house) and BNS 304 (snatching) above
BNS 303 (theft). The model cited them; the verifier correctly rejected the claims; a basic
question came back as "I cannot answer."

> **Without verification, the system would have confidently cited BNS 304 for theft and
> nobody would ever have noticed.** A safety mechanism made a retrieval bug *visible* —
> which is the inverse of the usual relationship, where safety layers hide problems by
> smoothing over them.

**Expect:** *"So your safety layer caused a regression?"* → No — it *revealed* one that had
always been there. Before the verifier the same bug produced a confident wrong citation.
Abstention is the better failure mode, and it's the one that got the bug fixed.

### 2.6 "The model can't grade itself" ⭐

> **The prior that invented BNS 999 will confirm BNS 999** — the same prior produced both.
> A model grading a model isn't an independent check; it's the same failure applied twice
> and reported as agreement.

Every check is a lookup against committed data:

| Class | Check |
|---|---|
| `statute` | section exists + quoted span appears verbatim |
| `classification` | matches its First Schedule row |
| `holding` | case exists **and** the graph records it as bearing on that section |
| `contested` | ≥2 positions, each with authority |
| `inference` | may cite nothing, must not read like law |

**Expect:** *"When would you use LLM-as-judge?"* → For things with no ground truth —
helpfulness, tone, whether an answer addresses the question. Not for citation correctness,
where a deterministic check exists. In this project the model is the **system under test**,
never the judge.

---

## 3. Chunking and batching — expect these

### "Walk me through your chunking strategy."

> "1,200 characters with 150 overlap, sized to the embedder's ~256-token window. But the
> parameters aren't the interesting part — **the reason** is.
>
> `all-MiniLM-L6-v2` doesn't error on long input, it **truncates silently**. A 60,000-char
> judgement indexed whole is represented by its first paragraph and can never match a query
> about its holding. There's no error and nothing in the logs — it just presents as
> 'retrieval isn't very good.'
>
> The split is hierarchical: whole document if it fits, else paragraphs, else sentences, else
> a hard cut — then **re-packed greedily** so chunks are near-uniform. A naive paragraph
> splitter gives you a 40-character proviso next to a 1,100-character sub-section, and short
> chunks embed badly because there's not enough context to place them.
>
> One detail specific to this domain: sentence splitting breaks on `;` and `:` as well as
> `.`, because statutory drafting uses semicolon-separated clauses far more than full stops.
>
> The most important part is metadata. Every chunk carries `parent_id`, so a retrieved
> fragment is **citable back to its section**. In a legal answer, a chunk you can't attribute
> is a chunk you can't use, whatever its similarity score."

**The payoff to mention:** `parent_id` later let the verifier check a quotation against the
**whole section** rather than the retrieved chunk. That mattered — the model quoted BNS 303
correctly while retrieval had returned that section's *fifth* chunk, and checking only the
chunk **rejected a true statement of the law**.

### "Why batch, and how did you size it?"

> "256 chunks per write. Three reasons, in order:
>
> **Peak memory** — `encode()` over 3,184 texts at once materialises the whole activation
> set. Batching bounds it, which is what lets the seed run in a memory-limited container
> instead of getting OOM-killed halfway.
>
> **Failure isolation and progress** — a failure names the batch instead of losing a
> five-minute run with no indication where.
>
> **Write efficiency** — per-document `add()` calls are dominated by transaction overhead.
> 256 is comfortably inside Chroma's limits and large enough to amortise it.
>
> Related: the embedding model is a **singleton** — it's ~90 MB and takes seconds to load, so
> constructing it per request would dominate query latency."

### "How many chunks, and why so few?"

1,089 documents → **3,184 chunks**. Low because **most statutory sections fit in one chunk** —
the strategy doesn't fragment a 400-char section for no reason. The expansion is concentrated
in the 30 judgements.

---

## 4. Evaluation — expect these

### "How do you know it works?"

Three layers, and say all three:

1. **Retrieval eval** — 69 golden queries in 5 failure classes, recall@{1,3,5,10}, MRR,
   nDCG@10, reports committed to `backend/eval/`.
2. **Answer-grounding metrics** — grounding rate, verbatim fidelity, unsupported-claim count
   (the build gate), unattributed interpretations, inference share.
3. **Adversarial suite against the real model** — injection, fabrication bait, drift.

### "Why classes instead of one number?"

> "One average would have shown 0.652 and told me nothing about *which* kind of query was
> broken. Split by class, it showed **`citation` at 0.250** — a catastrophic failure in the
> single most common way a lawyer phrases a question — hiding inside a respectable mean.
>
> Classes also make regressions legible. `--compare` prints a per-class delta **and names
> every individual query whose first correct hit moved to a worse rank.** An aggregate can
> improve while one class silently breaks."

### "How do you measure hallucination?"

> "As a count, not a score. A confidence score is the model's own feeling about its output,
> which is precisely what fails when the output is wrong.
>
> `unsupported` is the number of claims the verifier rejected. It's **totalled** across the
> golden set, never averaged — one bad claim in fifty answers is one too many, and a mean
> rounds it into invisibility."

**Have the two anti-gaming decisions ready — they show real thought:**

> "`verbatim_fidelity` is measured over **every** statute claim, not just the quoted ones.
> Otherwise a model that **stops quoting to avoid being checked** shows an unchanged score
> over a shrinking denominator. It has to appear as a drop.
>
> And metrics are computed over the answer **as synthesis emitted it**, before the verifier
> rewrites failures. Scoring the survivors would delete every failure from the record and
> report a perfect 1.0 for having caught them."

### "What are the weaknesses of your eval?"

**Volunteer these — it reads as maturity, not weakness:**

- 69 queries is small; 8–16 per class is smaller.
- **I wrote both the system and the golden set.** That's the real methodological weak point;
  a second annotator is the fix.
- `judgement` recall never moved — no layer targeted it.
- It measures **retrieval**, not answers. Perfect recall@3 with a hallucinating generator is
  still broken — which is why the grounding metrics exist.
- `0.93` is retrieval recall on my own 69-query set. **Not "accuracy", not a public
  benchmark.** The landing page has a test asserting it quotes no accuracy percentage.

---

## 5. Testing — expect these

### "What's your testing strategy?"

**763 backend tests (755 pass, 8 skip), 106 frontend.** Structure:

- **Unit** — services, verifier, parsers, graph, metrics.
- **Data integrity** — because the corpus *is* the guarantee: **21 offences transcribed by
  eye from the PDF** are pinned exactly, with invariants over the other 444.
- **Verifier tests** — deliberately fabricated claims (BNS 999, misquoted text, a real case
  cited for a section it never mentions, "murder is bailable", a one-sided contested claim);
  each must be caught.
- **Integration/live** — marked `live`, skipped without `AIML_API_KEY`, so a plain `pytest`
  is green with no credentials or bill.
- **Adversarial** — injection, drift, fabrication bait.

### "What did your tests miss?" ⭐

**This is the best testing answer you have. Lead with it if asked anything about testing
limitations.**

> "Four real bugs got past a fully green suite.
>
> The worst: the agent emitted claim `sources` as **bare strings**, and the other endpoint
> emitted typed **`{ref, kind}` objects**. The UI reads `source.ref`, so it threw a
> `TypeError` and crashed to an error screen **on every single answer** through the main
> path.
>
> Every test passed — the component tests used the endpoint's shape, which was correct; the
> agent tests checked the agent's own contract, which was self-consistent. **Nothing compared
> the two payloads to each other.**
>
> That's the lesson: **two independent surfaces can each satisfy their own tests and still
> disagree.** Unit tests verify the contract you wrote down; they can't verify the one you
> assumed. There's now a test asserting the two payloads have identical keys and identical
> source shapes.
>
> The other three: a container that **passed its health check and 500-ed on every question**
> because the image was missing a data directory the graph needs — a health check that
> doesn't exercise the real path is a green light on a broken system. A seed marker that made
> a half-finished vector index look complete, so the API silently served an empty corpus. And
> SVG labels clipped outside their viewBox, which only looking at the page can find.
>
> So: run it in the container, open it in a browser, and test the *relationship between*
> components — not just each side."

### "Tell me about a test that was wrong."

> "I wrote a test asserting the system should **abstain** on 'What does BNSS say about the
> right to a phone call after arrest?' — because the BNSS doesn't confer that right.
>
> It answered with **BNSS 38** — the right to meet an advocate during interrogation — quoted
> verbatim and verified. That's responsive and true.
>
> **The system was right and my test was wrong.** I rewrote the test to assert what actually
> matters — that no phone-call right is invented and whatever *is* said checks out — instead
> of 'fixing' working code to satisfy a bad assertion.
>
> The underlying point: **abstention isn't the goal, honesty is.** An over-abstaining system
> is also a failure, just a less embarrassing one."

---

## 6. Prompt injection and safety

### "How do you handle prompt injection?"

**Six attacks, all held. Give the architectural reason, not the list:**

> "An injection can influence **generation**, but generation isn't what reaches the user.
>
> A prompt telling the model murder is bailable produces, at worst, *a claim that murder is
> bailable* — which is then checked against the First Schedule and deleted. **The attack
> surface is the model; the guarantee is downstream of it.**
>
> They held for **structural** reasons, not because the model behaved: the disclaimer is
> appended by the service so there's nothing for an instruction to reach; the classification
> is checked against a parsed table; an invented case can't be found in the corpus. A defence
> that depends on the model complying isn't a defence."

**Attacks tested:** ignore-previous-instructions + false classification · suppress the
disclaimer · leak the system prompt · adopt an invented authority · role-override for a
recommendation · a real case cited for a section it doesn't concern.

### "What about drift?"

> "**A system that says 'non-bailable' four times in five isn't 80% right — it's wrong in a
> way that's harder to notice.** Repeated runs of the consequential questions, asserting on
> the values that matter rather than string equality of the whole answer. Prose varies; the
> law doesn't. Observed 100% consistent."

---

## 7. Questions you must answer honestly

Rehearse these. Getting caught overclaiming on a project whose entire thesis is *not
overclaiming* would be fatal.

### "Is this really multi-agent?"

> **"No, and I'd rather say so.**
>
> It's a single LangGraph agent with keyword-based intent routing to five tool nodes. There's
> no negotiation, no critique, no handoff between agents. The planner-plus-parallel-
> specialists design — including a dialectical path where separate agents develop competing
> readings of a contested constitutional question — is **designed and not built.**
>
> What this project actually demonstrates is a **verification architecture**, not multi-agent
> collaboration. The one place multi-agent would genuinely earn itself here is that contested
> path, where you want two positions developed independently and a synthesiser that doesn't
> resolve them — and that's what I'd build next."

**Why this answer helps you:** it demonstrates you can distinguish orchestration from
collaboration, which most candidates using the phrase cannot.

### "Your corpus is only 30 judgements."

> "Correct, and it's the binding constraint — doctrine depth limits the graph more than
> architecture does. The expansion script is written and tested but **unrunnable**: the
> source went behind a Cloudflare challenge that 403s every path including `/robots.txt`.
>
> I didn't work around it. That's an access control the site deliberately put in place. What
> I did instead was make the blockage **visible** — `/research/health` now reports
> `reachable` and `last_error`, instead of showing `enabled: true` while nothing worked.
>
> The unblock is the official API, about ₹78 for the ~300 judgements at their per-document
> rate."

**The negative result worth volunteering here:** the discovery script *cannot* derive which
sections a judgement is an authority on from its text. Measured against the 30 curated
judgements: reading the act out of each citation recovers **1 of 27**, because judgements
write a bare "Section 438" and rely on context. Taking each judgement's most-mentioned act is
**worse** — Nandini Satpathy is an authority on the Evidence Act while mentioning the CrPC 32
times to its 2. So derived sections are written to `cited_sections` — a checkable claim about
the document — and **never** to `relevant_sections`, which would become a graph edge.

> That's a good story because it's a **negative result I measured rather than a feature I
> shipped**, and shipping it would have produced confident wrong edges in the graph.

### "What would you do differently?"

1. **The manifest.** Swapping the embedder against an existing Chroma volume **silently
   serves an index built by a different model** — everything works, every answer is slightly
   wrong. A manifest of model + chunk params in the volume, reseeding on mismatch. I designed
   it and didn't build it, and it's the highest-risk gap.
2. **A second annotator on the golden set.**
3. **Cross-encoder reranking**, gated on beating the committed baseline — it becomes
   load-bearing at a 10:1 judgement-to-statute chunk ratio.
4. **Build the contested path**, which is the one place multi-agent earns itself.

### "What's missing for production?"

No authentication, no rate limiting, no observability beyond logs, no CI. Agent "streaming"
is faux — the graph runs to completion and the string is sliced into SSE chunks, because real
streaming would discard the structured `sources`. Single-node ChromaDB with no replication.

---

## 8. Numbers to have memorised

| | |
|---|---|
| Corpus | 358 BNS + 531 BNSS + 170 BSA = **1,059 sections**, 30 judgements |
| Structured data | **465** offence rows, **1,195** concordance mappings, 16 doctrines |
| Index | 1,089 docs → **3,184 chunks**; 1,200 chars / 150 overlap / batch 256 |
| Embedder | `all-MiniLM-L6-v2`, 384-dim, ~256-token window |
| Graph | **931** cross-refs, 34 interprets edges, 288 classified sections |
| Retrieval | recall@3 **0.652 → 0.928**; citation 0.250 → **1.000**; term_of_art 0.500 → **0.875**; repealed 0.125 → **1.000** |
| Abstention evidence | answerable worst **0.577**, adversarial best **0.423** — overlapping |
| Tests | **763 backend** (755 pass / 8 skip), **106 frontend** |
| Injection | **6/6 held** |

---

## 9. The one-liners worth landing

- *"I didn't try to stop the model hallucinating. I assumed it would, and built the pipeline
  so a hallucination can't reach the user."*
- *"The attack surface is the model; the guarantee is downstream of it."*
- *"The prior that invented BNS 999 will confirm BNS 999."*
- *"A citation isn't a search — it names one document."*
- *"BM25 wouldn't fix it; the term isn't in the text at all."*
- *"A guessed 'bailable' is the most dangerous value this system can emit."*
- *"Two surfaces can each pass their own tests and still disagree with each other."*
- *"A health check that doesn't exercise the real path is a green light on a broken system."*
- *"Abstention isn't the goal — honesty is."*
- *"Right facts, wrong provision — and the citation is what the reader follows."*

---

*Source documents: [`ENGINEERING_DEEP_DIVE.md`](ENGINEERING_DEEP_DIVE.md) ·
[`RAG_PIPELINE.md`](RAG_PIPELINE.md) ·
[`EVALUATION_AND_TESTING.md`](EVALUATION_AND_TESTING.md) ·
[`CHALLENGES_AND_SOLUTIONS.md`](CHALLENGES_AND_SOLUTIONS.md)*
