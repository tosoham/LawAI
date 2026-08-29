"""
Capturing what production is telling us.

Three properties matter more than the storage, and each has a way of failing
quietly:

* **capture must never fail an answer.** It sits beside the request path, not
  in front of it. A feedback store that can 500 a legal answer is worse than no
  feedback store.
* **only failures are kept.** A log of every answer is a log nobody opens, and
  the whole point is that a person reads this.
* **a candidate is not a golden query.** `expected` is left empty on purpose:
  filling it from what the system returned would assert that the system returns
  what the system returned, which passes by construction and means nothing.
"""
import json
from unittest.mock import MagicMock

import pytest

from models.claims import Claim, ClaimVerdict, EpistemicClass, StructuredAnswer
from services import feedback


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    path = tmp_path / "events.jsonl"
    monkeypatch.setattr(feedback, "FEEDBACK_PATH", path)
    monkeypatch.setenv("ENABLE_FEEDBACK_CAPTURE", "true")
    return path


def answer(*, abstained=False, verdicts=(), sources=(), claims=()):
    result = MagicMock()
    result.abstained = abstained
    result.verdicts = list(verdicts)
    result.sources = list(sources)
    result.structured = StructuredAnswer(claims=list(claims))
    return result


def verdict(verified: bool, index: int = 0):
    return ClaimVerdict(
        index=index,
        verified=verified,
        original_class=EpistemicClass.STATUTE,
        reason="" if verified else "cites BNS 999, which is not in the corpus",
    )


def claim(text="Murder is punished with death."):
    return Claim(
        text=text, epistemic_class=EpistemicClass.STATUTE, sources=["BNS 103"]
    )


class TestTheDefault:
    def test_capture_is_off_unless_switched_on(self, monkeypatch):
        """This writes user-typed text to disk. That is a data-handling
        decision, not something to inherit by upgrading."""
        monkeypatch.delenv("ENABLE_FEEDBACK_CAPTURE", raising=False)
        assert feedback.feedback_enabled() is False
        assert feedback.capture(answer(abstained=True), "q") is None


class TestWhatIsKept:
    def test_an_abstention_is_kept(self):
        event = feedback.capture(answer(abstained=True), "what about GST")
        assert event and "abstained" in event.signals

    def test_removed_claims_are_kept_with_their_reason(self):
        """Already a fully specified failure — no labelling needed to act."""
        event = feedback.capture(
            answer(
                verdicts=[verdict(False)],
                sources=[{"citation": "BNS 103"}],
                claims=[claim()],
            ),
            "punishment for murder",
        )
        assert "claims_removed" in event.signals
        assert "not in the corpus" in event.removed[0]["reason"]
        assert event.removed[0]["text"].startswith("Murder is punished")

    def test_an_empty_retrieval_is_kept(self):
        event = feedback.capture(answer(sources=[]), "q")
        assert "nothing_retrieved" in event.signals

    def test_a_clean_answer_is_not_kept(self):
        """A log of everything is a log nobody opens."""
        event = feedback.capture(
            answer(verdicts=[verdict(True)], sources=[{"citation": "BNS 103"}]), "q"
        )
        assert event is None

    def test_a_user_note_is_kept_even_on_a_clean_answer(self):
        event = feedback.capture(
            answer(verdicts=[verdict(True)], sources=[{"citation": "BNS 103"}]),
            "q",
            note="this was wrong",
        )
        assert event and "user_reported" in event.signals


class TestItNeverFailsAnAnswer:
    def test_a_broken_result_object_does_not_raise(self):
        """Capture sits beside the answer, not in front of it."""
        broken = MagicMock()
        broken.abstained = True
        broken.verdicts = "not a list"
        broken.sources = None
        assert feedback.capture(broken, "q") is None

    def test_an_unwritable_store_does_not_raise(self, monkeypatch):
        monkeypatch.setattr(
            feedback, "FEEDBACK_PATH", __import__("pathlib").Path("/proc/nope/x.jsonl")
        )
        assert feedback.capture(answer(abstained=True), "q") is None


class TestPrivacy:
    def test_a_long_query_is_truncated(self, monkeypatch):
        """
        A legal question can carry facts about a real person. This is a
        diagnostic store, not a case file, and a truncated query still
        reproduces a retrieval failure.
        """
        monkeypatch.setattr(feedback, "MAX_QUERY_CHARS", 20)
        event = feedback.capture(answer(abstained=True), "x" * 500)
        assert len(event.to_dict()["query"]) == 20


class TestReading:
    def test_events_round_trip(self, store):
        feedback.capture(answer(abstained=True), "first")
        feedback.capture(answer(abstained=True), "second")

        events = feedback.read_events()
        assert [e["query"] for e in events] == ["first", "second"]

    def test_a_malformed_line_does_not_hide_the_rest(self, store):
        """The same rule the synthesis parser follows for a bad claim."""
        feedback.capture(answer(abstained=True), "good")
        with store.open("a") as handle:
            handle.write("{not json\n")
        feedback.capture(answer(abstained=True), "also good")

        assert len(feedback.read_events()) == 2

    def test_a_missing_store_reads_as_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(feedback, "FEEDBACK_PATH", tmp_path / "nothing.jsonl")
        assert feedback.read_events() == []

    def test_the_summary_counts_by_signal(self):
        feedback.capture(answer(abstained=True), "a")
        feedback.capture(
            answer(verdicts=[verdict(False)], sources=[{"citation": "x"}], claims=[claim()]),
            "b",
        )
        summary = feedback.summarise()

        assert summary["events"] == 2
        assert summary["by_signal"]["abstained"] == 1
        assert summary["by_signal"]["claims_removed"] == 1


class TestCandidatesAreNotGoldenQueries:
    def test_expected_is_left_empty(self, capsys):
        """
        The trap this avoids: filling `expected` from what retrieval returned
        would assert that the system returns what the system returned. It would
        score beautifully and mean nothing — the same failure
        `docs/ATTRIBUTION_GAP.md` describes for unreviewed model-proposed edges.
        """
        import importlib

        module = importlib.import_module("scripts.review_feedback")
        module.print_candidates(
            [{"query": "can they hold him past 60 days", "signals": ["abstained"]}]
        )
        payload = json.loads(capsys.readouterr().out)

        assert payload["queries"][0]["expected"] == []
        assert "TODO" in payload["queries"][0]["class"]

    def test_duplicate_queries_collapse(self, capsys):
        import importlib

        module = importlib.import_module("scripts.review_feedback")
        module.print_candidates(
            [
                {"query": "same question", "signals": ["abstained"]},
                {"query": "Same Question", "signals": ["abstained"]},
            ]
        )
        assert len(json.loads(capsys.readouterr().out)["queries"]) == 1


class TestTheEndpoint:
    """
    The one failure the system cannot notice on its own.

    Abstained / claims-removed / nothing-retrieved all mean *the system spotted
    something*. None of them catches a confident answer that is simply wrong --
    every claim in it passed verification, so nothing internal flags it. Only
    the reader knows, which is the whole reason this endpoint exists.
    """

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        import main

        return TestClient(main.app)

    def test_a_report_is_recorded(self, client):
        response = client.post(
            "/api/v1/feedback",
            json={"query": "is murder bailable", "note": "wrong trying court"},
        )
        assert response.status_code == 202
        assert response.json()["recorded"] is True

        events = feedback.read_events()
        assert events[-1]["signals"] == ["user_reported"]
        assert events[-1]["note"] == "wrong trying court"

    def test_a_bare_report_still_queues_the_query(self, client):
        """Enough to reproduce it, which is what a reviewer needs."""
        response = client.post("/api/v1/feedback", json={"query": "is theft bailable"})
        assert response.status_code == 202
        assert feedback.read_events()[-1]["query"] == "is theft bailable"

    def test_an_empty_query_is_refused(self, client):
        assert client.post("/api/v1/feedback", json={"query": ""}).status_code == 422

    def test_capture_disabled_is_told_plainly_not_failed(self, client, monkeypatch):
        """
        A deployment that has not turned capture on made a deliberate choice
        about storing user text. A client should be told, not shown an error.
        """
        monkeypatch.delenv("ENABLE_FEEDBACK_CAPTURE", raising=False)
        response = client.post("/api/v1/feedback", json={"query": "q"})

        assert response.status_code == 202
        assert response.json()["recorded"] is False

    def test_the_summary_serves_no_queries_or_notes(self, client):
        """
        Serving them would turn a diagnostic store into a way to read other
        people's questions. A reviewer reads those locally.
        """
        client.post("/api/v1/feedback", json={"query": "a private matter", "note": "x"})
        body = client.get("/api/v1/feedback/summary").json()

        assert body["enabled"] is True
        assert "a private matter" not in str(body)
        assert body["by_signal"]["user_reported"] >= 1
