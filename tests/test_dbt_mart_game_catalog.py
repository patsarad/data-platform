"""Offline catalog contracts; PostgreSQL tests evaluate actual values and grain."""

from pathlib import Path
import re

import yaml


DBT = Path(__file__).resolve().parents[1] / "dbt"
COLUMNS = [
    "game_id", "name", "slug", "first_release_at", "rating", "rating_count",
    "total_rating", "total_rating_count", "observed_genres", "observed_platforms",
    "observed_company_relationships",
]


def test_catalog_uses_curated_lineage_and_existing_table_materialization():
    """Keep ingestion and staging casts outside the exploration model."""

    query = (DBT / "models/marts/mart_game_catalog.sql").read_text()
    assert set(re.findall(r"ref\('([^']+)'\)", query)) == {
        "stg_games", "stg_genres", "stg_platforms", "stg_companies",
        "int_game_genres", "int_game_platforms", "int_game_companies",
    }
    assert "source(" not in query
    assert "config(" not in query
    config = yaml.safe_load((DBT / "dbt_project.yml").read_text())
    assert config["models"]["data_platform"]["marts"]["+materialized"] == "table"


def test_catalog_documents_exact_projection_and_only_requires_game_identity():
    """Reject undocumented/stale columns or invented optional-field constraints."""

    query = (DBT / "models/marts/mart_game_catalog.sql").read_text()
    projection = query.rsplit("\nselect\n", 1)[1].split("\nfrom ", 1)[0]
    columns = [line.strip().rstrip(",").split(" as ")[-1].removeprefix("games.")
               for line in projection.splitlines()]
    assert columns == COLUMNS
    models = yaml.safe_load((DBT / "models/marts/schema.yml").read_text())["models"]
    model, = [model for model in models if model["name"] == "mart_game_catalog"]
    assert model["name"] == "mart_game_catalog" and model["description"].strip()
    assert [column["name"] for column in model["columns"]] == COLUMNS
    assert "data_tests" not in model
    for column in model["columns"]:
        assert column["description"].strip()
        assert column.get("data_tests", []) == (
            ["unique", "not_null"] if column["name"] == "game_id" else []
        )


def test_catalog_coverage_checks_both_missing_and_extra_games():
    """Uniqueness alone cannot detect dropped games or invented catalog rows."""

    query = (DBT / "tests/mart_game_catalog_game_coverage.sql").read_text()
    assert re.findall(r"ref\('([^']+)'\)", query) == [
        "stg_games", "mart_game_catalog", "mart_game_catalog", "stg_games",
    ]
    assert query.count("except") == 2
    assert "union all" in query
