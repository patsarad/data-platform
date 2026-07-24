"""Tests for Twitch OAuth token management."""

from __future__ import annotations

from typing import Any

import pytest

from src.ingestion.auth import IGDBAuthError, TwitchTokenManager


class FakeResponse:
    """Minimal fake response for request mocking."""

    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        """Raise for unexpected HTTP status codes."""

        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        """Return the mocked JSON payload."""

        return self._payload


class FakeSession:
    """Minimal fake session that returns queued responses."""

    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        """Record the request and return the next queued response."""

        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def test_token_manager_caches_token_until_expired() -> None:
    """Token manager should reuse an in-memory token before expiry."""

    clock_value = {"now": 1_000.0}

    def clock() -> float:
        return clock_value["now"]

    session = FakeSession(
        [FakeResponse(200, {"access_token": "token-1", "expires_in": 120})]
    )
    token_manager = TwitchTokenManager(
        client_id="client-id",
        client_secret="client-secret",
        session=session,
        clock=clock,
    )

    first_token = token_manager.get_access_token()
    second_token = token_manager.get_access_token()

    assert first_token == "token-1"
    assert second_token == "token-1"
    assert len(session.calls) == 1


def test_token_manager_refreshes_expired_token() -> None:
    """Token manager should fetch a new token after expiration."""

    clock_value = {"now": 1_000.0}

    def clock() -> float:
        return clock_value["now"]

    session = FakeSession(
        [
            FakeResponse(200, {"access_token": "token-1", "expires_in": 120}),
            FakeResponse(200, {"access_token": "token-2", "expires_in": 120}),
        ]
    )
    token_manager = TwitchTokenManager(
        client_id="client-id",
        client_secret="client-secret",
        session=session,
        clock=clock,
    )

    first_token = token_manager.get_access_token()
    clock_value["now"] = 1_061.0
    second_token = token_manager.get_access_token()

    assert first_token == "token-1"
    assert second_token == "token-2"
    assert len(session.calls) == 2


def test_token_manager_requires_igdb_credentials() -> None:
    """Token manager should fail clearly when credentials are missing."""

    token_manager = TwitchTokenManager(
        client_id="",
        client_secret="",
        session=FakeSession([]),
    )

    with pytest.raises(IGDBAuthError):
        token_manager.get_access_token()
