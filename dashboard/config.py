from __future__ import annotations

from pathlib import Path

from . import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_DB_PATH,
    DEFAULT_METADATA_PATH,
    DEFAULT_PRICING_SNAPSHOT_PATH,
    DEFAULT_SNAPSHOT_DIR,
    DEFAULT_STATE_DIR,
    PROJECT_ROOT,
    SCHEMA_VERSION,
    STATE_DIR_NAME,
)

DEFAULT_TIMEZONE = "local"
DEFAULT_INCLUDE_TEMP = False
DEFAULT_PROVIDER = "all"
DEFAULT_METRIC = "cost"
DEFAULT_SORT = "cost"
DEFAULT_SORT_DIRECTION = "desc"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def repo_root() -> Path:
    return PROJECT_ROOT


def state_dir() -> Path:
    return DEFAULT_STATE_DIR


def default_db_path() -> Path:
    return DEFAULT_DB_PATH


def default_pricing_snapshot_path() -> Path:
    return DEFAULT_PRICING_SNAPSHOT_PATH


def default_metadata_path() -> Path:
    return DEFAULT_METADATA_PATH


def default_snapshot_dir() -> Path:
    return DEFAULT_SNAPSHOT_DIR


def default_codex_dir() -> Path:
    return Path.home() / ".codex"


def default_claude_dir() -> Path:
    return Path.home() / ".claude"
