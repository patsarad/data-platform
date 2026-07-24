"""Reusable client for querying the IGDB API."""

from __future__ import annotations

import time
from typing import Any

import requests

from src.ingestion.auth import TwitchTokenManager, create_token_manager
from src.utils.logger import get_logger


IGDB_BASE_URL = "https://api.igdb.com/v4"


class IGDBClientError(RuntimeError):
    """Raised when an IGDB API request fails."""


class IGDBClient:
    """Client for sending APIcalypse POST queries to IGDB."""

    def __init__(
        self,
        token_manager: TwitchTokenManager,
        session: requests.Session | None = None,
        base_url: str = IGDB_BASE_URL,
        timeout_seconds: int = 30,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
        sleep: Any = time.sleep,
    ) -> None:
        """Initialize the IGDB client."""

        self.token_manager = token_manager
        self.session = session or requests.Session()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.sleep = sleep
        self.logger = get_logger(__name__)

    def query(self, endpoint: str, query: str) -> list[dict[str, Any]]:
        """Send a POST query to an IGDB endpoint and return the JSON payload."""

        url = f"{self.base_url}/{endpoint.strip('/')}"
        headers = self._build_headers()

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.post(
                    url,
                    data=query,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )

                if response.status_code == 401 and attempt < self.max_retries:
                    self.logger.warning("IGDB token expired or unauthorized. Refreshing token.")
                    self.token_manager._token = None
                    headers = self._build_headers()
                    self._sleep_before_retry(attempt)
                    continue

                if response.status_code in {429, 500, 502, 503, 504}:
                    if attempt < self.max_retries:
                        self.logger.warning(
                            "IGDB request failed with status %s. Retrying attempt %s/%s.",
                            response.status_code,
                            attempt,
                            self.max_retries,
                        )
                        self._sleep_before_retry(attempt)
                        continue

                response.raise_for_status()
                payload = response.json()

                if not isinstance(payload, list):
                    raise IGDBClientError("IGDB response payload was not a list.")

                return payload
            except requests.RequestException as exc:
                if attempt >= self.max_retries:
                    raise IGDBClientError(f"IGDB request failed for endpoint '{endpoint}'.") from exc

                self.logger.warning(
                    "IGDB request raised %s. Retrying attempt %s/%s.",
                    exc.__class__.__name__,
                    attempt,
                    self.max_retries,
                )
                self._sleep_before_retry(attempt)

        raise IGDBClientError(f"IGDB request failed for endpoint '{endpoint}'.")

    def _build_headers(self) -> dict[str, str]:
        """Build headers required for IGDB API requests."""

        access_token = self.token_manager.get_access_token()
        return {
            "Accept": "application/json",
            "Client-ID": self.token_manager.client_id,
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "text/plain",
        }

    def _sleep_before_retry(self, attempt: int) -> None:
        """Sleep using exponential backoff before the next retry."""

        self.sleep(self.retry_backoff_seconds * attempt)


def create_igdb_client(session: requests.Session | None = None) -> IGDBClient:
    """Build an IGDB client from environment-backed settings."""

    token_manager = create_token_manager(session=session)
    return IGDBClient(token_manager=token_manager, session=session)
