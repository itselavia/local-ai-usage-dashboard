from __future__ import annotations

from pathlib import Path

from .db import connect
from .queries import get_doctor_summary


def run(args) -> int:
    db_path = Path(args.db).expanduser()
    if not db_path.exists():
        print(f"database not found: {db_path}")
        return 2

    with connect(db_path, read_only=True) as db:
        summary = get_doctor_summary(
            db,
            {
                "db": str(db_path),
                "codex_dir": str(Path(args.codex_dir).expanduser()),
                "claude_dir": str(Path(args.claude_dir).expanduser()),
            },
        )

    source_paths = {
        "Codex": Path(args.codex_dir).expanduser(),
        "Claude": Path(args.claude_dir).expanduser(),
        "DuckDB": db_path,
    }

    print("doctor summary")
    print(f"  latest ingest: {summary['latest_ingest_at']}")
    print(f"  sessions: {summary['session_count']}")
    print(f"  partial parses: {summary['partial_parses']}")
    print(f"  excluded sessions: {summary['excluded_sessions']}")
    print(f"  unsupported sessions: {summary['unsupported_sessions']}")
    for row in summary["pricing_freshness"]:
        print(f"  pricing {row['label']}: {row['value']}")
    for label, path in source_paths.items():
        status = "present" if path.exists() else "missing"
        print(f"  {label}: {path} ({status})")

    return 0
