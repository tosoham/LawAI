# The attribution gap

*Why the system cannot check, on its own, that a case is an authority on a section — and
what would actually close it.*

Written 2026-08-27, after the judgement corpus went from 30 to 300. Revisit this before
attempting any automated fix; the obvious ones have been tried and measured here.

---

## 1. What the gap is

`services/claim_verifier.py` catches the subtlest failure in the whole set: **a real case
cited for a section it has nothing to do with.** Both halves check out separately — the
case exists, the section exists — and only the relation between them is false.

It is caught by requiring a graph edge:

```
judgement --interprets--> section
```

Those edges are transcribed from each judgement's curated `relevant_sections` field. Only
the 30 hand-pinned judgements carry that field. After discovery took the corpus to 300:

| | |
|---|---|
| judgements in the graph | 300 |
| with any `interprets` edge | **27** |
| without | **273** |

The check is written `if stray and recorded:` — so when `recorded` is empty it **fails
open**. Coverage fell from 27-of-30 (90%) to 27-of-300 (**9%**) the moment the corpus grew,
with no test failing and every grounding metric *improving* over the same change.

---

## 2. The fix that was tried

A **text-mention check**: a case that never names the section it is cited for is not an
authority on it. Weaker than the edge, but checkable by string match, and it needs no
curation.

It was built carefully:

- section numbers extracted with `\bs(?:ec(?:tion)?s?)?\.?\s*(\d{1,3}[A-Za-z]{0,2})\b`,
  not bare numbers — judgements are full of years, paragraph numbers and money;
- **the old numbering translated through the concordance**, because the corpus runs
  1950–2026 with a median of 2012. A 2019 anticipatory-bail case says "Section 438
  Cr.P.C." and never writes "482", so checking the new number alone would reject exactly
  the pre-2023 landmarks the doctrine rests on;
- letter suffixes folded on both sides, so "124A" and "124" could match;
- a narrow variant that only rejects when the judgement cites *some* section and none of
  them match, so a judgement citing nothing is not judged at all.

## 3. What measuring it showed

Scored against the **34 curated (case, section) pairs** — the only ground truth that
exists, because they are the ones a human asserted:

| variant | wrongly rejected | rate |
|---|---|---|
| exact number match | 14 / 34 | **41%** |
| + concordance translation | 14 / 34 | 41% |
| + suffix folding | 14 / 34 | 41% |
| + skip judgements citing nothing | 11 / 34 | **32%** |

A check that deletes one true statement in three is unusable. Deleting true statements is
this project's most-repeated failure — see `CHALLENGES_AND_SOLUTIONS.md` 3.9, 4.16, and
the BNS 105 nesting bug — and it is worse than the hole it would close, because the hole
is at least visible in a metric.

## 4. Why it fails — the four causes, and why none are bugs

### A. The judgement cites no section number at all (3 of 14)

| case | curated to | length |
|---|---|---|
| State of Rajasthan v. Balchand | BNSS 480 | 5,609 chars |
| Hussainara Khatoon v. Home Secretary | BNSS 479 | 44,334 chars |
| Selvi v. State of Karnataka | BSA 23 | 60,126 chars |

*Balchand* is **the** authority for "bail is the rule, jail the exception" and does not
contain a single section number in its entirety. The proposition it stands for is a
principle, and the judgement states it as one.

### B. The two provisions are not equivalent, and the source correctly refuses to map them (1 of 14)

Kedar Nath Singh v. State of Bihar → BNS 152. The concordance has **no IPC 124A row at
all**, and that is not a parser gap — 121 lettered old sections *are* present (29A, 120B,
376AB…). The Bureau declined to equate them.

`data/curated/doctrines.json` already says why, in the `sedition_confined_to_incitement`
entry, which is marked **contested**:

> "Kedar Nath Singh read down the sedition provision then in force. BNS 152 is a
> differently worded provision, not a re-enactment of it, and how far the reading-down
> carries across to the new section has not been settled by this corpus."

So the mention check fails hardest on precisely the cases where the legal question is most
interesting: a 1962 judgement about a repealed offence, curated to a new provision whose
reach is genuinely open. **No text analysis can confirm that relation, because the relation
is contested.**

### C/D. The edge asserts a relation the text does not state (10 of 14)

Initially split into "truncated at the 60k ingestion cap" and "cites other sections only",
on the theory that the missing citation lay past the cut. **That theory was tested against
the full documents and is wrong:**

| case | curated to | number sought | full text | present? |
|---|---|---|---|---|
| P. Chidambaram v. Directorate of Enforcement | BNSS 480 | 437 | 92,874 chars | **no** |
| Satender Kumar Antil v. CBI | BNSS 482 | 438 | 207,994 chars | **no** |

Refetched whole, past the cap, the numbers are simply absent. The correlation with length
was spurious — long judgements cite many sections, so the missing one *looked* like it had
been cut off.

What is actually happening: these are authorities on bail **principles**. They argue under
section 439 (the High Court's and Sessions Court's bail power) or under the PMLA's own
provisions, while being authority for how 437 is to be approached. A lawyer knows this. The
document does not say it.

**So: 14 of 14 failures are fundamental. None are data-pipeline bugs. Raising the 60k cap
fixes nothing.**

---

## 5. The underlying reason, stated once

`relevant_sections` encodes **what a case is an authority for**. A judgement's text records
**what it cited**. These are different propositions, and the first is not recoverable from
the second.

This is the same finding `scripts/discover_judgments.py` reached from the opposite
direction and refused to work around: reading the act out of each citation recovers **1 of
27** curated section attributions, and taking each judgement's most-mentioned act is worse
than useless (Nandini Satpathy is an authority on the Evidence Act while mentioning the
CrPC 32 times to its 2). That is why discovery writes `cited_sections` and never
`relevant_sections`.

The attribution gap is that same wall, met from the verification side.

---

## 6. What shipped instead

1. **A verbatim check on quoted judgement text** — a `holding` or `interpretation` claim
   carrying a `verbatim_span` must have those words appear in the cited judgement, exactly
   as a `statute` claim's span is checked against its section. This became possible only
   when the corpus started storing whole judgements. It caught **3 misquoted judgements**
   over the golden set that had been passing unchecked. Sound, no false-positive risk
   beyond what statute claims already accept.
2. **`AnswerMetrics.unverifiable_attribution`** — counts `holding`/`interpretation` claims
   that cite both a section and a judgement with no recorded edges. Totalled, never
   averaged, for the same reason `unsupported` is. It measured **2** over the answerable
   golden set.

Measure what cannot be gated.

---

## 7. What would actually close it

**Curation, and only curation.** In rough order of cost:

1. **Hand-curate `relevant_sections` for high-value discovered cases.** ~50 well-chosen
   judgements would cover most of what answers actually rest on. Pure data work; no code
   changes; every added edge immediately re-arms the existing check for that case. This is
   the recommended path.
2. **LLM-proposed, human-approved edges.** A model reads a judgement and proposes the
   sections it is an authority on; a human accepts or rejects each. Note this does **not**
   violate the no-LLM-inferred-edges rule *only if* the human review is real — an approved
   edge is a human assertion that a model happened to draft. If the review degrades into
   rubber-stamping, this becomes exactly the confident-wrong-edge failure the rule exists
   to prevent, and it will be invisible.
3. **Treat absence of an edge as a UI signal**, not a verification one — render an
   attribution the graph cannot confirm differently in `ClaimList`, so the reader sees
   which citations rest on curation and which do not. Cheap, honest, and it does not risk
   deleting anything true.

**What must not be done:** synthesising `interprets` edges from `cited_sections`, from
topic overlap, from co-occurrence, or from a model's unreviewed opinion. Every one of those
produces confident wrong edges that propagate into every answer touching either endpoint,
with nothing in the output to show they were invented.

---

## 8. How to tell if a future fix is real

Score it against the 34 curated pairs before shipping. The reproduction is:

```python
# false-rejection rate of any proposed check, against the only ground truth there is
from services.legal_graph import get_legal_graph
graph = get_legal_graph()
pairs = [(j, s) for j, sections in graph.interprets.items() for s in sections]
wrong = [(j, s) for j, s in pairs if not proposed_check(graph.judgements[j], s)]
print(len(wrong), "/", len(pairs))
```

Anything above a few percent deletes true statements from answers. The bar is not "better
than nothing" — the hole is measured and visible, and a wrong check is worse than an
honest gap.
