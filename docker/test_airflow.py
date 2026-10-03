"""Offline checks for local Airflow initialization; no Airflow host dependency."""

import base64
import importlib.util
import json
from pathlib import Path
import subprocess
from urllib.parse import unquote, urlsplit

import pytest


SPEC = importlib.util.spec_from_file_location("bootstrap", Path(__file__).parent / "airflow/bootstrap.py")
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


@pytest.fixture
def configured(monkeypatch):
    """Use synthetic credentials and capture migration calls without execution."""
    monkeypatch.setenv("AIRFLOW_DB_PASSWORD", "synthetic:@/% password")
    monkeypatch.setenv("AIRFLOW_ADMIN_PASSWORD", "synthetic-admin")
    calls = []
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *a, **kw: calls.append((a, kw)))
    return calls


def test_database_uri_encodes_password_and_fixes_target(configured):
    uri = urlsplit(bootstrap.database_uri())
    assert unquote(uri.password) == "synthetic:@/% password"
    assert (uri.hostname, uri.port, uri.path, uri.username) == ("airflow-postgres", 5432, "/airflow", "airflow")


def test_init_is_private_repeatable_and_preserves_credentials(tmp_path, configured, monkeypatch):
    bootstrap.initialize(tmp_path)
    original = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert json.loads(original["passwords.json"]) == {"admin": "synthetic-admin"}
    assert len(base64.urlsafe_b64decode(original["fernet-key"])) == 32
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in tmp_path.iterdir())
    monkeypatch.delenv("AIRFLOW_ADMIN_PASSWORD")
    bootstrap.initialize(tmp_path)
    assert original == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert configured == [((["airflow", "db", "migrate"],), {"check": True})] * 2


@pytest.mark.parametrize("key", ["AIRFLOW_DB_PASSWORD", "AIRFLOW_ADMIN_PASSWORD"])
def test_missing_credentials_fail_before_writes(tmp_path, configured, monkeypatch, key):
    monkeypatch.setenv(key, "")
    with pytest.raises(ValueError):
        bootstrap.initialize(tmp_path)
    assert not list(tmp_path.iterdir())
    assert not configured


def test_repeat_refuses_password_rotation(tmp_path, configured, monkeypatch):
    bootstrap.initialize(tmp_path)
    original = (tmp_path / "passwords.json").read_bytes()
    monkeypatch.setenv("AIRFLOW_ADMIN_PASSWORD", "different")
    with pytest.raises(ValueError, match="differs"):
        bootstrap.initialize(tmp_path)
    assert (tmp_path / "passwords.json").read_bytes() == original
    assert len(configured) == 1


@pytest.mark.parametrize("name,content", [("fernet-key", ""), ("jwt-secret", None), ("passwords.json", "{}")])
def test_damaged_state_is_not_silently_replaced(tmp_path, configured, name, content):
    bootstrap.initialize(tmp_path)
    path = tmp_path / name
    if content is None:
        path.unlink()
    else:
        path.write_text(content)
    with pytest.raises(ValueError):
        bootstrap.initialize(tmp_path)
    assert len(configured) == 1


def test_migration_failure_propagates(tmp_path, configured, monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["airflow", "db", "migrate"])
    monkeypatch.setattr(bootstrap.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        bootstrap.initialize(tmp_path)
