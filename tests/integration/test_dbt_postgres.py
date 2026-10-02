"""Build the actual dbt project and assert PostgreSQL types and evaluated row values."""

from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter

import psycopg
from psycopg import sql
import pytest

from src.storage import raw_companies, raw_games, raw_genres, raw_involved_companies, raw_platforms
from src.storage.raw_games import create_connection
from src.utils.config import Settings


PROJECT = Path(__file__).resolve().parents[2] / "dbt"
FETCHED_AT = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)


@pytest.fixture
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
    mode = getattr(request, "param", "explicit")
    assert mode in {"explicit", "legacy", "explicit_over_legacy"}
    if mode == "legacy":
        env["POSTGRES_SCHEMA"] = source_schema
    else:
        env["POSTGRES_RAW_SCHEMA"] = source_schema
        if mode == "explicit_over_legacy":
            env["POSTGRES_SCHEMA"] = source_schema + "_unused"

    return env


def run_dbt(tmp_path, env, command, *selectors, full_parse=False):
    """Run dbt with an isolated parse cache and record invocation time outside the repo.

    Full-project schema checks force a fresh parse; repeated commands in each
    behavior case can reuse that case's cache. No cache crosses test boundaries.
    """

    started = perf_counter()
    result = subprocess.run(
        [sys.executable, "-c", "from dbt.cli.main import cli; cli()", command, *selectors,
         "--project-dir", str(PROJECT.resolve()), "--profiles-dir", str(PROJECT.resolve()),
         "--no-partial-parse" if full_parse else "--partial-parse",
         "--target-path", str(tmp_path / "target"),
         "--log-path", str(tmp_path / "logs")],
        env=env, cwd=tmp_path, capture_output=True, text=True, timeout=120,
    )
    with (tmp_path / "dbt-invocations.jsonl").open("a") as timings:
        timings.write(json.dumps({"command": command, "selectors": selectors,
                                  "full_parse": full_parse, "seconds": perf_counter() - started,
                                  "returncode": result.returncode}) + "\n")
    results = json.loads((tmp_path / "target" / "run_results.json").read_text())["results"]
    manifest = json.loads((tmp_path / "target" / "manifest.json").read_text())
    return result, results, manifest


@pytest.fixture
def loaded_sources(postgres_schemas):
    """Load fresh source fixtures in schemas owned by this one test."""

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

    return source_schema, output_schema


@pytest.fixture
def built_staging(loaded_sources, tmp_path, dbt_environment, request):
    """Build staging plus explicitly requested model ancestors, without rerunning all tests.

    Model value/error/recovery assertions live in the behavior cases; the three
    full-project schema cases own the complete build and manifest assertions.
    """

    marker = request.node.get_closest_marker("dbt_models")
    models = marker.args if marker else ()
    result, results, _ = run_dbt(
        tmp_path, dbt_environment, "run", "--select", "path:models/staging", *models,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert results and all(row["status"] == "success" for row in results)
    assert all(row["unique_id"].startswith("model.") for row in results)
    return loaded_sources


@pytest.mark.parametrize("dbt_environment", ["explicit", "legacy", "explicit_over_legacy"], indirect=True)
def test_full_project_schema_modes(loaded_sources, dbt_environment, tmp_path):
    """Keep complete fresh builds, schema precedence, documentation and value checks in each mode."""

    source_schema, output_schema = loaded_sources
    result, results, manifest = run_dbt(tmp_path, dbt_environment, "build", full_parse=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert sum(row["status"] == "pass" for row in results) == 46
    assert len(results) == 59
    assert {row["unique_id"] for row in results if row["status"] == "success"} == {
        "model.data_platform.stg_games", "model.data_platform.stg_genres",
        "model.data_platform.stg_platforms", "model.data_platform.stg_companies",
        "model.data_platform.stg_involved_companies", "model.data_platform.int_game_genres",
        "model.data_platform.int_game_platforms", "model.data_platform.int_game_companies",
        "model.data_platform.mart_game_catalog",
        "model.data_platform.mart_release_trends",
        "model.data_platform.mart_genre_performance",
        "model.data_platform.mart_platform_performance",
        "model.data_platform.mart_company_output",
    }
    assert {source["schema"] for source in manifest["sources"].values()} == {source_schema}
    test_nodes = [node for node in manifest["nodes"].values() if node["resource_type"] == "test"]
    assert len(test_nodes) == 46
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
    # Check values as well as schema resolution: wrong-schema data cannot pass
    # merely because it has compatible columns.
    assert_catalog_matches_sources(output_schema)
    assert_release_trends_matches_sources(output_schema)
    assert_performance_matches_sources(source_schema, output_schema)
    assert_company_output_matches_sources(source_schema, output_schema)
    for node in manifest["nodes"].values():
        if node["resource_type"] != "model":
            continue
        assert node["schema"] == output_schema
        assert node["description"].strip()
        with create_connection() as connection:
            columns = connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name=%s", (output_schema, node["name"]),
            ).fetchall()
        assert set(node["columns"]) == {name for (name,) in columns}
        assert all(column["description"].strip() for column in node["columns"].values())

    # Repeated commands use only this test's cache, with identical model/source
    # resolution and all dbt invariants still passing after the fresh build.
    assert (tmp_path / "target/partial_parse.msgpack").is_file()
    process, repeated, cached = run_dbt(tmp_path, dbt_environment, "test")
    assert process.returncode == 0, process.stdout + process.stderr
    assert len(repeated) == 46 and all(row["status"] == "pass" for row in repeated)
    for collection in ("nodes", "sources"):
        for key, node in manifest[collection].items():
            if node["resource_type"] not in {"model", "source"}:
                continue
            for field in ("schema", "relation_name", "depends_on", "columns", "description"):
                assert cached[collection][key].get(field) == node.get(field)


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
        process, results, manifest = run_dbt(
            tmp_path, dbt_environment, "test", "--select", "path:models/staging", "source:*",
            "--indirect-selection", "cautious",
        )
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

    process, results, _ = run_dbt(
        tmp_path, dbt_environment, "test", "--select", "path:models/staging", "source:*",
        "--indirect-selection", "cautious",
    )
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


@pytest.mark.dbt_models("+int_game_genres")
def test_game_genres_values_and_incomplete_coverage(built_staging, tmp_path):
    """Expand real JSONB, collapse duplicates, and retain unmatched/reused BIGINT IDs."""

    source_schema, output_schema = built_staging
    manifest = json.loads((tmp_path / "target/manifest.json").read_text())
    node = manifest["nodes"]["model.data_platform.int_game_genres"]
    assert node["depends_on"]["nodes"] == ["model.data_platform.stg_games"]
    assert node["schema"] == output_schema
    assert node["config"]["materialized"] == "view"
    assert node["description"].strip()
    assert set(node["columns"]) == {"game_id", "genre_id"}
    assert all(column["description"].strip() for column in node["columns"].values())
    with create_connection() as connection:
        assert connection.execute(
            "SELECT table_type FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = 'int_game_genres'", (output_schema,),
        ).fetchone() == ("VIEW",)
        types = connection.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = 'int_game_genres'", (output_schema,),
        ).fetchall()
        assert dict(types) == {"game_id": "bigint", "genre_id": "bigint"}
        # Baseline games 1/2/3 have absent/JSON-null/empty arrays: none get a row.
        assert connection.execute(
            f"SELECT * FROM {output_schema}.int_game_genres ORDER BY 1, 2"
        ).fetchall() == [(4, 1), (4, 2), (4, 999)]
        raw_games.upsert_raw_games(connection, [
            {"id": 3000000001, "genres": [999, 1, 3000000000, 3000000002, 1, 0]},
        ], source_schema, FETCHED_AT)
        rows = connection.execute(
            f"SELECT * FROM {output_schema}.int_game_genres ORDER BY 1, 2"
        ).fetchall()
        assert rows == [(4, 1), (4, 2), (4, 999), (3000000001, 0),
                        (3000000001, 1), (3000000001, 999),
                        (3000000001, 3000000000), (3000000001, 3000000002)]
        assert len(rows) == len(set(rows))
        unmatched = connection.execute(f"""
            SELECT bridge.game_id, bridge.genre_id
            FROM {output_schema}.int_game_genres bridge
            LEFT JOIN {output_schema}.stg_genres genres USING (genre_id)
            WHERE genres.genre_id IS NULL ORDER BY 1, 2
        """).fetchall()
        assert unmatched == [(4, 999), (3000000001, 0),
                             (3000000001, 999), (3000000001, 3000000002)]
        # Independent Python expectation over original arrays checks both omissions
        # and extras, without reusing the model's SQL expansion.
        raw = connection.execute(
            f"SELECT igdb_id, payload FROM {source_schema}.raw_games"
        ).fetchall()
        assert set(rows) == {(game_id, genre_id) for game_id, payload in raw
                             for genre_id in (payload.get("genres") or [])}


@pytest.mark.dbt_models("+int_game_genres")
def test_game_genres_rejects_malformed_arrays_and_null_members(
    built_staging, dbt_environment, tmp_path,
):
    """Bad arrays/casts raise; a null member is exposed to the not-null test."""

    source_schema, output_schema = built_staging
    for value in (42, {}, "bad-array", ["bad-id"], [1.5], [True], [{}], [[1]], [2**63]):
        with create_connection() as connection:
            raw_games.upsert_raw_games(connection, [{"id": 6, "genres": value}],
                                       source_schema, FETCHED_AT)
        with pytest.raises(psycopg.DataError):
            with create_connection() as connection:
                connection.execute(f"SELECT * FROM {output_schema}.int_game_genres").fetchall()
    with create_connection() as connection:
        raw_games.upsert_raw_games(connection, [{"id": 6, "genres": [999, None]}],
                                   source_schema, FETCHED_AT)
        assert connection.execute(
            f"SELECT * FROM {output_schema}.int_game_genres WHERE game_id = 6 ORDER BY genre_id"
        ).fetchall() == [(6, 999), (6, None)]
    process, results, _ = run_dbt(
        tmp_path, dbt_environment, "test", "--select", "int_game_genres",
        "--indirect-selection", "cautious",
    )
    assert process.returncode == 1, process.stdout + process.stderr
    assert len(results) == 3
    failed = [row for row in results if row["status"] == "fail"]
    assert len(failed) == 1
    assert failed[0]["unique_id"].startswith("test.data_platform.not_null_int_game_genres_genre_id.")
    assert failed[0]["failures"] == 1


@pytest.mark.dbt_models("+int_game_genres")
@pytest.mark.parametrize("defect", ["duplicate_pair", "null_game", "null_genre"])
def test_game_genres_tests_reject_bad_output(built_staging, dbt_environment, tmp_path, defect):
    """Prove the pair/null tests fail on broken output and recover after restoration."""

    _, output_schema = built_staging
    with create_connection() as connection:
        original = connection.execute(
            "SELECT pg_get_viewdef(c.oid) FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relname = 'int_game_genres'", (output_schema,),
        ).fetchone()[0].strip().rstrip(";")
        extra = {"duplicate_pair": "4::bigint, 999::bigint",
                 "null_game": "NULL::bigint, 999::bigint",
                 "null_genre": "4::bigint, NULL::bigint"}[defect]
        connection.execute(sql.SQL("CREATE OR REPLACE VIEW {} AS {} UNION ALL SELECT " + extra).format(
            sql.Identifier(output_schema, "int_game_genres"), sql.SQL(original),
        ))
    try:
        process, results, _ = run_dbt(
            tmp_path, dbt_environment, "test", "--select", "int_game_genres",
            "--indirect-selection", "cautious",
        )
        assert process.returncode == 1, process.stdout + process.stderr
        assert len(results) == 3
        failed = [row for row in results if row["status"] == "fail"]
        assert len(failed) == 1
        expected = {"duplicate_pair": "int_game_genres_unique_pair",
                    "null_game": "not_null_int_game_genres_game_id",
                    "null_genre": "not_null_int_game_genres_genre_id"}[defect]
        assert failed[0]["unique_id"].startswith(f"test.data_platform.{expected}")
        assert failed[0]["failures"] == 1
        assert sum(row["status"] == "pass" for row in results) == 2
    finally:
        with create_connection() as connection:
            connection.execute(sql.SQL("CREATE OR REPLACE VIEW {} AS {}").format(
                sql.Identifier(output_schema, "int_game_genres"), sql.SQL(original),
            ))
    process, results, _ = run_dbt(
        tmp_path, dbt_environment, "test", "--select", "int_game_genres",
        "--indirect-selection", "cautious",
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert len(results) == 3
    assert all(row["status"] == "pass" for row in results)


@pytest.mark.dbt_models("+int_game_platforms")
def test_game_platforms_values_and_incomplete_coverage(built_staging, dbt_environment, tmp_path):
    """Expand real JSONB, collapse duplicates, and retain unmatched/reused BIGINT IDs."""

    source_schema, output_schema = built_staging
    manifest = json.loads((tmp_path / "target/manifest.json").read_text())
    node = manifest["nodes"]["model.data_platform.int_game_platforms"]
    assert node["depends_on"]["nodes"] == ["model.data_platform.stg_games"]
    assert node["schema"] == output_schema
    assert node["config"]["materialized"] == "view"
    assert node["description"].strip()
    assert set(node["columns"]) == {"game_id", "platform_id"}
    assert all(column["description"].strip() for column in node["columns"].values())
    with create_connection() as connection:
        assert connection.execute(
            "SELECT table_type FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = 'int_game_platforms'", (output_schema,),
        ).fetchone() == ("VIEW",)
        types = connection.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = 'int_game_platforms'", (output_schema,),
        ).fetchall()
        assert dict(types) == {"game_id": "bigint", "platform_id": "bigint"}
        # Baseline games 1/2/3 have absent/JSON-null/empty arrays: none get a row.
        assert connection.execute(
            f"SELECT * FROM {output_schema}.int_game_platforms ORDER BY 1, 2"
        ).fetchall() == [(4, 2), (4, 3), (4, 999)]
        raw_games.upsert_raw_games(connection, [
            {"id": 3000000001, "platforms": [999, 1, 3000000000, 3000000002, 1, "1", "0001", 0, -1]},
        ], source_schema, FETCHED_AT)
        rows = connection.execute(
            f"SELECT * FROM {output_schema}.int_game_platforms ORDER BY 1, 2"
        ).fetchall()
        assert rows == [(4, 2), (4, 3), (4, 999), (3000000001, -1), (3000000001, 0),
                        (3000000001, 1), (3000000001, 999),
                        (3000000001, 3000000000), (3000000001, 3000000002)]
        assert len(rows) == len(set(rows))
        unmatched = connection.execute(f"""
            SELECT bridge.game_id, bridge.platform_id
            FROM {output_schema}.int_game_platforms bridge
            LEFT JOIN {output_schema}.stg_platforms platforms USING (platform_id)
            WHERE platforms.platform_id IS NULL ORDER BY 1, 2
        """).fetchall()
        assert unmatched == [(4, 999), (3000000001, -1), (3000000001, 0),
                             (3000000001, 999), (3000000001, 3000000002)]
        # Independent Python expectation over original arrays checks both omissions
        # and extras, without reusing the model's SQL expansion.
        raw = connection.execute(
            f"SELECT igdb_id, payload FROM {source_schema}.raw_games"
        ).fetchall()
        assert set(rows) == {(game_id, int(platform_id)) for game_id, payload in raw
                             for platform_id in (payload.get("platforms") or [])}

    process, results, _ = run_dbt(
        tmp_path, dbt_environment, "test", "--select", "int_game_platforms",
        "--indirect-selection", "cautious",
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert len(results) == 3
    assert all(row["status"] == "pass" for row in results)


@pytest.mark.dbt_models("+int_game_platforms")
def test_game_platforms_rejects_malformed_arrays_and_null_members(
    built_staging, dbt_environment, tmp_path,
):
    """Bad arrays/casts raise; a null member is exposed to the not-null test."""

    source_schema, output_schema = built_staging
    for value in (42, {}, "bad-array", ["bad-id"], [1.5], [True], [{}], [[1]], [2**63]):
        with create_connection() as connection:
            raw_games.upsert_raw_games(connection, [{"id": 6, "platforms": value}],
                                       source_schema, FETCHED_AT)
        with pytest.raises(psycopg.DataError):
            with create_connection() as connection:
                connection.execute(f"SELECT * FROM {output_schema}.int_game_platforms").fetchall()
    with create_connection() as connection:
        raw_games.upsert_raw_games(connection, [{"id": 6, "platforms": [999, None]}],
                                   source_schema, FETCHED_AT)
        assert connection.execute(
            f"SELECT * FROM {output_schema}.int_game_platforms WHERE game_id = 6 ORDER BY platform_id"
        ).fetchall() == [(6, 999), (6, None)]
    process, results, _ = run_dbt(
        tmp_path, dbt_environment, "test", "--select", "int_game_platforms",
        "--indirect-selection", "cautious",
    )
    assert process.returncode == 1, process.stdout + process.stderr
    assert len(results) == 3
    failed = [row for row in results if row["status"] == "fail"]
    assert len(failed) == 1
    assert failed[0]["unique_id"].startswith("test.data_platform.not_null_int_game_platforms_platform_id.")
    assert failed[0]["failures"] == 1

    with create_connection() as connection:
        raw_games.upsert_raw_games(connection, [{"id": 6, "platforms": [999, "999"]}],
                                   source_schema, FETCHED_AT)
        assert connection.execute(
            f"SELECT * FROM {output_schema}.int_game_platforms WHERE game_id = 6"
        ).fetchall() == [(6, 999)]
    process, results, _ = run_dbt(
        tmp_path, dbt_environment, "test", "--select", "int_game_platforms",
        "--indirect-selection", "cautious",
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert len(results) == 3
    assert all(row["status"] == "pass" for row in results)


@pytest.mark.dbt_models("+int_game_platforms")
@pytest.mark.parametrize("defect", ["duplicate_pair", "null_game", "null_platform"])
def test_game_platforms_tests_reject_bad_output(built_staging, dbt_environment, tmp_path, defect):
    """Prove the pair/null tests fail on broken output and recover after restoration."""

    _, output_schema = built_staging
    with create_connection() as connection:
        original = connection.execute(
            "SELECT pg_get_viewdef(c.oid) FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relname = 'int_game_platforms'", (output_schema,),
        ).fetchone()[0].strip().rstrip(";")
        extra = {"duplicate_pair": "4::bigint, 999::bigint",
                 "null_game": "NULL::bigint, 999::bigint",
                 "null_platform": "4::bigint, NULL::bigint"}[defect]
        connection.execute(sql.SQL("CREATE OR REPLACE VIEW {} AS {} UNION ALL SELECT " + extra).format(
            sql.Identifier(output_schema, "int_game_platforms"), sql.SQL(original),
        ))
    try:
        process, results, _ = run_dbt(
            tmp_path, dbt_environment, "test", "--select", "int_game_platforms",
            "--indirect-selection", "cautious",
        )
        assert process.returncode == 1, process.stdout + process.stderr
        assert len(results) == 3
        failed = [row for row in results if row["status"] == "fail"]
        assert len(failed) == 1
        expected = {"duplicate_pair": "int_game_platforms_unique_pair",
                    "null_game": "not_null_int_game_platforms_game_id",
                    "null_platform": "not_null_int_game_platforms_platform_id"}[defect]
        assert failed[0]["unique_id"].startswith(f"test.data_platform.{expected}")
        assert failed[0]["failures"] == 1
        assert sum(row["status"] == "pass" for row in results) == 2
    finally:
        with create_connection() as connection:
            connection.execute(sql.SQL("CREATE OR REPLACE VIEW {} AS {}").format(
                sql.Identifier(output_schema, "int_game_platforms"), sql.SQL(original),
            ))
    process, results, _ = run_dbt(
        tmp_path, dbt_environment, "test", "--select", "int_game_platforms",
        "--indirect-selection", "cautious",
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert len(results) == 3
    assert all(row["status"] == "pass" for row in results)


@pytest.mark.dbt_models("+int_game_companies")
def test_game_companies_values_and_incomplete_coverage(built_staging, dbt_environment, tmp_path):
    """Preserve record grain, repeated pairs, all nullable roles, and unloaded references."""

    source_schema, output_schema = built_staging
    manifest = json.loads((tmp_path / "target/manifest.json").read_text())
    node = manifest["nodes"]["model.data_platform.int_game_companies"]
    assert node["depends_on"]["nodes"] == ["model.data_platform.stg_involved_companies"]
    assert node["schema"] == output_schema
    assert node["config"]["materialized"] == "view"
    assert node["description"].strip()
    columns = {"involved_company_id": "bigint", "game_id": "bigint", "company_id": "bigint",
               "developer": "boolean", "publisher": "boolean"}
    assert set(node["columns"]) == set(columns)
    assert all(column["description"].strip() for column in node["columns"].values())
    model_tests = [test for test in manifest["nodes"].values()
                   if test["resource_type"] == "test"
                   and test["depends_on"]["nodes"] == [node["unique_id"]]]
    assert len(model_tests) == 2
    assert {test["test_metadata"]["name"] for test in model_tests} == {"unique", "not_null"}
    assert all(test["column_name"] == "involved_company_id"
               and test["config"]["severity"] == "ERROR" for test in model_tests)
    with create_connection() as connection:
        assert connection.execute(
            "SELECT table_type FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = 'int_game_companies'", (output_schema,),
        ).fetchone() == ("VIEW",)
        assert dict(connection.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = 'int_game_companies'", (output_schema,),
        ).fetchall()) == columns
        baseline = [(1, None, None, None, None), (2, None, None, None, None),
                    (3, 3000000001, 3000000002, True, False),
                    (4, 3000000001, 3000000002, False, True), (5, 0, 0, True, True),
                    (3000000000, 4, 4, False, False)]
        assert connection.execute(
            f"SELECT * FROM {output_schema}.int_game_companies ORDER BY 1"
        ).fetchall() == baseline
        # Every nullable role combination on the same pair, plus identical-role
        # records: neither pair deduplication nor role aggregation is valid.
        roles = [(developer, publisher) for developer in (True, False, None)
                 for publisher in (True, False, None)]
        records = [{"id": 10 + index, "game": 3000000001, "company": 3000000002,
                    "developer": developer, "publisher": publisher}
                   for index, (developer, publisher) in enumerate(roles)]
        records += [{"id": 20, "game": None, "company": 4, "developer": True},
                    {"id": 21, "game": 4, "company": None, "publisher": False},
                    {"id": 22, "game": "-1", "company": "0000",
                     "developer": "yes", "publisher": "0"}]
        raw_involved_companies.upsert_raw_involved_companies(
            connection, records, source_schema, FETCHED_AT,
        )
        rows = connection.execute(
            f"SELECT * FROM {output_schema}.int_game_companies ORDER BY 1"
        ).fetchall()
        expected = baseline + [(10 + i, 3000000001, 3000000002, d, p)
                               for i, (d, p) in enumerate(roles)]
        expected += [(20, None, 4, True, None), (21, 4, None, None, False),
                     (22, -1, 0, True, False)]
        assert rows == sorted(expected)
        assert len(rows) == len({row[0] for row in rows})
        assert rows == connection.execute(
            f"SELECT involved_company_id, game_id, company_id, developer, publisher "
            f"FROM {output_schema}.stg_involved_companies ORDER BY 1"
        ).fetchall()
        unmatched = connection.execute(f"""
            SELECT bridge.involved_company_id FROM {output_schema}.int_game_companies bridge
            LEFT JOIN {output_schema}.stg_games games USING (game_id)
            LEFT JOIN {output_schema}.stg_companies companies USING (company_id)
            WHERE (bridge.game_id IS NOT NULL AND games.game_id IS NULL)
               OR (bridge.company_id IS NOT NULL AND companies.company_id IS NULL)
            ORDER BY 1
        """).fetchall()
        assert unmatched == [(i,) for i in [3, 4, 5, *range(10, 19), 22]]
        # Game 4's array is [5, 4, 999], yet relationship 3000000000 points to it.
        # Pair preservation above proves that no reciprocal-array join is required.
    process, results, _ = run_dbt(
        tmp_path, dbt_environment, "test", "--select", "int_game_companies",
        "--indirect-selection", "cautious",
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert len(results) == 2
    assert all(row["status"] == "pass" for row in results)


@pytest.mark.dbt_models("+int_game_companies")
def test_game_companies_malformed_values_and_recovery(built_staging, dbt_environment, tmp_path):
    """Direct staging casts raise on malformed references/roles; corrected input recovers."""

    source_schema, output_schema = built_staging
    for field, invalid_values in (
        ("game", ("bad-id", 1.5, True, {}, [], 2**63)),
        ("company", ("bad-id", 1.5, False, {}, [], -(2**63) - 1)),
        ("developer", ("bad-role", 2, {}, [])),
        ("publisher", ("bad-role", 2, {}, [])),
    ):
        for value in invalid_values:
            with create_connection() as connection:
                raw_involved_companies.upsert_raw_involved_companies(
                    connection, [{"id": 6, field: value}], source_schema, FETCHED_AT,
                )
            with pytest.raises(psycopg.DataError):
                with create_connection() as connection:
                    connection.execute(f"SELECT * FROM {output_schema}.int_game_companies").fetchall()
            with create_connection() as connection:
                raw_involved_companies.upsert_raw_involved_companies(
                    connection, [{"id": 6, "game": 999, "company": 999,
                                  "developer": False, "publisher": None}], source_schema, FETCHED_AT,
                )
                assert connection.execute(
                    f"SELECT * FROM {output_schema}.int_game_companies WHERE involved_company_id = 6"
                ).fetchone() == (6, 999, 999, False, None)
    process, results, _ = run_dbt(
        tmp_path, dbt_environment, "test", "--select", "int_game_companies",
        "--indirect-selection", "cautious",
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert len(results) == 2
    assert all(row["status"] == "pass" for row in results)


@pytest.mark.dbt_models("+int_game_companies")
@pytest.mark.parametrize("defect", ["duplicate", "null"])
def test_game_companies_tests_reject_bad_output(built_staging, dbt_environment, tmp_path, defect):
    """Prove record-key tests fail independently and recover after view restoration."""

    _, output_schema = built_staging
    with create_connection() as connection:
        original = connection.execute(
            "SELECT pg_get_viewdef(c.oid) FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relname = 'int_game_companies'", (output_schema,),
        ).fetchone()[0].strip().rstrip(";")
        # Duplicate identity with different references/roles must still fail.
        identifier = "1" if defect == "duplicate" else "NULL"
        extra = f"{identifier}::bigint, 999::bigint, 999::bigint, true, false"
        connection.execute(sql.SQL("CREATE OR REPLACE VIEW {} AS {} UNION ALL SELECT " + extra).format(
            sql.Identifier(output_schema, "int_game_companies"), sql.SQL(original),
        ))
    try:
        process, results, _ = run_dbt(
            tmp_path, dbt_environment, "test", "--select", "int_game_companies",
            "--indirect-selection", "cautious",
        )
        assert process.returncode == 1, process.stdout + process.stderr
        assert len(results) == 2
        failed = [row for row in results if row["status"] == "fail"]
        assert len(failed) == 1
        test = "unique" if defect == "duplicate" else "not_null"
        assert failed[0]["unique_id"].startswith(
            f"test.data_platform.{test}_int_game_companies_involved_company_id."
        )
        assert failed[0]["failures"] == 1
        assert sum(row["status"] == "pass" for row in results) == 1
    finally:
        with create_connection() as connection:
            connection.execute(sql.SQL("CREATE OR REPLACE VIEW {} AS {}").format(
                sql.Identifier(output_schema, "int_game_companies"), sql.SQL(original),
            ))
    process, results, _ = run_dbt(
        tmp_path, dbt_environment, "test", "--select", "int_game_companies",
        "--indirect-selection", "cautious",
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert len(results) == 2
    assert all(row["status"] == "pass" for row in results)


def assert_catalog_matches_sources(output_schema):
    """Compare every catalog value with independent Python grouping of source models."""

    with create_connection() as connection:
        games = connection.execute(
            f"SELECT game_id, name, slug, first_release_at, rating, rating_count, "
            f"total_rating, total_rating_count FROM {output_schema}.stg_games ORDER BY game_id"
        ).fetchall()
        aggregates = []
        for entity, key in (("genres", "genre_id"), ("platforms", "platform_id")):
            names = dict(connection.execute(
                f"SELECT {key}, name FROM {output_schema}.stg_{entity}"
            ).fetchall())
            grouped = {}
            for game_id, ref_id in connection.execute(
                f"SELECT * FROM {output_schema}.int_game_{entity} ORDER BY game_id, {key}"
            ).fetchall():
                grouped.setdefault(game_id, []).append({key: ref_id, "name": names.get(ref_id)})
            aggregates.append(grouped)
        names = dict(connection.execute(
            f"SELECT company_id, name FROM {output_schema}.stg_companies"
        ).fetchall())
        companies = {}
        for record_id, game_id, company_id, developer, publisher in connection.execute(
            f"SELECT * FROM {output_schema}.int_game_companies ORDER BY involved_company_id"
        ).fetchall():
            companies.setdefault(game_id, []).append({
                "involved_company_id": record_id, "company_id": company_id,
                "name": names.get(company_id), "developer": developer, "publisher": publisher,
            })
        aggregates.append(companies)
        actual = connection.execute(
            f"SELECT * FROM {output_schema}.mart_game_catalog ORDER BY game_id"
        ).fetchall()
    expected = [game + tuple(grouped.get(game[0], []) for grouped in aggregates) for game in games]
    assert actual == expected
    assert len(actual) == len({row[0] for row in actual}) == len(games)
    return actual


@pytest.mark.dbt_models("+mart_game_catalog")
def test_game_catalog_values_grain_and_incomplete_coverage(built_staging, dbt_environment, tmp_path):
    """Cover scalar fidelity, missing data, independent aggregates, roles, and ordering."""

    source_schema, output_schema = built_staging
    manifest = json.loads((tmp_path / "target/manifest.json").read_text())
    node = manifest["nodes"]["model.data_platform.mart_game_catalog"]
    assert node["config"]["materialized"] == "table"
    assert node["schema"] == output_schema
    assert set(node["depends_on"]["nodes"]) == {
        f"model.data_platform.{model}" for model in (
            "stg_games", "stg_genres", "stg_platforms", "stg_companies",
            "int_game_genres", "int_game_platforms", "int_game_companies",
        )
    }
    columns = {"game_id": "bigint", "name": "text", "slug": "text",
               "first_release_at": "timestamp with time zone", "rating": "numeric",
               "rating_count": "bigint", "total_rating": "numeric", "total_rating_count": "bigint",
               "observed_genres": "jsonb", "observed_platforms": "jsonb",
               "observed_company_relationships": "jsonb"}
    assert node["description"].strip() and set(node["columns"]) == set(columns)
    assert all(column["description"].strip() for column in node["columns"].values())
    with create_connection() as connection:
        assert connection.execute(
            "SELECT table_type FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = 'mart_game_catalog'", (output_schema,),
        ).fetchone() == ("BASE TABLE",)
        assert dict(connection.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = 'mart_game_catalog'", (output_schema,),
        ).fetchall()) == columns
    baseline = assert_catalog_matches_sources(output_schema)
    # Absent, explicit JSON null, and empty arrays all retain their games.
    assert baseline[0] == (1, None, None, None, None, None, None, None, [], [], [])
    assert baseline[1] == (2, None, None, None, None, None, None, None, [], [], [])
    assert baseline[2] == (3, None, None, datetime.fromtimestamp(0, timezone.utc),
                           Decimal(0), 0, Decimal(0), 0, [], [], [])
    assert baseline[3][:8] == (4, "Example", "example", datetime.fromtimestamp(-1, timezone.utc),
                               Decimal("83.125"), 4, Decimal("90.5"), 7)
    assert baseline[4][5] == 3000000000
    assert baseline[3][8] == [{"genre_id": i, "name": None} for i in (1, 2, 999)]
    assert baseline[3][9] == [{"platform_id": 2, "name": None},
                              {"platform_id": 3, "name": ""}, {"platform_id": 999, "name": None}]
    assert baseline[3][10] == [{"involved_company_id": 3000000000, "company_id": 4,
                               "name": "Example Studio", "developer": False, "publisher": False}]

    roles = [(d, p) for d in (True, False, None) for p in (True, False, None)]
    records = [{"id": 10 + i, "game": 4, "company": 4, "developer": d, "publisher": p}
               for i, (d, p) in enumerate(roles)]
    records += [{"id": 30, "game": 4, "company": 4, "developer": True, "publisher": True},
                {"id": 31, "game": 4, "company": 999, "developer": False},
                {"id": 32, "game": 4, "company": None, "publisher": False},
                {"id": 33, "game": 4}, {"id": 34, "game": 4, "company": 3},
                {"id": 35, "game": "-1", "company": "0000", "developer": "yes", "publisher": "0"},
                {"id": 36, "game": 4, "company": 2}]
    with create_connection() as connection:
        raw_involved_companies.upsert_raw_involved_companies(
            connection, list(reversed(records)), source_schema, FETCHED_AT,
        )
        raw_games.upsert_raw_games(connection, [
            {"id": -1, "name": "", "slug": "", "genres": [999, 4, "04", 3, 0, -1, 3000000000],
             "platforms": [999, 4, "004", 3, 0, -1, 3000000000], "involved_companies": [999]},
            {"id": 0},
        ], source_schema, FETCHED_AT)
        # Two different IDs may have the same label; they must remain separate.
        raw_genres.upsert_raw_genres(connection, [{"id": 999, "name": "Role-playing (RPG)"}],
                                     source_schema, FETCHED_AT)
        raw_platforms.upsert_raw_platforms(connection, [{"id": 999, "name": "PC (Microsoft Windows)"}],
                                           source_schema, FETCHED_AT)
        # A table snapshot changes only after a rebuild.
        assert connection.execute(
            f"SELECT * FROM {output_schema}.mart_game_catalog ORDER BY game_id"
        ).fetchall() == baseline
    process, results, _ = run_dbt(tmp_path, dbt_environment, "build", "--select", "mart_game_catalog")
    assert process.returncode == 0, process.stdout + process.stderr
    assert len(results) == 5 and sum(row["status"] == "pass" for row in results) == 4
    rows = assert_catalog_matches_sources(output_schema)
    assert rows[0][:3] == (-1, "", "")
    assert rows[0][8] == [
        {"genre_id": i, "name": name} for i, name in (
            (-1, None), (0, None), (3, ""), (4, "Role-playing (RPG)"),
            (999, "Role-playing (RPG)"), (3000000000, "Stratégie"),
        )
    ]
    assert rows[0][9] == [
        {"platform_id": i, "name": name} for i, name in (
            (-1, None), (0, None), (3, ""), (4, "PC (Microsoft Windows)"),
            (999, "PC (Microsoft Windows)"), (3000000000, "Café Console"),
        )
    ]
    assert rows[0][10] == [{"involved_company_id": 35, "company_id": 0, "name": None,
                           "developer": True, "publisher": False}]
    game = next(row for row in rows if row[0] == 4)
    assert len(game[8]) == len(game[9]) == 3  # Neither expands with company fanout.
    assert [r["involved_company_id"] for r in game[10]] == [*range(10, 19), 30, 31, 32, 33, 34, 36, 3000000000]
    assert [(r["developer"], r["publisher"]) for r in game[10][:9]] == roles
    assert game[10][0] == dict(game[10][9], involved_company_id=10)
    assert [r["name"] for r in game[10][10:15]] == [None, None, None, "", None]
    assert game[10][11]["company_id"] is None and game[10][12]["company_id"] is None
    assert game[:8] == baseline[3][:8]
    assert not any(row[0] == 3000000001 for row in rows)  # Unloaded games cannot invent catalog rows.


@pytest.mark.dbt_models("+mart_game_catalog")
def test_game_catalog_empty_sources(built_staging, dbt_environment, tmp_path):
    """An empty staged game set produces an empty catalog even with orphan relationships."""

    source_schema, output_schema = built_staging
    with create_connection() as connection:
        connection.execute(f"DELETE FROM {source_schema}.raw_games")  # Disposable fixture only.
    process, results, _ = run_dbt(tmp_path, dbt_environment, "build", "--select", "mart_game_catalog")
    assert process.returncode == 0, process.stdout + process.stderr
    assert len(results) == 5 and sum(row["status"] == "pass" for row in results) == 4
    assert assert_catalog_matches_sources(output_schema) == []


@pytest.mark.dbt_models("+mart_game_catalog")
@pytest.mark.parametrize("defect", ["duplicate", "null", "missing", "extra"])
def test_game_catalog_tests_reject_bad_output(built_staging, dbt_environment, tmp_path, defect):
    """Corrupt only the disposable table; prove each invariant fails and rebuild recovers."""

    _, output_schema = built_staging
    with create_connection() as connection:
        if defect == "duplicate":
            connection.execute(f"INSERT INTO {output_schema}.mart_game_catalog "
                               f"SELECT * FROM {output_schema}.mart_game_catalog WHERE game_id = 1")
        elif defect == "null":
            connection.execute(f"INSERT INTO {output_schema}.mart_game_catalog (game_id) VALUES (NULL)")
        elif defect == "missing":
            connection.execute(f"DELETE FROM {output_schema}.mart_game_catalog WHERE game_id = 1")
        else:
            connection.execute(f"INSERT INTO {output_schema}.mart_game_catalog (game_id) VALUES (999)")
    try:
        process, results, manifest = run_dbt(
            tmp_path, dbt_environment, "test", "--select", "mart_game_catalog",
        )
        assert process.returncode == 1, process.stdout + process.stderr
        assert len(results) == 4
        failed = {manifest["nodes"][r["unique_id"]]["name"]: r["failures"]
                  for r in results if r["status"] == "fail"}
        expected = {
            "duplicate": {"unique_mart_game_catalog_game_id": 1},
            "null": {"not_null_mart_game_catalog_game_id": 1, "mart_game_catalog_game_coverage": 1,
                     "mart_game_catalog_relationship_arrays": 3},
            "missing": {"mart_game_catalog_game_coverage": 1},
            "extra": {"mart_game_catalog_game_coverage": 1,
                      "mart_game_catalog_relationship_arrays": 3},
        }
        assert failed == expected[defect]
        assert sum(row["status"] == "pass" for row in results) == 4 - len(failed)
    finally:
        process, results, _ = run_dbt(tmp_path, dbt_environment, "build", "--select", "mart_game_catalog")
        assert process.returncode == 0, process.stdout + process.stderr
        assert len(results) == 5 and sum(row["status"] == "pass" for row in results) == 4
    assert_catalog_matches_sources(output_schema)


@pytest.mark.dbt_models("+mart_game_catalog")
@pytest.mark.parametrize("entity,field", [("games", "rating"), ("games", "genres"),
                                         ("involved_companies", "developer")])
def test_game_catalog_malformed_input_and_recovery(
    built_staging, dbt_environment, tmp_path, entity, field,
):
    """Materializing projected casts rejects invalid input; corrected source rebuilds."""

    source_schema, output_schema = built_staging
    before = assert_catalog_matches_sources(output_schema)
    module = raw_games if entity == "games" else raw_involved_companies
    load = getattr(module, f"upsert_raw_{entity}")
    with create_connection() as connection:
        load(connection, [{"id": 6, "game": 4, field: "invalid-value"}], source_schema, FETCHED_AT)
    try:
        process, results, _ = run_dbt(tmp_path, dbt_environment, "run", "--select", "mart_game_catalog")
        assert process.returncode == 1, process.stdout + process.stderr
        assert len(results) == 1 and results[0]["status"] == "error"
        with create_connection() as connection:
            assert connection.execute(
                f"SELECT * FROM {output_schema}.mart_game_catalog ORDER BY game_id"
            ).fetchall() == before
    finally:
        with create_connection() as connection:
            load(connection, [{"id": 6, "game": 4}], source_schema, FETCHED_AT)
        process, results, _ = run_dbt(tmp_path, dbt_environment, "build", "--select", "mart_game_catalog")
        assert process.returncode == 0, process.stdout + process.stderr
        assert len(results) == 5 and sum(row["status"] == "pass" for row in results) == 4
    assert_catalog_matches_sources(output_schema)


@pytest.mark.dbt_models("+mart_game_catalog")
def test_game_catalog_relationship_arrays_fail_and_recover(built_staging, dbt_environment, tmp_path):
    """Reject each invalid container independently, retaining nullable object values."""

    _, output_schema = built_staging
    before = assert_catalog_matches_sources(output_schema)
    columns = ("observed_genres", "observed_platforms", "observed_company_relationships")
    # Each column has SQL NULL, JSON null, an object and a scalar on separate rows.
    # The valid fifth row and existing empty arrays must not become violations.
    with create_connection() as connection:
        for column in columns:
            for game_id, value in enumerate((None, "null", "{}", "false"), start=1):
                connection.execute(
                    sql.SQL("UPDATE {}.mart_game_catalog SET {} = %s::jsonb WHERE game_id = %s")
                    .format(sql.Identifier(output_schema), sql.Identifier(column)),
                    (value, game_id),
                )
    try:
        process, results, manifest = run_dbt(
            tmp_path, dbt_environment, "test", "--select", "mart_game_catalog",
        )
        assert process.returncode == 1, process.stdout + process.stderr
        assert len(results) == 4
        failed = {manifest["nodes"][r["unique_id"]]["name"]: r["failures"]
                  for r in results if r["status"] == "fail"}
        assert failed == {"mart_game_catalog_relationship_arrays": 12}
        assert sum(r["status"] == "pass" for r in results) == 3
        node = manifest["nodes"]["test.data_platform.mart_game_catalog_relationship_arrays"]
        assert node["depends_on"]["nodes"] == ["model.data_platform.mart_game_catalog"]
        assert node["config"]["severity"] == "ERROR"
        with create_connection() as connection:
            violations = connection.execute(node["compiled_code"]).fetchall()
        assert sorted(violations) == sorted(
            (game_id, column) for game_id in range(1, 5) for column in columns
        )
    finally:
        process, results, _ = run_dbt(
            tmp_path, dbt_environment, "build", "--select", "mart_game_catalog",
        )
        assert process.returncode == 0, process.stdout + process.stderr
        assert len(results) == 5 and sum(r["status"] == "pass" for r in results) == 4
    assert assert_catalog_matches_sources(output_schema) == before


def assert_release_trends_matches_sources(output_schema):
    """Reconcile exact annual counts and undated population using Python UTC grouping."""

    with create_connection() as connection:
        games = connection.execute(
            f"SELECT game_id, first_release_at FROM {output_schema}.stg_games"
        ).fetchall()
        actual = connection.execute(
            f"SELECT * FROM {output_schema}.mart_release_trends ORDER BY release_year"
        ).fetchall()
    expected = {}
    undated = 0
    for _, released in games:
        if released is None:
            undated += 1
        else:
            year = released.astimezone(timezone.utc).year
            expected[year] = expected.get(year, 0) + 1
    assert actual == sorted(expected.items())
    assert len(actual) == len({year for year, _ in actual})
    assert sum(count for _, count in actual) + undated == len(games)
    return actual, undated


@pytest.mark.dbt_models("+mart_release_trends")
def test_release_trends_values_utc_grain_and_reconciliation(built_staging, dbt_environment, tmp_path):
    """UTC boundary years must survive different build-session timezones and fanout."""

    source_schema, output_schema = built_staging
    manifest = json.loads((tmp_path / "target/manifest.json").read_text())
    node = manifest["nodes"]["model.data_platform.mart_release_trends"]
    assert node["config"]["materialized"] == "table" and node["schema"] == output_schema
    assert node["depends_on"]["nodes"] == ["model.data_platform.stg_games"]
    assert node["description"].strip()
    assert set(node["columns"]) == {"release_year", "release_count"}
    assert all(column["description"].strip() for column in node["columns"].values())
    with create_connection() as connection:
        assert connection.execute(
            "SELECT table_type FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = 'mart_release_trends'", (output_schema,),
        ).fetchone() == ("BASE TABLE",)
        assert dict(connection.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = 'mart_release_trends'", (output_schema,),
        ).fetchall()) == {"release_year": "integer", "release_count": "bigint"}
        baseline, undated = assert_release_trends_matches_sources(output_schema)
        assert baseline == [(1969, 1), (1970, 1), (2026, 1)] and undated == 2
        # Every game has many relationships; dates, not those multiplicities, drive counts.
        records = [{"id": i, "first_release_date": epoch, "genres": [1, 2, 999],
                    "platforms": [3, 4, 999], "involved_companies": [3, 4, 999]}
                   for i, epoch in enumerate([-1, 0, 946684799, 946684800, "946684801",
                                              4102444800], start=10)]
        raw_games.upsert_raw_games(connection, records, source_schema, FETCHED_AT)
        assert connection.execute(
            f"SELECT * FROM {output_schema}.mart_release_trends ORDER BY release_year"
        ).fetchall() == baseline  # Table changes only on rebuild.
    expected = [(1969, 2), (1970, 2), (1999, 1), (2000, 2), (2026, 1), (2100, 1)]
    for zone in ("UTC", "America/Los_Angeles", "Asia/Tokyo"):
        env = dict(dbt_environment, PGOPTIONS=f"-c timezone={zone}")
        # Prove libpq receives the requested session setting, also used by dbt.
        with create_connection() as connection:
            # ConnectionInfo.dsn omits the password; retain it for authenticated servers.
            with psycopg.connect(
                connection.info.dsn, password=connection.info.password, options=env["PGOPTIONS"],
            ) as zoned:
                assert zoned.execute("SHOW timezone").fetchone() == (zone,)
        process, results, _ = run_dbt(tmp_path, env, "build", "--select", "mart_release_trends")
        assert process.returncode == 0, process.stdout + process.stderr
        assert len(results) == 6 and sum(row["status"] == "pass" for row in results) == 5
        assert assert_release_trends_matches_sources(output_schema) == (expected, 2)


@pytest.mark.dbt_models("+mart_release_trends")
@pytest.mark.parametrize("population", ["empty", "undated"])
def test_release_trends_no_dated_observations(built_staging, dbt_environment, tmp_path, population):
    """No unknown bucket or zero-filled calendar is invented for empty/all-NULL input."""

    source_schema, output_schema = built_staging
    with create_connection() as connection:
        connection.execute(f"DELETE FROM {source_schema}.raw_games")  # Disposable fixture only.
        if population == "undated":
            raw_games.upsert_raw_games(connection, [{"id": 1}, {"id": 2, "first_release_date": None}],
                                       source_schema, FETCHED_AT)
    process, results, _ = run_dbt(tmp_path, dbt_environment, "build", "--select", "mart_release_trends")
    assert process.returncode == 0, process.stdout + process.stderr
    assert len(results) == 6 and sum(row["status"] == "pass" for row in results) == 5
    assert assert_release_trends_matches_sources(output_schema) == ([], 2 if population == "undated" else 0)


@pytest.mark.dbt_models("+mart_release_trends")
@pytest.mark.parametrize("defect", ["duplicate", "null_year", "null_count", "zero", "negative",
                                  "missing", "extra", "wrong_count", "redistributed"])
def test_release_trends_tests_reject_bad_output(built_staging, dbt_environment, tmp_path, defect):
    """Each declared invariant rejects deliberate defects and recovers on rebuild."""

    _, output_schema = built_staging
    table = f"{output_schema}.mart_release_trends"
    mutations = {
        "duplicate": f"INSERT INTO {table} SELECT * FROM {table} WHERE release_year = 1970",
        "null_year": f"INSERT INTO {table} VALUES (NULL, 1)",
        "null_count": f"UPDATE {table} SET release_count = NULL WHERE release_year = 1970",
        "zero": f"UPDATE {table} SET release_count = 0 WHERE release_year = 1970",
        "negative": f"UPDATE {table} SET release_count = -1 WHERE release_year = 1970",
        "missing": f"DELETE FROM {table} WHERE release_year = 1970",
        "extra": f"INSERT INTO {table} VALUES (2001, 1)",
        "wrong_count": f"UPDATE {table} SET release_count = 2 WHERE release_year = 1970",
        "redistributed": f"UPDATE {table} SET release_year = 2001 WHERE release_year = 1970",
    }
    with create_connection() as connection:
        connection.execute(mutations[defect])
    reconciliation = "mart_release_trends_yearly_reconciliation"
    expected = {
        "duplicate": {"unique_mart_release_trends_release_year": 1},
        "null_year": {"not_null_mart_release_trends_release_year": 1, reconciliation: 1},
        "null_count": {"not_null_mart_release_trends_release_count": 1, reconciliation: 1},
        "zero": {"mart_release_trends_positive_count": 1, reconciliation: 1},
        "negative": {"mart_release_trends_positive_count": 1, reconciliation: 1},
        "missing": {reconciliation: 1}, "extra": {reconciliation: 1},
        "wrong_count": {reconciliation: 1}, "redistributed": {reconciliation: 2},
    }
    try:
        process, results, manifest = run_dbt(tmp_path, dbt_environment, "test", "--select", "mart_release_trends")
        assert process.returncode == 1, process.stdout + process.stderr
        assert len(results) == 5
        failed = {manifest["nodes"][row["unique_id"]]["name"]: row["failures"]
                  for row in results if row["status"] == "fail"}
        assert failed == expected[defect]
        assert sum(row["status"] == "pass" for row in results) == 5 - len(failed)
    finally:
        process, results, _ = run_dbt(tmp_path, dbt_environment, "build", "--select", "mart_release_trends")
        assert process.returncode == 0, process.stdout + process.stderr
        assert len(results) == 6 and sum(row["status"] == "pass" for row in results) == 5
    assert_release_trends_matches_sources(output_schema)


@pytest.mark.dbt_models("+mart_release_trends")
def test_release_trends_invalid_timestamp_and_recovery(built_staging, dbt_environment, tmp_path):
    """Invalid non-NULL dates fail materialization without replacing the prior table."""

    source_schema, output_schema = built_staging
    before, _ = assert_release_trends_matches_sources(output_schema)
    with create_connection() as connection:
        raw_games.upsert_raw_games(connection, [{"id": 6, "first_release_date": "invalid"}],
                                   source_schema, FETCHED_AT)
    try:
        process, results, _ = run_dbt(tmp_path, dbt_environment, "run", "--select", "mart_release_trends")
        assert process.returncode == 1, process.stdout + process.stderr
        assert len(results) == 1 and results[0]["status"] == "error"
        with create_connection() as connection:
            assert connection.execute(
                f"SELECT * FROM {output_schema}.mart_release_trends ORDER BY release_year"
            ).fetchall() == before
    finally:
        with create_connection() as connection:
            raw_games.upsert_raw_games(connection, [{"id": 6, "first_release_date": 0}],
                                       source_schema, FETCHED_AT)
        process, results, _ = run_dbt(tmp_path, dbt_environment, "build", "--select", "mart_release_trends")
        assert process.returncode == 0, process.stdout + process.stderr
        assert len(results) == 6 and sum(row["status"] == "pass" for row in results) == 5
    assert assert_release_trends_matches_sources(output_schema) == ([(1969, 1), (1970, 2), (2026, 1)], 2)


PERFORMANCE_MODELS = ("mart_genre_performance", "mart_platform_performance")


def build_performance(tmp_path, env):
    """Rebuild both independent snapshots and require all six mart tests to pass."""

    process, results, manifest = run_dbt(tmp_path, env, "build", "--select", *PERFORMANCE_MODELS)
    assert process.returncode == 0, process.stdout + process.stderr
    assert len(results) == 8 and sum(row["status"] == "pass" for row in results) == 6
    return manifest


def assert_performance_matches_sources(source_schema, output_schema):
    """Independently group Python sets and Decimal values, reconciling raw arrays/bridges."""

    result = {}
    with create_connection() as connection:
        games = {row[0]: row[1:] for row in connection.execute(
            f"SELECT game_id, rating, rating_count FROM {output_schema}.stg_games"
        ).fetchall()}
        raw = connection.execute(f"SELECT igdb_id, payload FROM {source_schema}.raw_games").fetchall()
        assert set(games) == {game_id for game_id, _ in raw}
        for dimension in ("genre", "platform"):
            key = f"{dimension}_id"
            pairs = set(connection.execute(
                f"SELECT game_id, {key} FROM {output_schema}.int_game_{dimension}s"
            ).fetchall())
            assert pairs == {(game_id, int(value)) for game_id, payload in raw
                             for value in (payload.get(f"{dimension}s") or [])}
            names = dict(connection.execute(
                f"SELECT {key}, name FROM {output_schema}.stg_{dimension}s"
            ).fetchall())
            members = {}
            for game_id, dimension_id in pairs:
                members.setdefault(dimension_id, set()).add(game_id)
            actual = connection.execute(
                f"SELECT * FROM {output_schema}.mart_{dimension}_performance ORDER BY {key}"
            ).fetchall()
            assert len(actual) == len({r[0] for r in actual}) == len(members)
            for row in actual:
                dimension_id, name, count, rated, average, counted, volume = row
                ids = members[dimension_id]
                ratings = [games[i][0] for i in ids if games[i][0] is not None]
                counts = [games[i][1] for i in ids if games[i][1] is not None]
                assert (name, count, rated, counted, volume) == (
                    names.get(dimension_id), len(ids), len(ratings), len(counts),
                    sum(counts) if counts else None,
                )
                if ratings:
                    # PostgreSQL NUMERIC AVG rounds repeating decimals at its result scale.
                    expected = sum(ratings) / len(ratings)
                    assert average == expected.quantize(Decimal(1).scaleb(average.as_tuple().exponent))
                else:
                    assert average is None
            assert sum(row[2] for row in actual) == len(pairs)
            result[dimension] = actual
    return result


@pytest.mark.dbt_models("+mart_genre_performance", "+mart_platform_performance")
def test_performance_values_grain_types_and_snapshot(built_staging, dbt_environment, tmp_path):
    """Exact metrics survive multi-membership, duplicates, missing labels and optional values."""

    source_schema, output_schema = built_staging
    baseline = assert_performance_matches_sources(source_schema, output_schema)
    with create_connection() as connection:
        # Only disposable fixture source tables are changed. Repeated IDs test raw upsert identity.
        connection.execute(f"DELETE FROM {source_schema}.raw_games")
        records = [
            {"id": 10, "rating": 999, "genres": [99], "platforms": [99]},
            {"id": 10, "rating": 80.25, "rating_count": 100, "total_rating": 1,
             "genres": [1, 1, "01", 2, 3, 999], "platforms": [1, "01", 2, 999]},
            {"id": 11, "rating": 0, "rating_count": 0,
             "genres": [1, 2], "platforms": [1, 3]},
            {"id": 12, "rating": None, "rating_count": 3000000000,
             "genres": [1, 4], "platforms": [1, 4]},
            {"id": 13, "rating": 20.75, "rating_count": None,
             "genres": [1, 5], "platforms": [1, 5]},
            {"id": 14, "rating": None, "rating_count": None,
             "genres": [2, 6], "platforms": [2, 6]},
            {"id": 15, "genres": [2, 7], "platforms": [2, 7]},
            {"id": 16, "rating": -10.5, "rating_count": -2,
             "genres": [-1, 0, 3000000000], "platforms": [-1, 0, 3000000000]},
            {"id": 17}, {"id": 18, "genres": None, "platforms": None},
            {"id": 19, "genres": [], "platforms": []},
        ]
        raw_games.upsert_raw_games(connection, records, source_schema, FETCHED_AT)
        for dimension, module in (("genre", raw_genres), ("platform", raw_platforms)):
            load = getattr(module, f"upsert_raw_{dimension}s")
            load(connection, [{"id": 1, "name": "old"}, {"id": 1, "name": "Shared"},
                              {"id": 2, "name": "Shared"}, {"id": 3, "name": ""},
                              {"id": 4}, {"id": 5, "name": None},
                              {"id": 88, "name": "No observed games"}], source_schema, FETCHED_AT)
            assert connection.execute(
                f"SELECT * FROM {output_schema}.mart_{dimension}_performance ORDER BY {dimension}_id"
            ).fetchall() == baseline[dimension]
    manifest = build_performance(tmp_path, dbt_environment)
    rows = assert_performance_matches_sources(source_schema, output_schema)
    for dimension in ("genre", "platform"):
        by_id = {r[0]: r for r in rows[dimension]}
        assert by_id[1] == (1, "Shared", 4, 3, Decimal("33.6666666666666667"), 3, 3000000100)
        assert by_id[999] == (999, None, 1, 1, Decimal("80.25"), 1, 100)
        assert by_id[4] == (4, None, 1, 0, None, 1, 3000000000)
        assert by_id[5] == (5, None, 1, 1, Decimal("20.75"), 0, None)
        assert by_id[6] == (6, None, 1, 0, None, 0, None)
        assert by_id[7] == (7, None, 1, 0, None, 0, None)
        assert by_id[3][1] == "" and 88 not in by_id and 99 not in by_id
        assert by_id[0] == (0, None, 1, 1, Decimal("-10.5"), 1, -2)
        assert len(by_id) == 11 and sum(r[2] for r in by_id.values()) > 10
        model = f"mart_{dimension}_performance"
        node = manifest["nodes"][f"model.data_platform.{model}"]
        assert node["config"]["materialized"] == "table" and node["schema"] == output_schema
        assert set(node["depends_on"]["nodes"]) == {
            f"model.data_platform.int_game_{dimension}s", "model.data_platform.stg_games",
            f"model.data_platform.stg_{dimension}s",
        }
        assert node["description"].strip()
        with create_connection() as connection:
            assert connection.execute(
                "SELECT table_type FROM information_schema.tables WHERE table_schema=%s AND table_name=%s",
                (output_schema, model),
            ).fetchone() == ("BASE TABLE",)
            types = dict(connection.execute(
                "SELECT column_name,data_type FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name=%s", (output_schema, model),
            ).fetchall())
        assert types == {f"{dimension}_id": "bigint", "name": "text", "game_count": "bigint",
                         "rated_game_count": "bigint", "avg_rating": "numeric",
                         "rating_count_game_count": "bigint", "rating_count_sum": "numeric"}
        assert set(node["columns"]) == set(types)
        assert all(c["description"].strip() for c in node["columns"].values())
    assert {r[0]: r for r in rows["platform"]}[3] == (3, "", 1, 1, 0, 1, 0)


@pytest.mark.dbt_models("+mart_genre_performance", "+mart_platform_performance")
@pytest.mark.parametrize("population", ["empty", "unassociated"])
def test_performance_empty_observations(built_staging, dbt_environment, tmp_path, population):
    """Loaded dimensions do not manufacture rows, including for missing/NULL/empty arrays."""

    source_schema, output_schema = built_staging
    with create_connection() as connection:
        connection.execute(f"DELETE FROM {source_schema}.raw_games")
        if population == "unassociated":
            raw_games.upsert_raw_games(connection, [{"id": 1}, {"id": 2, "genres": None, "platforms": None},
                                       {"id": 3, "genres": [], "platforms": []}], source_schema, FETCHED_AT)
    build_performance(tmp_path, dbt_environment)
    assert assert_performance_matches_sources(source_schema, output_schema) == {"genre": [], "platform": []}


@pytest.mark.dbt_models("+mart_genre_performance", "+mart_platform_performance")
def test_performance_repeated_bridge_pairs_do_not_inflate_metrics(built_staging, dbt_environment, tmp_path):
    """Defensive pair deduplication protects every metric even with broken bridge multiplicity."""

    source_schema, output_schema = built_staging
    baseline = assert_performance_matches_sources(source_schema, output_schema)
    originals = {}
    try:
        with create_connection() as connection:
            for dimension in ("genre", "platform"):
                model = f"{output_schema}.int_game_{dimension}s"
                original = connection.execute("SELECT pg_get_viewdef(%s::regclass)", (model,)).fetchone()[0].rstrip(";\n ")
                originals[model] = original
                connection.execute(f"CREATE OR REPLACE VIEW {model} AS "
                                   f"SELECT * FROM ({original}) a UNION ALL SELECT * FROM ({original}) b")
        build_performance(tmp_path, dbt_environment)
        assert assert_performance_matches_sources(source_schema, output_schema) == baseline
    finally:
        with create_connection() as connection:
            for model, original in originals.items():
                connection.execute(f"CREATE OR REPLACE VIEW {model} AS {original}")
    build_performance(tmp_path, dbt_environment)


@pytest.mark.dbt_models("+mart_genre_performance", "+mart_platform_performance")
def test_performance_invariants_fail_for_each_column_and_recover(built_staging, dbt_environment, tmp_path):
    """Each independently corrupted row must be returned by reconciliation, then recover."""

    source_schema, output_schema = built_staging
    # A different observed ID gets each defect, so every checked column must detect its own row.
    defects = [(column, value) for column in ("game_count", "rated_game_count", "avg_rating",
                                             "rating_count_game_count", "rating_count_sum")
               for value in (None, -1, 0, 999)] + [("name", "wrong"), ("name", "")]
    ids = list(range(100, 100 + len(defects)))
    with create_connection() as connection:
        raw_games.upsert_raw_games(connection, [{"id": 90, "rating": 42.5, "rating_count": 3,
                                   "genres": ids, "platforms": ids}], source_schema, FETCHED_AT)
    build_performance(tmp_path, dbt_environment)
    for dimension in ("genre", "platform"):
        table = f"{output_schema}.mart_{dimension}_performance"
        key = f"{dimension}_id"
        with create_connection() as connection:
            for dimension_id, (column, value) in zip(ids, defects):
                connection.execute(f"UPDATE {table} SET {column}=%s WHERE {key}=%s", (value, dimension_id))
            connection.execute(f"DELETE FROM {table} WHERE {key}=999")
            connection.execute(f"INSERT INTO {table} ({key}) VALUES (888), (NULL)")
            connection.execute(f"INSERT INTO {table} SELECT * FROM {table} WHERE {key}=2")
    try:
        process, results, manifest = run_dbt(tmp_path, dbt_environment, "test", "--select", *PERFORMANCE_MODELS)
        assert process.returncode == 1, process.stdout + process.stderr
        assert len(results) == 6 and all(r["status"] == "fail" for r in results)
        expected_failures = {}
        for dimension in ("genre", "platform"):
            model = f"mart_{dimension}_performance"
            expected_failures.update({f"unique_{model}_{dimension}_id": 1,
                                      f"not_null_{model}_{dimension}_id": 1,
                                      f"{model}_reconciliation": len(defects) + 3})
            node = manifest["nodes"][f"test.data_platform.{model}_reconciliation"]
            with create_connection() as connection:
                violations = connection.execute(node["compiled_code"]).fetchall()
            assert set(violations) == {(i, i) for i in ids} | {(999, None), (None, 888), (None, None)}
        assert {manifest["nodes"][r["unique_id"]]["name"]: r["failures"] for r in results} == expected_failures
    finally:
        build_performance(tmp_path, dbt_environment)
    assert_performance_matches_sources(source_schema, output_schema)


@pytest.mark.dbt_models("+mart_genre_performance", "+mart_platform_performance")
@pytest.mark.parametrize("field", ["rating", "rating_count"])
def test_performance_invalid_projected_values_and_recovery(built_staging, dbt_environment, tmp_path, field):
    """Invalid casts fail table replacement; valid source correction restores both marts."""

    source_schema, output_schema = built_staging
    baseline = assert_performance_matches_sources(source_schema, output_schema)
    with create_connection() as connection:
        raw_games.upsert_raw_games(connection, [{"id": 90, field: "invalid", "genres": [999],
                                   "platforms": [999]}], source_schema, FETCHED_AT)
    try:
        process, results, _ = run_dbt(tmp_path, dbt_environment, "run", "--select", *PERFORMANCE_MODELS)
        assert process.returncode == 1, process.stdout + process.stderr
        assert len(results) == 2 and all(r["status"] == "error" for r in results)
        with create_connection() as connection:
            for dimension in ("genre", "platform"):
                assert connection.execute(
                    f"SELECT * FROM {output_schema}.mart_{dimension}_performance ORDER BY {dimension}_id"
                ).fetchall() == baseline[dimension]
    finally:
        with create_connection() as connection:
            raw_games.upsert_raw_games(connection, [{"id": 90, field: 0, "genres": [999],
                                       "platforms": [999]}], source_schema, FETCHED_AT)
        build_performance(tmp_path, dbt_environment)
    assert_performance_matches_sources(source_schema, output_schema)


COMPANY_OUTPUT_COLUMNS = ["company_id", "name", "company_loaded", "relationship_record_count",
                          "null_game_relationship_count", "game_count", "loaded_game_count",
                          "developer_game_count", "publisher_game_count"]


def build_company_output(tmp_path, env):
    """Refresh the snapshot and require all three company-output invariants to pass."""

    process, results, manifest = run_dbt(tmp_path, env, "build", "--select", "mart_company_output")
    assert process.returncode == 0, process.stdout + process.stderr
    assert len(results) == 4 and sum(r["status"] == "pass" for r in results) == 3
    return manifest


def assert_company_output_matches_sources(source_schema, output_schema):
    """Reconcile raw/staged records and independently derive exact metrics with Python sets."""

    with create_connection() as connection:
        records = connection.execute(
            f"SELECT * FROM {output_schema}.int_game_companies ORDER BY involved_company_id"
        ).fetchall()
        assert records == connection.execute(
            f"SELECT involved_company_id, game_id, company_id, developer, publisher "
            f"FROM {output_schema}.stg_involved_companies ORDER BY involved_company_id"
        ).fetchall()
        raw = connection.execute(
            f"SELECT igdb_id, payload FROM {source_schema}.raw_involved_companies ORDER BY igdb_id"
        ).fetchall()
        assert records == [(i, p.get("game"), p.get("company"), p.get("developer"), p.get("publisher"))
                           for i, p in raw]
        names = dict(connection.execute(f"SELECT company_id, name FROM {output_schema}.stg_companies"))
        loaded_games = {r[0] for r in connection.execute(f"SELECT game_id FROM {output_schema}.stg_games")}
        actual = connection.execute(
            f"SELECT * FROM {output_schema}.mart_company_output ORDER BY company_id"
        ).fetchall()
    expected = []
    for company in sorted({r[2] for r in records if r[2] is not None}):
        members = [r for r in records if r[2] == company]
        games = {r[1] for r in members if r[1] is not None}
        developer = {r[1] for r in members if r[1] is not None and r[3] is True}
        publisher = {r[1] for r in members if r[1] is not None and r[4] is True}
        expected.append((company, names.get(company), company in names, len(members),
                         sum(r[1] is None for r in members), len(games),
                         len(games & loaded_games), len(developer), len(publisher)))
    assert actual == expected
    assert sum(r[3] for r in actual) + sum(r[2] is None for r in records) == len(records)
    assert sum(r[5] for r in actual) == len({(r[2], r[1]) for r in records
                                          if r[2] is not None and r[1] is not None})
    return actual


@pytest.mark.dbt_models("+mart_company_output")
def test_company_output_values_roles_grain_and_snapshot(built_staging, dbt_environment, tmp_path):
    """Keep record identity and unknown roles while counting each game once per role scope."""

    source_schema, output_schema = built_staging
    baseline = assert_company_output_matches_sources(source_schema, output_schema)
    roles = [(d, p) for d in (True, False, None) for p in (True, False, None)]
    records = []
    # Distinct games isolate every nullable combination; a repeated pair combines conflicting roles.
    for index, (developer, publisher) in enumerate(roles):
        for company, game, offset in [(1, 100 + index, 0), (2, 4, 20),
                                       (100 + index, 100 + index, 40)]:
            records.append({"id": 100 + index + offset, "game": game, "company": company,
                            "developer": developer, "publisher": publisher})
    records += [
        {"id": 200, "game": 4, "company": 2, "developer": True, "publisher": True},
        {"id": 201, "game": 4, "company": 2, "developer": True, "publisher": True},
        {"id": 202, "game": 4, "company": 1, "developer": True},
        {"id": 203, "game": None, "company": 1, "developer": True, "publisher": True},
        {"id": 204, "company": 1}, {"id": 205, "company": 3},
        {"id": 206, "company": 4, "game": 999},
        {"id": 207, "company": 5, "game": 999},
        {"id": 208, "company": 999, "game": 999, "publisher": True},
        {"id": 209, "company": None, "game": 4, "developer": True}, {"id": 210},
        {"id": 211, "company": 0, "game": 0, "developer": True},
        {"id": 212, "company": -1, "game": -1, "publisher": True},
        {"id": 2**63-1, "company": 2**63-1, "game": 2**63-1, "developer": True},
        {"id": -1, "company": 777, "game": 777, "developer": True},
        {"id": -1, "company": 3, "game": None, "publisher": False},
        {"id": 0, "company": 3, "game": None},
    ]
    with create_connection() as connection:
        connection.execute(f"DELETE FROM {source_schema}.raw_involved_companies")
        raw_involved_companies.upsert_raw_involved_companies(connection, records, source_schema, FETCHED_AT)
        raw_companies.upsert_raw_companies(connection, [
            {"id": 1, "name": "old"}, {"id": 1, "name": "Shared"}, {"id": 2, "name": "Shared"},
            {"id": 3, "name": ""}, {"id": 4}, {"id": 5, "name": None},
            {"id": 88, "name": "No observed relationships"},
        ], source_schema, FETCHED_AT)
        raw_games.upsert_raw_games(connection, [{"id": 0}, {"id": -1}, {"id": 100}], source_schema, FETCHED_AT)
        assert connection.execute(
            f"SELECT * FROM {output_schema}.mart_company_output ORDER BY company_id"
        ).fetchall() == baseline
    manifest = build_company_output(tmp_path, dbt_environment)
    rows = assert_company_output_matches_sources(source_schema, output_schema)
    by_id = {r[0]: r for r in rows}
    assert by_id[1] == (1, "Shared", True, 12, 2, 10, 2, 4, 3)
    assert by_id[2] == (2, "Shared", True, 11, 0, 1, 1, 1, 1)
    assert by_id[3] == (3, "", True, 3, 3, 0, 0, 0, 0)
    assert by_id[4] == (4, None, True, 1, 0, 1, 0, 0, 0)
    assert by_id[5] == (5, None, True, 1, 0, 1, 0, 0, 0)
    assert by_id[999] == (999, None, False, 1, 0, 1, 0, 0, 1)
    assert by_id[0] == (0, None, False, 1, 0, 1, 1, 1, 0)
    assert by_id[-1] == (-1, None, False, 1, 0, 1, 1, 0, 1)
    assert by_id[2**63-1] == (2**63-1, None, False, 1, 0, 1, 0, 1, 0)
    assert 88 not in by_id and 777 not in by_id
    for index, (developer, publisher) in enumerate(roles):
        assert by_id[100 + index] == (100 + index, None, False, 1, 0, 1,
                                     int(index == 0), int(developer is True), int(publisher is True))
    node = manifest["nodes"]["model.data_platform.mart_company_output"]
    assert node["config"]["materialized"] == "table" and node["schema"] == output_schema
    assert set(node["depends_on"]["nodes"]) == {"model.data_platform.int_game_companies",
                                               "model.data_platform.stg_games",
                                               "model.data_platform.stg_companies"}
    with create_connection() as connection:
        assert connection.execute(
            "SELECT table_type FROM information_schema.tables WHERE table_schema=%s AND table_name=%s",
            (output_schema, "mart_company_output"),
        ).fetchone() == ("BASE TABLE",)
        types = connection.execute(
            "SELECT column_name,data_type FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
            (output_schema, "mart_company_output"),
        ).fetchall()
    assert types == [(c, "text" if c == "name" else "boolean" if c == "company_loaded" else "bigint")
                     for c in COMPANY_OUTPUT_COLUMNS]
    assert set(node["columns"]) == set(COMPANY_OUTPUT_COLUMNS)
    assert node["description"].strip() and all(c["description"].strip() for c in node["columns"].values())


@pytest.mark.dbt_models("+mart_company_output")
@pytest.mark.parametrize("population", ["empty", "null_companies"])
def test_company_output_empty_observations(built_staging, dbt_environment, tmp_path, population):
    """No placeholder company row, even with loaded companies and unattributable records."""

    source_schema, output_schema = built_staging
    with create_connection() as connection:
        connection.execute(f"DELETE FROM {source_schema}.raw_involved_companies")
        if population == "null_companies":
            raw_involved_companies.upsert_raw_involved_companies(connection, [
                {"id": 1}, {"id": 2, "company": None, "game": 4, "developer": True},
            ], source_schema, FETCHED_AT)
    build_company_output(tmp_path, dbt_environment)
    assert assert_company_output_matches_sources(source_schema, output_schema) == []


@pytest.mark.dbt_models("+mart_company_output")
def test_company_output_repeated_records_and_lookups(built_staging, dbt_environment, tmp_path):
    """Broken record IDs remain detectable; multiplicity cannot inflate distinct games."""

    source_schema, output_schema = built_staging
    baseline = assert_company_output_matches_sources(source_schema, output_schema)
    originals = {}
    try:
        with create_connection() as connection:
            for model in ("int_game_companies", "stg_games", "stg_companies"):
                relation = f"{output_schema}.{model}"
                original = connection.execute("SELECT pg_get_viewdef(%s::regclass)", (relation,)).fetchone()[0].rstrip(";\n ")
                originals[relation] = original
                connection.execute(f"CREATE OR REPLACE VIEW {relation} AS "
                                   f"SELECT * FROM ({original}) a UNION ALL SELECT * FROM ({original}) b")
        # Run just this mart: upstream duplicates must not be silently legitimized by a full build.
        process, results, _ = run_dbt(tmp_path, dbt_environment, "run", "--select", "mart_company_output")
        assert process.returncode == 0, process.stdout + process.stderr
        with create_connection() as connection:
            rows = connection.execute(f"SELECT * FROM {output_schema}.mart_company_output").fetchall()
        names = {0: False, 4: True, 3000000002: False}
        for original in baseline:
            expected = (*original[:3], original[3] * 2, original[4] * 2, *original[5:])
            assert rows.count(expected) == (2 if names[original[0]] else 1)
        process, results, manifest = run_dbt(
            tmp_path, dbt_environment, "test", "--select", "int_game_companies", "stg_games", "stg_companies",
            "--indirect-selection", "cautious",
        )
        assert process.returncode == 1, process.stdout + process.stderr
        assert {manifest["nodes"][r["unique_id"]]["name"] for r in results if r["status"] == "fail"} == {
            "unique_int_game_companies_involved_company_id", "unique_stg_games_game_id", "unique_stg_companies_company_id",
        }
    finally:
        with create_connection() as connection:
            for relation, original in originals.items():
                connection.execute(f"CREATE OR REPLACE VIEW {relation} AS {original}")
    build_company_output(tmp_path, dbt_environment)
    assert assert_company_output_matches_sources(source_schema, output_schema) == baseline
    process, results, _ = run_dbt(tmp_path, dbt_environment, "test", "--select",
                                 "int_game_companies", "stg_games", "stg_companies",
                                 "--indirect-selection", "cautious")
    assert process.returncode == 0, process.stdout + process.stderr
    assert len(results) == 6 and all(r["status"] == "pass" for r in results)


@pytest.mark.dbt_models("+mart_company_output")
def test_company_output_invariants_fail_and_recover(built_staging, dbt_environment, tmp_path):
    """Independently corrupt every column and population invariant, then rebuild to recover."""

    source_schema, output_schema = built_staging
    defects = [(column, value) for column in COMPANY_OUTPUT_COLUMNS[3:] for value in (None, -1, 0, 999)]
    defects += [("name", "wrong"), ("name", ""), ("company_loaded", None), ("company_loaded", True)]
    ids = list(range(100, 100 + len(defects)))
    with create_connection() as connection:
        # Positive values in every count ensure zero is a defect in every metric.
        records = [{"id": 1000 + i * 2 + j, "company": company, "game": 4 if j == 0 else None,
                    "developer": True, "publisher": True} for i, company in enumerate(ids) for j in (0, 1)]
        raw_involved_companies.upsert_raw_involved_companies(connection, records, source_schema, FETCHED_AT)
    build_company_output(tmp_path, dbt_environment)
    table = f"{output_schema}.mart_company_output"
    with create_connection() as connection:
        for company, (column, value) in zip(ids, defects):
            connection.execute(f"UPDATE {table} SET {column}=%s WHERE company_id=%s", (value, company))
        connection.execute(f"DELETE FROM {table} WHERE company_id=3000000002")
        connection.execute(f"INSERT INTO {table} (company_id) VALUES (888), (NULL)")
        connection.execute(f"INSERT INTO {table} SELECT * FROM {table} WHERE company_id=4")
    try:
        process, results, manifest = run_dbt(tmp_path, dbt_environment, "test", "--select", "mart_company_output")
        assert process.returncode == 1, process.stdout + process.stderr
        assert len(results) == 3 and all(r["status"] == "fail" for r in results)
        assert {manifest["nodes"][r["unique_id"]]["name"]: r["failures"] for r in results} == {
            "unique_mart_company_output_company_id": 1, "not_null_mart_company_output_company_id": 1,
            "mart_company_output_reconciliation": len(defects) + 3,
        }
        node = manifest["nodes"]["test.data_platform.mart_company_output_reconciliation"]
        with create_connection() as connection:
            violations = connection.execute(node["compiled_code"]).fetchall()
        assert set(violations) == {(i, i) for i in ids} | {(3000000002, None), (None, 888), (None, None)}
    finally:
        build_company_output(tmp_path, dbt_environment)
    assert_company_output_matches_sources(source_schema, output_schema)


@pytest.mark.dbt_models("+mart_company_output")
@pytest.mark.parametrize("field", ["game", "company", "developer", "publisher"])
def test_company_output_invalid_casts_and_recovery(built_staging, dbt_environment, tmp_path, field):
    """Existing casts reject malformed references/roles and preserve the prior snapshot."""

    source_schema, output_schema = built_staging
    baseline = assert_company_output_matches_sources(source_schema, output_schema)
    record = {"id": 900, "company": 999, "game": 4, "developer": True, "publisher": True}
    with create_connection() as connection:
        raw_involved_companies.upsert_raw_involved_companies(connection, [dict(record, **{field: "invalid"})],
                                                           source_schema, FETCHED_AT)
    try:
        process, results, _ = run_dbt(tmp_path, dbt_environment, "run", "--select", "mart_company_output")
        assert process.returncode == 1, process.stdout + process.stderr
        assert len(results) == 1 and results[0]["status"] == "error"
        with create_connection() as connection:
            assert connection.execute(
                f"SELECT * FROM {output_schema}.mart_company_output ORDER BY company_id"
            ).fetchall() == baseline
    finally:
        with create_connection() as connection:
            raw_involved_companies.upsert_raw_involved_companies(connection, [record], source_schema, FETCHED_AT)
        build_company_output(tmp_path, dbt_environment)
    assert_company_output_matches_sources(source_schema, output_schema)
