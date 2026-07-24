"""Authentication helpers for Twitch OAuth and IGDB access."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests

from src.utils.config import get_settings
from src.utils.logger import get_logger


TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TOKEN_REFRESH_BUFFER_SECONDS = 60


class IGDBAuthError(RuntimeError):
    """Raised when Twitch OAuth authentication fails."""


@dataclass(frozen=True)
class OAuthToken:
    """Represents an OAuth access token and its expiration time."""

    access_token: str
    expires_at: float

    def is_expired(self, now: float, refresh_buffer_seconds: int = TOKEN_REFRESH_BUFFER_SECONDS) -> bool:
        """Return True when the token should be refreshed."""

        return now >= self.expires_at - refresh_buffer_seconds


class TwitchTokenManager:
    """Fetch and cache Twitch OAuth tokens for IGDB requests."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        session: requests.Session | None = None,
        timeout_seconds: int = 30,
        clock: Any = time.time,
    ) -> None:
        """Initialize the token manager."""

        self.client_id = client_id
        self.client_secret = client_secret
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.clock = clock
        self.logger = get_logger(__name__)
        self._token: OAuthToken | None = None

    def get_access_token(self) -> str:
        """Return a valid access token, refreshing it when needed."""

        if self._token and not self._token.is_expired(now=float(self.clock())):
            return self._token.access_token

        self._token = self._request_new_token()
        return self._token.access_token

    def _request_new_token(self) -> OAuthToken:
        """Request a new OAuth token from Twitch."""

        if not self.client_id or not self.client_secret:
            raise IGDBAuthError(
                "Missing igdb_client_id or igdb_client_secret environment variables."
            )

        self.logger.info("Requesting a new Twitch OAuth token for IGDB access.")

        try:
            response = self.session.post(
                TOKEN_URL,
                params={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise IGDBAuthError("Unable to retrieve Twitch OAuth token.") from exc

        access_token = payload.get("access_token", "")
        expires_in = int(payload.get("expires_in", 0))

        if not access_token or expires_in <= 0:
            raise IGDBAuthError("Twitch OAuth response did not include a valid token.")

        return OAuthToken(
            access_token=access_token,
            expires_at=float(self.clock()) + expires_in,
        )


def create_token_manager(session: requests.Session | None = None) -> TwitchTokenManager:
    """Build a token manager from environment-backed settings."""

    settings = get_settings()
    return TwitchTokenManager(
        client_id=settings.igdb_client_id,
        client_secret=settings.igdb_client_secret,
        session=session,
    )
