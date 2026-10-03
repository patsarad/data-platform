"""Initialize local Airflow secrets explicitly; never overwrite existing state."""

import base64
import json
import logging
import os
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.parse import quote


CONFIG = Path("/opt/airflow/config")


def database_uri() -> str:
    """Encode the metadata password without allowing a different database target."""
    password = os.environ.get("AIRFLOW_DB_PASSWORD", "")
    if not password:
        raise ValueError("Set AIRFLOW_DB_PASSWORD before starting Airflow")
    return "postgresql+psycopg2://airflow:" + quote(password, safe="") + "@airflow-postgres:5432/airflow"


def initialize(config: Path = CONFIG) -> None:
    """Seed private files once, then migrate only the configured metadata database.

    Run serially with services stopped. Repetition preserves keys and passwords;
    a conflicting password fails rather than silently rotating an account.
    """
    database_uri()  # Fail before writing files when metadata credentials are absent.
    password_path = config / "passwords.json"
    supplied = os.environ.get("AIRFLOW_ADMIN_PASSWORD", "")
    if password_path.exists():
        passwords = json.loads(password_path.read_text())
        if not isinstance(passwords.get("admin"), str) or not passwords["admin"]:
            raise ValueError("Existing Airflow password file is invalid; restore it")
        if supplied and supplied != passwords["admin"]:
            raise ValueError("AIRFLOW_ADMIN_PASSWORD differs from the retained account")
        if any(not (config / name).is_file() for name in ("fernet-key", "jwt-secret")):
            raise ValueError("Retained Airflow keys are missing; restore them")
    elif not supplied:
        raise ValueError("Set AIRFLOW_ADMIN_PASSWORD for first initialization")

    config.mkdir(parents=True, exist_ok=True)
    values = {
        "fernet-key": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "jwt-secret": secrets.token_urlsafe(48),
        "passwords.json": json.dumps({"admin": supplied}),
    }
    for name, value in values.items():
        path = config / name
        if path.exists():
            if not path.read_text().strip():
                raise ValueError("Existing Airflow configuration file is empty; restore it")
            continue
        # O_EXCL refuses concurrent replacement; mode is private from creation.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write(value + "\n")
    subprocess.run(["airflow", "db", "migrate"], check=True)
    logging.info("Airflow metadata migration completed; retained local authentication")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        if sys.argv[1:] == ["database-uri"]:
            # Machine-only output consumed by Airflow's supported _CMD setting.
            sys.stdout.write(database_uri())
        elif sys.argv[1:] == ["init"]:
            initialize()
        else:
            raise ValueError("Expected init or database-uri")
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        # Do not echo data, credentials, database URLs or subprocess output.
        logging.error("Airflow setup failed (%s); check required settings and retained files", type(error).__name__)
        sys.exit(1)
