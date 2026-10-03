"""Check a built Airflow image offline; invoke with host Python and its image tag."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
IMAGE = sys.argv.pop(1)


def check(python: str, code: str, *, cwd: str = "/opt/airflow/app") -> None:
    """Execute assertions with no network, credentials, volumes or host mounts."""
    subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "-i", "--workdir", cwd,
         "--entrypoint", python, IMAGE, "-"], input=code, text=True, check=True,
    )


class AirflowImageChecks(unittest.TestCase):
    """Verify the actual SDK/operator, packaged bytes and isolated dependencies."""

    def test_application_environment_and_packaged_source(self):
        expected = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (ROOT / "src").rglob("*.py") if "ai" not in p.relative_to(ROOT).parts}
        check("/opt/airflow/app-venv/bin/python", f"EXPECTED = {expected!r}\n" + """
import hashlib, importlib.util, os, sys
from pathlib import Path
import dotenv, psycopg, requests, dbt.cli.main
import importlib.metadata
from src.ingestion import run_ingestion
assert os.getuid() == 50000
assert sys.prefix == '/opt/airflow/app-venv' and sys.prefix != sys.base_prefix
assert importlib.util.find_spec('airflow') is None
assert Path(dbt.cli.main.__file__).is_relative_to(sys.prefix)
assert Path('/opt/airflow/app-venv/bin/dbt').read_text().splitlines()[0] == '#!/opt/airflow/app-venv/bin/python'
print('dbt-core', importlib.metadata.version('dbt-core'), 'dbt-postgres', importlib.metadata.version('dbt-postgres'))
assert importlib.util.find_spec('pytest') is None
assert all(str(Path(m.__file__)).startswith(sys.prefix) for m in (dotenv, psycopg, requests))
assert {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in Path('src').rglob('*.py')} == EXPECTED
assert not list(Path('.').rglob('.env*'))
assert not list(Path('src').rglob('*.pyc'))
archive = Path('data/raw/permission-probe')
archive.write_text('synthetic')
archive.unlink()
artifact = Path('/opt/airflow/dbt-artifacts/permission-probe')
artifact.write_text('synthetic')
artifact.unlink()
""")

    def test_packaged_dbt_project_matches_existing_definitions(self):
        expected = {str(p.relative_to(ROOT / "dbt")): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (ROOT / "dbt").rglob("*")
                    if p.is_file() and p.suffix in {".yml", ".sql"}
                    and (p.parent == ROOT / "dbt" and p.name in {"dbt_project.yml", "profiles.yml"}
                         or p.relative_to(ROOT / "dbt").parts[0] in {"models", "tests", "macros"})}
        check("/opt/airflow/app-venv/bin/python", f"EXPECTED = {expected!r}\n" + """
import hashlib
from pathlib import Path
root = Path('/opt/airflow/app/dbt')
assert {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob('*') if p.is_file()} == EXPECTED
""")

    def test_real_dag_and_operator_exit_handling(self):
        digest = hashlib.sha256((ROOT / "dags/igdb_ingestion.py").read_bytes()).hexdigest()
        check("python", f"EXPECTED = {json.dumps(digest)}\n" + """
import hashlib, runpy
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from airflow.exceptions import AirflowException
path = Path('/opt/airflow/dags/igdb_ingestion.py')
assert hashlib.sha256(path.read_bytes()).hexdigest() == EXPECTED
assert {p.name for p in path.parent.glob('*.py')} == {'igdb_ingestion.py'}
dag = runpy.run_path(str(path))['dag']
assert dag.schedule is None and dag.is_paused_upon_creation
assert dag.task_ids == ['ingest_all', 'dbt_build']
ingest = dag.get_task('ingest_all')
build = dag.get_task('dbt_build')
assert ingest.bash_command == 'exec /opt/airflow/app-venv/bin/python -m src.ingestion.run_ingestion --entity all'
assert build.bash_command == 'exec /opt/airflow/app-venv/bin/dbt build --project-dir /opt/airflow/app/dbt --profiles-dir /opt/airflow/app/dbt'
assert not ingest.upstream_task_ids and ingest.downstream_task_ids == {'dbt_build'}
assert build.upstream_task_ids == {'ingest_all'} and not build.downstream_task_ids
assert build.trigger_rule == 'all_success'
for task in (ingest, build):
    assert task.cwd == '/opt/airflow/app' and not task.do_xcom_push
    assert task.retries == 1
    assert task.retry_delay == timedelta(minutes=1)
    assert task.retry_exponential_backoff is False
    assert task.trigger_rule == 'all_success'
    assert task.skip_on_exit_code == []
    for code in (0, 1, 2, 99):
        task.subprocess_hook = Mock()
        task.subprocess_hook.run_command.return_value = SimpleNamespace(exit_code=code, output='synthetic')
        try:
            task.execute(context={})
        except AirflowException:
            assert code != 0
        else:
            assert code == 0
""")


if __name__ == "__main__":
    unittest.main(verbosity=2)
