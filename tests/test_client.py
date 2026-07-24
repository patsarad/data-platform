"""Tests for the reusable IGDB API client."""

from __future__ import annotations

from typing import Any

import pytest
import requests

from src.ingestion.client import IGDBClient, IGDBClientError


class FakeTokenManager:
    """Minimal token manager stub for client testing."""

    def __init__(self, client_id: str = "client-id") -> None:
        self.client_id = client_id
        self.tokens = ["token-1", "token-2"]
        self._token = object()
        self.calls = 0

    def get_access_token(self) -> str:
        """Return the next token in sequence."""

        token = self.tokens[min(self.calls, len(self.tokens) - 1)]
        self.calls += 1
        return token


class FakeResponse:
    """Minimal fake response for request mocking."""

    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        """Raise an HTTP error for 4xx and 5xx responses."""

        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        """Return the mocked JSON payload."""

        return self._payload


class FakeSession:
    """Minimal fake session that records outgoing requests."""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> Any:
        """Record the request and return the next queued response."""

        self.calls.append({"url": url, **kwargs})
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_query_sends_expected_headers_and_body() -> None:
    """Client should send IGDB headers and APIcalypse query body."""

    token_manager = FakeTokenManager()
    session = FakeSession([FakeResponse(200, [{"id": 1, "name": "Halo"}])])
    client = IGDBClient(
        token_manager=token_manager,
        session=session,
        sleep=lambda _: None,
    )

    response = client.query("games", "fields name; limit 1;")

    assert response == [{"id": 1, "name": "Halo"}]
    sent_request = session.calls[0]
    assert sent_request["url"].endswith("/games")
    assert sent_request["data"] == "fields name; limit 1;"
    assert sent_request["headers"]["Client-ID"] == "client-id"
    assert sent_request["headers"]["Authorization"] == "Bearer token-1"
    assert sent_request["headers"]["Content-Type"] == "text/plain"


def test_query_retries_transient_http_failures() -> None:
    """Client should retry transient IGDB failures."""

    token_manager = FakeTokenManager()
    session = FakeSession(
        [
            FakeResponse(503, {"message": "busy"}),
            FakeResponse(200, [{"id": 2, "name": "Celeste"}]),
        ]
    )
    client = IGDBClient(
        token_manager=token_manager,
        session=session,
        sleep=lambda _: None,
    )

    response = client.query("games", "fields name; limit 1;")

    assert response == [{"id": 2, "name": "Celeste"}]
    assert len(session.calls) == 2


def test_query_refreshes_token_after_unauthorized_response() -> None:
    """Client should rebuild headers after a 401 response."""

    token_manager = FakeTokenManager()
    session = FakeSession(
        [
            FakeResponse(401, {"message": "unauthorized"}),
            FakeResponse(200, [{"id": 3, "name": "Portal"}]),
        ]
    )
    client = IGDBClient(
        token_manager=token_manager,
        session=session,
        sleep=lambda _: None,
    )

    response = client.query("games", "fields name; limit 1;")

    assert response == [{"id": 3, "name": "Portal"}]
    assert session.calls[0]["headers"]["Authorization"] == "Bearer token-1"
    assert session.calls[1]["headers"]["Authorization"] == "Bearer token-2"


def test_query_raises_after_retry_exhaustion() -> None:
    """Client should fail once retries are exhausted."""

    token_manager = FakeTokenManager()
    session = FakeSession([requests.Timeout("timeout")] * 3)
    client = IGDBClient(
        token_manager=token_manager,
        session=session,
        max_retries=3,
        sleep=lambda _: None,
    )

    with pytest.raises(IGDBClientError):
        client.query("games", "fields name; limit 1;")
