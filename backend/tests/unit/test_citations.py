"""
Unit tests for citation formatting.

Citations are a correctness surface in this project, not presentation: a wrong
or unusable section reference is a bug.
"""
from agents.citations import format_citation, source_payload

GAZETTE = "Ministry of Home Affairs, Gazette of India"


class TestFormatCitation:
    """Statute and case-law rendering."""

    def test_statute_uses_the_required_form(self):
        citation = format_citation({
            "section_number": "103",
            "act": "Bharatiya Nyaya Sanhita",
            "year": "2023",
            "title": "Punishment for murder",
        })
        assert citation == "Section 103, Bharatiya Nyaya Sanhita, 2023 (Punishment for murder)"

    def test_statute_without_a_title_omits_the_parenthetical(self):
        citation = format_citation({
            "section_number": "482",
            "act": "Bharatiya Nagarik Suraksha Sanhita",
            "year": "2023",
        })
        assert citation == "Section 482, Bharatiya Nagarik Suraksha Sanhita, 2023"

    def test_missing_components_are_omitted_not_guessed(self):
        """A partial citation is fine; an invented act or year is not."""
        assert format_citation({"section_number": "7"}) == "Section 7"

    def test_judgement_keeps_only_the_leading_report(self):
        """
        Indian Kanoon lists every reporter that carried a judgement. Bachan
        Singh arrives as eleven parallel citations over 200 characters long,
        which is unusable as a label.
        """
        citation = format_citation({
            "case_name": "Bachan Singh v. State of Punjab",
            "citation": (
                "AIR1980SC898, 1980CRILJ636, 1982(1)SCALE713, (1980)2SCC684, "
                "[1983]1SCR145, AIR 1980 SUPREME COURT 898"
            ),
        })
        assert citation == "Bachan Singh v. State of Punjab, AIR1980SC898"

    def test_judgement_citation_as_a_list(self):
        citation = format_citation({
            "case_name": "Sushila Aggarwal v. State (NCT of Delhi)",
            "citation": ["(2020) 5 SCC 1", "AIR 2020 SC 831"],
        })
        assert citation == "Sushila Aggarwal v. State (NCT of Delhi), (2020) 5 SCC 1"

    def test_judgement_without_a_reported_citation(self):
        assert format_citation({"case_name": "Some v. Other"}) == "Some v. Other"

    def test_falls_back_to_provenance_rather_than_unknown(self):
        """
        Every corpus chunk carries the same generic `source` string. Naming the
        gazette is at least true; the previous code printed that string as if it
        were the citation for all three sources, which told a reader nothing
        about which section an answer rested on.
        """
        assert format_citation({"source": GAZETTE}) == GAZETTE

    def test_empty_metadata(self):
        assert format_citation({}) == "Source not identified"


class TestSourcePayload:
    """What gets handed to clients."""

    def test_carries_the_citation_and_the_text(self):
        payload = source_payload({
            "text": "Whoever commits murder shall be punished with death...",
            "relevance_score": 0.91,
            "metadata": {
                "section_number": "103",
                "act": "Bharatiya Nyaya Sanhita",
                "year": "2023",
                "title": "Punishment for murder",
                "source_url": "https://www.mha.gov.in/x.pdf",
            },
        })

        assert payload["citation"].startswith("Section 103, Bharatiya Nyaya Sanhita")
        assert payload["relevance_score"] == 0.91
        assert payload["source_url"] == "https://www.mha.gov.in/x.pdf"

    def test_internal_bookkeeping_is_not_exposed(self):
        """parent_id and chunk_count are indexing details, not API surface."""
        payload = source_payload({
            "text": "…",
            "metadata": {"section_number": "1", "parent_id": "bns_1", "chunk_count": 3},
        })
        assert "parent_id" not in payload
        assert "chunk_count" not in payload
