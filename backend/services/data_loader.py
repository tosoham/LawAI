"""
Legal Data Loader for LawAI

Loads the ingested legal corpus from ``data/processed/``. Those JSON files are
produced by ``scripts/ingest_legal_acts.py`` (the three 2023 codes, parsed from
the official Ministry of Home Affairs gazette PDFs) and
``scripts/ingest_judgments.py`` (curated Supreme Court judgements).

Run those scripts before seeding the vector database. This module deliberately
has no sample-data fallback: quietly serving placeholder text from a legal
assistant is worse than failing loudly.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BACKEND_DIR.parent / "data" / "processed"

BNS_FILE = "bns_sections.json"
BNSS_FILE = "bnss_sections.json"
BSA_FILE = "bsa_sections.json"
JUDGEMENTS_FILE = "sc_judgements.json"

INGEST_HINT = (
    "Run 'python scripts/ingest_legal_acts.py' and "
    "'python scripts/ingest_judgments.py' from the backend directory first."
)


class LegalCorpusNotIngested(FileNotFoundError):
    """Raised when the processed corpus is missing from data/processed/."""


def _load(filename: str) -> List[Dict[str, Any]]:
    """Load one processed corpus file, validating its shape."""
    path = PROCESSED_DIR / filename

    if not path.exists():
        raise LegalCorpusNotIngested(f"Missing {path}. {INGEST_HINT}")

    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc

    if not isinstance(records, list) or not records:
        raise ValueError(f"{path} contains no records. {INGEST_HINT}")

    for record in records:
        missing = {"id", "text", "metadata"} - set(record)
        if missing:
            raise ValueError(f"{path}: a record is missing keys {sorted(missing)}")

    logger.info(f"Loaded {len(records)} records from {filename}")
    return records


class LegalDataLoader:
    """Loads the ingested Indian legal corpus for vector database seeding."""

    @staticmethod
    def get_bns_sections() -> List[Dict[str, Any]]:
        """Sections of the Bharatiya Nyaya Sanhita, 2023."""
        return _load(BNS_FILE)

    @staticmethod
    def get_bnss_sections() -> List[Dict[str, Any]]:
        """Sections of the Bharatiya Nagarik Suraksha Sanhita, 2023."""
        return _load(BNSS_FILE)

    @staticmethod
    def get_bsa_sections() -> List[Dict[str, Any]]:
        """Sections of the Bharatiya Sakshya Adhiniyam, 2023."""
        return _load(BSA_FILE)

    @staticmethod
    def get_sc_judgements() -> List[Dict[str, Any]]:
        """Curated landmark Supreme Court judgements."""
        return _load(JUDGEMENTS_FILE)

    def load_all_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Load the whole corpus.

        Returns:
            Dict with keys: 'bns', 'bnss', 'bsa', 'sc_judgements'
        """
        data = {
            'bns': self.get_bns_sections(),
            'bnss': self.get_bnss_sections(),
            'bsa': self.get_bsa_sections(),
            'sc_judgements': self.get_sc_judgements(),
        }
        total = sum(len(v) for v in data.values())
        logger.info(f"Loaded {total} documents across {len(data)} collections")
        return data
