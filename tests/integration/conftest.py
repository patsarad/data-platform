"""Opt-in PostgreSQL fixtures; never reuse or remove a configured project schema."""

import os
from uuid import uuid4

import pytest
from psycopg import sql
import requests

from src.storage.raw_games import create_connection


@pytest.fixture(autouse=True)
def require_postgres_opt_in(monkeypatch):
    """Keep default tests offline and prohibit accidental live source requests."""

    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("Set RUN_POSTGRES_INTEGRATION=1 to run PostgreSQL/dbt checks.")

    def reject_http(*args, **kwargs):
        raise AssertionError("PostgreSQL integration tests must not call live HTTP services.")

    monkeypatch.setattr(requests.Session, "request", reject_http)


@pytest.fixture
def postgres_schemas(require_postgres_opt_in):
    """Create unique raw/output schemas and clean up even when an assertion fails.

    Connection errors intentionally fail an opted-in run, rather than silently
    skipping it. Separate committed connections expose actual durability.
    """

    prefix = "test_dp_" + uuid4().hex
    names = (prefix + "_raw", prefix + "_dbt")
    with create_connection() as connection:
        for name in names:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
    try:
        yield names
    finally:
        with create_connection() as connection:
            for name in reversed(names):
                connection.execute(
                    sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name))
                )
        with create_connection() as connection:
            assert not connection.execute(
                "SELECT nspname FROM pg_namespace WHERE nspname = ANY(%s)",
                (list(names),),
            ).fetchall()
