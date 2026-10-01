"""Offline checks for the single-source games staging contract."""

from pathlib import Path
import re

from src.entities import GAMES


MODEL = Path(__file__).resolve().parents[1] / "dbt" / "models" / "staging" / "stg_games.sql"


def test_stg_games_preserves_raw_grain_and_relationship_references() -> None:
    """Keep one row per game and pass reference arrays to later models."""

    sql = MODEL.read_text(encoding="utf-8").lower()
    assert GAMES.raw_table == "raw_games"
    assert len(re.findall(r"\bfrom\s+\{\{\s*source\('igdb', 'raw_games'\)\s*\}\}", sql)) == 1
    assert re.search(r"\bigdb_id\s+as\s+game_id\b", sql)
    assert not re.search(r"\b(join|unnest|jsonb_array_elements|group by|distinct|union)\b", sql)

    for source_key, output in (
        ("genres", "genre_ids"),
        ("platforms", "platform_ids"),
        ("involved_companies", "involved_company_ids"),
    ):
        assert source_key in GAMES.fields
        assert re.search(rf"payload\s*->\s*'{source_key}'\s+as\s+{output}\b", sql)


def test_stg_games_types_optional_payload_values_without_defaults() -> None:
    """Missing scalar values stay SQL NULL; JSON arrays retain their shape."""

    sql = MODEL.read_text(encoding="utf-8").lower()
    for source_key, output in (
        ("first_release_date", "first_release_at"),
        ("updated_at", "source_updated_at"),
    ):
        assert source_key in GAMES.fields
        assert re.search(
            rf"to_timestamp\(\(payload\s*->>\s*'{source_key}'\)::bigint\)\s+as\s+{output}\b",
            sql,
        )

    for source_key, sql_type in (
        ("rating", "numeric"),
        ("rating_count", "bigint"),
        ("total_rating", "numeric"),
        ("total_rating_count", "bigint"),
    ):
        assert source_key in GAMES.fields
        assert re.search(rf"\(payload\s*->>\s*'{source_key}'\)::\s*{sql_type}\s+as\s+{source_key}\b", sql)

    assert re.search(r"\bname\s*,\s*slug\s*,", sql)
    assert re.search(r"\bfetched_at\s+from\b", sql)
    assert not re.search(r"\b(coalesce|case|where|filter)\b", sql)
