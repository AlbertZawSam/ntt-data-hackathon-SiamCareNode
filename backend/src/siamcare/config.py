"""Database configuration shared by application entry points."""

import os
from pathlib import Path

from dotenv import dotenv_values


def configuration_directory() -> Path:
    source_root = Path(__file__).resolve().parents[2]
    if (source_root / "pyproject.toml").is_file():
        return source_root
    return Path.cwd()


def database_path() -> Path:
    directory = configuration_directory()
    values = dotenv_values(directory / ".env")
    configured = os.environ.get(
        "SIAMCARE_DATABASE_PATH", values.get("SIAMCARE_DATABASE_PATH")
    )
    if not configured or not configured.strip():
        return Path.home() / ".siamcare" / "referrals.sqlite3"
    path = Path(configured).expanduser()
    return (directory / path).resolve()
