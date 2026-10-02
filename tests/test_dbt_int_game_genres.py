"""Offline SQL/documentation contracts; PostgreSQL tests evaluate actual rows."""

from pathlib import Path
import re

import yaml


DBT = Path(__file__).resolve().parents[1] / "dbt"


def test_game_genres_expands_staging_without_requiring_lookup_coverage():
    """Protect pair grain, JSON-null normalization, typing, and unmatched IDs."""

    query = (DBT / "models/intermediate/int_game_genres.sql").read_text().lower()
    assert re.findall(r"ref\('([^']+)'\)", query) == ["stg_games"]
    assert "source(" not in query
    assert re.search(r"select\s+distinct\s+games.game_id,\s+genre.genre_id::bigint as genre_id", query)
    assert re.search(r"cross join lateral jsonb_array_elements_text\(\s*"
                     r"nullif\(games.genre_ids, 'null'::jsonb\)\s*\)", query)
    assert not re.search(r"\b(where|limit|stg_genres)\b", query)


def test_game_genres_documentation_and_tests_protect_pair_not_individual_uniqueness():
    """Require both key docs/null tests and composite uniqueness, without foreign keys."""

    document = yaml.safe_load((DBT / "models/intermediate/schema.yml").read_text())
    assert document["version"] == 2
    models = [model for model in document["models"] if model["name"] == "int_game_genres"]
    assert len(models) == 1
    model = models[0]
    assert model["name"] == "int_game_genres"
    assert model["description"].strip()
    assert [column["name"] for column in model["columns"]] == ["game_id", "genre_id"]
    for column in model["columns"]:
        assert column["description"].strip()
        assert column["data_tests"] == ["not_null"]
    assert "data_tests" not in model
    query = (DBT / "tests/int_game_genres_unique_pair.sql").read_text().lower()
    assert "ref('int_game_genres')" in query
    assert re.search(r"group by game_id, genre_id\s+having count\(\*\) > 1", query)
