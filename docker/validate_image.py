"""Check Docker's actual context filtering and a built image, without network access.

Run from the repository root with a Docker engine available:
    python docker/validate_image.py data-platform-runtime:local
Only uniquely named probe images/containers created here are removed.
"""

from pathlib import Path
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
IMAGE = sys.argv.pop(1) if len(sys.argv) > 1 else "data-platform-runtime:local"


def docker(*args: str, input: bytes | None = None) -> bytes:
    """Run Docker without echoing environment values or full image configuration."""
    result = subprocess.run(["docker", *args], input=input, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr.decode() + result.stdout.decode())
    return result.stdout


def context_files(context: Path) -> set[str]:
    """Export COPY's view of the context using Docker's own ignore implementation."""
    probe = "data-platform-context-" + uuid4().hex
    container = None
    built = False
    try:
        docker("build", "-t", probe, "-f", "-", str(context),
               input=b"FROM scratch\nCOPY . /context/\nCMD [\"probe\"]\n")
        built = True
        container = docker("create", "--network", "none", probe).decode().strip()
        archive = docker("export", container)
        with tarfile.open(fileobj=io.BytesIO(archive)) as contents:
            return {m.name.removeprefix("context/") for m in contents
                    if m.isfile() and m.name.startswith("context/")}
    finally:
        if container:
            docker("rm", container)
        if built:
            docker("image", "rm", probe)


class ImageChecks(unittest.TestCase):
    """Exercise exclusions, packaged source parity, and safe command defaults."""

    def test_exclusions_with_nested_sentinels(self):
        """Local/private files must be absent even beneath allowed directories."""
        allowed = {"requirements.txt", "src/__init__.py", "src/utils/config.py",
                   "tests/integration/conftest.py", "dbt/profiles.yml",
                   "dbt/dbt_project.yml", "dbt/models/staging/model.sql",
                   "dbt/models/staging/schema.yml", "dbt/tests/check.sql",
                   "dbt/macros/example.sql"}
        denied = {".env", ".env.example", ".env.production", ".git/config",
                  "docs/portfolio/private.md", "data/raw/archive.jsonl",
                  ".venv/lib/example.py", "venv/lib/example.py",
                  "src/.env", "src/credentials.py", "src/secrets.py",
                  "src/.venv/nested.py", "src/venv/nested.py",
                  "src/data/raw/archive.py", "src/__pycache__/module.pyc",
                  "tests/.pytest_cache/cache.py", "tests/.cache/cached.py",
                  "dbt/target/manifest.json", "dbt/logs/dbt.log",
                  "dbt/.user.yml", "dbt/dbt_packages/pkg/model.sql",
                  "dbt/models/target/leak.sql", "dbt/models/.env.local",
                  "dbt/models/credentials.yml", "dbt/models/secrets.yml",
                  "dbt/models/private.key", "dbt/models/private.pem",
                  "src/local.json", "dbt/local.yml",
                  "dbt/analyses/.gitkeep", "dbt/models/.gitkeep",
                  "tests/local.json", "dbt/credentials.json"}
        with tempfile.TemporaryDirectory(prefix="data-platform-context-") as folder:
            context = Path(folder)
            shutil.copyfile(ROOT / ".dockerignore", context / ".dockerignore")
            for name in allowed | denied:
                path = context / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("synthetic context sentinel\n")
            self.assertEqual(context_files(context), allowed)

    def test_real_context_and_image_source_parity(self):
        """Only intended definitions reach Docker; the image contains those bytes."""
        expected = {"requirements.txt", "dbt/dbt_project.yml", "dbt/profiles.yml"}
        for tree in ("src", "tests"):
            expected.update(str(p.relative_to(ROOT)) for p in (ROOT / tree).rglob("*.py"))
        for tree in ("models", "tests", "macros"):
            for suffix in (("*.sql", "*.yml") if tree == "models" else ("*.sql",)):
                expected.update(str(p.relative_to(ROOT)) for p in (ROOT / "dbt" / tree).rglob(suffix))
        self.assertEqual(context_files(ROOT), expected)
        hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                  for name in expected}
        check = """
import hashlib, json, os
from pathlib import Path
assert os.getuid() != 0
expected = json.loads(EXPECTED)
actual = {str(p.relative_to('/app')): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in Path('/app').rglob('*') if p.is_file()}
assert actual == expected, 'Image source differs from allowed build context'
assert not list(Path('/home/app').glob('.env*'))
assert os.environ['DBT_TARGET_PATH'].startswith('/tmp/')
assert os.environ['DBT_LOG_PATH'].startswith('/tmp/')
"""
        docker("run", "--rm", "--network", "none", "-i", IMAGE, "python", "-",
               input=("EXPECTED = " + repr(json.dumps(hashes)) + "\n" + check).encode())

    def test_default_command_is_offline_help(self):
        """An unconfigured invocation must exit successfully without source access."""
        output = docker("run", "--rm", "--network", "none", IMAGE).decode()
        self.assertIn("--entity", output)
        self.assertIn("--backfill-start", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
