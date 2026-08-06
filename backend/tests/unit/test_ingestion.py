"""
Unit tests for the legal corpus ingestion pipeline.

Covers the chunking used when seeding ChromaDB and the PDF-layout helpers that
turn the gazette PDFs into sections.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = BACKEND_DIR.parent / "data" / "processed"


def _load_script(name):
    """Import a scripts/*.py module directly (they are not a package)."""
    path = BACKEND_DIR / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # @dataclass resolves annotations via sys.modules, so register before exec.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


init_vector_db = _load_script("init_vector_db")
ingest_legal_acts = _load_script("ingest_legal_acts")


class TestSplitText:
    """Chunking must keep every passage retrievable and within the model window."""

    def test_short_text_is_left_whole(self):
        text = "Section 114 - Hurt\n114. Whoever causes bodily pain to any person."
        assert init_vector_db.split_text(text) == [text]

    def test_long_text_is_split(self):
        text = "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(20))
        chunks = init_vector_db.split_text(text)
        assert len(chunks) > 1

    def test_every_chunk_fits_the_embedding_window(self):
        text = "\n\n".join(f"Paragraph {i}. " + "word " * 80 for i in range(30))
        for chunk in init_vector_db.split_text(text):
            assert len(chunk) <= init_vector_db.MAX_CHUNK_CHARS

    def test_a_single_oversized_paragraph_is_still_split(self):
        text = "x" * (init_vector_db.MAX_CHUNK_CHARS * 3)
        chunks = init_vector_db.split_text(text)
        assert len(chunks) > 1
        assert all(len(c) <= init_vector_db.MAX_CHUNK_CHARS for c in chunks)

    def test_content_is_not_lost(self):
        """A distinctive phrase late in the text must survive chunking."""
        marker = "ANTICIPATORY_BAIL_MARKER"
        text = "\n\n".join(["filler " * 50 for _ in range(20)] + [marker])
        assert any(marker in chunk for chunk in init_vector_db.split_text(text))


class TestChunkRecords:
    """Chunks must remain attributable to the section or judgement they came from."""

    def test_single_chunk_keeps_the_original_id(self):
        record = {"id": "bns_114", "text": "Short section text.",
                  "metadata": {"section_number": "114"}}
        chunks = init_vector_db.chunk_records([record])
        assert len(chunks) == 1
        assert chunks[0]["id"] == "bns_114"
        assert chunks[0]["metadata"]["parent_id"] == "bns_114"

    def test_split_records_get_unique_suffixed_ids(self):
        record = {
            "id": "sc_case_2020",
            "text": "\n\n".join(f"Para {i}. " + "word " * 80 for i in range(20)),
            "metadata": {"case_name": "Test v. State"},
        }
        chunks = init_vector_db.chunk_records([record])
        assert len(chunks) > 1
        assert len({c["id"] for c in chunks}) == len(chunks)
        assert all(c["metadata"]["parent_id"] == "sc_case_2020" for c in chunks)
        assert all(c["metadata"]["case_name"] == "Test v. State" for c in chunks)
        assert {c["metadata"]["chunk_index"] for c in chunks} == set(range(len(chunks)))

    def test_parent_metadata_is_copied_not_shared(self):
        record = {
            "id": "sc_case_2020",
            "text": "\n\n".join(f"Para {i}. " + "word " * 80 for i in range(10)),
            "metadata": {"case_name": "Test v. State"},
        }
        chunks = init_vector_db.chunk_records([record])
        chunks[0]["metadata"]["case_name"] = "Mutated"
        assert chunks[1]["metadata"]["case_name"] == "Test v. State"


class TestActParsingHelpers:
    """Regexes encoding the gazette's layout quirks."""

    @pytest.mark.parametrize("line,expected", [
        ("CHAPTER II", "II"),
        ("CHAPTERV", "V"),      # the space is missing in the extracted text
        ("CHAPTERXX", "XX"),
        ("CHAPTER 5", "5"),
    ])
    def test_chapter_heading_matches_glued_numerals(self, line, expected):
        match = ingest_legal_acts.CHAPTER_HEADING.match(line)
        assert match and match.group(1) == expected

    def test_chapter_heading_ignores_prose(self):
        assert ingest_legal_acts.CHAPTER_HEADING.match("CHAPTER II is about punishments") is None

    @pytest.mark.parametrize("line,number", [
        ("103. (1) Whoever commits murder", "103"),
        ("4. The punishments to which offenders", "4"),
    ])
    def test_section_start_captures_the_number(self, line, number):
        match = ingest_legal_acts.SECTION_START.match(line)
        assert match and match.group(1) == number

    def test_section_start_ignores_sub_clauses(self):
        assert ingest_legal_acts.SECTION_START.match("(2) In every case of an offence") is None

    def test_marginal_citations_are_stripped_from_titles(self):
        """Marginal act references share the title column and must be removed."""
        cleaned = ingest_legal_acts.MARGIN_CITATION.sub("", "Repeal and 45 of 1860. savings")
        assert "1860" not in cleaned
        assert "Repeal and" in cleaned and "savings" in cleaned

    @pytest.mark.parametrize("line", [
        "THE FIRST SCHEDULE",
        "THE SCHEDULE",
        "THE SECOND SCHEDULE",
        "SCHEDULE",
        "SCHEDULES",
    ])
    def test_schedule_heading_matches(self, line):
        assert ingest_legal_acts.SCHEDULE_HEADING.match(line)

    @pytest.mark.parametrize("line", [
        "THE FIRST SCHEDULE shall apply to offences",
        "as specified in the Schedule to this Sanhita",
        "531. (1) The Code of Criminal Procedure, 1973 is hereby repealed.",
    ])
    def test_schedule_heading_ignores_prose(self, line):
        """
        Only a bare heading terminates a section. Prose that merely mentions a
        schedule -- and section bodies routinely cross-reference one -- must not
        truncate the section it appears in.
        """
        assert ingest_legal_acts.SCHEDULE_HEADING.match(line) is None

    def test_assign_titles_binds_notes_to_the_nearest_section_above(self):
        """
        Regression: notes are emitted out of order, and two titles set close
        together were once merged, leaving section 103 with no title at all.
        """
        s102 = ingest_legal_acts.ParsedSection(number="102", chapter="")
        s103 = ingest_legal_acts.ParsedSection(number="103", chapter="")
        margin_lines = [
            (85.0, "Culpable homicide by causing death"),
            (142.6, "of person other than intended"),
            (157.5, "Punishment"),
            (167.1, "for murder"),
        ]
        orphans = ingest_legal_acts.assign_titles(
            margin_lines, [(84.0, s102), (155.9, s103)]
        )
        assert orphans == 0
        assert s103.title == "Punishment for murder"
        assert "Culpable homicide" in s102.title
        assert "Punishment for murder" not in s102.title

    def test_assign_titles_allows_a_note_set_slightly_above_its_section(self):
        """Section 78's "Stalking." note sits a few points above the section."""
        s78 = ingest_legal_acts.ParsedSection(number="78", chapter="")
        orphans = ingest_legal_acts.assign_titles([(125.3, "Stalking.")], [(128.6, s78)])
        assert orphans == 0
        assert s78.title == "Stalking"


@pytest.mark.skipif(
    not (PROCESSED_DIR / "bns_sections.json").exists(),
    reason="corpus not ingested; run scripts/ingest_legal_acts.py",
)
class TestIngestedCorpus:
    """Sanity checks on the corpus actually on disk."""

    @pytest.mark.parametrize("filename,count", [
        ("bns_sections.json", 358),
        ("bnss_sections.json", 531),
        ("bsa_sections.json", 170),
    ])
    def test_expected_section_counts(self, filename, count):
        records = json.loads((PROCESSED_DIR / filename).read_text())
        assert len(records) == count

    def test_sections_are_contiguous_and_titled(self):
        records = json.loads((PROCESSED_DIR / "bns_sections.json").read_text())
        numbers = {r["metadata"]["section_number"] for r in records}
        assert numbers == {str(i) for i in range(1, 359)}
        assert all(r["metadata"]["title"] for r in records)

    @pytest.mark.parametrize("filename,section,limit", [
        ("bnss_sections.json", "531", 4_000),
        ("bsa_sections.json", "170", 4_000),
    ])
    def test_final_section_does_not_swallow_the_schedules(
        self, filename, section, limit
    ):
        """
        Regression: the parser had no terminator for the last section of an act,
        so it kept accumulating to the end of the document. BNSS 531 ("Repeal
        and savings", genuinely ~1,900 characters) came out at 129,022 —
        the First Schedule plus every blank form, roughly 108 chunks of
        dotted-line templates competing for retrieval against actual law.
        """
        records = json.loads((PROCESSED_DIR / filename).read_text())
        text = next(
            r["text"] for r in records
            if r["metadata"]["section_number"] == section
        )
        assert len(text) < limit, f"{filename} §{section} is {len(text)} chars"
        # The tell-tale form boilerplate, and the schedule heading itself.
        assert ".........." not in text
        assert "THE FIRST SCHEDULE" not in text

    def test_no_section_is_implausibly_long(self):
        """
        A section running past ~15k characters means the parser has merged
        something it should have split, which is how the schedule bug hid.
        """
        for filename in ("bns_sections.json", "bnss_sections.json", "bsa_sections.json"):
            for record in json.loads((PROCESSED_DIR / filename).read_text()):
                assert len(record["text"]) < 15_000, (
                    f"{filename} §{record['metadata']['section_number']} "
                    f"is {len(record['text'])} chars"
                )

    def test_known_sections_have_the_right_titles(self):
        records = json.loads((PROCESSED_DIR / "bns_sections.json").read_text())
        by_number = {r["metadata"]["section_number"]: r for r in records}
        assert by_number["103"]["metadata"]["title"] == "Punishment for murder"
        assert by_number["63"]["metadata"]["title"] == "Rape"
        assert "murder" in by_number["103"]["text"].lower()

    def test_judgements_carry_citable_metadata(self):
        path = PROCESSED_DIR / "sc_judgements.json"
        if not path.exists():
            pytest.skip("judgements not ingested")
        records = json.loads(path.read_text())
        assert records
        for record in records:
            meta = record["metadata"]
            assert meta["case_name"] and meta["year"]
            assert meta["court"] == "Supreme Court of India"
            assert meta["source_url"].startswith("https://indiankanoon.org/doc/")

    def test_every_manifest_entry_was_ingested(self):
        """A skipped judgement means a document id drifted; fail rather than shrink."""
        path = PROCESSED_DIR / "sc_judgements.json"
        if not path.exists():
            pytest.skip("judgements not ingested")
        records = json.loads(path.read_text())
        ingest_judgments = _load_script("ingest_judgments")
        assert len(records) == len(ingest_judgments.JUDGEMENTS)

    def test_landmark_authorities_are_present(self):
        path = PROCESSED_DIR / "sc_judgements.json"
        if not path.exists():
            pytest.skip("judgements not ingested")
        names = " | ".join(r["metadata"]["case_name"] for r in json.loads(path.read_text()))
        for expected in ("Bhajan Lal", "Selvi", "Puttaswamy", "Mohd. Arif",
                         "Sushila Aggarwal", "Lalita Kumari", "Arnesh Kumar"):
            assert expected in names, f"{expected} missing from the judgement corpus"


class TestJudgementVerification:
    """Identity checks that stop the wrong authority being stored."""

    @staticmethod
    def _page(title: str, body: str) -> str:
        return (
            f'<div class="doc_title">{title}</div>'
            f'<div class="doc_citations">Equivalent citations: 1992 AIR 604</div>'
            f'<div class="doc_bench">Bench: Some Judge</div>'
            f'<div class="judgments">{body}</div>'
        )

    def _spec(self, **kw):
        ingest_judgments = _load_script("ingest_judgments")
        defaults = {"doc_id": "1", "case_name": "Test v. State", "year": "1990",
                    "subject": "s", "expect": ("test",)}
        defaults.update(kw)
        return ingest_judgments.JudgementSpec(**defaults)

    def test_accepts_a_matching_page(self):
        ingest_judgments = _load_script("ingest_judgments")
        html = self._page("Test vs State on 1 January, 1990", "the holding mentions mala fide conduct")
        record = ingest_judgments.parse_judgement(html, self._spec(expect_text=("mala fide",)))
        assert record is not None
        assert record["metadata"]["case_name"] == "Test v. State"

    def test_rejects_a_different_case_with_the_same_parties(self):
        """Regression: the first Bhajan Lal id matched by title but was a later
        contempt petition in the same matter."""
        ingest_judgments = _load_script("ingest_judgments")
        html = self._page("Test vs State on 1 January, 1992", "contempt petition dismissed, no costs")
        assert ingest_judgments.parse_judgement(html, self._spec(expect_text=("mala fide",))) is None

    def test_rejects_a_title_mismatch(self):
        ingest_judgments = _load_script("ingest_judgments")
        html = self._page("Someone Else vs Another on 1 January, 1990", "body text")
        assert ingest_judgments.parse_judgement(html, self._spec()) is None
