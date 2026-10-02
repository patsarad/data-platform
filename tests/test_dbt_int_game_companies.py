"""Offline relationship contracts; opt-in PostgreSQL tests evaluate row semantics."""

from pathlib import Path
import re

import yaml


DBT = Path(__file__).resolve().parents[1] / "dbt"
COLUMNS = ["involved_company_id", "game_id", "company_id", "developer", "publisher"]


def test_game_companies_preserves_staged_record_identity_references_and_roles():
    """A direct projection cannot collapse pairs, infer roles, or drop references."""

    query = (DBT / "models/intermediate/int_game_companies.sql").read_text().lower()
    assert re.findall(r"ref\('([^']+)'\)", query) == ["stg_involved_companies"]
    projection, source = query.strip().split("\nfrom ")
    assert projection.removeprefix("select").strip().split(",\n    ") == COLUMNS
    assert source == "{{ ref('stg_involved_companies') }}"


def test_game_companies_documents_all_columns_and_tests_only_record_grain():
    """Optional references and independent nullable BOOLEAN roles need no constraints."""

    document = yaml.safe_load((DBT / "models/intermediate/schema.yml").read_text())
    models = [model for model in document["models"] if model["name"] == "int_game_companies"]
    assert len(models) == 1
    model = models[0]
    assert model["description"].strip()
    assert [column["name"] for column in model["columns"]] == COLUMNS
    assert "data_tests" not in model
    for column in model["columns"]:
        assert column["description"].strip()
        assert column.get("data_tests", []) == (
            ["unique", "not_null"] if column["name"] == "involved_company_id" else []
        )
