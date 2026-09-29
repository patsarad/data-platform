"""Tests for the implemented entity source-to-raw contracts."""

from dataclasses import FrozenInstanceError

import pytest

from src.entities import COMPANIES, GAMES, GENRES, INVOLVED_COMPANIES, PLATFORMS
from src.ingestion.fetch_companies import DEFAULT_COMPANY_FIELDS
from src.ingestion.fetch_involved_companies import DEFAULT_INVOLVED_COMPANY_FIELDS
from src.ingestion.fetch_games import DEFAULT_GAME_FIELDS
from src.ingestion.fetch_genres import DEFAULT_GENRE_FIELDS
from src.ingestion.fetch_platforms import DEFAULT_PLATFORM_FIELDS


def test_games_contract_preserves_source_and_raw_mapping() -> None:
    """Keep source keys distinct from SQL keys and preserve requested fields."""

    assert GAMES.endpoint == "games"
    assert GAMES.raw_table == "raw_games"
    assert GAMES.source_primary_key == "id"
    assert GAMES.raw_primary_key == "igdb_id"
    assert GAMES.update_field == "updated_at"
    assert GAMES.fields == (
        "id", "name", "slug", "first_release_date", "rating", "rating_count",
        "total_rating", "total_rating_count", "updated_at",
        "genres", "platforms", "involved_companies",
    )
    assert DEFAULT_GAME_FIELDS is GAMES.fields


def test_games_contract_is_immutable() -> None:
    """Shared configuration cannot be accidentally changed by a consumer."""

    with pytest.raises(FrozenInstanceError):
        GAMES.endpoint = "changed"
    with pytest.raises(TypeError):
        GAMES.fields[0] = "changed"


def test_genres_contract() -> None:
    """Keep the genres contract minimal, immutable, and separate from games."""

    assert GENRES.endpoint == "genres"
    assert GENRES.fields == ("id", "name", "slug", "updated_at")
    assert DEFAULT_GENRE_FIELDS is GENRES.fields
    assert GENRES.raw_table == "raw_genres"
    assert GENRES.source_primary_key == "id"
    assert GENRES.raw_primary_key == "igdb_id"
    assert GENRES.update_field == "updated_at"
    with pytest.raises(FrozenInstanceError):
        GENRES.endpoint = "changed"
    with pytest.raises(TypeError):
        GENRES.fields[0] = "changed"


def test_platforms_contract() -> None:
    """Keep platforms minimal and immutable with the established raw key mapping."""

    assert PLATFORMS.endpoint == "platforms"
    assert PLATFORMS.fields == ("id", "name", "slug", "updated_at")
    assert DEFAULT_PLATFORM_FIELDS is PLATFORMS.fields
    assert PLATFORMS.raw_table == "raw_platforms"
    assert PLATFORMS.source_primary_key == "id"
    assert PLATFORMS.raw_primary_key == "igdb_id"
    assert PLATFORMS.update_field == "updated_at"
    with pytest.raises(FrozenInstanceError):
        PLATFORMS.endpoint = "changed"
    with pytest.raises(TypeError):
        PLATFORMS.fields[0] = "changed"


def test_companies_contract() -> None:
    """Keep companies minimal and immutable with the established raw key mapping."""

    assert COMPANIES.endpoint == "companies"
    assert COMPANIES.fields == ("id", "name", "slug", "updated_at")
    assert DEFAULT_COMPANY_FIELDS is COMPANIES.fields
    assert COMPANIES.raw_table == "raw_companies"
    assert COMPANIES.source_primary_key == "id"
    assert COMPANIES.raw_primary_key == "igdb_id"
    assert COMPANIES.update_field == "updated_at"
    with pytest.raises(FrozenInstanceError):
        COMPANIES.endpoint = "changed"
    with pytest.raises(TypeError):
        COMPANIES.fields[0] = "changed"


def test_involved_companies_contract() -> None:
    """Relationship records retain their own ID, references, roles, and update time."""

    assert INVOLVED_COMPANIES.endpoint == "involved_companies"
    assert INVOLVED_COMPANIES.fields == (
        "id", "game", "company", "developer", "publisher", "updated_at",
    )
    assert DEFAULT_INVOLVED_COMPANY_FIELDS is INVOLVED_COMPANIES.fields
    assert INVOLVED_COMPANIES.raw_table == "raw_involved_companies"
    assert INVOLVED_COMPANIES.source_primary_key == "id"
    assert INVOLVED_COMPANIES.raw_primary_key == "igdb_id"
    assert INVOLVED_COMPANIES.update_field == "updated_at"
    with pytest.raises(FrozenInstanceError):
        INVOLVED_COMPANIES.endpoint = "changed"
    with pytest.raises(TypeError):
        INVOLVED_COMPANIES.fields[0] = "changed"
