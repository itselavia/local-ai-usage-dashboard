from __future__ import annotations

from pathlib import Path
from typing import Any

from . import DEFAULT_DB_PATH, SCHEMA_SQL_PATH, VIEWS_SQL_PATH


def _load_duckdb() -> Any:
    try:
        import duckdb
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised in runtime environments
        raise RuntimeError(
            "duckdb is required for dashboard storage. Install duckdb before using the dashboard database layer."
        ) from exc

    return duckdb


def resolve_db_path(db_path: str | Path | None = None) -> Path:
    if db_path is None:
        return DEFAULT_DB_PATH

    return Path(db_path).expanduser()


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def connect(db_path: str | Path | None = None, read_only: bool = False):
    duckdb = _load_duckdb()

    if db_path is None:
        path = resolve_db_path()
        ensure_parent_dir(path)
        return duckdb.connect(str(path), read_only=read_only)

    path_str = str(db_path)
    if path_str == ":memory:":
        return duckdb.connect(":memory:")

    path = resolve_db_path(path_str)
    if not read_only:
        ensure_parent_dir(path)
    return duckdb.connect(str(path), read_only=read_only)


def apply_schema(connection) -> None:
    connection.execute(read_sql(SCHEMA_SQL_PATH))


def apply_views(connection) -> None:
    connection.execute(read_sql(VIEWS_SQL_PATH))


def initialize_database(db_path: str | Path | None = None):
    connection = connect(db_path)
    apply_schema(connection)
    apply_views(connection)
    return connection


def open_database(db_path: str | Path | None = None):
    return initialize_database(db_path)
