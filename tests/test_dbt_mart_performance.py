"""Offline performance-mart contracts; opt-in PostgreSQL tests evaluate values."""

from pathlib import Path
import re

import pytest
import yaml


DBT = Path(__file__).resolve().parents[1] / "dbt"
METRICS = ["game_count", "rated_game_count", "avg_rating",
           "rating_count_game_count", "rating_count_sum"]


@pytest.mark.parametrize("dimension", ["genre", "platform"])
def test_performance_lineage_grain_and_aggregation(dimension):
    """Deduplicate IDs before rating aggregation and attach labels afterward."""

    query = (DBT / f"models/marts/mart_{dimension}_performance.sql").read_text()
    key = f"{dimension}_id"
    assert re.findall(r"ref\('([^']+)'\)", query) == [
        f"int_game_{dimension}s", "stg_games", f"stg_{dimension}s",
    ]
    assert f"select distinct game_id, {key}" in query
    assert f"group by associations.{key}" in query
    for expression in ("count(*) as game_count", "count(games.rating) as rated_game_count",
                       "avg(games.rating) as avg_rating",
                       "count(games.rating_count) as rating_count_game_count",
                       "sum(games.rating_count) as rating_count_sum"):
        assert expression in query
    assert f"left join {{{{ ref('stg_{dimension}s') }}}} as dimensions using ({key})" in query
    assert not re.search(r"\b(where|having|round|coalesce|rank|total_rating)\b", query)
    assert "source(" not in query and "config(" not in query
    config = yaml.safe_load((DBT / "dbt_project.yml").read_text())
    assert config["models"]["data_platform"]["marts"]["+materialized"] == "table"


@pytest.mark.parametrize("dimension", ["genre", "platform"])
def test_performance_documented_projection_and_identity_tests(dimension):
    """All seven output columns have contracts; no unsupported range policy is added."""

    models = yaml.safe_load((DBT / "models/marts/schema.yml").read_text())["models"]
    model, = [m for m in models if m["name"] == f"mart_{dimension}_performance"]
    columns = model["columns"]
    assert [c["name"] for c in columns] == [f"{dimension}_id", "name", *METRICS]
    assert columns[0]["data_tests"] == ["unique", "not_null"]
    assert all(c["description"].strip() for c in columns)
    assert all("data_tests" not in c for c in columns[1:])
    for meaning in ("unweighted", "NULL", "zero", "Unmatched", "omitted", "Bounded",
                    "Cross-dimension", "total_rating", "reconcile"):
        assert meaning in model["description"]


@pytest.mark.parametrize("dimension", ["genre", "platform"])
def test_performance_reconciliation_checks_every_value_and_both_populations(dimension):
    """A semi-join oracle is insensitive to repeated pairs and detects every column defect."""

    query = (DBT / f"tests/mart_{dimension}_performance_reconciliation.sql").read_text()
    assert re.findall(r"ref\('([^']+)'\)", query) == [
        f"int_game_{dimension}s", "stg_games", f"stg_{dimension}s",
        f"mart_{dimension}_performance",
    ]
    assert "on exists (" in query
    assert "full outer join" in query
    assert f"expected.{dimension}_id is null" in query
    assert f"actual.{dimension}_id is null" in query
    for column in ["name", *METRICS]:
        assert f"expected.{column} is distinct from actual.{column}" in query
