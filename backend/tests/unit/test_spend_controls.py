"""
The two things that must hold before a public URL exists.

Both were found while planning the deployment rather than while writing the
code, and both fail silently:

* **there was no rate limiting at all.** `API_RATE_LIMIT` has been in
  `.env.example` since the beginning and was read by nothing. Harmless on
  localhost; on a public address in front of a paid model key it is an open tap,
  and each pull also costs 8 to 13 seconds of a single-process service.
* **the session cookie would not have survived a split-domain deployment.**
  `SameSite=Lax` is right for localhost and wrong for a Vercel frontend talking
  to a Hugging Face Space: the cookie is simply not sent cross-site, so sign-in
  appears to succeed and every request after it arrives anonymous.
"""
import importlib
import tempfile
from unittest.mock import patch

import pytest

from services.rate_limit import limiter


@pytest.fixture(autouse=True)
def clean_limiter(monkeypatch):
    """A small budget, and no state carried between tests."""
    monkeypatch.setenv("API_RATE_LIMIT", "3")
    monkeypatch.setenv("API_RATE_LIMIT_PERIOD", "60")
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
    monkeypatch.setenv("SESSION_SECRET", "a-test-secret-long-enough-to-be-real")
    monkeypatch.setenv("API_RATE_LIMIT", "3")
    monkeypatch.setenv("API_RATE_LIMIT_PERIOD", "60")

    import models.db as db

    importlib.reload(db)
    db.init_db()

    import main

    importlib.reload(main)
    from fastapi.testclient import TestClient

    return TestClient(main.app)


def ask(client):
    return client.post(
        "/api/v1/search/rag",
        json={"query": "murder", "collection": "bns_sections", "top_k": 1},
    )


class TestRateLimit:
    def test_the_budget_runs_out(self):
        for _ in range(3):
            assert limiter.check("someone")[0]
        allowed, retry_after = limiter.check("someone")
        assert not allowed
        assert retry_after > 0

    def test_budgets_are_per_key(self):
        """Keyed by account, not by IP: an IP is shared by an office NAT and
        changes for a phone between cells, so it punishes the wrong people and
        misses the right ones."""
        for _ in range(3):
            limiter.check("asha")
        assert limiter.check("bala")[0]

    def test_a_window_that_has_passed_frees_the_budget(self):
        import time as real_time

        import services.rate_limit as module

        for _ in range(3):
            limiter.check("someone")
        assert not limiter.check("someone")[0]

        # Advanced from the *current* clock, not from zero. `monotonic` counts
        # from an arbitrary origin -- on a machine up for hours it is already
        # far past any constant, so pinning it to 10_000 moved the clock
        # backwards and the window never cleared.
        later = real_time.monotonic() + 3600
        with patch.object(module.time, "monotonic", return_value=later):
            assert limiter.check("someone")[0]

    def test_a_limit_of_zero_disables_it(self, monkeypatch):
        monkeypatch.setenv("API_RATE_LIMIT", "0")
        for _ in range(50):
            assert limiter.check("someone")[0]

    def test_an_over_budget_request_is_refused_with_retry_after(self, client):
        for _ in range(3):
            assert ask(client).status_code == 200
        response = ask(client)

        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) > 0

    def test_free_routes_are_not_limited(self, client):
        """The deterministic layer costs nothing and demonstrates the system
        without spending. Limiting it would only make the app look broken."""
        for _ in range(10):
            assert client.get("/api/v1/offences/BNS/103").status_code == 200


class TestSignInGate:
    def test_answering_is_open_by_default(self, client):
        """Localhost and any deployment without Google credentials work exactly
        as they did before accounts existed."""
        assert ask(client).status_code == 200

    def test_answering_is_refused_without_an_account_when_required(
        self, client, monkeypatch
    ):
        monkeypatch.setenv("REQUIRE_SIGN_IN", "true")
        response = ask(client)

        assert response.status_code == 401
        assert "Sign in" in response.json()["detail"]

    def test_the_free_layer_stays_open_even_then(self, client, monkeypatch):
        monkeypatch.setenv("REQUIRE_SIGN_IN", "true")
        assert client.get("/api/v1/offences/BNS/103").status_code == 200
        assert client.get("/health").status_code == 200

    def test_requiring_sign_in_with_no_way_to_sign_in_is_fatal(self, monkeypatch):
        """
        Serving 401 to everyone forever looks broken rather than
        misconfigured, and nobody would diagnose it from a healthy container.
        The broad `except` in startup exists so a missing LLM key leaves
        /health up; this must not be swallowed by it.
        """
        monkeypatch.setenv("REQUIRE_SIGN_IN", "true")
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.setenv("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))

        import main

        importlib.reload(main)
        from fastapi.testclient import TestClient

        with pytest.raises(RuntimeError, match="REQUIRE_SIGN_IN"):
            with TestClient(main.app):
                pass


class TestCookiePolicy:
    def test_lax_and_secure_by_default(self, monkeypatch):
        monkeypatch.delenv("COOKIE_SAMESITE", raising=False)
        monkeypatch.delenv("AUTH_INSECURE_COOKIES", raising=False)
        from services.auth import _cookie_policy

        assert _cookie_policy() == ("lax", True)

    def test_localhost_may_drop_secure(self, monkeypatch):
        monkeypatch.setenv("AUTH_INSECURE_COOKIES", "true")
        from services.auth import _cookie_policy

        assert _cookie_policy() == ("lax", False)

    def test_cross_site_needs_none(self, monkeypatch):
        """
        A Vercel frontend and a Hugging Face Space backend are different sites.
        A Lax cookie is never sent between them, so sign-in would appear to
        work and every request after it would arrive anonymous.
        """
        monkeypatch.setenv("COOKIE_SAMESITE", "none")
        from services.auth import _cookie_policy

        assert _cookie_policy() == ("none", True)

    def test_none_forces_secure_whatever_else_is_set(self, monkeypatch):
        """Browsers reject `SameSite=None` without `Secure` outright, so the
        combination is corrected here rather than shipped."""
        monkeypatch.setenv("COOKIE_SAMESITE", "none")
        monkeypatch.setenv("AUTH_INSECURE_COOKIES", "true")
        from services.auth import _cookie_policy

        assert _cookie_policy() == ("none", True)

    def test_an_invalid_value_falls_back_to_lax(self, monkeypatch):
        monkeypatch.setenv("COOKIE_SAMESITE", "sometimes")
        from services.auth import _cookie_policy

        assert _cookie_policy()[0] == "lax"
