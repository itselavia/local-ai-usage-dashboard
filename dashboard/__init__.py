from __future__ import annotations

from pathlib import Path

APP_NAME = "local-ai-usage-dashboard"
APP_VERSION = "0.1.0"
SCHEMA_VERSION = 1

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
STATE_DIR_NAME = ".dashboard"

DEFAULT_STATE_DIR = PROJECT_ROOT / STATE_DIR_NAME
DEFAULT_DB_PATH = DEFAULT_STATE_DIR / "dashboard.duckdb"
DEFAULT_PRICING_SNAPSHOT_PATH = DEFAULT_STATE_DIR / "pricing_snapshot.json"
DEFAULT_METADATA_PATH = DEFAULT_STATE_DIR / "metadata.json"
DEFAULT_SNAPSHOT_DIR = DEFAULT_STATE_DIR / "snapshots" / "latest"

SQL_DIR = PACKAGE_DIR / "sql"
SCHEMA_SQL_PATH = SQL_DIR / "schema.sql"
VIEWS_SQL_PATH = SQL_DIR / "views.sql"

__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "SCHEMA_VERSION",
    "PACKAGE_DIR",
    "PROJECT_ROOT",
    "STATE_DIR_NAME",
    "DEFAULT_STATE_DIR",
    "DEFAULT_DB_PATH",
    "DEFAULT_PRICING_SNAPSHOT_PATH",
    "DEFAULT_METADATA_PATH",
    "DEFAULT_SNAPSHOT_DIR",
    "SQL_DIR",
    "SCHEMA_SQL_PATH",
    "VIEWS_SQL_PATH",
]
