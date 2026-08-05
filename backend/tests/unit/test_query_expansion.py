"""
Unit tests for query expansion.

The alias table is curated by hand, so a wrong entry silently misdirects
retrieval. These tests pin the behaviour that matters: expansion is additive,
matches on whole phrases only, and covers the cases it was built for.
"""
import re

import pytest

from services.query_expansion import (
    LEGAL_ALIASES,
    REPEALED_CODES,
    expand_query,
    expansion_report,
)


class TestTermsOfArt:
    """Phrases whose statutory wording differs from how lawyers say them."""

    def test_anticipatory_bail_gains_the_statutory_phrasing(self):
        """
        The case this module exists for. BNSS 482 governs anticipatory bail but
        never uses the phrase, so an embedding of the user's wording ranks
        BNSS 480 and 483 above it.
        """
        expanded = expand_query("what are the grounds for anticipatory bail")

        assert "grounds for anticipatory bail" in expanded
        assert "person apprehending arrest" in expanded

    def test_expansion_is_additive(self):
        """The user's own wording must survive — it is not a substitution."""
        expanded = expand_query("anticipatory bail")

        assert expanded.startswith("anticipatory bail")
        assert len(expanded) > len("anticipatory bail")

    @pytest.mark.parametrize(
        "query,expected_fragment",
        [
            ("dying declaration", "cannot be called as witness"),
            ("double jeopardy", "not to be tried for same offence"),
            ("plea bargaining", "mutually satisfactory disposition"),
            ("hostile witness", "cross-examination of own witness"),
            ("organised crime", "continuing unlawful activity"),
            ("default bail", "failure to complete investigation"),
        ],
    )
    def test_known_terms(self, query, expected_fragment):
        assert expected_fragment in expand_query(query)

    def test_longest_phrase_wins(self):
        """
        "culpable homicide not amounting to murder" must match as a whole rather
        than as the shorter phrases nested inside it.
        """
        expanded = expand_query("culpable homicide not amounting to murder")
        assert "punishment for culpable homicide not amounting to murder" in expanded


class TestRepealedCodes:
    """Practitioners still search by the pre-2023 names."""

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("IPC 302", "Bharatiya Nyaya Sanhita"),
            ("what does the Indian Penal Code say", "Bharatiya Nyaya Sanhita"),
            ("CrPC 438", "Bharatiya Nagarik Suraksha Sanhita"),
            ("cr.p.c provisions", "Bharatiya Nagarik Suraksha Sanhita"),
            ("Evidence Act section 65B", "Bharatiya Sakshya Adhiniyam"),
        ],
    )
    def test_old_code_names_map_to_the_new_codes(self, query, expected):
        assert expected in expand_query(query)


class TestBoundaries:
    """Matching has to be conservative or it fires on everything."""

    def test_fir_does_not_match_inside_other_words(self):
        """
        Without word boundaries, "fir" hits "first", "confirm", "firm" — which
        would append the FIR expansion to a large share of all queries.
        """
        for query in ["the first schedule", "confirm the order", "a firm offer"]:
            assert expand_query(query) == query, query

    def test_unrecognised_query_is_returned_unchanged(self):
        query = "what is the punishment for theft"
        assert expand_query(query) == query

    def test_expansion_is_not_repeated_when_already_present(self):
        """
        A query that already contains the statutory wording gains nothing;
        repeating it would only skew the embedding.
        """
        query = (
            "anticipatory bail direction for grant of bail to person "
            "apprehending arrest"
        )
        assert expand_query(query) == query

    def test_matching_is_case_insensitive(self):
        assert "person apprehending arrest" in expand_query("ANTICIPATORY BAIL")

    @pytest.mark.parametrize("query", ["", "   ", "\n"])
    def test_blank_queries_pass_through(self, query):
        assert expand_query(query) == query

    def test_multiple_terms_each_expand_once(self):
        expanded = expand_query("anticipatory bail and dying declaration under CrPC")

        assert "person apprehending arrest" in expanded
        assert "cannot be called as witness" in expanded
        assert "Bharatiya Nagarik Suraksha Sanhita" in expanded


class TestTableHygiene:
    """Guard rails on the curated tables themselves."""

    def test_keys_are_lowercase(self):
        """Lookup is case-insensitive; a capitalised key would be dead weight."""
        for table in (LEGAL_ALIASES, REPEALED_CODES):
            for key in table:
                assert key == key.lower(), key

    def test_every_expansion_adds_vocabulary(self):
        """
        An expansion has to contribute words the trigger phrase does not already
        supply, or it is doing nothing.

        Note this permits an expansion that *contains* its trigger — "culpable
        homicide not amounting to murder" expanding to "punishment for culpable
        homicide not amounting to murder" adds "punishment for", which is the
        wording the section heading actually uses.
        """
        for key, expansion in LEGAL_ALIASES.items():
            key_words = set(re.findall(r"\w+", key.lower()))
            expansion_words = set(re.findall(r"\w+", expansion.lower()))
            assert expansion_words - key_words, key

    def test_no_expansion_is_empty(self):
        for table in (LEGAL_ALIASES, REPEALED_CODES):
            for key, expansion in table.items():
                assert expansion.strip(), key

    def test_report_flags_whether_anything_changed(self):
        assert expansion_report("anticipatory bail")["changed"] is True
        assert expansion_report("punishment for theft")["changed"] is False
