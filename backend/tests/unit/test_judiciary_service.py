"""
Unit tests for live judiciary data access.

These never touch the network: the HTTP session is mocked, so the parsing,
politeness and fail-soft behaviour can be checked deterministically.
"""
from unittest.mock import MagicMock

import pytest

from services.judiciary_service import (
    JudiciaryService,
    get_judiciary_service,
    live_fetching_enabled,
    reset_judiciary_service,
)

SEARCH_HTML = """
<html><body>
<article class="result">
  <h4 class="result_title">
    <a href="/docfragment/60022179/?formInput=x">Balmukund Singh Gautam vs State Of Madhya Pradesh on 13 February, 2026</a>
  </h4>
  <div class="headline">anticipatory <b>bail</b> is a legal safeguard</div>
  <div class="hlbottom">
    <span class="docsource">Supreme Court of India</span>
    <a class="cite_tag" href="/search/?formInput=citedby:60022179">Cited by 7</a>
  </div>
</article>
<article class="result">
  <h4 class="result_title">
    <a href="/doc/79532249/">Sumit vs State Of U P on 9 February, 2026</a>
  </h4>
  <div class="headline">cancellation of the anticipatory bail granted</div>
  <div class="hlbottom"><span class="docsource">Supreme Court of India</span></div>
</article>
</body></html>
"""

JUDGEMENT_HTML = """
<html><body>
<div class="doc_title">Sumit vs State Of U P on 9 February, 2026</div>
<div class="doc_citations">Equivalent citations: 2026 AIR SC 100</div>
<div class="doc_bench">Bench: A Judge, B Judge</div>
<div class="judgments">The appeal is allowed.\n\nAnticipatory bail is granted.</div>
</body></html>
"""


def _service(text: str = SEARCH_HTML, status: int = 200) -> JudiciaryService:
    """A service whose every HTTP call returns the given body."""
    session = MagicMock()
    response = MagicMock()
    response.text = text
    response.status_code = status
    response.raise_for_status = MagicMock()
    session.get.return_value = response
    service = JudiciaryService(session=session)
    # Skip the robots fetch; nothing is blocked unless a test says so.
    service._disallowed = set()
    return service


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_LIVE_JUDICIARY", "true")
    reset_judiciary_service()
    yield
    reset_judiciary_service()


class TestQueryBuilding:
    """The source expects D-M-YYYY and its own filter syntax."""

    @pytest.mark.parametrize("value,expected", [
        ("2026-02-13", "13-2-2026"),
        ("2026-2-3", "3-2-2026"),
        ("2025", "1-1-2025"),
        (None, None),
        ("", None),
    ])
    def test_date_formatting(self, value, expected):
        assert JudiciaryService._format_date(value) == expected

    def test_query_includes_court_and_dates(self):
        expr = _service()._build_query("bail", "supremecourt", "2026-01-01", "2026-08-03")
        assert "bail" in expr
        assert "doctypes:supremecourt" in expr
        assert "fromdate:1-1-2026" in expr
        assert "todate:3-8-2026" in expr

    def test_open_ended_range_is_closed_at_today(self):
        """A from_date with no to_date must not return an unbounded window."""
        expr = _service()._build_query("bail", "supremecourt", "2026-01-01", None)
        assert "fromdate:1-1-2026" in expr
        assert "todate:" in expr

    def test_all_courts_omits_the_doctype_filter(self):
        assert "doctypes:" not in _service()._build_query("bail", "all", None, None)

    @pytest.mark.parametrize("title,expected_name,expected_date", [
        ("Sumit vs State Of U P on 9 February, 2026", "Sumit vs State Of U P", "9 February, 2026"),
        ("A vs B", "A vs B", ""),
    ])
    def test_title_and_date_are_separated(self, title, expected_name, expected_date):
        name, judged_on = JudiciaryService._split_title_and_date(title)
        assert (name, judged_on) == (expected_name, expected_date)


class TestSearch:
    """Every hit must be citable: court, date and a source URL."""

    def test_parses_results(self):
        result = _service().search_case_law("anticipatory bail", limit=5)

        assert result["success"] is True
        assert result["num_results"] == 2
        first = result["results"][0]
        assert first["doc_id"] == "60022179"
        assert first["title"] == "Balmukund Singh Gautam vs State Of Madhya Pradesh"
        assert first["date"] == "13 February, 2026"
        assert first["court"] == "Supreme Court of India"
        assert first["source_url"] == "https://indiankanoon.org/doc/60022179/"
        assert first["cited_by"] == 7
        assert "bail" in first["snippet"]

    def test_marks_results_as_live(self):
        """Live material is retrieved, not curated, and must say so."""
        result = _service().search_case_law("bail")
        assert all(r["source"] == "Indian Kanoon (live)" for r in result["results"])

    def test_limit_is_respected(self):
        assert _service().search_case_law("bail", limit=1)["num_results"] == 1

    def test_rejects_empty_query(self):
        assert _service().search_case_law("")["success"] is False

    def test_rejects_unknown_court(self):
        result = _service().search_case_law("bail", court="districtcourt")
        assert result["success"] is False
        assert "districtcourt" in result["error"]

    def test_disallowed_documents_are_skipped(self):
        service = _service()
        service._disallowed = {"60022179"}
        ids = [r["doc_id"] for r in service.search_case_law("bail")["results"]]
        assert "60022179" not in ids
        assert "79532249" in ids

    def test_network_failure_is_reported_not_raised(self):
        """A source outage must degrade to the local corpus, not 500."""
        service = _service()
        service.session.get.side_effect = OSError("connection reset")

        result = service.search_case_law("bail")

        assert result["success"] is False
        assert result["results"] == []
        assert "connection reset" in result["error"]

    def test_results_are_cached(self):
        service = _service()
        service.search_case_law("bail")
        service.search_case_law("bail")
        assert service.session.get.call_count == 1

    def test_different_queries_are_not_confused(self):
        service = _service()
        service.search_case_law("bail")
        service.search_case_law("murder")
        assert service.session.get.call_count == 2


class TestFetchJudgment:
    def test_parses_a_judgement(self):
        result = _service(JUDGEMENT_HTML).fetch_judgment("79532249")

        assert result["success"] is True
        assert result["title"] == "Sumit vs State Of U P"
        assert result["date"] == "9 February, 2026"
        assert result["citation"] == "2026 AIR SC 100"
        assert result["bench"] == "A Judge, B Judge"
        assert "Anticipatory bail is granted." in result["text"]
        assert result["source_url"] == "https://indiankanoon.org/doc/79532249/"

    def test_truncates_long_text(self):
        result = _service(JUDGEMENT_HTML).fetch_judgment("79532249", max_chars=20)
        assert result["truncated"] is True
        assert "[Judgement truncated]" in result["text"]

    def test_rejects_a_non_numeric_id(self):
        assert _service(JUDGEMENT_HTML).fetch_judgment("../etc/passwd")["success"] is False

    def test_respects_the_robots_blocklist(self):
        service = _service(JUDGEMENT_HTML)
        service._disallowed = {"79532249"}

        result = service.fetch_judgment("79532249")

        assert result["success"] is False
        assert "robots" in result["error"]
        service.session.get.assert_not_called()

    def test_unparseable_page_fails_cleanly(self):
        result = _service("<html><body>nothing here</body></html>").fetch_judgment("1")
        assert result["success"] is False


class TestKillSwitch:
    """Live access must be disableable for offline use or rate-limit trouble."""

    def test_disabled_by_environment(self, monkeypatch):
        monkeypatch.setenv("ENABLE_LIVE_JUDICIARY", "false")
        assert live_fetching_enabled() is False

        service = _service()
        search = service.search_case_law("bail")
        fetch = service.fetch_judgment("1")

        assert search["success"] is False and "disabled" in search["error"]
        assert fetch["success"] is False and "disabled" in fetch["error"]
        service.session.get.assert_not_called()

    @pytest.mark.parametrize("value", ["0", "no", "off", "FALSE"])
    def test_falsey_spellings(self, monkeypatch, value):
        monkeypatch.setenv("ENABLE_LIVE_JUDICIARY", value)
        assert live_fetching_enabled() is False


class TestRobotsParsing:
    def test_only_the_wildcard_agent_block_applies(self):
        service = _service(
            "User-agent: *\nDisallow: /doc/111/\n\n"
            "User-agent: SemrushBot\nDisallow: /doc/222/\n"
        )
        service._disallowed = None

        disallowed = service._load_disallowed()

        assert "111" in disallowed
        assert "222" not in disallowed


class TestSingleton:
    def test_accessor_returns_one_instance(self):
        assert get_judiciary_service() is get_judiciary_service()

    def test_reset_creates_a_new_instance(self):
        first = get_judiciary_service()
        reset_judiciary_service()
        assert get_judiciary_service() is not first


class TestRobotsFailsClosed:
    """
    Not knowing is not permission.

    The disallow list names several thousand documents individually, so an
    unreadable robots.txt leaves no basis for fetching any of them. This used
    to log "proceeding cautiously" and then treat everything as allowed, which
    is the opposite of cautious -- found when the source put its whole site
    behind a challenge and robots.txt started returning 403 along with it.
    """

    def service(self, robots_status=200, robots_body="User-agent: *\nDisallow: /doc/999/"):
        from unittest.mock import Mock

        import requests

        from services.judiciary_service import JudiciaryService

        session = Mock(spec=requests.Session)
        session.headers = {}
        response = Mock()
        response.status_code = robots_status
        response.text = robots_body
        if robots_status != 200:
            response.raise_for_status.side_effect = requests.HTTPError(f"{robots_status}")
        else:
            response.raise_for_status.return_value = None
        session.get.return_value = response
        return JudiciaryService(session=session)

    def test_a_listed_document_is_refused(self):
        assert not self.service().is_allowed("999")

    def test_an_unlisted_document_is_allowed(self):
        assert self.service().is_allowed("1290514")

    def test_every_document_is_refused_when_robots_cannot_be_read(self):
        assert not self.service(robots_status=403).is_allowed("1290514")

    def test_the_failure_is_not_cached(self):
        """A bad response is usually transient; caching it would keep the
        source off limits for the life of the process."""
        service = self.service(robots_status=403)
        assert not service.is_allowed("1290514")
        assert service._disallowed is None


class TestHealthReportsReachability:
    """"enabled: true" was the whole answer, and read as healthy while every
    request was being refused."""

    def test_reachability_is_unknown_before_anything_is_attempted(self):
        from services.judiciary_service import JudiciaryService

        assert JudiciaryService().health_check()["reachable"] is None

    def test_a_failure_is_recorded(self):
        from services.judiciary_service import JudiciaryService

        service = JudiciaryService()
        service._record_outcome("403 Client Error: Forbidden")
        health = service.health_check()
        assert health["reachable"] is False
        assert "403" in health["last_error"]

    def test_a_success_clears_the_error(self):
        from services.judiciary_service import JudiciaryService

        service = JudiciaryService()
        service._record_outcome("boom")
        service._record_outcome(None)
        assert service.health_check() == {**service.health_check(), "reachable": True}
        assert service.health_check()["last_error"] is None


class TestRateLimitBackoff:
    """
    A 429 is an instruction, not a failure.

    The old behaviour treated it as the second: the exception propagated, the
    caller logged a failed search and moved on to the next topic at the same
    pace. A corpus-discovery run lost 21 of 36 topics that way, each refusal
    arriving faster than the request that caused it.
    """

    @staticmethod
    def _service_returning(statuses, monkeypatch):
        """A service whose successive GETs return the given status codes."""
        monkeypatch.setattr("services.judiciary_service.time.sleep", lambda _: None)
        session = MagicMock()
        responses = []
        for status in statuses:
            response = MagicMock()
            response.status_code = status
            response.text = SEARCH_HTML
            response.headers = {}
            response.raise_for_status = MagicMock(
                side_effect=None if status == 200 else RuntimeError(f"{status}")
            )
            responses.append(response)
        session.get.side_effect = responses
        service = JudiciaryService(session=session)
        service._disallowed = set()
        return service, session

    def test_a_429_is_retried_rather_than_surfaced(self, monkeypatch):
        service, session = self._service_returning([429, 200], monkeypatch)
        response = service._get("https://example.test/")
        assert response.status_code == 200
        assert session.get.call_count == 2

    def test_the_interval_widens_after_a_429(self, monkeypatch):
        service, _ = self._service_returning([429, 200], monkeypatch)
        before = service._interval
        service._get("https://example.test/")
        assert service._interval > before

    def test_retries_are_bounded(self, monkeypatch):
        """
        A caller that never gets an answer cannot fall back to the local
        corpus, so retrying forever to be polite is its own kind of rude.
        """
        from services.judiciary_service import MAX_RETRIES

        service, session = self._service_returning(
            [429] * (MAX_RETRIES + 1), monkeypatch
        )
        with pytest.raises(RuntimeError):
            service._get("https://example.test/")
        assert session.get.call_count == MAX_RETRIES + 1

    def test_retry_after_is_honoured_over_our_own_guess(self):
        """The source telling us exactly what it wants beats our estimate."""
        service = JudiciaryService(session=MagicMock())
        assert service._back_off(retry_after="120") == 120.0

    def test_a_junk_retry_after_falls_back_to_the_interval(self):
        service = JudiciaryService(session=MagicMock())
        assert service._back_off(retry_after="Wed, 21 Oct 2026 07:28:00 GMT") > 0

    def test_the_interval_has_a_ceiling(self):
        from services.judiciary_service import MAX_REQUEST_INTERVAL

        service = JudiciaryService(session=MagicMock())
        for _ in range(50):
            service._back_off()
        assert service._interval == MAX_REQUEST_INTERVAL

    def test_the_interval_never_narrows_again(self, monkeypatch):
        """
        The pace it refused once it will refuse again. A run that recovers
        only to re-trip is worse for the source than one that slows down.
        """
        service, _ = self._service_returning([429, 200, 200], monkeypatch)
        service._get("https://example.test/")
        widened = service._interval
        service._get("https://example.test/")
        assert service._interval == widened
