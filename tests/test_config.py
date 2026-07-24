"""Tests for environment-backed configuration loading."""

from src.utils.config import Settings


def test_settings_reads_existing_igdb_environment_variables(monkeypatch) -> None:
    """Settings should read the existing IGDB env var names."""

    monkeypatch.setenv("igdb_client_id", "client-id")
    monkeypatch.setenv("igdb_client_secret", "client-secret")
    monkeypatch.setenv("POSTGRES_PORT", "6543")

    settings = Settings.from_env()

    assert settings.igdb_client_id == "client-id"
    assert settings.igdb_client_secret == "client-secret"
    assert settings.postgres_port == 6543


def test_settings_uses_defaults_when_environment_is_missing(monkeypatch) -> None:
    """Settings should fall back to local development defaults."""

    monkeypatch.delenv("igdb_client_id", raising=False)
    monkeypatch.delenv("igdb_client_secret", raising=False)
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    settings = Settings.from_env()

    assert settings.igdb_client_id == ""
    assert settings.igdb_client_secret == ""
    assert settings.postgres_host == "localhost"
    assert settings.log_level == "INFO"
