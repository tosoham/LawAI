"""
Live judiciary data access for LawAI.

The ChromaDB corpus is a snapshot: it holds the complete 2023 codes and a
curated set of landmark judgements, but nothing decided after ingestion. This
service fetches current material from authentic public sources at query time so
the agent can answer questions about recent case law.

Sources
-------
Indian Kanoon (https://indiankanoon.org) - full-text search and judgement text
covering the Supreme Court, High Courts and tribunals. Its robots.txt permits
``/search/`` and ``/doc/`` for generic agents while listing several thousand
individual documents as disallowed; that list is parsed and honoured.

Operating rules
---------------
- Requests are rate limited and cached, because this is a free public service.
- Every result carries its court, date and source URL. A live result is
  unverified retrieved material, not curated corpus content, and callers are
  expected to present it with attribution.
- Failures are returned, never raised into the request path: if the source is
  slow or unreachable the agent should fall back to the local corpus rather
  than error.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://indiankanoon.org"
USER_AGENT = "LawAI/1.0 (legal research assistant; +https://github.com/tosoham/LawAI)"

DEFAULT_TIMEOUT = float(os.getenv("JUDICIARY_TIMEOUT_SECONDS", "20"))
MIN_REQUEST_INTERVAL = float(os.getenv("JUDICIARY_MIN_REQUEST_INTERVAL", "2.5"))
# The ceiling the adaptive interval may widen to, and how fast it widens. A
# discovery run at one request per second drew 429 on 21 of 36 searches; the
# floor above was raised on that evidence, and the rest is the source's to
# decide at run time.
MAX_REQUEST_INTERVAL = float(os.getenv("JUDICIARY_MAX_REQUEST_INTERVAL", "30.0"))
BACKOFF_FACTOR = float(os.getenv("JUDICIARY_BACKOFF_FACTOR", "2.0"))
# How many times a single request may be retried after a 429 before the caller
# is told it failed. Bounded, because a caller that never gets an answer cannot
# fall back to the local corpus.
MAX_RETRIES = int(os.getenv("JUDICIARY_MAX_RETRIES", "3"))
SEARCH_CACHE_TTL = float(os.getenv("JUDICIARY_SEARCH_CACHE_TTL", "900"))      # 15 min
JUDGEMENT_CACHE_TTL = float(os.getenv("JUDICIARY_DOC_CACHE_TTL", "86400"))    # 24 h
MAX_JUDGEMENT_CHARS = int(os.getenv("JUDICIARY_MAX_DOC_CHARS", "20000"))
CACHE_MAX_ENTRIES = 256

#: Courts the caller may target, mapped to Indian Kanoon's doctypes filter.
COURTS: dict[str, str] = {
    "supremecourt": "supremecourt",
    "highcourts": "highcourts",
    "tribunals": "tribunals",
    "all": "",
}


def live_fetching_enabled() -> bool:
    """
    Whether live lookups are permitted.

    Read at call time rather than import time so tests and deployments can flip
    it without reimporting the module.
    """
    return os.getenv("ENABLE_LIVE_JUDICIARY", "true").strip().lower() not in {
        "0", "false", "no", "off",
    }


@dataclass
class JudgementResult:
    """One search hit, with everything needed to cite it."""

    doc_id: str
    title: str
    court: str
    date: str
    snippet: str
    source_url: str
    cited_by: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "court": self.court,
            "date": self.date,
            "snippet": self.snippet,
            "source_url": self.source_url,
            "cited_by": self.cited_by,
            "source": "Indian Kanoon (live)",
        }


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


@dataclass
class _Cache:
    """Small TTL cache; live lookups are expensive and often repeated."""

    ttl: float
    entries: dict[str, _CacheEntry] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def get(self, key: str) -> Any | None:
        with self.lock:
            entry = self.entries.get(key)
            if entry is None:
                return None
            if entry.expires_at < time.monotonic():
                del self.entries[key]
                return None
            return entry.value

    def set(self, key: str, value: Any) -> None:
        with self.lock:
            if len(self.entries) >= CACHE_MAX_ENTRIES:
                oldest = min(self.entries, key=lambda k: self.entries[k].expires_at)
                del self.entries[oldest]
            self.entries[key] = _CacheEntry(value, time.monotonic() + self.ttl)

    def clear(self) -> None:
        with self.lock:
            self.entries.clear()


class JudiciaryService:
    """Fetches current case law from authentic public judiciary sources."""

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._search_cache = _Cache(SEARCH_CACHE_TTL)
        self._doc_cache = _Cache(JUDGEMENT_CACHE_TTL)
        self._disallowed: set[str] | None = None
        self._last_request_at = 0.0
        # Widened by _back_off when the source says we are going too fast, and
        # never narrowed again within the process: the pace it refused once it
        # will refuse again, and a run that recovers only to re-trip is worse
        # for the source than one that simply slows down.
        self._interval = MIN_REQUEST_INTERVAL
        self._request_lock = threading.Lock()
        self._reachable: bool | None = None
        self._last_error: str | None = None

    # -- politeness ------------------------------------------------------

    def _throttle(self) -> None:
        """
        Space out requests; this is a free public service.

        The interval is a floor that rises when the server says it should. A
        corpus-discovery run at one request per second drew **429 on 21 of 36
        searches** -- the source's own statement that the pace was too fast --
        and once it starts refusing, every subsequent request in the run is
        wasted work for both sides. ``_back_off`` widens the floor for the rest
        of the process on each 429, so a long run settles at a rate the source
        tolerates rather than hammering at one it has already declined.
        """
        with self._request_lock:
            elapsed = time.monotonic() - self._last_request_at
            wait = max(MIN_REQUEST_INTERVAL, self._interval) - elapsed
            if wait > 0:
                time.sleep(wait)
            self._last_request_at = time.monotonic()

    def _back_off(self, retry_after: str | None = None) -> float:
        """
        Widen the request interval after a 429, and say how long to wait now.

        ``Retry-After`` is honoured when the server sends one: it is the
        source telling us exactly what it wants, and guessing over the top of
        an explicit instruction is the rude version of this.
        """
        with self._request_lock:
            self._interval = min(self._interval * BACKOFF_FACTOR, MAX_REQUEST_INTERVAL)
            interval = self._interval
        if retry_after:
            try:
                return max(float(retry_after), interval)
            except ValueError:
                pass
        return interval

    def _get(self, url: str, **kwargs: Any) -> requests.Response:
        """
        A throttled GET that retries when the source says to slow down.

        A 429 is not a failure, it is an instruction, and the old behaviour
        treated it as the first: the exception propagated, the caller logged a
        failed search and moved straight on to the next one at the same pace.
        A discovery run lost 21 of 36 topics that way, each failure arriving
        faster than the request that caused it.

        Retries are bounded. A caller that never gets an answer cannot fall
        back to the local corpus, and blocking a request path indefinitely to
        be polite to a source is its own kind of rude.
        """
        for attempt in range(MAX_RETRIES + 1):
            self._throttle()
            response = self.session.get(url, **kwargs)
            if response.status_code != 429:
                response.raise_for_status()
                return response

            if attempt == MAX_RETRIES:
                response.raise_for_status()

            wait = self._back_off(response.headers.get("Retry-After"))
            logger.warning(
                f"429 from {url}; waiting {wait:.1f}s and widening the request "
                f"interval to {self._interval:.1f}s "
                f"(attempt {attempt + 1}/{MAX_RETRIES})"
            )
            time.sleep(wait)

        raise RuntimeError("unreachable")  # pragma: no cover

    def _load_disallowed(self) -> set[str] | None:
        """
        Document ids robots.txt puts off limits for generic agents.

        Returns ``None`` when robots.txt could not be read at all, which is a
        different thing from an empty disallow list and has to stay
        distinguishable: the caller must not fetch on the strength of a list it
        never obtained.
        """
        if self._disallowed is not None:
            return self._disallowed

        disallowed: set[str] = set()
        try:
            response = self._get(f"{BASE_URL}/robots.txt", timeout=DEFAULT_TIMEOUT)
            applies = False
            for line in response.text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                lowered = line.lower()
                if lowered.startswith("user-agent:"):
                    applies = line.split(":", 1)[1].strip() == "*"
                    continue
                if applies and lowered.startswith("disallow:"):
                    match = re.match(
                        r"^/doc(?:fragment)?/+(\d+)", line.split(":", 1)[1].strip()
                    )
                    if match:
                        disallowed.add(match.group(1))
        except Exception as exc:
            # Not cached: an unreadable robots.txt is usually transient, and
            # caching the failure would keep the source off limits for the
            # life of the process after one bad response.
            logger.warning(f"Could not read robots.txt ({exc}); treating every document as off limits")
            return None

        self._disallowed = disallowed
        logger.info(f"Judiciary source lists {len(disallowed)} disallowed documents")
        return disallowed

    def is_allowed(self, doc_id: str) -> bool:
        """
        Whether robots.txt permits fetching a document.

        Fails **closed**. If robots.txt cannot be read there is no list to
        check against, and answering "allowed" would mean fetching documents
        the source may well have excluded -- the disallow list names several
        thousand of them individually. Not knowing is not permission.
        """
        disallowed = self._load_disallowed()
        if disallowed is None:
            return False
        return doc_id not in disallowed

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _format_date(value: str | date | None) -> str | None:
        """Indian Kanoon expects D-M-YYYY."""
        if value is None:
            return None
        if isinstance(value, date):
            return f"{value.day}-{value.month}-{value.year}"
        text = str(value).strip()
        if not text:
            return None
        iso = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
        if iso:
            year, month, day = iso.groups()
            return f"{int(day)}-{int(month)}-{year}"
        if re.fullmatch(r"\d{4}", text):
            return f"1-1-{text}"
        return text

    @staticmethod
    def _split_title_and_date(title: str) -> tuple[str, str]:
        """Search titles read 'X vs Y on 13 February, 2026'."""
        match = re.search(r"\s+on\s+(\d{1,2}\s+\w+,\s*\d{4})\s*$", title)
        if match:
            return title[: match.start()].strip(), match.group(1).strip()
        return title.strip(), ""

    def _build_query(
        self,
        query: str,
        court: str,
        from_date: str | date | None,
        to_date: str | date | None,
    ) -> str:
        parts = [query.strip()]
        doctype = COURTS.get(court, "")
        if doctype:
            parts.append(f"doctypes:{doctype}")
        start = self._format_date(from_date)
        end = self._format_date(to_date)
        if start:
            parts.append(f"fromdate:{start}")
        if end:
            parts.append(f"todate:{end}")
        elif start:
            today = datetime.now(UTC).date()
            parts.append(f"todate:{today.day}-{today.month}-{today.year}")
        return " ".join(parts)

    # -- public API ------------------------------------------------------

    def search_case_law(
        self,
        query: str,
        court: str = "supremecourt",
        from_date: str | date | None = None,
        to_date: str | date | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        """
        Search current case law.

        Returns a dict with ``success``; on success ``results`` is a list of
        citable hits. Errors are reported, not raised, so the caller can fall
        back to the local corpus.
        """
        if not live_fetching_enabled():
            return {
                "success": False,
                "error": "Live judiciary lookups are disabled (ENABLE_LIVE_JUDICIARY=false)",
                "results": [],
            }

        if not query or not query.strip():
            return {"success": False, "error": "query is required", "results": []}

        if court not in COURTS:
            return {
                "success": False,
                "error": f"Unknown court {court!r}. Choose from {sorted(COURTS)}",
                "results": [],
            }

        limit = max(1, min(int(limit), 20))
        form_input = self._build_query(query, court, from_date, to_date)
        cache_key = f"{form_input}|{limit}"

        cached = self._search_cache.get(cache_key)
        if cached is not None:
            logger.info(f"Live case law search (cached): {form_input}")
            return cached

        try:
            logger.info(f"Live case law search: {form_input}")
            response = self._get(
                f"{BASE_URL}/search/",
                params={"formInput": form_input},
                timeout=DEFAULT_TIMEOUT,
            )
        except Exception as exc:
            logger.error(f"Live case law search failed: {exc}")
            self._record_outcome(str(exc))
            return {"success": False, "error": str(exc), "results": []}

        self._record_outcome(None)

        results = self._parse_search(response.text, limit)
        payload = {
            "success": True,
            "query": query,
            "court": court,
            "search_expression": form_input,
            "num_results": len(results),
            "results": [r.to_dict() for r in results],
            "retrieved_at": datetime.now(UTC).isoformat(),
        }
        self._search_cache.set(cache_key, payload)
        return payload

    def _parse_search(self, html: str, limit: int) -> list[JudgementResult]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[JudgementResult] = []
        seen: set[str] = set()

        for block in soup.select(".result"):
            link = block.select_one(".result_title a")
            if link is None:
                continue
            match = re.search(r"/(\d+)/", link.get("href") or "")
            if not match:
                continue
            doc_id = match.group(1)
            if doc_id in seen or not self.is_allowed(doc_id):
                continue
            seen.add(doc_id)

            title, judgement_date = self._split_title_and_date(
                link.get_text(" ", strip=True)
            )
            source_el = block.select_one(".docsource")
            snippet_el = block.select_one(".headline")

            cited_by = None
            for tag in block.select(".cite_tag"):
                cited = re.search(r"Cited by (\d+)", tag.get_text(strip=True))
                if cited:
                    cited_by = int(cited.group(1))

            results.append(
                JudgementResult(
                    doc_id=doc_id,
                    title=title,
                    court=source_el.get_text(strip=True) if source_el else "",
                    date=judgement_date,
                    snippet=(
                        re.sub(r"\s+", " ", snippet_el.get_text(" ", strip=True))[:600]
                        if snippet_el else ""
                    ),
                    source_url=f"{BASE_URL}/doc/{doc_id}/",
                    cited_by=cited_by,
                )
            )
            if len(results) >= limit:
                break

        return results

    def fetch_judgment(self, doc_id: str, max_chars: int | None = None) -> dict[str, Any]:
        """Fetch the text of one judgement by its Indian Kanoon document id."""
        if not live_fetching_enabled():
            return {
                "success": False,
                "error": "Live judiciary lookups are disabled (ENABLE_LIVE_JUDICIARY=false)",
            }

        doc_id = str(doc_id).strip()
        if not doc_id.isdigit():
            return {"success": False, "error": f"Invalid document id {doc_id!r}"}

        if not self.is_allowed(doc_id):
            return {
                "success": False,
                "error": f"Document {doc_id} is disallowed by the source's robots.txt",
            }

        limit = max_chars or MAX_JUDGEMENT_CHARS
        cache_key = f"{doc_id}|{limit}"
        cached = self._doc_cache.get(cache_key)
        if cached is not None:
            return cached

        url = f"{BASE_URL}/doc/{doc_id}/"
        try:
            logger.info(f"Fetching judgement {doc_id}")
            response = self._get(url, timeout=DEFAULT_TIMEOUT)
        except Exception as exc:
            logger.error(f"Fetching judgement {doc_id} failed: {exc}")
            self._record_outcome(str(exc))
            return {"success": False, "error": str(exc)}

        self._record_outcome(None)

        soup = BeautifulSoup(response.text, "html.parser")
        title_el = soup.select_one(".doc_title")
        body_el = soup.select_one(".judgments") or soup.select_one(".maindoc")
        if title_el is None or body_el is None:
            return {"success": False, "error": f"Could not parse judgement {doc_id}"}

        raw_title = title_el.get_text(" ", strip=True)
        title, judgement_date = self._split_title_and_date(raw_title)
        text = re.sub(r"\n{3,}", "\n\n", body_el.get_text("\n", strip=True))
        truncated = len(text) > limit
        if truncated:
            text = text[:limit].rsplit("\n", 1)[0] + "\n\n[Judgement truncated]"

        citation_el = soup.select_one(".doc_citations")
        bench_el = soup.select_one(".doc_bench")

        payload = {
            "success": True,
            "doc_id": doc_id,
            "title": title,
            "date": judgement_date,
            "citation": (
                re.sub(r"^Equivalent citations:\s*", "",
                       citation_el.get_text(" ", strip=True))
                if citation_el else ""
            ),
            "bench": (
                bench_el.get_text(" ", strip=True).replace("Bench:", "").strip()
                if bench_el else ""
            ),
            "text": text,
            "truncated": truncated,
            "source_url": url,
            "source": "Indian Kanoon (live)",
            "retrieved_at": datetime.now(UTC).isoformat(),
        }
        self._doc_cache.set(cache_key, payload)
        return payload

    def health_check(self) -> dict[str, Any]:
        """
        Report configuration, and whether the source last answered.

        ``reachable`` is recorded from real traffic rather than probed: a
        health check that calls out on every request adds load to a source we
        rate-limit ourselves against. It stays ``None`` until something has
        been attempted, which is honest about knowing nothing yet.

        This exists because "enabled: true" was the whole answer, and read as
        healthy while every request was being refused.
        """
        return {
            "enabled": live_fetching_enabled(),
            "source": BASE_URL,
            "reachable": self._reachable,
            "last_error": self._last_error,
            "timeout_seconds": DEFAULT_TIMEOUT,
            "min_request_interval": MIN_REQUEST_INTERVAL,
            "cached_searches": len(self._search_cache.entries),
            "cached_judgements": len(self._doc_cache.entries),
        }

    def _record_outcome(self, error: str | None) -> None:
        """Remember whether the source answered, for the health check."""
        self._reachable = error is None
        self._last_error = error

    def clear_caches(self) -> None:
        self._search_cache.clear()
        self._doc_cache.clear()


_judiciary_service: JudiciaryService | None = None


def get_judiciary_service() -> JudiciaryService:
    """Get or create the global judiciary service instance."""
    global _judiciary_service
    if _judiciary_service is None:
        _judiciary_service = JudiciaryService()
    return _judiciary_service


def reset_judiciary_service() -> None:
    """Reset the singleton (useful for tests)."""
    global _judiciary_service
    _judiciary_service = None
