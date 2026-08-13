"""
Unit tests for the repealed-code concordance and the script that builds it.

The concordance is the one piece of data here that is *asserted* by a third
party rather than parsed from enacted text, so the tests are about the two
things that can go wrong with it: the extraction slipping a row, and the file
drifting out of step with the corpus it points into.

The strongest check lives in the script itself -- the whole extraction is
compared against a second, independently typeset table from the same publisher
and the run fails if they disagree. What is tested here is the parsing that
feeds it, and the shape of the file that came out.
"""
import json
import re

import pytest

from tests.unit.test_ingestion import _load_script

ingest_concordance = _load_script("ingest_concordance")

CONCORDANCE = json.loads(
    (
        __import__("pathlib").Path(__file__).resolve().parents[3]
        / "data" / "processed" / "repealed_concordance.json"
    ).read_text()
)


class TestOldSections:
    def test_a_single_number(self):
        assert ingest_concordance.old_sections("302") == ["302"]

    def test_a_letter_suffix_is_part_of_the_number(self):
        """IPC 498A is not IPC 498, and they map to different BNS sections."""
        assert ingest_concordance.old_sections("498A") == ["498A"]

    def test_a_consolidated_list_yields_every_section(self):
        """One new section often absorbed several old ones, and a user
        searching any of them needs the answer."""
        assert ingest_concordance.old_sections("29 and 29A") == ["29", "29A"]
        assert ingest_concordance.old_sections("453/460") == ["453", "460"]

    @pytest.mark.parametrize(
        "cell,expected",
        [
            ("3, para 1", ["3"]),
            ("23\nClause-2", ["23"]),
            ("498A\nExplanation", ["498A"]),
            ("IEA 3\nInterpretation clause", ["3"]),
        ],
    )
    def test_a_paragraph_number_is_not_a_section_number(self, cell, expected):
        """
        The bug this was written for. "3, para 1" yielded sections 3 and 1, so
        IPC 1, 2 and 3 -- which are about the extent of the Code -- were mapped
        onto the BNS definitions clause, because they are paragraph numbers of
        IPC 23.
        """
        assert ingest_concordance.old_sections(cell) == expected

    @pytest.mark.parametrize("cell", ["-", "New", "Newly added", "Nil", "omitted", ""])
    def test_a_provision_with_no_counterpart_yields_nothing(self, cell):
        assert ingest_concordance.old_sections(cell) == []


class TestNormaliseRow:
    def test_a_four_column_row_passes_through(self):
        assert ingest_concordance.normalise_row(["1", "Subject", "2", "Summary"]) == [
            "1", "Subject", "2", "Summary"
        ]

    def test_extra_rule_lines_are_collapsed(self):
        """The BNS table carries two spare separators on some pages."""
        assert ingest_concordance.normalise_row(
            ["1(1)", "", "", "Short title", "1", "Summary"]
        ) == ["1(1)", "Short title", "1", "Summary"]

    def test_a_row_that_does_not_reduce_to_four_is_rejected(self):
        """Guessing at a row this parser does not understand is how a
        concordance acquires a mapping nobody wrote."""
        assert ingest_concordance.normalise_row(["a", "b", "c"]) is None
        assert ingest_concordance.normalise_row(["a", "b", "c", "d", "e"]) is None


class TestSubjectMatchesTitle:
    def test_identical_subjects_agree_fully(self):
        assert ingest_concordance.subject_matches_title("Murder.", "Punishment for murder") == 1.0

    def test_unrelated_text_does_not(self):
        assert ingest_concordance.subject_matches_title("Murder.", "Definitions") == 0.0

    def test_it_is_asymmetric_by_design(self):
        """The table abbreviates where the gazette's marginal note is fuller,
        so requiring either to contain the other would reject good rows."""
        score = ingest_concordance.subject_matches_title(
            "Theft.", "Theft in a dwelling house, or means of transportation"
        )
        assert score == 1.0


class TestCrossCheck:
    """
    The check that actually guards the extraction: a second table, typeset
    independently, from the same publisher.
    """

    def rows(self, pairs):
        return [
            {"old_act": "IPC", "old_section": old, "new_section": new} for old, new in pairs
        ]

    def test_agreement_is_reported(self):
        result = ingest_concordance.cross_check(
            self.rows([("302", "103"), ("420", "318")]), {"302": "103", "420": "318"}
        )
        assert result == {"compared": 2, "agreed": 2, "disagreements": []}

    def test_a_slipped_row_shows_up(self):
        result = ingest_concordance.cross_check(
            self.rows([("302", "104")]), {"302": "103"}
        )
        assert result["agreed"] == 0
        assert result["disagreements"] == [("302", ["104"], "103")]

    def test_one_provision_answered_by_several_is_agreement_not_conflict(self):
        """
        IPC 376 is answered by BNS 64 and BNS 65 alike, so the chart naming one
        of them agrees. Comparing single values called this a disagreement and
        it is not.
        """
        result = ingest_concordance.cross_check(
            self.rows([("376", "64"), ("376", "65")]), {"376": "64"}
        )
        assert result["disagreements"] == []

    def test_sections_the_chart_does_not_cover_are_not_counted(self):
        result = ingest_concordance.cross_check(self.rows([("302", "103")]), {})
        assert result["compared"] == 0


class TestTheCommittedFile:
    """Invariants over the 1,195 mappings nobody read individually."""

    SECTION = re.compile(r"^\d{1,3}[A-Z]{0,2}$")

    def test_all_three_repealed_codes_are_covered(self):
        assert {r["old_act"] for r in CONCORDANCE} == {"IPC", "CrPC", "Evidence Act"}

    def test_every_mapping_stays_within_its_own_pair_of_acts(self):
        """IPC maps into the BNS, never into the BNSS."""
        pairs = {(r["old_act"], r["new_act"]) for r in CONCORDANCE}
        assert pairs == {("IPC", "BNS"), ("CrPC", "BNSS"), ("Evidence Act", "BSA")}

    def test_every_section_number_is_well_formed(self):
        bad = [
            (r["old_section"], r["new_section"])
            for r in CONCORDANCE
            if not self.SECTION.match(r["old_section"]) or not r["new_section"].isdigit()
        ]
        assert not bad

    def test_every_target_exists_in_the_corpus(self):
        """A mapping into a section we do not hold is a dead end."""
        from services.legal_graph import get_legal_graph

        graph = get_legal_graph()
        missing = {
            f"{r['new_act']} {r['new_section']}"
            for r in CONCORDANCE
            if not graph.has_section(f"{r['new_act']} {r['new_section']}")
        }
        assert not missing

    def test_every_row_carries_its_provenance(self):
        """This is a third-party assertion, and has to be visibly one."""
        for record in CONCORDANCE:
            assert "Bureau of Police Research" in record["source"]
            assert record["source_url"].startswith("https://bprd.nic.in/")

    @pytest.mark.parametrize(
        "old_act,old_section,expected",
        [
            ("IPC", "302", {"103"}),
            ("IPC", "420", {"318"}),
            ("IPC", "379", {"303"}),
            ("IPC", "498A", {"85", "86"}),
            ("CrPC", "438", {"482"}),
            ("CrPC", "482", {"528"}),
            ("CrPC", "154", {"173"}),
            ("Evidence Act", "65B", {"63"}),
            ("Evidence Act", "32", {"26"}),
        ],
    )
    def test_the_mappings_a_practitioner_would_check_first(
        self, old_act, old_section, expected
    ):
        found = {
            r["new_section"]
            for r in CONCORDANCE
            if r["old_act"] == old_act and r["old_section"] == old_section
        }
        assert expected <= found

    def test_the_paragraph_bug_has_not_returned(self):
        """
        IPC 1, 2 and 3 are about the extent of the Code and have nothing to do
        with the BNS definitions clause. They appeared there when paragraph
        numbers were read as section numbers.
        """
        bogus = [
            r
            for r in CONCORDANCE
            if r["old_act"] == "IPC" and r["old_section"] in {"1", "2", "3"}
            and r["new_section"] == "2"
        ]
        assert not bogus
