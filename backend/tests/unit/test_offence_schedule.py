"""
Unit tests for the BNSS First Schedule parser and the table it produces.

The classification table is the one place in this system where a parsing slip
becomes a directly actionable falsehood: telling someone an offence is bailable
when it is not is worse than any retrieval miss, because it reads as a fact
rather than as a search result. So this file does two separate jobs.

``TestHandVerifiedOffences`` pins offences transcribed by eye from the gazette
PDF. It is the gate: if the parser starts mis-assigning columns, these fail.

The invariant tests then cover the 443 rows nobody transcribed, by asserting
things that must hold for every row -- classification cells drawn only from the
schedule's own vocabulary, court cells naming a court, no punishment text
leaking sideways. Cross-column bleed is the parser's characteristic failure and
it cannot hide from those.
"""
import json
import re
from pathlib import Path
from typing import ClassVar

import pytest

from tests.unit.test_ingestion import _load_script

ingest_offence_schedule = _load_script("ingest_offence_schedule")

PROCESSED_DIR = Path(__file__).resolve().parents[3] / "data" / "processed"
TABLE_PATH = PROCESSED_DIR / "offence_classification.json"


def word(text, x0, x1=None, top=100.0):
    """A minimal pdfplumber word."""
    return {"text": text, "x0": x0, "x1": x1 if x1 is not None else x0 + 20, "top": top}


class TestColumnIndex:
    ANCHORS = (58.0, 94.0, 193.0, 285.0, 369.0, 453.0)

    def test_word_on_an_anchor_is_in_that_column(self):
        assert ingest_offence_schedule.column_index(285.0, self.ANCHORS) == 3

    def test_word_just_left_of_an_anchor_still_reaches_it(self):
        """Column 3 starts at 192 on some pages and 193 on others."""
        assert ingest_offence_schedule.column_index(191.5, self.ANCHORS) == 2

    def test_the_tolerance_is_narrow_enough_to_need_runs(self):
        """
        Wrapped column-4 text reaches x0=367, which this function alone would
        read as column 5. That is why it is only ever asked about the leading
        word of a run -- see TestSplitIntoRuns for the protection that matters.
        """
        assert ingest_offence_schedule.column_index(367.0, self.ANCHORS) == 4
        assert ingest_offence_schedule.column_index(366.0, self.ANCHORS) == 3


class TestSplitIntoRuns:
    ANCHORS = (58.0, 94.0, 193.0, 285.0, 369.0, 453.0)

    def runs(self, words):
        return [
            [w["text"] for w in run]
            for run in ingest_offence_schedule.split_into_runs(words, self.ANCHORS)
        ]

    def test_words_a_space_apart_stay_together(self):
        line = [word("Simple", 193.0, 220.0), word("imprisonment", 223.3, 270.0)]
        assert self.runs(line) == [["Simple", "imprisonment"]]

    def test_a_column_one_space_away_still_breaks(self):
        """"...7 years" ends at 283 and "According" starts at 286."""
        line = [word("years", 264.0, 283.0), word("According", 286.0, 318.0)]
        assert self.runs(line) == [["years"], ["According"]]

    def test_a_wide_section_number_does_not_swallow_the_offence(self):
        """"111(2)(a)" ends at 92 and pushes "Organised" to 97, off its anchor."""
        line = [word("111(2)(a)", 57.6, 92.0), word("Organised", 97.0, 130.0)]
        assert self.runs(line) == [["111(2)(a)"], ["Organised"]]

    def test_wrapped_text_reaching_towards_the_next_column_does_not_break(self):
        """A run must not split where only wrapped prose is drifting right."""
        line = [
            word("person", 295.0, 317.0),
            word("aggrieved", 320.4, 352.0),
            word("by", 355.3, 363.0),
            word("the", 366.3, 378.0),
        ]
        assert self.runs(line) == [["person", "aggrieved", "by", "the"]]


class TestModalX0:
    def test_nearby_values_are_one_edge(self):
        assert ingest_offence_schedule.modal_x0([285.0, 285.6, 286.1, 285.2]) == 285.0

    def test_too_few_agreeing_words_is_no_evidence(self):
        assert ingest_offence_schedule.modal_x0([285.0, 400.0]) is None

    def test_empty(self):
        assert ingest_offence_schedule.modal_x0([]) is None


class TestDetectAnchors:
    def test_a_page_is_measured_from_its_own_columns(self):
        """
        Columns 4 and 5 move by up to 19pt between pages, so they must be read
        off the page rather than assumed.
        """
        lines = []
        for i in range(5):
            lines.append((100.0 + i, [
                word("103", 58.0, 72.0),
                word("Murder.", 94.0, 130.0),
                word("Imprisonment", 193.0, 240.0),
                word("Cognizable.", 304.0, 344.0),
                word("Non-bailable.", 385.0, 430.0),
                word("Court", 466.0, 484.0),
            ]))
        anchors = ingest_offence_schedule.detect_anchors(lines, page_number=1)
        assert anchors == (58.0, 94.0, 193.0, 304.0, 385.0, 466.0)

    def test_deferred_classifications_place_both_columns(self):
        """Abetment pages say "According as..." in columns 4 and 5 alike."""
        lines = []
        for i in range(5):
            lines.append((100.0 + i, [
                word("49", 58.0, 68.0),
                word("Abetment", 94.0, 130.0),
                word("Same", 193.0, 210.0),
                word("According", 286.0, 318.0),
                word("According", 370.0, 402.0),
                word("Court", 453.0, 471.0),
            ]))
        anchors = ingest_offence_schedule.detect_anchors(lines, page_number=1)
        assert anchors[3] == 286.0
        assert anchors[4] == 370.0

    def test_implausible_edges_fall_back_rather_than_shredding_the_page(self, caplog):
        lines = [(100.0, [word("x", 58.0), word("y", 60.0)])]
        anchors = ingest_offence_schedule.detect_anchors(lines, page_number=1)
        assert anchors == ingest_offence_schedule.DEFAULT_ANCHORS


class TestStartsARow:
    def row(self, **cells):
        r = ingest_offence_schedule.Row(page=1)
        for column, value in cells.items():
            r.add(column, value)
        return r

    def test_the_first_line_opens_a_row(self):
        assert ingest_offence_schedule.starts_a_row({"section": "103"}, None)

    def test_a_second_section_number_opens_a_row(self):
        current = self.row(section="70(2)", cognizable="Cognizable.")
        assert ingest_offence_schedule.starts_a_row({"section": "71"}, current)

    def test_a_second_classification_opens_a_row_without_a_section_number(self):
        """
        BNS 356(2) is classified twice and the second row's column 1 is blank.
        Keying on the section number would report the wrong court for it.
        """
        current = self.row(section="356(2)", cognizable="Non-cognizable.")
        cells = {"offence": "Defamation in any other case.", "cognizable": "Non-cognizable."}
        assert ingest_offence_schedule.starts_a_row(cells, current)

    def test_wrapped_classification_text_does_not_open_a_row(self):
        current = self.row(section="49", cognizable="According as offence")
        cells = {"cognizable": "abetted is cognizable", "bailable": "abetted is bailable"}
        assert not ingest_offence_schedule.starts_a_row(cells, current)

    def test_a_classification_typeset_below_its_section_joins_that_row(self):
        """BNS 264 sets its section number a line above its classification."""
        current = self.row(section="264", offence="Omission to apprehend, or")
        cells = {"cognizable": "Non-cognizable.", "bailable": "Bailable."}
        assert not ingest_offence_schedule.starts_a_row(cells, current)


class TestNormaliseSection:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("103", "103"),
            ("103(1)", "103(1)"),
            ("58 (a)", "58(a)"),
            ("111(2)(a)", "111(2)(a)"),
            ("356(3)", "356(3)"),
        ],
    )
    def test_accepted(self, raw, expected):
        assert ingest_offence_schedule.normalise_section(raw) == expected

    @pytest.mark.parametrize("raw", ["61(2)(a) Criminal", "70(2) 71", "Murder", ""])
    def test_rejected(self, raw):
        """A cell holding anything but a section number is a parse failure."""
        assert ingest_offence_schedule.normalise_section(raw) is None


class TestClassify:
    def test_plain_values(self):
        c = ingest_offence_schedule.COGNIZABLE_VALUES
        assert ingest_offence_schedule.classify("Cognizable.", c) is True
        assert ingest_offence_schedule.classify("Non-cognizable.", c) is False
        assert ingest_offence_schedule.classify("Non-cognizable", c) is False

    def test_a_conditional_cell_is_left_unresolved(self):
        """
        "According as offence abetted is cognizable or non-cognizable" is not a
        classification, and guessing one would be the worst failure this table
        could have.
        """
        value = "According as offence abetted is cognizable or non-cognizable."
        assert ingest_offence_schedule.classify(value, ingest_offence_schedule.COGNIZABLE_VALUES) is None
        value = "Cognizable if information relating to the commission is given."
        assert ingest_offence_schedule.classify(value, ingest_offence_schedule.COGNIZABLE_VALUES) is None


@pytest.fixture(scope="module")
def table():
    return json.loads(TABLE_PATH.read_text())


@pytest.fixture(scope="module")
def by_id(table):
    return {record["id"]: record for record in table}


class TestHandVerifiedOffences:
    """
    Transcribed by eye from the gazette PDF, pages 159-189.

    This is the gate the plan calls for. A wrong "bailable" here is the most
    dangerous single value this system can emit, so these are read off the
    source rather than off the parser's own output.
    """

    EXPECTED: ClassVar = [
        # id, offence opening, cognizable, bailable, triable by
        ("bns_64(1)", "Rape.", True, False, "Court of Session."),
        ("bns_69", "Sexual intercourse by", True, False, "Court of Session."),
        ("bns_70(1)", "Gang rape.", True, False, "Court of Session."),
        ("bns_80(2)", "Dowry death.", True, False, "Court of Session."),
        ("bns_103(1)", "Murder.", True, False, "Court of Session."),
        ("bns_105", "Culpable homicide not", True, False, "Court of Session."),
        ("bns_106(1)", "Causing death by", True, True, "Magistrate of the first class."),
        ("bns_111(2)(a)", "Organised crime resulting", True, False, "Court of Session."),
        ("bns_115(2)", "Voluntarily causing hurt.", False, True, "Any Magistrate."),
        ("bns_117(2)", "Voluntarily causing grievous", True, True, "Any Magistrate."),
        ("bns_137(2)", "Kidnapping.", True, True, "Magistrate of the first class."),
        ("bns_140(1)", "Kidnapping or abducting in", True, False, "Court of Session."),
        ("bns_152", "Act endangering sovereignty,", True, False, "Court of Session."),
        ("bns_189(2)", "Being member of an", True, True, "Any Magistrate."),
        ("bns_303(2)", "Theft.", True, False, "Any Magistrate."),
        ("bns_310(2)", "Dacoity.", True, False, "Court of Session."),
        ("bns_316(2)", "Criminal breach of trust.", True, False, "Magistrate of the first class."),
        ("bns_318(4)", "Cheating and dishonestly", True, False, "Magistrate of the first class."),
        ("bns_351(2)", "Criminal intimidation.", False, True, "Any Magistrate."),
        ("bns_356(2)", "Defamation against the", False, True, "Court of Session."),
        ("bns_357", "Being bound to attend on", False, True, "Any Magistrate."),
    ]

    @pytest.mark.parametrize("record_id,offence,cognizable,bailable,court", EXPECTED)
    def test_matches_the_gazette(self, by_id, record_id, offence, cognizable, bailable, court):
        record = by_id.get(record_id)
        assert record is not None, f"{record_id} missing from the table"
        assert record["offence"].startswith(offence)
        assert record["cognizable"] is cognizable
        assert record["bailable"] is bailable
        assert record["triable_by"] == court

    def test_a_twice_classified_section_keeps_both_courts(self, by_id):
        """
        BNS 356(2) is a Court of Session matter when the President is defamed
        and a Magistrate's matter otherwise. Merging the two rows would report
        the wrong court for one of them.
        """
        assert by_id["bns_356(2)"]["triable_by"] == "Court of Session."
        variant = by_id["bns_356(2)_v1"]
        assert variant["offence"] == "Defamation in any other case."
        assert variant["triable_by"] == "Magistrate of the first class."
        assert variant["section"] == "356(2)"


class TestTableInvariants:
    """What must hold for all 465 rows, including the ones nobody transcribed."""

    SECTION = re.compile(r"^\d{1,3}(\(\w{1,3}\))*$")
    # Lower case because a few rows defer ("The court by which the offence
    # attempted is triable") rather than naming a court outright.
    COURT = re.compile(r"\b(court|magistrate|sessions?)\b", re.IGNORECASE)

    def test_the_table_is_not_short(self, table):
        """Part I classifies every punishable BNS section; 465 rows in 2023."""
        assert len(table) >= 460

    def test_ids_are_unique(self, table):
        ids = [record["id"] for record in table]
        assert len(ids) == len(set(ids))

    def test_every_section_number_is_well_formed(self, table):
        bad = [r["section"] for r in table if not self.SECTION.match(r["section"])]
        assert not bad

    def test_every_section_exists_in_the_bns_corpus(self, table):
        """A row citing a section the corpus does not have is unciteable."""
        sections = {
            record["metadata"]["section_number"]
            for record in json.loads((PROCESSED_DIR / "bns_sections.json").read_text())
        }
        missing = sorted({
            r["section"] for r in table
            if re.match(r"^\d+", r["section"]).group() not in sections
        })
        assert not missing

    def test_classification_cells_hold_only_classification_text(self, table):
        """
        Cross-column bleed is the parser's characteristic failure: a punishment
        term drifting into column 4 once made "2 Non-cognizable." out of a
        perfectly good row. Every cell must open the way the schedule opens it.
        """
        opener = re.compile(r"^(Cognizable|Non-cognizable|According)\b")
        bad = [(r["id"], r["cognizable_text"]) for r in table if not opener.match(r["cognizable_text"])]
        assert not bad, bad[:5]

        opener = re.compile(r"^(Bailable|Non-bailable|According)\b")
        bad = [(r["id"], r["bailable_text"]) for r in table if not opener.match(r["bailable_text"])]
        assert not bad, bad[:5]

    def test_every_row_names_a_court(self, table):
        bad = [(r["id"], r["triable_by"]) for r in table if not self.COURT.search(r["triable_by"])]
        assert not bad, bad[:5]

    def test_every_row_has_an_offence_and_a_punishment(self, table):
        assert not [r["id"] for r in table if not r["offence"] or not r["punishment"]]

    def test_resolved_classifications_are_unconditional(self, table):
        """
        A boolean may only come from a cell that says one thing. Everything
        conditional stays ``None`` with the schedule's own words beside it,
        because "it depends on the offence abetted" cannot be reduced to yes.
        """
        for record in table:
            if record["cognizable"] is not None:
                assert record["cognizable_text"].rstrip(".").lower() in {
                    "cognizable", "non-cognizable",
                }
            else:
                assert record["cognizable_text"]

    def test_unresolved_rows_are_the_conditional_ones(self, table):
        """
        Around 40 rows defer to another offence. If that count collapses the
        parser has started guessing; if it explodes, columns are bleeding.
        """
        unresolved = [r for r in table if r["cognizable"] is None or r["bailable"] is None]
        assert 20 <= len(unresolved) <= 60
        for record in unresolved:
            # Unresolved precisely because the cell says more than the bare
            # word: "According as offence abetted is...", "Cognizable (only on
            # the complaint of the victim)".
            for key, flag in (("cognizable_text", "cognizable"), ("bailable_text", "bailable")):
                if record[flag] is None:
                    assert len(record[key].split()) > 2, record

    def test_murder_is_not_bailable(self, table):
        """The single most consequential value in the file."""
        murder = next(r for r in table if r["section"] == "103(1)")
        assert murder["offence"] == "Murder."
        assert murder["bailable"] is False
        assert murder["cognizable"] is True
