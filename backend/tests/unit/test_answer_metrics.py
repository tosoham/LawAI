"""
Unit tests for the answer metrics.

A metric that cannot move is decoration, so most of these check that a specific
degradation makes a specific number drop: the model stops citing, grounding
falls; it stops quoting to avoid being checked, fidelity falls rather than
holding steady over a shrinking denominator; it answers a statute question
mostly by reasoning, inference share rises.
"""
from models.claims import (
    Claim,
    ClaimSource,
    EpistemicClass,
    Position,
    SourceKind,
    StructuredAnswer,
)
from services.answer_metrics import AnswerMetrics, aggregate, compute
from services.claim_verifier import VerificationContext, verify
from services.legal_graph import get_legal_graph

BNS_103_TEXT = (
    "Whoever commits murder shall be punished with death or imprisonment for life."
)


def context():
    return VerificationContext(
        graph=get_legal_graph(), section_texts={"BNS 103": BNS_103_TEXT}
    )


def statute(span=None, sources=("BNS 103",)):
    return Claim(
        text="Murder is punished with death or imprisonment for life.",
        epistemic_class=EpistemicClass.STATUTE,
        sources=list(sources),
        verbatim_span=span,
    )


class TestGroundingRate:
    def test_every_claim_cited_scores_one(self):
        answer = StructuredAnswer(claims=[statute(), statute()])
        assert compute(answer).grounding_rate == 1.0

    def test_an_uncited_claim_drags_it_down(self):
        answer = StructuredAnswer(claims=[statute(), statute(sources=())])
        assert compute(answer).grounding_rate == 0.5

    def test_inference_is_excluded_from_the_denominator(self):
        """Reasoning has nothing to cite; counting it would make an honest
        answer look ungrounded."""
        answer = StructuredAnswer(
            claims=[statute(), Claim(text="likely", epistemic_class=EpistemicClass.INFERENCE)]
        )
        assert compute(answer).grounding_rate == 1.0

    def test_a_contested_claim_is_grounded_by_its_positions(self):
        """The authority lives on each side of the split, which is where it has
        to be for the split to mean anything."""
        answer = StructuredAnswer(
            claims=[
                Claim(
                    text="contested",
                    epistemic_class=EpistemicClass.CONTESTED,
                    positions=[
                        Position(summary="a", authority=["sc_a_2017"]),
                        Position(summary="b", authority=["sc_b_2022"]),
                    ],
                )
            ]
        )
        assert compute(answer).grounding_rate == 1.0

    def test_a_contested_claim_with_a_bare_position_is_not_grounded(self):
        answer = StructuredAnswer(
            claims=[
                Claim(
                    text="contested",
                    epistemic_class=EpistemicClass.CONTESTED,
                    positions=[Position(summary="a", authority=["sc_a_2017"]), Position(summary="b")],
                )
            ]
        )
        assert compute(answer).grounding_rate == 0.0

    def test_an_empty_answer_scores_zero_not_one(self):
        """Nothing verified perfectly is not the same as nothing to verify."""
        assert compute(StructuredAnswer()).grounding_rate == 0.0


class TestVerbatimFidelity:
    def test_a_matching_quotation_scores(self):
        answer = StructuredAnswer(claims=[statute("death or imprisonment for life")])
        _, verdicts = verify(answer, context())
        assert compute(answer, verdicts).verbatim_fidelity == 1.0

    def test_a_misquotation_does_not(self):
        answer = StructuredAnswer(claims=[statute("death or imprisonment for seven years")])
        _, verdicts = verify(answer, context())
        assert compute(answer, verdicts).verbatim_fidelity == 0.0

    def test_dropping_the_quotation_lowers_the_score(self):
        """
        The gaming move this is built against: a model that stops quoting can
        no longer be caught misquoting. Fidelity is measured over every statute
        claim, so it falls instead of holding steady.
        """
        quoted = StructuredAnswer(claims=[statute("death or imprisonment for life")])
        paraphrased = StructuredAnswer(claims=[statute()])
        _, quoted_verdicts = verify(quoted, context())
        _, paraphrase_verdicts = verify(paraphrased, context())
        assert compute(quoted, quoted_verdicts).verbatim_fidelity == 1.0
        assert compute(paraphrased, paraphrase_verdicts).verbatim_fidelity == 0.0

    def test_an_answer_with_no_statute_claims_scores_zero(self):
        answer = StructuredAnswer(
            claims=[Claim(text="x", epistemic_class=EpistemicClass.INFERENCE)]
        )
        assert compute(answer).verbatim_fidelity == 0.0


class TestUnsupported:
    def test_it_counts_what_the_verifier_rejected(self):
        answer = StructuredAnswer(
            claims=[
                statute("death or imprisonment for life"),
                Claim(
                    text="Murder is bailable.",
                    epistemic_class=EpistemicClass.CLASSIFICATION,
                    sources=["BNS 103"],
                ),
            ]
        )
        _, verdicts = verify(answer, context())
        metrics = compute(answer, verdicts)
        assert metrics.unsupported == 1
        assert not metrics.clean

    def test_an_answer_with_nothing_removed_is_clean(self):
        answer = StructuredAnswer(claims=[statute("death or imprisonment for life")])
        _, verdicts = verify(answer, context())
        assert compute(answer, verdicts).clean

    def test_the_classes_recorded_are_the_ones_asserted(self):
        """
        Metrics take the answer as synthesis emitted it. Passing the rewritten
        answer would delete every failure from the record and score a perfect
        fidelity for having caught them.
        """
        # A section that does not exist, rather than a misquotation: a bad
        # quotation is no longer unsupported -- the span is dropped and the
        # statement kept -- so it is the wrong example for this property.
        answer = StructuredAnswer(claims=[statute(sources=("BNS 999",))])
        _, verdicts = verify(answer, context())
        metrics = compute(answer, verdicts)
        assert metrics.by_class == {"statute": 1}
        assert metrics.unsupported == 1


class TestUnattributedInterpretation:
    def test_an_interpretation_with_no_case_is_counted(self):
        answer = StructuredAnswer(
            claims=[
                Claim(
                    text="Courts read this narrowly.",
                    epistemic_class=EpistemicClass.INTERPRETATION,
                    sources=["BNS 103"],
                )
            ]
        )
        assert compute(answer).unattributed_interpretation == 1

    def test_an_attributed_one_is_not(self):
        answer = StructuredAnswer(
            claims=[
                Claim(
                    text="Bachan Singh read this narrowly.",
                    epistemic_class=EpistemicClass.INTERPRETATION,
                    sources=["BNS 103", "sc_bachan_singh_v_state_of_punjab_1980"],
                )
            ]
        )
        assert compute(answer).unattributed_interpretation == 0


class TestInferenceShareAndSourceMix:
    def test_inference_share_is_over_all_claims(self):
        answer = StructuredAnswer(
            claims=[
                statute(),
                Claim(text="a", epistemic_class=EpistemicClass.INFERENCE),
                Claim(text="b", epistemic_class=EpistemicClass.INFERENCE),
            ]
        )
        assert compute(answer).inference_share == round(2 / 3, 4)

    def test_source_mix_separates_live_from_corpus(self):
        """An answer resting mainly on unverified live results has to be
        visible as such rather than reading like settled law."""
        answer = StructuredAnswer(
            claims=[
                Claim(
                    text="x",
                    epistemic_class=EpistemicClass.HOLDING,
                    sources=["BNS 103", "https://indiankanoon.org/doc/1/"],
                )
            ]
        )
        assert compute(answer).source_mix == {"section": 1, "live": 1}


class TestAggregate:
    def test_unsupported_is_totalled_not_averaged(self):
        """One unsupported claim in fifty answers is one too many, and a mean
        would round it into invisibility."""
        answer = StructuredAnswer(claims=[statute(sources=("BNS 999",))])
        _, verdicts = verify(answer, context())
        bad = compute(answer, verdicts)
        clean = compute(StructuredAnswer(claims=[statute()]))
        summary = aggregate([bad, *[clean] * 49])
        assert summary["unsupported_total"] == 1
        assert summary["clean_answers"] == 49

    def test_an_empty_run_reports_itself(self):
        assert aggregate([]) == {"n": 0}


class TestUnverifiableAttribution:
    """
    The gap Phase 3 opened, made visible because it cannot be gated.

    `interprets` edges are transcribed from curated `relevant_sections`, which
    only the 30 pinned judgements carry. At 300 judgements 273 have none, so a
    holding claim citing one of those for a section cannot be checked for the
    relation at all. A text-mention check was measured against the 34 curated
    pairs and rejected 41% of them, so it is counted rather than rejected.
    """

    @staticmethod
    def _holding(judgement, section="BNS 103"):
        return Claim(
            text="x",
            epistemic_class=EpistemicClass.HOLDING,
            sources=[
                ClaimSource(kind=SourceKind.JUDGEMENT, ref=judgement),
                ClaimSource(kind=SourceKind.SECTION, ref=section),
            ],
        )

    def test_a_curated_case_with_edges_is_verifiable(self):
        answer = StructuredAnswer(
            claims=[self._holding("sc_bachan_singh_v_state_of_punjab_1980")]
        )
        assert compute(answer).unverifiable_attribution == 0

    def test_a_discovered_case_without_edges_is_counted(self):
        from services.legal_graph import get_legal_graph

        graph = get_legal_graph()
        discovered = next(
            j for j in graph.judgements if not graph.interprets.get(j)
        )
        answer = StructuredAnswer(claims=[self._holding(discovered)])
        assert compute(answer).unverifiable_attribution == 1

    def test_a_holding_citing_no_section_is_not_counted(self):
        """Nothing to be wrong about: with no section cited there is no
        case-to-section relation to leave unchecked."""
        claim = Claim(
            text="x",
            epistemic_class=EpistemicClass.HOLDING,
            sources=[
                ClaimSource(
                    kind=SourceKind.JUDGEMENT, ref="sc_bachan_singh_v_state_of_punjab_1980"
                )
            ],
        )
        assert compute(StructuredAnswer(claims=[claim])).unverifiable_attribution == 0

    def test_it_reaches_the_serialised_metrics(self):
        assert "unverifiable_attribution" in AnswerMetrics().to_dict()


class TestMisquoteDoesNotScorePerfectly:
    def test_a_dropped_quotation_still_costs_fidelity(self):
        """
        The hole the salvage opened, closed.

        A claim whose quotation was dropped is verified -- the statement stands
        -- but the model *misquoted*, and fidelity measures quoting accurately.
        Counting it as a match would score a model that quotes badly at 1.0,
        which is the same gaming this metric exists to prevent from the other
        side: it is measured over every statute claim so that a model which
        stops quoting to avoid being checked shows up as a drop. One that
        quotes wrongly has to show up too.
        """
        answer = StructuredAnswer(claims=[statute("words not in the section")])
        _, verdicts = verify(answer, context())

        assert verdicts[0].verified, "the statement stands"
        assert verdicts[0].quote_dropped, "but the quotation went"
        assert compute(answer, verdicts).verbatim_fidelity == 0.0
        assert compute(answer, verdicts).unsupported == 0
