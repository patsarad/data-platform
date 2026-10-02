"""Offline release-trend contracts; PostgreSQL checks evaluate actual SQL behavior."""

from pathlib import Path
import re

import yaml


DBT = Path(__file__).resolve().parents[1] / "dbt"


def test_release_trends_uses_game_grain_utc_and_existing_table_convention():
    """Avoid raw recasts, relationship fanout, cutoffs, and calendar zero filling."""

    query = (DBT / "models/marts/mart_release_trends.sql").read_text()
    assert re.findall(r"ref\('([^']+)'\)", query) == ["stg_games"]
    assert "extract(year from first_release_at at time zone 'UTC')::integer as release_year" in query
    assert "count(*) as release_count" in query
    assert "where first_release_at is not null\ngroup by 1" in query
    assert not re.search(r"\b(join|union|generate_series|current_date|to_timestamp|distinct)\b", query)
    assert "source(" not in query and "config(" not in query
    config = yaml.safe_load((DBT / "dbt_project.yml").read_text())
    assert config["models"]["data_platform"]["marts"]["+materialized"] == "table"


def test_release_trends_documents_exact_columns_and_invariants():
    """Keep the small public contract documented, including missing-data meanings."""

    models = yaml.safe_load((DBT / "models/marts/schema.yml").read_text())["models"]
    model, = [model for model in models if model["name"] == "mart_release_trends"]
    assert [column["name"] for column in model["columns"]] == ["release_year", "release_count"]
    for column in model["columns"]:
        assert column["description"].strip()
        assert column["data_tests"] == (["unique", "not_null"]
                                          if column["name"] == "release_year" else ["not_null"])
    for meaning in ("UTC", "NULL", "unreleased", "omitted", "zero-filled", "Bounded", "reconcile"):
        assert meaning in model["description"]


def test_release_trends_checks_positive_counts_and_exact_yearly_reconciliation():
    """A total alone misses incorrect year allocation or dropped/invented years."""

    positive = (DBT / "tests/mart_release_trends_positive_count.sql").read_text()
    assert "ref('mart_release_trends')" in positive and "where release_count <= 0" in positive
    query = (DBT / "tests/mart_release_trends_yearly_reconciliation.sql").read_text()
    assert re.findall(r"ref\('([^']+)'\)", query) == ["stg_games", "mart_release_trends"]
    assert "at time zone 'UTC'" in query and "where first_release_at is not null" in query
    assert "full outer join" in query and "using (release_year)" in query
    assert "expected.release_year is null" in query and "actual.release_year is null" in query
    assert "expected.release_count is distinct from actual.release_count" in query
