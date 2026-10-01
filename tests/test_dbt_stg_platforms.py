"""Offline checks for the single-source platforms staging contract."""

from pathlib import Path
import re

from src.entities import PLATFORMS


MODEL = Path(__file__).resolve().parents[1] / "dbt" / "models" / "staging" / "stg_platforms.sql"


def test_stg_platforms_preserves_raw_grain_and_optional_values() -> None:
    """Keep source rows and nullable fields without business transformations."""

    sql = MODEL.read_text(encoding="utf-8").lower()
    assert PLATFORMS.raw_table == "raw_platforms"
    assert "updated_at" in PLATFORMS.fields
    assert len(re.findall(r"\bfrom\s+\{\{\s*source\('igdb', 'raw_platforms'\)\s*\}\}", sql)) == 1
    assert re.search(r"\bigdb_id\s+as\s+platform_id\b", sql)
    assert re.search(r"\bname\s*,\s*slug\s*,", sql)
    assert re.search(
        r"to_timestamp\(\(payload\s*->>\s*'updated_at'\)::bigint\)\s+as\s+source_updated_at\b",
        sql,
    )
    assert re.search(r"\bfetched_at\s+from\b", sql)
    assert not re.search(
        r"\b(join|unnest|jsonb_array_elements|group by|distinct|union|coalesce|case|where|filter|limit)\b",
        sql,
    )
