"""Offline checks for the dbt source contract against Python-owned raw tables."""

import os
from pathlib import Path

from jinja2 import Environment
import pytest
import yaml

from src.entities import COMPANIES, GAMES, GENRES, INVOLVED_COMPANIES, PLATFORMS
from src.utils.config import Settings


SOURCE_FILE = Path(__file__).resolve().parents[1] / "dbt" / "models" / "sources.yml"


def test_dbt_sources_match_raw_entity_contracts() -> None:
    """Expose exactly the five raw tables with their real primary-key contract."""

    document = yaml.safe_load(SOURCE_FILE.read_text(encoding="utf-8"))
    assert document["version"] == 2
    (source,) = document["sources"]
    assert source["name"] == "igdb"
    assert source["description"]
    assert "freshness" not in source

    entities = (GAMES, GENRES, PLATFORMS, COMPANIES, INVOLVED_COMPANIES)
    tables = {table["name"]: table for table in source["tables"]}
    assert len(source["tables"]) == len(tables) == len(entities)
    assert set(tables) == {entity.raw_table for entity in entities}

    for entity in entities:
        table = tables[entity.raw_table]
        assert table["description"]
        assert "freshness" not in table
        columns = {column["name"]: column for column in table["columns"]}
        expected = {"igdb_id", "payload", "fetched_at"}
        if entity is not INVOLVED_COMPANIES:
            expected |= {"name", "slug"}
        assert set(columns) == expected
        assert all(column["description"] for column in columns.values())
        assert entity.source_primary_key == "id"
        assert entity.raw_primary_key == "igdb_id"
        assert set(columns["igdb_id"]["data_tests"]) == {"unique", "not_null"}
        assert all("data_tests" not in column for name, column in columns.items() if name != "igdb_id")


@pytest.mark.parametrize("raw,legacy,expected", [
    (None, None, "raw"),
    (None, "analytics", "analytics"),
    ("custom_raw", None, "custom_raw"),
    ("custom_raw", "legacy_raw", "custom_raw"),
])
def test_dbt_and_python_resolve_the_same_source_schema(monkeypatch, raw, legacy, expected):
    """Render schema configuration and protect precedence across both consumers."""

    for key, value in (("POSTGRES_RAW_SCHEMA", raw), ("POSTGRES_SCHEMA", legacy)):
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    monkeypatch.setenv("DBT_SCHEMA", "independent_output")
    template = Environment().from_string(SOURCE_FILE.read_text(encoding="utf-8"))
    sources = yaml.safe_load(template.render(env_var=os.getenv))["sources"]
    assert sources[0]["schema"] == Settings.from_env().postgres_schema == expected
