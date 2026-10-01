"""Offline checks for the single-source involved-company staging contract."""

from pathlib import Path
import re

from src.entities import INVOLVED_COMPANIES


MODEL = Path(__file__).resolve().parents[1] / "dbt" / "models" / "staging" / "stg_involved_companies.sql"


def test_stg_involved_companies_preserves_relationship_grain_and_optional_values() -> None:
    """Keep relationship IDs, nullable references/roles, and source timestamps."""

    sql = MODEL.read_text(encoding="utf-8").lower()
    assert INVOLVED_COMPANIES.raw_table == "raw_involved_companies"
    assert {"game", "company", "developer", "publisher", "updated_at"} <= set(INVOLVED_COMPANIES.fields)
    assert len(re.findall(r"\bfrom\s+\{\{\s*source\('igdb', 'raw_involved_companies'\)\s*\}\}", sql)) == 1
    assert re.search(r"\bigdb_id\s+as\s+involved_company_id\b", sql)
    for field, column, sql_type in (
        ("game", "game_id", "bigint"), ("company", "company_id", "bigint"),
        ("developer", "developer", "boolean"), ("publisher", "publisher", "boolean"),
    ):
        assert re.search(rf"\(payload\s*->>\s*'{field}'\)::{sql_type}\s+as\s+{column}\b", sql)
    assert re.search(
        r"to_timestamp\(\(payload\s*->>\s*'updated_at'\)::bigint\)\s+as\s+source_updated_at\b",
        sql,
    )
    assert re.search(r"\bfetched_at\s+from\b", sql)
    assert not re.search(
        r"\b(join|unnest|jsonb_array_elements|group by|distinct|union|coalesce|case|where|filter|limit)\b",
        sql,
    )
