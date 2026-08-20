"""
Resolving a passage to the offence it is about.

Run against the committed First Schedule, not a fixture. The whole point of
this layer is that the Schedule names every offence in a column of its own, so
a stubbed table would test the matching and none of the thing that makes the
matching trustworthy.

Two failure directions, and both have happened:

* a claim about one offence cited to another and *passing*, because the two
  carry the same attributes (theft cited to BNS 304, snatching);
* a correctly cited claim *rejected*, because the offence's own Schedule row
  was too long to index and a shorter offence name matched inside it (culpable
  homicide not amounting to murder resolving to BNS 103, murder).

The second is the cheaper of the two and still fatal: a system that deletes
true statements from its answers stops being used.
"""
import pytest

from services.retrieval.offence_lookup import (
    _phrase,
    find_offences,
    is_classification_question,
    is_offence_question,
    match_offences,
)


class TestPhrase:
    def test_a_short_name_is_used_as_is(self):
        assert _phrase("Murder.") == "murder"

    def test_trailing_punctuation_goes(self):
        assert _phrase("Theft.") == "theft"

    def test_a_conditional_variant_is_refused(self):
        """"If offence be not committed" describes a case, not an offence, and
        would match on its stopwords."""
        assert _phrase("If offence be not committed.") is None

    def test_an_other_case_row_is_refused(self):
        assert _phrase("In any other case.") is None

    def test_a_long_name_falls_back_to_its_head(self):
        """
        The Schedule states many offences as "<name>, if <condition>". The head
        is the offence; the tail is the case it applies to.
        """
        assert (
            _phrase(
                "Culpable homicide not amounting to murder, if act by which the "
                "death is caused is done with the intention of causing death."
            )
            == "culpable homicide not amounting to murder"
        )

    def test_a_long_name_with_no_qualifier_is_still_refused(self):
        """Only a comma-qualifier separates a name from a case. Truncating an
        arbitrary long row at six words would invent a phrase the Schedule
        never uses."""
        assert (
            _phrase(
                "Abetment of any offence punishable with imprisonment for a term "
                "which may extend to seven years and no express provision"
            )
            is None
        )

    def test_a_head_that_is_still_too_long_is_refused(self):
        assert (
            _phrase(
                "Doing something with intent to cause harm to another person, if "
                "the act is committed at night."
            )
            is None
        )


class TestMatchOffences:
    @pytest.mark.parametrize(
        ("passage", "expected"),
        [
            ("Murder is non-bailable.", "BNS 103"),
            ("Theft is non-bailable.", "BNS 303"),
            ("Snatching is cognizable and non-bailable.", "BNS 304"),
        ],
    )
    def test_a_named_offence_resolves_to_its_own_section(self, passage, expected):
        assert match_offences(passage) == [expected]

    def test_a_nested_shorter_name_is_not_reported(self):
        """
        The regression this file exists for.

        "murder" is a substring of "culpable homicide not amounting to murder",
        so a passage about BNS 105 also matches BNS 103. Reported as-is, the
        verifier concluded the claim named an offence the Schedule keys to BNS
        103 while citing BNS 105, and deleted a correct claim from the answer.
        """
        matched = match_offences(
            "Culpable homicide not amounting to murder is cognizable, "
            "non-bailable, and triable by a Court of Session."
        )
        assert matched == ["BNS 105"]

    def test_theft_and_snatching_stay_distinct(self):
        """
        Suppressing nested matches must not suppress *related* ones. BNS 304
        opens "Theft is snatching if...", which is exactly the confusion the
        binding was introduced to prevent, and the two names do not nest.
        """
        assert match_offences("Theft is non-bailable.") == ["BNS 303"]
        assert match_offences("Snatching is non-bailable.") == ["BNS 304"]

    def test_two_offences_in_one_passage_both_resolve(self):
        matched = match_offences("Both theft and extortion are cognizable.")
        assert "BNS 303" in matched
        assert "BNS 308" in matched

    def test_a_passage_naming_no_offence_resolves_to_nothing(self):
        assert match_offences("The weather today is pleasant.") == []


class TestQuestionShape:
    @pytest.mark.parametrize(
        "query",
        [
            "is murder bailable",
            "is theft cognizable",
            "which court tries murder",
            "can they arrest without a warrant",
        ],
    )
    def test_classification_vocabulary_is_recognised(self, query):
        assert is_classification_question(query)

    def test_prose_about_an_offence_is_not_a_classification_question(self):
        assert not is_classification_question("what happened in the murder case")

    def test_a_punishment_question_is_an_offence_question(self):
        """Not a classification question, but still one the offence column
        answers exactly: "what is the punishment for theft" ranked BNS 305 and
        304 above BNS 303."""
        assert is_offence_question("what is the punishment for theft")
        assert not is_classification_question("what is the punishment for theft")


class TestFindOffences:
    def test_a_classification_question_resolves(self):
        assert find_offences("is murder bailable") == ["BNS 103"]

    def test_a_question_about_no_offence_resolves_to_nothing(self):
        assert find_offences("is the sky blue") == []

    def test_a_generic_phrase_is_too_broad_to_be_a_lookup(self):
        """More than a handful of matches means this was a search, not a
        lookup, and injecting the whole table would crowd out what was asked."""
        assert find_offences("what is the punishment for any offence") == []
