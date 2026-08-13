"""
Unit tests for the claim verifier.

These are written as fabrications, because that is what the verifier is for.
Each test states a claim that a competent model might plausibly produce and
that is nevertheless wrong, and asserts that it does not survive: a section
that does not exist, a misquoted provision, a real case cited for a section it
never mentions, a false bailability, a contested question answered with one
side.

The last two are the ones worth dwelling on. A false "bailable" is the most
dangerous single value this system can emit, and it is only checkable at all
because the First Schedule was parsed into a table. A real case cited for the
wrong section is the subtlest failure in the set: the case is real, the section
is real, and only the edge between them shows the claim is not.
"""
import pytest

from models.claims import Claim, EpistemicClass, Position, StructuredAnswer
from services.claim_verifier import (
    VerificationContext,
    regeneration_feedback,
    verify,
    verify_claim,
)
from services.legal_graph import get_legal_graph

BNS_103_TEXT = (
    "Section 103 - Punishment for murder 103. (1) Whoever commits murder shall be "
    "punished with death or imprisonment for life, and shall also be liable to fine."
)


@pytest.fixture(scope="module")
def context():
    return VerificationContext(
        graph=get_legal_graph(), section_texts={"BNS 103": BNS_103_TEXT}
    )


def claim(**kwargs):
    kwargs.setdefault("text", "x")
    return Claim(**kwargs)


class TestStatuteClaims:
    def test_a_quoted_provision_that_matches_verifies(self, context):
        verified, _ = verify_claim(
            claim(
                epistemic_class=EpistemicClass.STATUTE,
                sources=["BNS 103"],
                verbatim_span="death or imprisonment for life",
            ),
            context,
        )
        assert verified

    def test_whitespace_and_case_are_not_differences_in_the_law(self, context):
        verified, _ = verify_claim(
            claim(
                epistemic_class=EpistemicClass.STATUTE,
                sources=["BNS 103"],
                verbatim_span="Death   or\nimprisonment for LIFE",
            ),
            context,
        )
        assert verified

    def test_a_misquoted_provision_fails(self, context):
        """A changed word is a changed provision."""
        verified, reason = verify_claim(
            claim(
                epistemic_class=EpistemicClass.STATUTE,
                sources=["BNS 103"],
                verbatim_span="death or imprisonment for seven years",
            ),
            context,
        )
        assert not verified
        assert "does not appear" in reason

    def test_a_section_that_does_not_exist_fails(self, context):
        verified, reason = verify_claim(
            claim(epistemic_class=EpistemicClass.STATUTE, sources=["BNS 999"]), context
        )
        assert not verified
        assert "not in the corpus" in reason

    def test_a_statute_claim_with_no_citation_fails(self, context):
        verified, reason = verify_claim(
            claim(epistemic_class=EpistemicClass.STATUTE), context
        )
        assert not verified
        assert "cites no section" in reason

    def test_a_paraphrase_is_allowed_but_not_checked(self, context):
        """Legitimate, and the metrics count it separately rather than
        crediting it as fidelity."""
        verified, _ = verify_claim(
            claim(epistemic_class=EpistemicClass.STATUTE, sources=["BNS 103"]), context
        )
        assert verified

    def test_a_quotation_from_a_section_not_retrieved_cannot_be_checked(self, context):
        verified, reason = verify_claim(
            claim(
                epistemic_class=EpistemicClass.STATUTE,
                sources=["BNSS 187"],
                verbatim_span="sixty days",
            ),
            context,
        )
        assert not verified
        assert "not retrieved this turn" in reason


class TestClassificationClaims:
    """
    Checkable only because the First Schedule was parsed into a table. Before
    that, "murder is bailable" was as verifiable as any other sentence.
    """

    def test_the_true_classification_verifies(self, context):
        verified, _ = verify_claim(
            claim(
                text="Murder is cognizable, non-bailable and triable by a Court of Session.",
                epistemic_class=EpistemicClass.CLASSIFICATION,
                sources=["BNS 103"],
            ),
            context,
        )
        assert verified

    def test_a_false_bailability_fails(self, context):
        verified, reason = verify_claim(
            claim(
                text="Murder is bailable.",
                epistemic_class=EpistemicClass.CLASSIFICATION,
                sources=["BNS 103"],
            ),
            context,
        )
        assert not verified
        assert "Non-bailable" in reason

    def test_prose_negation_is_read_as_negation(self, context):
        """"not bailable" must not register as asserting bailable, or a true
        claim is rejected for disagreeing with itself."""
        verified, _ = verify_claim(
            claim(
                text="Murder is not bailable.",
                epistemic_class=EpistemicClass.CLASSIFICATION,
                sources=["BNS 103"],
            ),
            context,
        )
        assert verified

    def test_a_wrong_court_fails(self, context):
        verified, reason = verify_claim(
            claim(
                text="Murder is triable by any Magistrate.",
                epistemic_class=EpistemicClass.CLASSIFICATION,
                sources=["BNS 103"],
            ),
            context,
        )
        assert not verified
        assert "Court of Session" in reason

    def test_classifying_a_section_with_no_schedule_row_fails(self, context):
        """BNSS is procedure; none of it is a punishable offence."""
        verified, reason = verify_claim(
            claim(
                text="It is cognizable.",
                epistemic_class=EpistemicClass.CLASSIFICATION,
                sources=["BNSS 187"],
            ),
            context,
        )
        assert not verified
        assert "no row in the First Schedule" in reason

    def test_a_classification_claim_that_classifies_nothing_fails(self, context):
        verified, reason = verify_claim(
            claim(
                text="Murder is a serious offence.",
                epistemic_class=EpistemicClass.CLASSIFICATION,
                sources=["BNS 103"],
            ),
            context,
        )
        assert not verified
        assert "states no classification" in reason


class TestHoldingAndInterpretation:
    def test_a_case_cited_for_a_section_it_construes_verifies(self, context):
        verified, _ = verify_claim(
            claim(
                epistemic_class=EpistemicClass.HOLDING,
                sources=["BNS 103", "sc_bachan_singh_v_state_of_punjab_1980"],
            ),
            context,
        )
        assert verified

    def test_a_real_case_cited_for_a_section_it_never_mentions_fails(self, context):
        """
        The subtlest failure in the set. Bachan Singh is real, BNSS 482 is
        real, and nothing but the edge between them shows the claim is not.
        """
        verified, reason = verify_claim(
            claim(
                text="Bachan Singh governs anticipatory bail.",
                epistemic_class=EpistemicClass.HOLDING,
                sources=["BNSS 482", "sc_bachan_singh_v_state_of_punjab_1980"],
            ),
            context,
        )
        assert not verified
        assert "not recorded as interpreting" in reason

    def test_an_invented_case_fails(self, context):
        verified, reason = verify_claim(
            claim(
                epistemic_class=EpistemicClass.HOLDING,
                sources=["sc_ramesh_kumar_v_state_of_nowhere_2019"],
            ),
            context,
        )
        assert not verified
        assert "not in the corpus" in reason

    def test_an_interpretation_naming_no_case_fails(self, context):
        """
        The classic route for an invented holding: the reading is plausible,
        the class is right, and nobody is named.
        """
        verified, reason = verify_claim(
            claim(
                text="Courts have read this as reserving death for the rarest of rare case.",
                epistemic_class=EpistemicClass.INTERPRETATION,
                sources=["BNS 103"],
            ),
            context,
        )
        assert not verified
        assert "names no judgement" in reason

    def test_a_live_result_is_accepted_on_existence_alone(self):
        """
        A judgement retrieved live this turn has no graph edges yet. It can be
        checked to exist and no further; the metrics keep its provenance
        separate rather than treating it as corpus.
        """
        context = VerificationContext(
            graph=get_legal_graph(), live_judgements={"sc_some_2026_decision"}
        )
        verified, _ = verify_claim(
            claim(
                epistemic_class=EpistemicClass.HOLDING,
                sources=["BNSS 482", "sc_some_2026_decision"],
            ),
            context,
        )
        assert verified


class TestContestedClaims:
    def positions(self, n):
        return [
            Position(summary=f"position {i}", authority=["sc_bachan_singh_v_state_of_punjab_1980"])
            for i in range(n)
        ]

    def test_two_attributed_positions_verify(self, context):
        verified, _ = verify_claim(
            claim(epistemic_class=EpistemicClass.CONTESTED, positions=self.positions(2)),
            context,
        )
        assert verified

    def test_one_position_fails_however_well_cited(self, context):
        """A contested question answered one-sidedly is a failure even when
        that side is impeccably cited."""
        verified, reason = verify_claim(
            claim(epistemic_class=EpistemicClass.CONTESTED, positions=self.positions(1)),
            context,
        )
        assert not verified
        assert "fewer than two positions" in reason

    def test_an_unattributed_position_fails(self, context):
        verified, reason = verify_claim(
            claim(
                epistemic_class=EpistemicClass.CONTESTED,
                positions=[*self.positions(1), Position(summary="the other view")],
            ),
            context,
        )
        assert not verified
        assert "cite no authority" in reason

    def test_an_invented_authority_fails(self, context):
        verified, reason = verify_claim(
            claim(
                epistemic_class=EpistemicClass.CONTESTED,
                positions=[
                    *self.positions(1),
                    Position(summary="other", authority=["sc_not_a_real_case_2020"]),
                ],
            ),
            context,
        )
        assert not verified
        assert "not in the corpus" in reason


class TestInferenceClaims:
    def test_reasoning_with_no_source_is_fine(self, context):
        verified, _ = verify_claim(
            claim(
                text="On 70 days of custody the delay argument is the strongest available.",
                epistemic_class=EpistemicClass.INFERENCE,
            ),
            context,
        )
        assert verified

    def test_reasoning_dressed_as_law_fails(self, context):
        """
        Correctly labelled in the data and indistinguishable from a provision
        on the page. The label does not help a reader who is reading the
        sentence.
        """
        verified, reason = verify_claim(
            claim(
                text="Under section 187(3) you are entitled to release.",
                epistemic_class=EpistemicClass.INFERENCE,
            ),
            context,
        )
        assert not verified
        assert "without a source" in reason

    def test_reasoning_that_cites_what_it_relies_on_is_fine(self, context):
        verified, _ = verify_claim(
            claim(
                text="Under section 187 the ninety-day limit is what matters here.",
                epistemic_class=EpistemicClass.INFERENCE,
                sources=["BNSS 187"],
            ),
            context,
        )
        assert verified


class TestVerifyAnswer:
    def answer(self):
        return StructuredAnswer(
            claims=[
                Claim(
                    text="Murder is punished with death or imprisonment for life.",
                    epistemic_class=EpistemicClass.STATUTE,
                    sources=["BNS 103"],
                    verbatim_span="death or imprisonment for life",
                ),
                Claim(
                    text="Murder is bailable.",
                    epistemic_class=EpistemicClass.CLASSIFICATION,
                    sources=["BNS 103"],
                ),
            ]
        )

    def test_failures_are_reclassified_rather_than_deleted(self):
        """Still present after verification so the trace can report what was
        removed and why."""
        verified, verdicts = verify(self.answer(), VerificationContext(get_legal_graph()))
        assert len(verified.claims) == 2
        assert verified.claims[1].epistemic_class is EpistemicClass.UNSUPPORTED
        assert verdicts[1].reclassified_to is EpistemicClass.UNSUPPORTED

    def test_a_failed_claim_does_not_reach_the_reader(self):
        verified, _ = verify(self.answer(), VerificationContext(get_legal_graph()))
        assert "bailable" not in verified.without_unsupported().render()

    def test_verdicts_line_up_with_claims(self):
        _, verdicts = verify(self.answer(), VerificationContext(get_legal_graph()))
        assert [v.index for v in verdicts] == [0, 1]

    def test_an_empty_answer_verifies_vacuously(self):
        verified, verdicts = verify(StructuredAnswer(), VerificationContext(get_legal_graph()))
        assert verified.claims == []
        assert verdicts == []


class TestRegenerationFeedback:
    def test_the_offending_claims_are_named_with_their_reasons(self):
        answer = StructuredAnswer(
            claims=[
                Claim(
                    text="Murder is bailable.",
                    epistemic_class=EpistemicClass.CLASSIFICATION,
                    sources=["BNS 103"],
                )
            ]
        )
        _, verdicts = verify(answer, VerificationContext(get_legal_graph()))
        feedback = regeneration_feedback(answer, verdicts)
        assert "Murder is bailable." in feedback
        assert "Non-bailable" in feedback

    def test_the_model_is_told_not_to_hedge_instead_of_fixing(self):
        answer = StructuredAnswer(
            claims=[Claim(text="x", epistemic_class=EpistemicClass.STATUTE)]
        )
        _, verdicts = verify(answer, VerificationContext(get_legal_graph()))
        assert "more cautiously" in regeneration_feedback(answer, verdicts)

    def test_nothing_to_say_when_everything_verified(self):
        answer = StructuredAnswer(
            claims=[Claim(text="x", epistemic_class=EpistemicClass.INFERENCE)]
        )
        _, verdicts = verify(answer, VerificationContext(get_legal_graph()))
        assert regeneration_feedback(answer, verdicts) == ""


class TestVerificationContextFromRetrieval:
    def test_section_text_is_reassembled_from_its_chunks(self):
        """A section arrives in pieces; a span from the tail must not look
        fabricated because only the head was kept."""
        context = VerificationContext.from_retrieval({
            "documents": ["Whoever commits murder", "shall be punished with death"],
            "metadatas": [
                {"short_name": "BNS", "section_number": "103"},
                {"short_name": "BNS", "section_number": "103"},
            ],
        })
        assert "murder shall be punished" in context.section_texts["BNS 103"]

    def test_judgement_chunks_contribute_no_section_text(self):
        context = VerificationContext.from_retrieval({
            "documents": ["The rarest of rare test..."],
            "metadatas": [{"case_name": "Bachan Singh v. State of Punjab"}],
        })
        assert context.section_texts == {}

    def test_no_retrieval_is_an_empty_context(self):
        assert VerificationContext.from_retrieval().section_texts == {}
