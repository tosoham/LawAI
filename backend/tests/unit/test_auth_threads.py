"""
Accounts, and conversations that belong to exactly one of them.

The property this file exists for is isolation. A thread id is a small
integer, so an endpoint that fetched by id alone would serve one person's legal
questions to anyone who counted upwards — and a legal question is often the
most sensitive thing a person will type anywhere. Every handler filters by the
signed-in user *in the query*, and the tests below try to get round it.

The Google token is stubbed. What is being tested is what this service does
with verified claims, not whether Google's library verifies tokens; calling out
to Google in a unit test would test the network.
"""
import tempfile
from unittest.mock import patch

import pytest


@pytest.fixture
def app(monkeypatch):
    """A fresh database and a configured, insecure-cookie app."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + tempfile.mktemp(suffix=".db"))
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test.apps.googleusercontent.com")
    monkeypatch.setenv("SESSION_SECRET", "a-test-secret-long-enough-to-be-real")
    monkeypatch.setenv("AUTH_INSECURE_COOKIES", "true")

    import importlib

    import models.db as db

    importlib.reload(db)
    db.init_db()

    import main

    importlib.reload(main)
    return main.app


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)


def sign_in(client, sub: str, email: str):
    """Sign a client in as a given Google identity."""
    claims = {
        "sub": sub,
        "email": email,
        "email_verified": True,
        "name": email.split("@")[0],
        "iss": "https://accounts.google.com",
    }
    # Patched where it is *used*, not where it is defined: `api/v1/auth.py`
    # binds the name at import, so patching `services.auth` leaves the router
    # holding the original.
    with patch("api.v1.auth.verify_google_token", return_value=claims):
        response = client.post("/api/v1/auth/google", json={"credential": "x" * 40})
    assert response.status_code == 200
    return response


class TestSignIn:
    def test_signing_in_creates_an_account_and_a_session(self, client):
        body = sign_in(client, "sub-1", "asha@example.com").json()
        assert body["signed_in"] and body["email"] == "asha@example.com"
        assert client.get("/api/v1/auth/me").json()["signed_in"]

    def test_signing_in_twice_reuses_the_account(self, client):
        """
        Keyed on Google's `sub`, not the email. An address can be reassigned
        inside a Workspace domain, and if it were the key the new holder would
        inherit the previous person's conversations.
        """
        sign_in(client, "sub-1", "asha@example.com")
        client.post("/api/v1/threads")
        sign_in(client, "sub-1", "asha.renamed@example.com")

        assert len(client.get("/api/v1/threads").json()) == 1

    def test_an_unverified_email_is_refused(self, client):
        claims = {"sub": "s", "email": "x@y.z", "email_verified": False,
                  "iss": "https://accounts.google.com"}
        from services.auth import verify_google_token

        with patch("google.oauth2.id_token.verify_oauth2_token", return_value=claims):
            with pytest.raises(Exception) as caught:
                verify_google_token("token")
        assert "verified email" in str(caught.value)

    def test_logging_out_ends_the_session(self, client):
        sign_in(client, "sub-1", "asha@example.com")
        client.post("/api/v1/auth/logout")

        assert not client.get("/api/v1/auth/me").json()["signed_in"]
        assert client.get("/api/v1/threads").status_code == 401

    def test_a_forged_cookie_is_refused(self, client):
        """The cookie is signed. Anyone can write a plausible-looking one."""
        client.cookies.set("lawai_session", "not-a-real-signature")
        assert client.get("/api/v1/threads").status_code == 401


class TestIsolation:
    """The reason this file exists."""

    def test_one_account_cannot_read_anothers_conversation(self, client):
        sign_in(client, "sub-a", "asha@example.com")
        thread = client.post("/api/v1/threads").json()
        client.post(
            f"/api/v1/threads/{thread['id']}/messages",
            json={"role": "user", "content": "my bail application"},
        )

        sign_in(client, "sub-b", "bala@example.com")
        assert client.get(f"/api/v1/threads/{thread['id']}").status_code == 404

    def test_a_stranger_gets_404_not_403(self, client):
        """
        403 would confirm the id is real, which is the one thing an
        enumeration attack is looking for.
        """
        sign_in(client, "sub-a", "asha@example.com")
        thread = client.post("/api/v1/threads").json()

        sign_in(client, "sub-b", "bala@example.com")
        assert client.get(f"/api/v1/threads/{thread['id']}").status_code == 404

    def test_one_account_cannot_write_into_anothers_conversation(self, client):
        sign_in(client, "sub-a", "asha@example.com")
        thread = client.post("/api/v1/threads").json()

        sign_in(client, "sub-b", "bala@example.com")
        response = client.post(
            f"/api/v1/threads/{thread['id']}/messages",
            json={"role": "user", "content": "injected"},
        )
        assert response.status_code == 404

    def test_one_account_cannot_delete_anothers_conversation(self, client):
        sign_in(client, "sub-a", "asha@example.com")
        thread = client.post("/api/v1/threads").json()

        sign_in(client, "sub-b", "bala@example.com")
        assert client.delete(f"/api/v1/threads/{thread['id']}").status_code == 404

        sign_in(client, "sub-a", "asha@example.com")
        assert client.get(f"/api/v1/threads/{thread['id']}").status_code == 200

    def test_listing_shows_only_your_own(self, client):
        sign_in(client, "sub-a", "asha@example.com")
        client.post("/api/v1/threads")
        client.post("/api/v1/threads")

        sign_in(client, "sub-b", "bala@example.com")
        assert client.get("/api/v1/threads").json() == []


class TestConversationsSurvive:
    """The whole point: a refresh used to lose everything."""

    def test_a_conversation_reads_back_after_signing_in_again(self, client):
        sign_in(client, "sub-a", "asha@example.com")
        thread = client.post("/api/v1/threads").json()
        client.post(
            f"/api/v1/threads/{thread['id']}/messages",
            json={"role": "user", "content": "is murder bailable"},
        )
        client.post(
            f"/api/v1/threads/{thread['id']}/messages",
            json={
                "role": "assistant",
                "content": "Murder is non-bailable.",
                "payload": {"claims": [{"epistemic_class": "classification"}]},
            },
        )

        client.post("/api/v1/auth/logout")
        sign_in(client, "sub-a", "asha@example.com")

        detail = client.get(f"/api/v1/threads/{thread['id']}").json()
        assert [m["content"] for m in detail["messages"]] == [
            "is murder bailable",
            "Murder is non-bailable.",
        ]

    def test_the_structured_half_survives_too(self, client):
        """
        Without the payload a reloaded conversation shows prose and loses the
        claim types, the citations and the record of what was removed — the
        part that makes an answer defensible.
        """
        sign_in(client, "sub-a", "asha@example.com")
        thread = client.post("/api/v1/threads").json()
        payload = {
            "claims": [{"text": "x", "epistemic_class": "statute"}],
            "removed": 1,
        }
        client.post(
            f"/api/v1/threads/{thread['id']}/messages",
            json={"role": "assistant", "content": "answer", "payload": payload},
        )

        detail = client.get(f"/api/v1/threads/{thread['id']}").json()
        assert detail["messages"][0]["payload"] == payload

    def test_the_title_comes_from_the_first_question(self, client):
        """A list of conversations should read as a list of questions."""
        sign_in(client, "sub-a", "asha@example.com")
        thread = client.post("/api/v1/threads").json()
        client.post(
            f"/api/v1/threads/{thread['id']}/messages",
            json={"role": "user", "content": "what is the punishment for theft"},
        )

        assert client.get("/api/v1/threads").json()[0]["title"] == (
            "what is the punishment for theft"
        )

    def test_deleting_removes_the_messages_too(self, client):
        """A real delete. Someone removing a question about their own matter
        means it should be gone."""
        sign_in(client, "sub-a", "asha@example.com")
        thread = client.post("/api/v1/threads").json()
        client.post(
            f"/api/v1/threads/{thread['id']}/messages",
            json={"role": "user", "content": "sensitive"},
        )
        client.delete(f"/api/v1/threads/{thread['id']}")

        import models.db as db

        with db.SessionLocal() as session:
            assert session.query(db.Message).count() == 0


class TestWithoutGoogleConfigured:
    def test_the_api_says_sign_in_is_unavailable(self, monkeypatch, client):
        """
        A deployment with no Google credentials is a valid one: every other
        endpoint works without an account, and only history needs identity.
        """
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        assert client.get("/api/v1/auth/config").json()["enabled"] is False
