"""Build the actual dbt project and assert PostgreSQL types and evaluated row values."""

from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys

import psycopg
from psycopg import sql
import pytest

from src.storage import raw_companies, raw_games, raw_genres, raw_involved_companies, raw_platforms
from src.storage.raw_games import create_connection
from src.utils.config import Settings


PROJECT = Path(__file__).resolve().parents[2] / "dbt"
FETCHED_AT = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)


@pytest.fixture(params=["explicit", "legacy", "explicit_over_legacy"])
def dbt_environment(request, postgres_schemas):
    """Resolve isolated raw/output settings using each supported precedence mode."""

    source_schema, output_schema = postgres_schemas
    settings = Settings.from_env()
    env = dict(os.environ, POSTGRES_HOST=settings.postgres_host,
               POSTGRES_PORT=str(settings.postgres_port), POSTGRES_DB=settings.postgres_db,
               POSTGRES_USER=settings.postgres_user, POSTGRES_PASSWORD=settings.postgres_password,
               DBT_SCHEMA=output_schema, DBT_SEND_ANONYMOUS_USAGE_STATS="false",
               PYTHONDONTWRITEBYTECODE="1")
    env.pop("POSTGRES_RAW_SCHEMA", None)
    env.pop("POSTGRES_SCHEMA", None)
    if request.param == "legacy":
        env["POSTGRES_SCHEMA"] = source_schema
    else:
        env["POSTGRES_RAW_SCHEMA"] = source_schema
        if request.param == "explicit_over_legacy":
            env["POSTGRES_SCHEMA"] = source_schema + "_unused"

    return env


def run_dbt(tmp_path, env, command, *selectors):
    """Run dbt with external artifacts and return its process and parsed results."""

    result = subprocess.run(
        [sys.executable, "-c", "from dbt.cli.main import cli; cli()", command, *selectors,
         "--project-dir", str(PROJECT.resolve()), "--profiles-dir", str(PROJECT.resolve()),
         "--no-partial-parse", "--target-path", str(tmp_path / "target"),
         "--log-path", str(tmp_path / "logs")],
        env=env, cwd=tmp_path, capture_output=True, text=True, timeout=120,
    )
    results = json.loads((tmp_path / "target" / "run_results.json").read_text())["results"]
    manifest = json.loads((tmp_path / "target" / "manifest.json").read_text())
    return result, results, manifest


@pytest.fixture
def built_staging(postgres_schemas, tmp_path, dbt_environment):
    """Load source fixtures and build through the installed dbt CLI."""

    source_schema, output_schema = postgres_schemas
    games = [
        {"id": 1},
        {"id": 2, "rating": None, "total_rating": None, "rating_count": None,
         "total_rating_count": None, "first_release_date": None, "updated_at": None,
         "genres": None, "platforms": None, "involved_companies": None},
        {"id": 3, "first_release_date": 0, "updated_at": 0, "rating": 0,
         "rating_count": 0, "total_rating": 0, "total_rating_count": 0,
         "genres": [], "platforms": [], "involved_companies": []},
        {"id": 4, "name": "Example", "slug": "example", "first_release_date": -1,
         "updated_at": 1, "rating": 83.125, "rating_count": 4,
         "total_rating": 90.5, "total_rating_count": 7,
         "genres": [1, 2, 1, 999], "platforms": [3, 2, 999], "involved_companies": [5, 4, 999]},
        {"id": 5, "first_release_date": 1790000000, "updated_at": 1790000001,
         "rating_count": 3000000000},
    ]
    genres = [
        {"id": 1},
        {"id": 2, "name": None, "slug": None, "updated_at": None},
        {"id": 3, "name": "", "slug": "", "updated_at": 0},
        {"id": 4, "name": "Role-playing (RPG)", "slug": "role-playing-rpg", "updated_at": -1},
        {"id": 3000000000, "name": "Stratégie", "slug": "strategie", "updated_at": 1790000001},
    ]
    platforms = [
        {"id": 1},
        {"id": 2, "name": None, "slug": None, "updated_at": None},
        {"id": 3, "name": "", "slug": "", "updated_at": 0},
        {"id": 4, "name": "PC (Microsoft Windows)", "slug": "win", "updated_at": -1},
        {"id": 3000000000, "name": "Café Console", "slug": "cafe-console", "updated_at": 1790000001},
    ]
    companies = [
        {"id": 1},
        {"id": 2, "name": None, "slug": None, "updated_at": None},
        {"id": 3, "name": "", "slug": "", "updated_at": 0},
        {"id": 4, "name": "Example Studio", "slug": "example-studio", "updated_at": -1},
        {"id": 3000000000, "name": "Café Studio", "slug": "cafe-studio", "updated_at": 1790000001},
    ]
    involved_companies = [
        {"id": 1},
        {"id": 2, "game": None, "company": None, "developer": None,
         "publisher": None, "updated_at": None},
        {"id": 3, "game": 3000000001, "company": 3000000002,
         "developer": True, "publisher": False, "updated_at": 0},
        {"id": 4, "game": 3000000001, "company": 3000000002,
         "developer": False, "publisher": True, "updated_at": -1},
        {"id": 5, "game": 0, "company": 0, "developer": True,
         "publisher": True, "updated_at": 1790000001},
        {"id": 3000000000, "game": 4, "company": 4,
         "developer": False, "publisher": False, "updated_at": 1790000001},
    ]
    for entity, module in (
        ("games", raw_games), ("genres", raw_genres), ("platforms", raw_platforms),
        ("companies", raw_companies), ("involved_companies", raw_involved_companies),
    ):
        records = {"games": games, "genres": genres, "platforms": platforms,
                   "companies": companies, "involved_companies": involved_companies}[entity]
        with create_connection() as connection:
            getattr(module, f"ensure_raw_{entity}_table")(connection, source_schema)
            getattr(module, f"upsert_raw_{entity}")(connection, records, source_schema, FETCHED_AT)

    result, results, manifest = run_dbt(tmp_path, dbt_environment, "build")
    assert result.returncode == 0, result.stdout + result.stderr
    assert sum(row["status"] == "pass" for row in results) == 20
    assert len(results) == 25
    assert {row["unique_id"] for row in results if row["status"] == "success"} == {
        "model.data_platform.stg_games", "model.data_platform.stg_genres",
        "model.data_platform.stg_platforms", "model.data_platform.stg_companies",
        "model.data_platform.stg_involved_companies",
    }
    assert {source["schema"] for source in manifest["sources"].values()} == {source_schema}
    test_nodes = [node for node in manifest["nodes"].values() if node["resource_type"] == "test"]
    assert len(test_nodes) == 20
    for model, identifier in (
        ("stg_games", "game_id"), ("stg_genres", "genre_id"),
        ("stg_platforms", "platform_id"), ("stg_companies", "company_id"),
        ("stg_involved_companies", "involved_company_id"),
    ):
        model_tests = [node for node in test_nodes
                       if node["depends_on"]["nodes"] == [f"model.data_platform.{model}"]]
        assert {node["test_metadata"]["name"] for node in model_tests} == {"unique", "not_null"}
        assert len(model_tests) == 2
        for node in model_tests:
            assert node["column_name"] == identifier
            assert node["config"]["severity"] == "ERROR"

    for model, source in (
        ("stg_games", "raw_games"), ("stg_genres", "raw_genres"), ("stg_platforms", "raw_platforms"),
        ("stg_companies", "raw_companies"),
        ("stg_involved_companies", "raw_involved_companies"),
    ):
        node = manifest["nodes"][f"model.data_platform.{model}"]
        assert node["config"]["materialized"] == "view"
        assert node["schema"] == output_schema
        assert node["depends_on"]["nodes"] == [f"source.data_platform.igdb.{source}"]
        assert node["description"].strip()
        with create_connection() as connection:
            actual_columns = connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s",
                (output_schema, model),
            ).fetchall()
        assert set(node["columns"]) == {name for (name,) in actual_columns}
        assert all(column["description"].strip() for column in node["columns"].values())
    return source_schema, output_schema


@pytest.mark.parametrize("defect", ["duplicate", "null"])
def test_staging_identifier_tests_reject_bad_output(
    built_staging, dbt_environment, tmp_path, defect,
):
    """Fail each model key test despite valid raw PKs, then pass after restoration.

    Only disposable views are changed. This models a broken transformation without
    weakening raw constraints or letting source tests account for the failure.
    """

    _, output_schema = built_staging
    originals = {}
    with create_connection() as connection:
        for model, identifier in (
            ("stg_games", "game_id"), ("stg_genres", "genre_id"),
            ("stg_platforms", "platform_id"), ("stg_companies", "company_id"),
            ("stg_involved_companies", "involved_company_id"),
        ):
            relation = sql.Identifier(output_schema, model)
            original = connection.execute(
                "SELECT pg_get_viewdef(c.oid) FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = %s AND c.relname = %s", (output_schema, model),
            ).fetchone()[0].strip().rstrip(";")
            originals[model] = original
            if defect == "duplicate":
                projection = sql.SQL("SELECT * FROM ({}) base UNION ALL "
                                     "SELECT * FROM ({}) base WHERE {} = 1").format(
                    sql.SQL(original), sql.SQL(original), sql.Identifier(identifier),
                )
            else:
                columns = connection.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
                    (output_schema, model),
                ).fetchall()
                projection = sql.SQL("SELECT {} FROM ({}) base").format(
                    sql.SQL(", ").join(
                        sql.SQL("CASE WHEN {} = 1 THEN NULL::bigint ELSE {} END AS {}").format(
                            *([sql.Identifier(column)] * 3)
                        ) if column == identifier else sql.Identifier(column)
                        for (column,) in columns
                    ), sql.SQL(original),
                )
            connection.execute(sql.SQL("CREATE OR REPLACE VIEW {} AS {}").format(relation, projection))

    try:
        process, results, manifest = run_dbt(tmp_path, dbt_environment, "test")
        assert process.returncode == 1, process.stdout + process.stderr
        assert len(results) == 20
        failed = [row for row in results if row["status"] == "fail"]
        assert len(failed) == 5
        assert sum(row["status"] == "pass" for row in results) == 15
        expected_test = "unique" if defect == "duplicate" else "not_null"
        assert {manifest["nodes"][row["unique_id"]]["depends_on"]["nodes"][0]
                for row in failed} == {f"model.data_platform.{model}" for model in originals}
        for row in failed:
            assert row["failures"] == 1
            assert manifest["nodes"][row["unique_id"]]["test_metadata"]["name"] == expected_test
    finally:
        with create_connection() as connection:
            for model, original in originals.items():
                connection.execute(sql.SQL("CREATE OR REPLACE VIEW {} AS {}").format(
                    sql.Identifier(output_schema, model), sql.SQL(original),
                ))

    process, results, _ = run_dbt(tmp_path, dbt_environment, "test")
    assert process.returncode == 0, process.stdout + process.stderr
    assert len(results) == 20
    assert all(row["status"] == "pass" for row in results)


def test_staging_types_and_values(built_staging):
    """Evaluate every output column, including null/zero/epoch and reference semantics."""

    _, output_schema = built_staging
    with create_connection() as connection:
        types = connection.execute("""SELECT column_name, data_type FROM information_schema.columns
            WHERE table_schema = %s AND table_name = 'stg_games'""", (output_schema,)).fetchall()
        assert dict(types) == {
            "game_id": "bigint", "name": "text", "slug": "text",
            "first_release_at": "timestamp with time zone", "source_updated_at": "timestamp with time zone",
            "rating": "numeric", "rating_count": "bigint", "total_rating": "numeric",
            "total_rating_count": "bigint", "genre_ids": "jsonb", "platform_ids": "jsonb",
            "involved_company_ids": "jsonb", "fetched_at": "timestamp with time zone",
        }
        rows = connection.execute(f"SELECT * FROM {output_schema}.stg_games ORDER BY game_id").fetchall()
        assert len(rows) == 5
        assert rows[0] == (1, *([None] * 11), FETCHED_AT)
        assert rows[1] == (2, *([None] * 11), FETCHED_AT)
        assert rows[2] == (3, None, None, datetime(1970, 1, 1, tzinfo=timezone.utc),
                           datetime(1970, 1, 1, tzinfo=timezone.utc), 0, 0, 0, 0, [], [], [], FETCHED_AT)
        assert rows[3] == (4, "Example", "example", datetime.fromtimestamp(-1, timezone.utc),
                           datetime.fromtimestamp(1, timezone.utc), Decimal("83.125"), 4,
                           Decimal("90.5"), 7, [1, 2, 1, 999], [3, 2, 999], [5, 4, 999], FETCHED_AT)
        assert rows[4] == (5, None, None, datetime.fromtimestamp(1790000000, timezone.utc),
                           datetime.fromtimestamp(1790000001, timezone.utc), None, 3000000000,
                           None, None, None, None, None, FETCHED_AT)
        nulls = connection.execute(f"""SELECT genre_ids IS NULL, platform_ids IS NULL,
            involved_company_ids IS NULL FROM {output_schema}.stg_games
            WHERE game_id IN (1, 2) ORDER BY game_id""").fetchall()
        assert nulls == [(True, True, True), (False, False, False)]


def test_invalid_scalar_fails_when_view_is_read(built_staging):
    """A view is evaluated on read; successful creation is not row validation."""

    source_schema, output_schema = built_staging
    for field, column in (("rating", "rating"), ("rating_count", "rating_count"),
                          ("first_release_date", "first_release_at")):
        with create_connection() as connection:
            raw_games.upsert_raw_games(
                connection, [{"id": 6, field: "invalid-number"}], source_schema, FETCHED_AT,
            )
        with pytest.raises(psycopg.errors.InvalidTextRepresentation):
            with create_connection() as connection:
                connection.execute(f"SELECT {column} FROM {output_schema}.stg_games WHERE game_id = 6").fetchall()


def test_genres_types_grain_and_values(built_staging):
    """Read every genre value, preserving missing/null/empty fields and epoch instants."""

    source_schema, output_schema = built_staging
    with create_connection() as connection:
        types = connection.execute("""SELECT column_name, data_type FROM information_schema.columns
            WHERE table_schema = %s AND table_name = 'stg_genres'""", (output_schema,)).fetchall()
        assert dict(types) == {
            "genre_id": "bigint", "name": "text", "slug": "text",
            "source_updated_at": "timestamp with time zone", "fetched_at": "timestamp with time zone",
        }
        assert connection.execute("""SELECT table_type FROM information_schema.tables
            WHERE table_schema = %s AND table_name = 'stg_genres'""", (output_schema,)).fetchone() == ("VIEW",)
        rows = connection.execute(f"SELECT * FROM {output_schema}.stg_genres ORDER BY genre_id").fetchall()
        assert rows == [
            (1, None, None, None, FETCHED_AT),
            (2, None, None, None, FETCHED_AT),
            (3, "", "", datetime(1970, 1, 1, tzinfo=timezone.utc), FETCHED_AT),
            (4, "Role-playing (RPG)", "role-playing-rpg", datetime.fromtimestamp(-1, timezone.utc), FETCHED_AT),
            (3000000000, "Stratégie", "strategie", datetime.fromtimestamp(1790000001, timezone.utc), FETCHED_AT),
        ]
        raw_ids = connection.execute(f"SELECT igdb_id FROM {source_schema}.raw_genres ORDER BY igdb_id").fetchall()
        assert [(row[0],) for row in rows] == raw_ids
        assert len(rows) == len({row[0] for row in rows}) == 5


def test_invalid_genre_timestamp_fails_when_view_is_read(built_staging):
    """Successful view creation cannot hide an invalid source timestamp on read."""

    source_schema, output_schema = built_staging
    with create_connection() as connection:
        raw_genres.upsert_raw_genres(
            connection, [{"id": 6, "updated_at": "invalid-number"}], source_schema, FETCHED_AT,
        )
    with pytest.raises(psycopg.errors.InvalidTextRepresentation):
        with create_connection() as connection:
            connection.execute(
                f"SELECT source_updated_at FROM {output_schema}.stg_genres WHERE genre_id = 6"
            ).fetchall()


def test_platforms_types_grain_and_values(built_staging):
    """Read every platform value, preserving missing/null/empty fields and epoch instants."""

    source_schema, output_schema = built_staging
    with create_connection() as connection:
        types = connection.execute("""SELECT column_name, data_type FROM information_schema.columns
            WHERE table_schema = %s AND table_name = 'stg_platforms'""", (output_schema,)).fetchall()
        assert dict(types) == {
            "platform_id": "bigint", "name": "text", "slug": "text",
            "source_updated_at": "timestamp with time zone", "fetched_at": "timestamp with time zone",
        }
        assert connection.execute("""SELECT table_type FROM information_schema.tables
            WHERE table_schema = %s AND table_name = 'stg_platforms'""", (output_schema,)).fetchone() == ("VIEW",)
        rows = connection.execute(f"SELECT * FROM {output_schema}.stg_platforms ORDER BY platform_id").fetchall()
        assert rows == [
            (1, None, None, None, FETCHED_AT),
            (2, None, None, None, FETCHED_AT),
            (3, "", "", datetime(1970, 1, 1, tzinfo=timezone.utc), FETCHED_AT),
            (4, "PC (Microsoft Windows)", "win", datetime.fromtimestamp(-1, timezone.utc), FETCHED_AT),
            (3000000000, "Café Console", "cafe-console", datetime.fromtimestamp(1790000001, timezone.utc), FETCHED_AT),
        ]
        raw_ids = connection.execute(f"SELECT igdb_id FROM {source_schema}.raw_platforms ORDER BY igdb_id").fetchall()
        assert [(row[0],) for row in rows] == raw_ids
        assert len(rows) == len({row[0] for row in rows}) == 5


def test_invalid_platform_timestamp_fails_when_view_is_read(built_staging):
    """Successful view creation cannot hide an invalid source timestamp on read."""

    source_schema, output_schema = built_staging
    with create_connection() as connection:
        raw_platforms.upsert_raw_platforms(
            connection, [{"id": 6, "updated_at": "invalid-number"}], source_schema, FETCHED_AT,
        )
    with pytest.raises(psycopg.errors.InvalidTextRepresentation):
        with create_connection() as connection:
            connection.execute(
                f"SELECT source_updated_at FROM {output_schema}.stg_platforms WHERE platform_id = 6"
            ).fetchall()


def test_companies_types_grain_and_values(built_staging):
    """Read every company value, preserving missing/null/empty fields and epoch instants."""

    source_schema, output_schema = built_staging
    with create_connection() as connection:
        types = connection.execute("""SELECT column_name, data_type FROM information_schema.columns
            WHERE table_schema = %s AND table_name = 'stg_companies'""", (output_schema,)).fetchall()
        assert dict(types) == {
            "company_id": "bigint", "name": "text", "slug": "text",
            "source_updated_at": "timestamp with time zone", "fetched_at": "timestamp with time zone",
        }
        assert connection.execute("""SELECT table_type FROM information_schema.tables
            WHERE table_schema = %s AND table_name = 'stg_companies'""", (output_schema,)).fetchone() == ("VIEW",)
        rows = connection.execute(f"SELECT * FROM {output_schema}.stg_companies ORDER BY company_id").fetchall()
        assert rows == [
            (1, None, None, None, FETCHED_AT),
            (2, None, None, None, FETCHED_AT),
            (3, "", "", datetime(1970, 1, 1, tzinfo=timezone.utc), FETCHED_AT),
            (4, "Example Studio", "example-studio", datetime.fromtimestamp(-1, timezone.utc), FETCHED_AT),
            (3000000000, "Café Studio", "cafe-studio", datetime.fromtimestamp(1790000001, timezone.utc), FETCHED_AT),
        ]
        raw_ids = connection.execute(f"SELECT igdb_id FROM {source_schema}.raw_companies ORDER BY igdb_id").fetchall()
        assert [(row[0],) for row in rows] == raw_ids
        assert len(rows) == len({row[0] for row in rows}) == 5


def test_invalid_company_timestamp_fails_when_view_is_read(built_staging):
    """Successful view creation cannot hide an invalid source timestamp on read."""

    source_schema, output_schema = built_staging
    with create_connection() as connection:
        raw_companies.upsert_raw_companies(
            connection, [{"id": 6, "updated_at": "invalid-number"}], source_schema, FETCHED_AT,
        )
    with pytest.raises(psycopg.errors.InvalidTextRepresentation):
        with create_connection() as connection:
            connection.execute(
                f"SELECT source_updated_at FROM {output_schema}.stg_companies WHERE company_id = 6"
            ).fetchall()


def test_involved_companies_types_grain_and_values(built_staging):
    """Preserve relationship IDs, repeated/unmatched pairs, nullable roles, and instants."""

    source_schema, output_schema = built_staging
    with create_connection() as connection:
        types = connection.execute("""SELECT column_name, data_type FROM information_schema.columns
            WHERE table_schema = %s AND table_name = 'stg_involved_companies'""", (output_schema,)).fetchall()
        assert dict(types) == {
            "involved_company_id": "bigint", "game_id": "bigint", "company_id": "bigint",
            "developer": "boolean", "publisher": "boolean",
            "source_updated_at": "timestamp with time zone", "fetched_at": "timestamp with time zone",
        }
        assert connection.execute("""SELECT table_type FROM information_schema.tables
            WHERE table_schema = %s AND table_name = 'stg_involved_companies'""", (output_schema,)).fetchone() == ("VIEW",)
        rows = connection.execute(
            f"SELECT * FROM {output_schema}.stg_involved_companies ORDER BY involved_company_id"
        ).fetchall()
        assert rows == [
            (1, None, None, None, None, None, FETCHED_AT),
            (2, None, None, None, None, None, FETCHED_AT),
            (3, 3000000001, 3000000002, True, False, datetime.fromtimestamp(0, timezone.utc), FETCHED_AT),
            (4, 3000000001, 3000000002, False, True, datetime.fromtimestamp(-1, timezone.utc), FETCHED_AT),
            (5, 0, 0, True, True, datetime.fromtimestamp(1790000001, timezone.utc), FETCHED_AT),
            (3000000000, 4, 4, False, False, datetime.fromtimestamp(1790000001, timezone.utc), FETCHED_AT),
        ]
        raw_ids = connection.execute(
            f"SELECT igdb_id FROM {source_schema}.raw_involved_companies ORDER BY igdb_id"
        ).fetchall()
        assert [(row[0],) for row in rows] == raw_ids
        assert len(rows) == len({row[0] for row in rows}) == 6


def test_invalid_involved_company_scalars_fail_when_view_is_read(built_staging):
    """Invalid references, roles, or timestamps fail on read instead of being defaulted."""

    source_schema, output_schema = built_staging
    for field, column in (("game", "game_id"), ("company", "company_id"),
                          ("developer", "developer"), ("publisher", "publisher"),
                          ("updated_at", "source_updated_at")):
        with create_connection() as connection:
            raw_involved_companies.upsert_raw_involved_companies(
                connection, [{"id": 6, field: "invalid-scalar"}], source_schema, FETCHED_AT,
            )
        with pytest.raises(psycopg.errors.InvalidTextRepresentation):
            with create_connection() as connection:
                connection.execute(
                    f"SELECT {column} FROM {output_schema}.stg_involved_companies WHERE involved_company_id = 6"
                ).fetchall()
