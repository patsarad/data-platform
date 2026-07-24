"""Configuration helpers for the data platform project."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"

# Load local environment variables without overriding values already present
# in the shell or deployment environment.
load_dotenv(dotenv_path=ENV_FILE, override=False)


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    igdb_client_id: str = ""
    igdb_client_secret: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "gaming_analytics"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_schema: str = "analytics"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from environment variables."""

        return cls(
            igdb_client_id=os.getenv("igdb_client_id", ""),
            igdb_client_secret=os.getenv("igdb_client_secret", ""),
            postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
            postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
            postgres_db=os.getenv("POSTGRES_DB", "gaming_analytics"),
            postgres_user=os.getenv("POSTGRES_USER", "postgres"),
            postgres_password=os.getenv("POSTGRES_PASSWORD", "postgres"),
            postgres_schema=os.getenv("POSTGRES_SCHEMA", "analytics"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings.from_env()
