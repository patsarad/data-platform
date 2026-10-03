"""Check Compose interpolation offline without loading repository credentials.

Run with host Python: python docker/validate_compose.py
Requires Docker Compose, but no running engine. Resolved environments stay private.
"""

import json
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")


def config(values: dict[str, str], *, profiles: bool = True,
           airflow: bool = False, init: bool = False) -> subprocess.CompletedProcess:
    """Resolve only explicit synthetic settings, never the caller's project env."""
    environment = {key: os.environ[key] for key in
                   ("PATH", "HOME", "DOCKER_CONFIG", "DOCKER_HOST") if key in os.environ}
    environment.update(values)
    args = ["docker", "compose", "--env-file", os.devnull,
            "-p", "data-platform-config-check", "-f", str(ROOT / "compose.yaml")]
    if profiles:
        args.extend(["--profile", "tools"])
    if airflow:
        args.extend(["--profile", "airflow"])
    if init:
        args.extend(["--profile", "airflow-init"])
    return subprocess.run(args + ["config", "--format", "json"],
                          env=environment, capture_output=True, text=True)


class ComposeChecks(unittest.TestCase):
    """Protect selection, internal addressing, environment scope and persistence."""

    def setUp(self):
        self.values = {key: "synthetic_validation" for key in REQUIRED}

    def resolved(self, **kwargs) -> dict:
        result = config(self.values, **kwargs)
        self.assertEqual(result.returncode, 0, "Compose resolution failed")
        return json.loads(result.stdout)

    def test_default_services_and_runtime_contract(self):
        self.assertEqual(set(self.resolved(profiles=False)["services"]), {"postgres"})
        services = self.resolved()["services"]
        self.assertEqual(set(services), {"postgres", "runtime"})
        runtime = services["runtime"]
        self.assertEqual(runtime["profiles"], ["tools"])
        self.assertEqual(runtime["depends_on"]["postgres"]["condition"], "service_healthy")
        self.assertEqual(runtime["build"]["dockerfile"], "docker/Dockerfile")
        self.assertNotIn("args", runtime["build"])
        self.assertIsNone(runtime.get("command"))  # Inherit offline help; run can override it.
        self.assertIsNone(runtime.get("entrypoint"))
        self.assertNotIn("restart", runtime)

    def test_required_database_settings(self):
        for key in REQUIRED:
            for value in (None, ""):
                with self.subTest(key=key, empty=value == ""):
                    values = self.values.copy()
                    if value is None:
                        del values[key]
                    else:
                        values[key] = value
                    result = config(values)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(key, result.stderr)

    def test_host_port_does_not_change_internal_address(self):
        for port in (None, "55473"):
            with self.subTest(port=port):
                if port:
                    self.values["POSTGRES_PORT"] = port
                self.values["POSTGRES_HOST"] = "host-must-not-reach-container"
                services = self.resolved()["services"]
                published = services["postgres"]["ports"][0]
                self.assertEqual(published["host_ip"], "127.0.0.1")
                self.assertEqual(str(published["published"]), port or "5433")
                self.assertEqual(published["target"], 5432)
                runtime = services["runtime"]["environment"]
                self.assertEqual(runtime["POSTGRES_HOST"], "postgres")
                self.assertEqual(runtime["POSTGRES_PORT"], "5432")

    def test_allowlist_and_unset_schema_variables(self):
        self.values["UNRELATED_SECRET"] = "must_not_pass"
        services = self.resolved()["services"]
        self.assertEqual(set(services["postgres"]["environment"]), set(REQUIRED))
        runtime = services["runtime"]["environment"]
        self.assertEqual(set(runtime), set(REQUIRED) | {
            "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_RAW_SCHEMA", "POSTGRES_SCHEMA",
            "DBT_SCHEMA", "LOG_LEVEL", "igdb_client_id", "igdb_client_secret"})
        for key in ("POSTGRES_RAW_SCHEMA", "POSTGRES_SCHEMA", "DBT_SCHEMA",
                    "igdb_client_id", "igdb_client_secret"):
            self.assertIsNone(runtime[key])  # Omitted from the container when unset.

    def test_shell_schema_precedence(self):
        self.values.update(POSTGRES_SCHEMA="legacy", DBT_SCHEMA="outputs")
        runtime = self.resolved()["services"]["runtime"]["environment"]
        self.assertIsNone(runtime["POSTGRES_RAW_SCHEMA"])
        self.assertEqual(runtime["POSTGRES_SCHEMA"], "legacy")
        self.assertEqual(runtime["DBT_SCHEMA"], "outputs")
        for explicit in ("shell_raw", ""):
            self.values["POSTGRES_RAW_SCHEMA"] = explicit
            runtime = self.resolved()["services"]["runtime"]["environment"]
            self.assertEqual(runtime["POSTGRES_RAW_SCHEMA"], explicit)
            self.assertEqual(runtime["POSTGRES_SCHEMA"], "legacy")
            self.assertEqual(runtime["DBT_SCHEMA"], "outputs")

    def test_postgres_and_named_storage_contract(self):
        resolved = self.resolved()
        postgres = resolved["services"]["postgres"]
        self.assertEqual(postgres["image"], "postgres:17.11-bookworm")
        self.assertIn("pg_isready -h 127.0.0.1", postgres["healthcheck"]["test"][1])
        self.assertEqual(postgres["volumes"][0]["target"], "/var/lib/postgresql/data")
        mounts = resolved["services"]["runtime"]["volumes"]
        self.assertEqual({m["source"]: m["target"] for m in mounts}, {
            "raw_archives": "/app/data/raw", "dbt_artifacts": "/tmp/dbt"})
        self.assertTrue(all(m["type"] == "volume" for m in mounts))
        self.assertEqual(set(resolved["volumes"]), {
            "postgres_data", "raw_archives", "dbt_artifacts"})

    def test_airflow_profiles_are_separate_from_tools_and_initialization(self):
        selected = set(self.resolved(profiles=False, airflow=True)["services"])
        self.assertEqual(selected, {"postgres", "airflow-postgres", "airflow-api-server",
                                    "airflow-scheduler", "airflow-dag-processor"})
        self.assertEqual(set(self.resolved(profiles=False, init=True)["services"]),
                         {"postgres", "airflow-postgres", "airflow-init"})

    def test_airflow_environment_and_storage_are_isolated(self):
        self.values.update(AIRFLOW_DB_PASSWORD="metadata-only", AIRFLOW_ADMIN_PASSWORD="init-only",
                           igdb_client_id="source-only", igdb_client_secret="source-secret",
                           UNRELATED_SECRET="excluded", AIRFLOW_PORT="58081")
        config = self.resolved(airflow=True, init=True)
        services = config["services"]
        for name in ("airflow-init", "airflow-api-server", "airflow-scheduler", "airflow-dag-processor"):
            service = services[name]
            env = service["environment"]
            self.assertEqual(service["user"], "50000:0")
            self.assertEqual(env["AIRFLOW__CORE__EXECUTOR"], "LocalExecutor")
            self.assertEqual(env["AIRFLOW__CORE__PARALLELISM"], "1")
            self.assertEqual(env["AIRFLOW__CORE__LOAD_EXAMPLES"], "false")
            self.assertEqual(env["AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS"], "false")
            self.assertEqual(env["AIRFLOW_DB_PASSWORD"], "metadata-only")
            self.assertEqual("AIRFLOW_ADMIN_PASSWORD" in env, name == "airflow-init")
            scheduler = name == "airflow-scheduler"
            self.assertEqual(set(REQUIRED) & set(env), set(REQUIRED) if scheduler else set())
            self.assertEqual({"igdb_client_id", "igdb_client_secret"} & set(env),
                             {"igdb_client_id", "igdb_client_secret"} if scheduler else set())
            self.assertNotIn("UNRELATED_SECRET", env)
            self.assertEqual("DBT_SCHEMA" in env, scheduler)
            if not scheduler:
                self.assertFalse(any(key.startswith("DBT_") for key in env))
            volumes = {"airflow_config", "airflow_logs"}
            if scheduler:
                volumes.update({"airflow_raw_archives", "airflow_dbt_artifacts"})
                self.assertIsNone(env["DBT_SCHEMA"])
                self.assertEqual(env["DBT_SEND_ANONYMOUS_USAGE_STATS"], "false")
                self.assertEqual(env["DBT_TARGET_PATH"], "/opt/airflow/dbt-artifacts/target")
                self.assertEqual(env["DBT_LOG_PATH"], "/opt/airflow/dbt-artifacts/logs")
                self.assertEqual(env["POSTGRES_HOST"], "postgres")
                self.assertEqual(env["POSTGRES_PORT"], "5432")
                self.assertIsNone(env["POSTGRES_RAW_SCHEMA"])
                self.assertIsNone(env["POSTGRES_SCHEMA"])
            self.assertEqual({m["source"] for m in service["volumes"]}, volumes)
            self.assertEqual(service["build"]["context"], str(ROOT))
            self.assertEqual(service["build"]["dockerfile"], "docker/airflow/Dockerfile")
            self.assertTrue(all(m["type"] == "volume" for m in service["volumes"]))
            self.assertNotIn("privileged", service)
            self.assertNotIn("restart", service)
            self.assertEqual(set(service["depends_on"]),
                             {"airflow-postgres", "postgres"} if scheduler else {"airflow-postgres"})
        self.assertNotIn("ports", services["airflow-postgres"])
        self.assertEqual(services["airflow-postgres"]["environment"]["POSTGRES_PASSWORD"], "metadata-only")
        self.assertNotIn("AIRFLOW_DB_PASSWORD", services["runtime"]["environment"])
        port = services["airflow-api-server"]["ports"][0]
        self.assertEqual((port["host_ip"], str(port["published"]), port["target"]), ("127.0.0.1", "58081", 8080))
        self.assertEqual(set(config["volumes"]), {"postgres_data", "raw_archives", "dbt_artifacts",
                                                "airflow_postgres_data", "airflow_config", "airflow_logs",
                                                "airflow_raw_archives", "airflow_dbt_artifacts"})

    def test_scheduler_preserves_source_schema_selection(self):
        for explicit in (None, "selected", ""):
            self.values.update(POSTGRES_SCHEMA="legacy", DBT_SCHEMA="outputs", POSTGRES_PORT="55482")
            if explicit is not None:
                self.values["POSTGRES_RAW_SCHEMA"] = explicit
            env = self.resolved(airflow=True)["services"]["airflow-scheduler"]["environment"]
            self.assertEqual(env["POSTGRES_RAW_SCHEMA"], explicit)
            self.assertEqual(env["POSTGRES_SCHEMA"], "legacy")
            self.assertEqual(env["POSTGRES_PORT"], "5432")
            self.assertEqual(env["DBT_SCHEMA"], "outputs")


if __name__ == "__main__":
    unittest.main(verbosity=2)
