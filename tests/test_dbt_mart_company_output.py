"""Offline company-output contracts; PostgreSQL tests evaluate the actual metrics."""

from pathlib import Path
import re

import yaml


DBT = Path(__file__).resolve().parents[1] / "dbt"
COLUMNS = ["company_id", "name", "company_loaded", "relationship_record_count",
           "null_game_relationship_count", "game_count", "loaded_game_count",
           "developer_game_count", "publisher_game_count"]


def test_company_output_lineage_and_fanout_boundaries():
    """Only authoritative memberships drive output; lookups cannot multiply aggregates."""

    query = (DBT / "models/marts/mart_company_output.sql").read_text()
    assert re.findall(r"ref\('([^']+)'\)", query) == [
        "stg_games", "int_game_companies", "stg_companies",
    ]
    assert "exists (" in query and "games.game_id = relationships.game_id" in query
    assert "where relationships.company_id is not null" in query
    assert "group by company_id" in query
    assert query.index("group by company_id") < query.index("left join")
    assert "count(*) as relationship_record_count" in query
    assert "count(*) filter (where game_id is null) as null_game_relationship_count" in query
    for condition, name in [("", "game_count"), ("game_loaded", "loaded_game_count"),
                            ("developer is true", "developer_game_count"),
                            ("publisher is true", "publisher_game_count")]:
        expression = "count(distinct game_id)"
        if condition:
            expression += f" filter (where {condition})"
        assert f"{expression} as {name}" in query
    assert not re.search(r"\b(coalesce|rating|rank|having|involved_company_ids)\b", query)
    assert "config(" not in query
    config = yaml.safe_load((DBT / "dbt_project.yml").read_text())
    assert config["models"]["data_platform"]["marts"]["+materialized"] == "table"


def test_company_output_documented_projection_and_invariants():
    """Every column has a contract; optional values do not acquire stricter constraints."""

    models = yaml.safe_load((DBT / "models/marts/schema.yml").read_text())["models"]
    model, = [m for m in models if m["name"] == "mart_company_output"]
    assert [c["name"] for c in model["columns"]] == COLUMNS
    assert model["columns"][0]["data_tests"] == ["unique", "not_null"]
    assert all(c["description"].strip() for c in model["columns"])
    assert all("data_tests" not in c for c in model["columns"][1:])
    query = (DBT / "models/marts/mart_company_output.sql").read_text().split("\nselect\n")[-1]
    assert re.findall(r"(?:output|companies)\.(\w+)(?:,|\n)", query) == [
        "company_id", "name", *COLUMNS[3:],
    ]
    for phrase in ("NULL remains unknown", "omitted", "last-upsert", "never sum",
                   "NULL-company", "conflicting", "reconcile", "Bounded"):
        assert phrase in model["description"]


def test_company_output_independent_reconciliation():
    """The oracle groups game pairs separately and compares both populations and every value."""

    query = (DBT / "tests/mart_company_output_reconciliation.sql").read_text()
    assert set(re.findall(r"ref\('([^']+)'\)", query)) == {
        "int_game_companies", "stg_games", "stg_companies", "mart_company_output",
    }
    assert "group by company_id, game_id" in query
    assert "bool_or(developer)" in query and "bool_or(publisher)" in query
    assert "full outer join" in query
    assert "expected.company_id is null" in query and "actual.company_id is null" in query
    for column in COLUMNS[1:]:
        assert f"expected.{column} is distinct from actual.{column}" in query
