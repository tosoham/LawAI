"""
What the API says when a request is wrong.

Error responses are part of the contract and are the easiest place to leak
something. On this API a request body is a legal question or a set of case
details, which makes a verbatim echo a privacy problem rather than a
debugging convenience.
"""
import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture(scope="module")
def client():
    return TestClient(main.app)


class TestValidationErrorsDoNotEchoTheRequest:
    """
    A 422 says which field was wrong. It must not say what was in it.

    On this API a request body is a legal question or a set of case details.
    The handler used to return `exc.errors()` and `str(exc.body)` verbatim: a
    draft request rejected for a missing field echoed "Jane Doe, PAN
    ABCDE1234F" twice into the response, and into a log line that outlives the
    request by however long logs are kept. A caller already knows what they
    sent; they need the field and the reason.
    """

    def test_the_body_is_not_returned(self, client):
        response = client.post(
            "/api/v1/documents/draft",
            json={
                "document_type": "bail_application",
                "details": {"accused_name": "Jane Doe, PAN ABCDE1234F"},
            },
        )
        assert response.status_code == 422
        assert "ABCDE1234F" not in response.text
        assert "Jane Doe" not in response.text
        assert "body" not in response.json()

    def test_the_offending_field_is_still_named(self, client):
        """Useless errors get worked around rather than fixed."""
        response = client.post("/api/v1/documents/draft", json={"document_type": "x"})
        fields = [d["field"] for d in response.json()["details"]]
        assert any("case_details" in f for f in fields)
        assert all(d["problem"] for d in response.json()["details"])
