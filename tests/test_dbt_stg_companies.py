"""Offline checks for the single-source companies staging contract."""

from pathlib import Path
import re

from src.entities import COMPANIES


MODEL = Path(__file__).resolve().parents[1] / "dbt" / "models" / "staging" / "stg_companies.sql"


def test_stg_companies_preserves_raw_grain_and_optional_values() -> None:
    """Keep source rows and nullable fields without business transformations."""

    sql = MODEL.read_text(encoding="utf-8").lower()
    assert COMPANIES.raw_table == "raw_companies"
    assert "updated_at" in COMPANIES.fields
    assert len(re.findall(r"\bfrom\s+\{\{\s*source\('igdb', 'raw_companies'\)\s*\}\}", sql)) == 1
    assert re.search(r"\bigdb_id\s+as\s+company_id\b", sql)
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
