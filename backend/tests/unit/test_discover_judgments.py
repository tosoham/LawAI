"""
Unit tests for judgement discovery.

The script cannot be run end to end here -- the source it searches is behind a
challenge -- so what is tested is the part that decides what gets *recorded*,
which is where a corpus acquires a falsehood.

The most important assertion in this file is that derived sections never land
in ``relevant_sections``. That key means "is an authority on" and becomes a
graph edge; what this script can derive is "cites", which is a different and
weaker claim. Keeping them apart is the whole finding.
"""
import json
from pathlib import Path

import pytest

from tests.unit.test_ingestion import _load_script

discover = _load_script("discover_judgments")

PROCESSED_DIR = Path(__file__).resolve().parents[3] / "data" / "processed"
CONCORDANCE = {("CrPC", "438"): ["482"], ("IPC", "302"): ["103"], ("CrPC", "154"): ["173"]}


class TestParseTitle:
    def test_a_judgement_title_yields_its_case_and_year(self):
        assert discover.parse_title(
            "Sushila Aggarwal vs State (Nct Of Delhi) on 29 January, 2020"
        ) == ("Sushila Aggarwal vs State (Nct Of Delhi)", "2020")

    @pytest.mark.parametrize(
        "title",
        [
            "Some Listing Notice",
            "Cause list for 5 May",
            "X vs Y on 32 Smarch, 2020",
            "",
        ],
    )
    def test_a_page_that_is_not_a_judgement_is_rejected(self, title):
        """The date is the check: an order sheet or a listing page has none."""
        assert discover.parse_title(title) is None


class TestSectionsCited:
    def test_a_section_named_with_its_act_twice_is_recorded(self):
        text = (
            "The appellant moved under Section 438 Cr.P.C. for relief. "
            "The scope of Section 438 of the Code of Criminal Procedure is settled."
        )
        assert discover.sections_cited(text, CONCORDANCE) == ["BNSS 482"]

    def test_a_single_mention_is_not_enough(self):
        """One mention is often a party's argument being recited, or a
        provision the court goes on to set aside."""
        text = "Counsel referred to Section 438 Cr.P.C. and moved on."
        assert discover.sections_cited(text, CONCORDANCE) == []

    def test_a_bare_section_number_records_nothing(self):
        """
        Judgements overwhelmingly write "Section 438" and rely on context.
        Guessing the act from the surrounding case is what this script
        deliberately refuses to do -- see the module docstring.
        """
        text = "Section 438 is a facility. Section 438 must be read widely."
        assert discover.sections_cited(text, CONCORDANCE) == []

    def test_a_repealed_citation_is_translated(self):
        """A 1980 judgement cites the CrPC and nothing else; recording it
        against no section would make the older corpus invisible."""
        text = "Under Section 302 IPC the sentence follows. Section 302 of the Indian Penal Code applies."
        assert discover.sections_cited(text, CONCORDANCE) == ["BNS 103"]

    def test_the_act_abbreviation_is_not_read_as_a_section_suffix(self):
        """"Section 438 Cr.P.C." parsed "Cr" as the suffix of 438, and the act
        vanished with it -- nothing was ever recorded."""
        text = "Section 438 Cr.P.C. applies. Again, Section 438 Cr.P.C. applies."
        assert discover.sections_cited(text, CONCORDANCE) == ["BNSS 482"]

    def test_the_number_of_sections_is_capped(self):
        text = " ".join(
            f"Section {n} of the Code of Criminal Procedure is relevant." for n in range(1, 40)
        ) * 2
        assert len(discover.sections_cited(text, {})) <= discover.MAX_SECTIONS_PER_JUDGEMENT

    def test_no_concordance_means_no_repealed_mappings_rather_than_a_crash(self):
        text = "Section 302 IPC. Section 302 IPC."
        assert discover.sections_cited(text, {}) == []


class TestBuildRecord:
    """What actually gets written."""

    def page(self, title="A vs B on 1 January, 2020", body=None, citations="AIR 2020 SC 1"):
        body = body or ("The court considered Section 438 Cr.P.C. at length. " * 200)
        return f"""
        <html><body>
          <div class="doc_title">{title}</div>
          <div class="doc_citations">Equivalent citations: {citations}</div>
          <div class="doc_bench">Bench: A Judge</div>
          <div class="judgments">{body}</div>
        </body></html>
        """

    def topic(self):
        return discover.Topic("bail", "anticipatory bail", "Bail: anticipatory bail")

    def test_a_judgement_page_becomes_a_record(self):
        record = discover.build_record("1", self.page(), self.topic(), CONCORDANCE)
        assert record["id"] == "sc_a_vs_b_2020"
        assert record["metadata"]["year"] == "2020"
        assert record["metadata"]["citation"] == "AIR 2020 SC 1"
        assert record["metadata"]["source_url"].endswith("/doc/1/")

    def test_derived_sections_never_become_interprets_edges(self):
        """
        The finding this script exists to record. `relevant_sections` means
        "is an authority on" and the legal graph turns it into an edge;
        `cited_sections` means the text cites it, which is all that can be
        established by reading the document.
        """
        record = discover.build_record("1", self.page(), self.topic(), CONCORDANCE)
        assert record["metadata"]["cited_sections"] == "BNSS 482"
        assert record["metadata"]["relevant_sections"] == ""

    def test_the_subject_records_how_it_was_found_and_nothing_more(self):
        record = discover.build_record("1", self.page(), self.topic(), CONCORDANCE)
        assert record["metadata"]["subject"] == "Bail: anticipatory bail"
        assert record["metadata"]["verification"] == "attributes"

    def test_a_stub_page_is_rejected(self):
        """An order sheet or a listing notice is not a decision."""
        assert discover.build_record("1", self.page(body="Adjourned."), self.topic(), {}) is None

    def test_a_page_with_no_title_is_rejected(self):
        html = "<html><body><div class='judgments'>text</div></body></html>"
        assert discover.build_record("1", html, self.topic(), {}) is None

    def test_a_title_that_does_not_parse_is_rejected(self):
        page = self.page(title="Cause List For Monday")
        assert discover.build_record("1", page, self.topic(), {}) is None

    def test_a_long_judgement_is_truncated_and_says_so(self):
        record = discover.build_record(
            "1", self.page(body="word " * 20_000), self.topic(), {}
        )
        assert len(record["text"]) < discover.MAX_DISCOVERED_CHARS + 500
        assert "[Judgement truncated]" in record["text"]


class TestTopics:
    def test_every_area_of_criminal_practice_is_covered(self):
        assert {t.key for t in discover.TOPICS} == {
            "bail", "arrest", "evidence", "procedure", "sentencing", "offences",
            "constitutional",
        }

    def test_queries_are_unique(self):
        queries = [t.query for t in discover.TOPICS]
        assert len(queries) == len(set(queries))


class TestExistingCorpusIsUntouched:
    """
    The thirty pinned judgements keep their curated edges. Discovery appends;
    it must never rewrite what someone decided by hand.
    """

    def test_the_curated_judgements_still_carry_their_sections(self):
        records = json.loads((PROCESSED_DIR / "sc_judgements.json").read_text())
        curated = [r for r in records if r["metadata"].get("relevant_sections")]
        assert len(curated) >= 27

    def test_no_record_claims_both_kinds_of_section(self):
        """A record is either hand-curated or discovered, not both."""
        records = json.loads((PROCESSED_DIR / "sc_judgements.json").read_text())
        for record in records:
            metadata = record["metadata"]
            assert not (
                metadata.get("relevant_sections") and metadata.get("cited_sections")
            )
