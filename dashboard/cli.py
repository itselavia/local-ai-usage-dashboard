from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from . import config

INGEST_PRICING_MODES = ("fresh", "snapshot", "auto")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=config.APP_NAME,
        description="Local AI usage dashboard CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="Normalize local logs into DuckDB.")
    ingest.add_argument("--codex-dir", type=Path, default=config.default_codex_dir())
    ingest.add_argument("--claude-dir", type=Path, default=config.default_claude_dir())
    ingest.add_argument("--timezone", default=config.DEFAULT_TIMEZONE)
    ingest.add_argument("--db", type=Path, default=config.default_db_path())
    ingest.add_argument("--include-temp", action="store_true", default=config.DEFAULT_INCLUDE_TEMP)
    ingest.add_argument("--anonymize-workspaces", action="store_true")
    ingest.add_argument("--pricing-mode", choices=INGEST_PRICING_MODES, default="auto")

    serve = subparsers.add_parser("serve", help="Run the local dashboard.")
    serve.add_argument("--db", type=Path, default=config.default_db_path())
    serve.add_argument("--host", default=config.DEFAULT_HOST)
    serve.add_argument("--port", type=int, default=config.DEFAULT_PORT)
    serve.add_argument("--reload", action="store_true")

    generate = subparsers.add_parser("generate", help="Render a static snapshot.")
    generate.add_argument("--db", type=Path, default=config.default_db_path())
    generate.add_argument("--output-dir", type=Path, default=config.default_snapshot_dir())
    generate.add_argument("--anonymize-workspaces", action="store_true")
    generate.add_argument("--latest", action="store_true")

    doctor = subparsers.add_parser("doctor", help="Check source paths and ingest health.")
    doctor.add_argument("--codex-dir", type=Path, default=config.default_codex_dir())
    doctor.add_argument("--claude-dir", type=Path, default=config.default_claude_dir())
    doctor.add_argument("--db", type=Path, default=config.default_db_path())

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args = _normalize_paths(args)

    if args.command == "ingest":
        return _run_ingest(args)
    if args.command == "serve":
        return _run_serve(args)
    if args.command == "generate":
        return _run_generate(args)
    if args.command == "doctor":
        return _run_doctor(args)

    raise SystemExit(f"unknown command: {args.command}")


def _normalize_paths(args: argparse.Namespace) -> argparse.Namespace:
    for name in ("codex_dir", "claude_dir", "db", "output_dir"):
        value = getattr(args, name, None)
        if isinstance(value, Path):
            setattr(args, name, value.expanduser())

    return args


def _run_ingest(args: argparse.Namespace) -> int:
    try:
        from . import ingest as ingest_module
    except ModuleNotFoundError as exc:
        expected = f"{__package__}.ingest"
        if exc.name == expected:
            print(
                "dashboard ingest is not wired yet. Implement dashboard/ingest.py with run(args).",
                file=sys.stderr,
            )
            return 2
        raise

    run = getattr(ingest_module, "run", None)
    if run is None:
        print("dashboard ingest is not wired yet. dashboard.ingest.run is missing.", file=sys.stderr)
        return 2

    result = run(args)
    return 0 if result is None else int(result)


def _run_serve(args: argparse.Namespace) -> int:
    try:
        from . import app as app_module
    except ModuleNotFoundError as exc:
        expected = f"{__package__}.app"
        if exc.name == expected:
            print(
                "dashboard serve is not wired yet. Implement dashboard/app.py with create_app().",
                file=sys.stderr,
            )
            return 2
        raise

    create_app = getattr(app_module, "create_app", None)
    if create_app is None:
        print("dashboard serve is not wired yet. dashboard.app.create_app is missing.", file=sys.stderr)
        return 2

    try:
        import uvicorn
    except ModuleNotFoundError:
        print("uvicorn is required for dashboard serve. Install uvicorn to run the local app.", file=sys.stderr)
        return 2

    if args.reload:
        os.environ["LOCAL_AI_USAGE_DASHBOARD_DB"] = str(args.db)
        uvicorn.run(
            "dashboard.app:create_app",
            host=args.host,
            port=args.port,
            reload=True,
            factory=True,
        )
        return 0

    app = create_app(db_path=args.db)
    uvicorn.run(app, host=args.host, port=args.port, reload=False)
    return 0


def _run_generate(args: argparse.Namespace) -> int:
    from . import generate as generate_module

    run = getattr(generate_module, "run", None)
    if run is None:
        print("dashboard generate is not wired yet. dashboard.generate.run is missing.", file=sys.stderr)
        return 2

    result = run(args)
    return 0 if result is None else int(result)


def _run_doctor(args: argparse.Namespace) -> int:
    from . import doctor as doctor_module

    run = getattr(doctor_module, "run", None)
    if run is None:
        print("dashboard doctor is not wired yet. dashboard.doctor.run is missing.", file=sys.stderr)
        return 2

    result = run(args)
    return 0 if result is None else int(result)


if __name__ == "__main__":
    raise SystemExit(main())
