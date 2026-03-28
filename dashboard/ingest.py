from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from usage_report_common import UNKNOWN_LABEL, resolve_timezone

from . import APP_VERSION, SCHEMA_VERSION
from . import config
from .db import initialize_database
from .estimates import (
    PricingSnapshotRow,
    SessionEstimateRow,
    estimate_claude_sessions,
    estimate_openai_sessions,
)
from .providers import NormalizedSession
from .providers.claude_local import discover_claude_rows
from .providers.openai_local import discover_openai_rows


def run(args) -> int:
    report_tz = resolve_timezone(args.timezone)
    ingest_id = uuid4().hex
    started_at = datetime.now(report_tz)
    snapshot_path = config.default_pricing_snapshot_path()
    metadata_path = config.default_metadata_path()
    db_path = args.db

    openai_sessions = discover_openai_rows(args.codex_dir, report_tz)
    claude_sessions = discover_claude_rows(args.claude_dir, report_tz)
    sessions = _dedupe_sessions(openai_sessions + claude_sessions)

    openai_snapshot_id = f"{ingest_id}:openai"
    claude_snapshot_id = f"{ingest_id}:claude"

    openai_pricing_rows, openai_estimates = estimate_openai_sessions(
        sessions=[session for session in sessions if session.provider == "openai"],
        snapshot_path=snapshot_path,
        report_tz=report_tz,
        pricing_mode=args.pricing_mode,
        snapshot_id=openai_snapshot_id,
    )
    claude_pricing_rows, claude_estimates = estimate_claude_sessions(
        sessions=[session for session in sessions if session.provider == "claude"],
        snapshot_path=snapshot_path,
        report_tz=report_tz,
        pricing_mode=args.pricing_mode,
        snapshot_id=claude_snapshot_id,
    )

    connection = initialize_database(db_path)
    _insert_ingest_run_start(connection, args, ingest_id, started_at)

    try:
        _replace_ingest_snapshot(
            connection=connection,
            ingest_id=ingest_id,
            sessions=sessions,
            pricing_rows=openai_pricing_rows + claude_pricing_rows,
            estimate_rows=openai_estimates + claude_estimates,
            anonymize_workspaces=args.anonymize_workspaces,
        )

        completed_at = datetime.now(report_tz)
        metadata = _build_metadata(
            args=args,
            ingest_id=ingest_id,
            started_at=started_at,
            completed_at=completed_at,
            sessions=sessions,
            pricing_rows=openai_pricing_rows + claude_pricing_rows,
            estimate_rows=openai_estimates + claude_estimates,
        )
        _write_metadata(metadata_path, metadata)
        _finish_ingest_run(connection, ingest_id, completed_at, "completed", metadata["notes"])
    except Exception as exc:
        completed_at = datetime.now(report_tz)
        _finish_ingest_run(connection, ingest_id, completed_at, "failed", [str(exc)])
        connection.close()
        raise

    connection.close()
    print(
        f"ingested {len(sessions)} sessions into {db_path} "
        f"({len(openai_sessions)} openai, {len(claude_sessions)} claude)"
    )
    return 0


def _replace_ingest_snapshot(
    connection,
    ingest_id: str,
    sessions: list[NormalizedSession],
    pricing_rows: list[PricingSnapshotRow],
    estimate_rows: list[SessionEstimateRow],
    anonymize_workspaces: bool,
) -> None:
    workspace_rows = _build_workspace_rows(sessions, anonymize_workspaces)

    connection.execute("BEGIN")
    try:
        connection.execute("DELETE FROM session_estimates")
        connection.execute("DELETE FROM session_usage")
        connection.execute("DELETE FROM session_facts")
        connection.execute("DELETE FROM pricing_snapshots")
        connection.execute("DELETE FROM workspaces")

        if workspace_rows:
            connection.executemany(
                """
                INSERT INTO workspaces (
                  workspace_id,
                  workspace_label,
                  cwd,
                  repo_root,
                  repo_name,
                  is_temp,
                  anonymized_label
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                workspace_rows,
            )

        if sessions:
            connection.executemany(
                """
                INSERT INTO session_facts (
                  provider,
                  session_id,
                  ingest_id,
                  source_app,
                  raw_path,
                  started_at,
                  local_day,
                  local_hour,
                  local_weekday,
                  workspace_id,
                  model,
                  model_confidence,
                  parse_status,
                  user_messages,
                  assistant_messages,
                  reasoning_messages,
                  duration_s,
                  has_tools,
                  has_web,
                  has_task_agent,
                  has_subagent,
                  has_edits,
                  has_mcp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_session_fact_record(ingest_id, session) for session in sessions],
            )
            connection.executemany(
                """
                INSERT INTO session_usage (
                  provider,
                  session_id,
                  input_tokens,
                  output_tokens,
                  total_tokens,
                  cached_input_tokens,
                  reasoning_output_tokens,
                  cache_creation_input_tokens,
                  cache_creation_5m_tokens,
                  cache_creation_1h_tokens,
                  cache_read_tokens,
                  token_coverage
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_session_usage_record(session) for session in sessions],
            )

        if pricing_rows:
            connection.executemany(
                """
                INSERT INTO pricing_snapshots (
                  snapshot_id,
                  provider,
                  model,
                  checked_at,
                  freshness_label,
                  source_url,
                  currency,
                  input_per_million,
                  cached_input_per_million,
                  output_per_million,
                  cache_write_5m_per_million,
                  cache_write_1h_per_million,
                  cache_read_per_million,
                  snapshot_path,
                  notes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_pricing_snapshot_record(row) for row in pricing_rows],
            )

        if estimate_rows:
            connection.executemany(
                """
                INSERT INTO session_estimates (
                  provider,
                  session_id,
                  snapshot_id,
                  estimation_method,
                  estimate_label,
                  pricing_freshness,
                  estimated_cost_usd,
                  estimated_cache_savings_usd,
                  excluded,
                  exclusion_reason,
                  assumption_flags_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_session_estimate_record(row) for row in estimate_rows],
            )

        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


def _insert_ingest_run_start(connection, args, ingest_id: str, started_at: datetime) -> None:
    notes = json.dumps([])
    connection.execute(
        """
        INSERT INTO ingest_runs (
          ingest_id,
          started_at,
          timezone,
          include_temp,
          codex_path,
          claude_path,
          pricing_mode,
          app_version,
          schema_version,
          status,
          notes_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ingest_id,
            started_at,
            args.timezone,
            bool(args.include_temp),
            str(args.codex_dir),
            str(args.claude_dir),
            args.pricing_mode,
            APP_VERSION,
            SCHEMA_VERSION,
            "running",
            notes,
        ),
    )


def _finish_ingest_run(
    connection,
    ingest_id: str,
    completed_at: datetime,
    status: str,
    notes: list[str],
) -> None:
    connection.execute(
        """
        UPDATE ingest_runs
        SET completed_at = ?, status = ?, notes_json = ?
        WHERE ingest_id = ?
        """,
        (completed_at, status, json.dumps(notes), ingest_id),
    )


def _build_workspace_rows(
    sessions: list[NormalizedSession],
    anonymize_workspaces: bool,
) -> list[tuple[str, str, str, str | None, str | None, bool, str | None]]:
    workspace_map: dict[str, tuple[str, str, str | None, str | None, bool, str | None]] = {}

    for session in sessions:
        workspace_id = _workspace_id(session.workspace_label)
        cwd = session.workspace_label if session.workspace_label != UNKNOWN_LABEL else session.cwd
        repo_root = None if session.workspace_label == UNKNOWN_LABEL else session.workspace_label
        repo_name = None if repo_root is None else Path(repo_root).name or None
        anonymized_label = _anonymized_workspace_label(session.workspace_label) if anonymize_workspaces else None

        existing = workspace_map.get(workspace_id)
        if existing is None:
            workspace_map[workspace_id] = (
                session.workspace_label,
                cwd,
                repo_root,
                repo_name,
                session.is_temp_workspace,
                anonymized_label,
            )
            continue

        existing_label, existing_cwd, existing_root, existing_name, existing_is_temp, existing_anonymized = existing
        workspace_map[workspace_id] = (
            existing_label or session.workspace_label,
            existing_cwd or cwd,
            existing_root or repo_root,
            existing_name or repo_name,
            existing_is_temp or session.is_temp_workspace,
            existing_anonymized or anonymized_label,
        )

    rows = []
    for workspace_id, values in sorted(workspace_map.items()):
        workspace_label, cwd, repo_root, repo_name, is_temp, anonymized_label = values
        rows.append((workspace_id, workspace_label, cwd, repo_root, repo_name, is_temp, anonymized_label))
    return rows


def _session_fact_record(ingest_id: str, session: NormalizedSession) -> tuple:
    return (
        session.provider,
        session.session_id,
        ingest_id,
        session.source_app,
        session.raw_path,
        session.started_at,
        session.local_day,
        session.local_hour,
        session.local_weekday,
        _workspace_id(session.workspace_label),
        session.model,
        session.model_confidence,
        session.parse_status,
        session.user_messages,
        session.assistant_messages,
        session.reasoning_messages,
        session.duration_s,
        session.has_tools,
        session.has_web,
        session.has_task_agent,
        session.has_subagent,
        session.has_edits,
        session.has_mcp,
    )


def _session_usage_record(session: NormalizedSession) -> tuple:
    return (
        session.provider,
        session.session_id,
        session.input_tokens,
        session.output_tokens,
        session.total_tokens,
        session.cached_input_tokens,
        session.reasoning_output_tokens,
        session.cache_creation_input_tokens,
        session.cache_creation_5m_tokens,
        session.cache_creation_1h_tokens,
        session.cache_read_tokens,
        session.token_coverage,
    )


def _pricing_snapshot_record(row: PricingSnapshotRow) -> tuple:
    return (
        row.snapshot_id,
        row.provider,
        row.model,
        row.checked_at,
        row.freshness_label,
        row.source_url,
        row.currency,
        row.input_per_million,
        row.cached_input_per_million,
        row.output_per_million,
        row.cache_write_5m_per_million,
        row.cache_write_1h_per_million,
        row.cache_read_per_million,
        row.snapshot_path,
        row.notes_json,
    )


def _session_estimate_record(row: SessionEstimateRow) -> tuple:
    return (
        row.provider,
        row.session_id,
        row.snapshot_id,
        row.estimation_method,
        row.estimate_label,
        row.pricing_freshness,
        row.estimated_cost_usd,
        row.estimated_cache_savings_usd,
        row.excluded,
        row.exclusion_reason,
        row.assumption_flags_json,
    )


def _build_metadata(
    args,
    ingest_id: str,
    started_at: datetime,
    completed_at: datetime,
    sessions: list[NormalizedSession],
    pricing_rows: list[PricingSnapshotRow],
    estimate_rows: list[SessionEstimateRow],
) -> dict:
    provider_counts: dict[str, int] = {}
    for session in sessions:
        provider_counts[session.provider] = provider_counts.get(session.provider, 0) + 1

    excluded_estimates = sum(1 for row in estimate_rows if row.excluded)
    notes = [
        f"sessions: {len(sessions)}",
        f"excluded_estimates: {excluded_estimates}",
        f"pricing_rows: {len(pricing_rows)}",
    ]

    return {
        "ingest_id": ingest_id,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "timezone": args.timezone,
        "db_path": str(args.db),
        "pricing_snapshot_path": str(config.default_pricing_snapshot_path()),
        "metadata_path": str(config.default_metadata_path()),
        "providers": provider_counts,
        "notes": notes,
    }


def _write_metadata(path: Path, metadata: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _workspace_id(workspace_label: str) -> str:
    return sha1(workspace_label.encode("utf-8")).hexdigest()[:16]


def _anonymized_workspace_label(workspace_label: str) -> str:
    if workspace_label == UNKNOWN_LABEL:
        return "workspace-unknown"

    digest = sha1(workspace_label.encode("utf-8")).hexdigest()[:8]
    return f"workspace-{digest}"


def _dedupe_sessions(sessions: list[NormalizedSession]) -> list[NormalizedSession]:
    deduped: dict[tuple[str, str], NormalizedSession] = {}

    for session in sessions:
        key = (session.provider, session.session_id)
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = session
            continue

        if _session_rank(session) > _session_rank(existing):
            deduped[key] = session

    rows = list(deduped.values())
    rows.sort(key=lambda item: item.started_at_local)
    return rows


def _session_rank(session: NormalizedSession) -> tuple:
    duration = session.duration_s or 0
    return (
        session.total_tokens,
        session.output_tokens,
        session.input_tokens,
        duration,
        session.started_at.timestamp(),
    )


if __name__ == "__main__":
    namespace = SimpleNamespace(
        codex_dir=config.default_codex_dir(),
        claude_dir=config.default_claude_dir(),
        timezone=config.DEFAULT_TIMEZONE,
        db=config.default_db_path(),
        include_temp=config.DEFAULT_INCLUDE_TEMP,
        anonymize_workspaces=False,
        pricing_mode="auto",
    )
    raise SystemExit(run(namespace))
