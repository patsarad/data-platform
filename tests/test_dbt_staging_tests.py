"""Offline checks for staging identifier tests and the bounded-ingestion policy."""

from pathlib import Path
import re

import pytest
import yaml

from src.entities import COMPANIES, GAMES, GENRES, INVOLVED_COMPANIES, PLATFORMS


STAGING = Path(__file__).resolve().parents[1] / "dbt" / "models" / "staging"


def test_staging_tests_cover_each_entity_identifier_only() -> None:
    """Test renamed raw keys, without inventing required/unique foreign keys."""

    document = yaml.safe_load((STAGING / "schema.yml").read_text(encoding="utf-8"))
    assert document["version"] == 2
    models = {model["name"]: model for model in document["models"]}
    assert len(document["models"]) == len(models) == 5
    assert set(models) == {path.stem for path in STAGING.glob("*.sql")}
    for entity, identifier in (
        (GAMES, "game_id"), (GENRES, "genre_id"), (PLATFORMS, "platform_id"),
        (COMPANIES, "company_id"), (INVOLVED_COMPANIES, "involved_company_id"),
    ):
        model_name = f"stg_{entity.endpoint}"
        model = models[model_name]
        assert "data_tests" not in model
        tested_columns = {
            column["name"]: column["data_tests"]
            for column in model["columns"] if "data_tests" in column
        }
        assert tested_columns == {identifier: ["unique", "not_null"]}
        sql = (STAGING / f"{model_name}.sql").read_text(encoding="utf-8")
        assert re.search(rf"\b{entity.raw_primary_key}\s+as\s+{identifier}\b", sql)


@pytest.mark.parametrize("model_path", sorted(STAGING.glob("*.sql")), ids=lambda path: path.stem)
def test_staging_documentation_covers_every_projected_column(model_path: Path) -> None:
    """Catch missing, duplicate, stale, or blank docs against the SQL projection."""

    document = yaml.safe_load((STAGING / "schema.yml").read_text(encoding="utf-8"))
    model = next(model for model in document["models"] if model["name"] == model_path.stem)
    assert isinstance(model["description"], str) and model["description"].strip()
    # These single-source staging models project one expression per line.
    projection = model_path.read_text(encoding="utf-8").split("\nfrom ", 1)[0]
    projected_names = [line.strip().rstrip(",").split()[-1]
                       for line in projection.splitlines()[1:] if line.strip()]
    documented_names = [column["name"] for column in model["columns"]]
    assert len(documented_names) == len(set(documented_names))
    assert set(documented_names) == set(projected_names)
    for column in model["columns"]:
        assert isinstance(column["description"], str) and column["description"].strip()
