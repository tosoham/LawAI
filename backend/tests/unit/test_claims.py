"""
Unit tests for the typed claim model.

The model's job is to make the difference between "the section says X" and "I
think X" survive all the way to the reader. Most of these tests are about that
difference not leaking: an inference must not render as law, an unsupported
claim must not render at all, and a source must be classified by what it
actually points at rather than by what the model called it.
"""
import pytest

from models.claims import (
    Claim,
    ClaimSource,
    EpistemicClass,
    Position,
    SourceKind,
    StructuredAnswer,
    classify_source,
    looks_like_law,
)


class TestClassifySource:
    @pytest.mark.parametrize(
        "ref,kind",
        [
            ("BNS 103", SourceKind.SECTION),
            ("BNSS 482", SourceKind.SECTION),
            ("BSA 63", SourceKind.SECTION),
            ("sc_bachan_singh_v_state_of_punjab_1980", SourceKind.JUDGEMENT),
            ("https://indiankanoon.org/doc/1234/", SourceKind.LIVE),
            ("rarest_of_rare", SourceKind.DOCTRINE),
            ("Bachan Singh v. State of Punjab", SourceKind.UNKNOWN),
            ("", SourceKind.UNKNOWN),
        ],
    )
    def test_kind_comes_from_the_shape(self, ref, kind):
        assert classify_source(ref) is kind

    def test_synthesis_may_emit_bare_strings(self):
        """Asking a model to tag the kind as well is one more thing to get
        wrong, and the kind is recoverable."""
        claim = Claim(
            text="x",
            epistemic_class=EpistemicClass.STATUTE,
            sources=["BNS 103", "sc_bachan_singh_v_state_of_punjab_1980"],
        )
        assert [s.kind for s in claim.sources] == [SourceKind.SECTION, SourceKind.JUDGEMENT]

    def test_a_typed_source_survives_unchanged(self):
        source = ClaimSource(ref="BNS 103", kind=SourceKind.SECTION)
        claim = Claim(text="x", epistemic_class=EpistemicClass.STATUTE, sources=[source])
        assert claim.sources[0] is source


class TestLooksLikeLaw:
    @pytest.mark.parametrize(
        "text",
        [
            "under section 187(3)",
            "section 41A of the old code",
            "sections 173 and 175",
            "BNSS 482 applies here",
            "Section 103 provides",
        ],
    )
    def test_citations_are_recognised(self, text):
        assert looks_like_law(text)

    @pytest.mark.parametrize(
        "text",
        ["the argument is strong", "7 years imprisonment", "he was held 70 days"],
    )
    def test_ordinary_prose_is_not(self, text):
        assert not looks_like_law(text)


class TestEpistemicClass:
    def test_inference_is_the_one_class_that_needs_no_source(self):
        """
        Applying law to facts is exactly the case where there is nothing to
        cite. Demanding a citation would push the model into inventing
        authority for its own reasoning.
        """
        assert not EpistemicClass.INFERENCE.requires_source
        for other in (
            EpistemicClass.STATUTE,
            EpistemicClass.CLASSIFICATION,
            EpistemicClass.HOLDING,
            EpistemicClass.INTERPRETATION,
            EpistemicClass.CONTESTED,
        ):
            assert other.requires_source

    def test_only_the_four_law_classes_may_be_read_as_law(self):
        law = {c for c in EpistemicClass if c.is_law}
        assert law == {
            EpistemicClass.STATUTE,
            EpistemicClass.CLASSIFICATION,
            EpistemicClass.HOLDING,
            EpistemicClass.INTERPRETATION,
        }

    def test_inference_and_contested_are_not_law(self):
        assert not EpistemicClass.INFERENCE.is_law
        assert not EpistemicClass.CONTESTED.is_law


class TestPosition:
    def test_a_position_without_authority_is_unattributed(self):
        assert not Position(summary="it is unconstitutional").is_attributed
        assert Position(summary="x", authority=["sc_a_v_b_2000"]).is_attributed


class TestRendering:
    def statute(self, text="Murder is punished with death or imprisonment for life."):
        return Claim(text=text, epistemic_class=EpistemicClass.STATUTE, sources=["BNS 103"])

    def test_law_claims_read_as_continuous_prose(self):
        answer = StructuredAnswer(claims=[self.statute(), self.statute("It is cognizable.")])
        assert answer.render() == (
            "Murder is punished with death or imprisonment for life. It is cognizable."
        )

    def test_inference_is_set_apart_and_labelled(self):
        """
        A structured client renders the classes itself. The heading exists for
        the clients that do not -- an export, a copy-paste, a log -- so the
        model's reasoning still cannot be read as a provision.
        """
        answer = StructuredAnswer(
            claims=[
                self.statute(),
                Claim(text="Life is likelier here.", epistemic_class=EpistemicClass.INFERENCE),
            ]
        )
        rendered = answer.render()
        assert "reasoning, not law" in rendered
        assert rendered.index("Applying this to the facts") > rendered.index("Murder is punished")

    def test_a_contested_claim_renders_both_positions(self):
        answer = StructuredAnswer(
            claims=[
                Claim(
                    text="The twin conditions are contested.",
                    epistemic_class=EpistemicClass.CONTESTED,
                    sources=["BNSS 480"],
                    positions=[
                        Position(summary="Struck down", authority=["sc_nikesh_2017"]),
                        Position(summary="Upheld as amended", authority=["sc_vijay_2022"]),
                    ],
                )
            ]
        )
        rendered = answer.render()
        assert "Struck down" in rendered
        assert "Upheld as amended" in rendered
        assert "The authorities differ" in rendered

    def test_an_abstention_renders_only_its_reason(self):
        answer = StructuredAnswer(
            claims=[self.statute()],
            abstained=True,
            abstention_reason="The corpus does not cover this.",
        )
        assert answer.render() == "The corpus does not cover this."


class TestRemovingUnsupported:
    def test_unsupported_claims_are_dropped_not_hedged(self):
        """
        "It appears that section 999 provides..." still puts the section number
        in front of the reader, and hedged text is what people skim past.
        """
        answer = StructuredAnswer(
            claims=[
                Claim(text="real", epistemic_class=EpistemicClass.STATUTE, sources=["BNS 103"]),
                Claim(text="invented", epistemic_class=EpistemicClass.UNSUPPORTED),
            ]
        )
        cleaned = answer.without_unsupported()
        assert [c.text for c in cleaned.claims] == ["real"]
        assert "invented" not in cleaned.render()

    def test_the_original_answer_is_left_intact(self):
        """The trace has to be able to report what was removed."""
        answer = StructuredAnswer(
            claims=[Claim(text="invented", epistemic_class=EpistemicClass.UNSUPPORTED)]
        )
        answer.without_unsupported()
        assert len(answer.claims) == 1

    def test_abstention_survives_removal(self):
        answer = StructuredAnswer(claims=[], abstained=True, abstention_reason="no")
        assert answer.without_unsupported().abstained
