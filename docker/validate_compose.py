"""Check Compose interpolation offline without loading repository credentials.

Run with host Python: python docker/validate_compose.py
Requires Docker Compose, but no running engine. Resolved environments stay private.
"""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")


def config(values: dict[str, str], *, profiles: bool = True,
           env_file: str = os.devnull) -> subprocess.CompletedProcess:
    """Resolve only explicit synthetic settings, never the caller's project env."""
    environment = {key: os.environ[key] for key in
                   ("PATH", "HOME", "DOCKER_CONFIG", "DOCKER_HOST") if key in os.environ}
    environment.update(values)
    args = ["docker", "compose", "--env-file", env_file,
            "-p", "data-platform-config-check", "-f", str(ROOT / "compose.yaml")]
    if profiles:
        args.extend(["--profile", "tools"])
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

    def test_env_file_and_shell_schema_precedence(self):
        with tempfile.TemporaryDirectory(prefix="data-platform-compose-config-") as folder:
            path = Path(folder) / "synthetic.env"
            path.write_text("POSTGRES_SCHEMA=legacy\nDBT_SCHEMA=outputs\nUNRELATED_SECRET=excluded\n")
            runtime = self.resolved(env_file=str(path))["services"]["runtime"]["environment"]
            self.assertIsNone(runtime["POSTGRES_RAW_SCHEMA"])
            self.assertEqual(runtime["POSTGRES_SCHEMA"], "legacy")
            self.assertEqual(runtime["DBT_SCHEMA"], "outputs")
            path.write_text(path.read_text() + "POSTGRES_RAW_SCHEMA=file_raw\n")
            self.values["POSTGRES_RAW_SCHEMA"] = "shell_raw"
            runtime = self.resolved(env_file=str(path))["services"]["runtime"]["environment"]
            self.assertEqual(runtime["POSTGRES_RAW_SCHEMA"], "shell_raw")
            self.assertEqual(runtime["POSTGRES_SCHEMA"], "legacy")
            self.assertEqual(runtime["DBT_SCHEMA"], "outputs")
            # Empty is set, not absent: preserve existing Settings/env_var semantics.
            self.values["POSTGRES_RAW_SCHEMA"] = ""
            runtime = self.resolved(env_file=str(path))["services"]["runtime"]["environment"]
            self.assertEqual(runtime["POSTGRES_RAW_SCHEMA"], "")

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
