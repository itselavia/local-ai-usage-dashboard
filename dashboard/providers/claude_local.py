from __future__ import annotations

import json
import hashlib
from datetime import tzinfo
from pathlib import Path

from usage_report_common import ClaudeSessionRecord, UNKNOWN_LABEL, is_temp_workspace, workspace_label
from usage_report_providers import discover_claude_sessions
from . import NormalizedSession

PROVIDER = "claude"
SOURCE_APP = "claude"


def discover_claude_rows(
    claude_dir: Path,
    report_tz: tzinfo,
    *,
    anonymize_workspaces: bool = False,
) -> list[NormalizedSession]:
    sessions = discover_claude_sessions(claude_dir, report_tz)
    rows: list[NormalizedSession] = []

    for session in sessions:
        rows.append(normalize_claude_session(session, anonymize_workspaces=anonymize_workspaces))

    rows.sort(key=lambda item: item.started_at_local)
    return rows


def normalize_claude_session(
    session: ClaudeSessionRecord,
    *,
    anonymize_workspaces: bool = False,
) -> NormalizedSession:
    flags = read_claude_session_flags(session.path)
    label = workspace_label(session.cwd)
    if anonymize_workspaces:
        label = _anonymized_workspace_label(session.cwd)

    token_coverage = "enriched" if session.has_enriched_tokens else "meta"
    parse_status = "partial" if session.is_partial_parse else "ok"
    model_confidence = "unknown" if session.model == UNKNOWN_LABEL else "inferred"

    return NormalizedSession(
        provider=PROVIDER,
        session_id=session.session_id,
        source_app=SOURCE_APP,
        raw_path=str(session.path),
        started_at=session.timestamp_utc,
        started_at_local=session.timestamp_local,
        local_day=session.local_day,
        local_hour=session.local_hour,
        local_weekday=session.local_weekday,
        cwd=session.cwd,
        workspace_label=label,
        is_temp_workspace=is_temp_workspace(session.cwd),
        model=session.model,
        model_confidence=model_confidence,
        parse_status=parse_status,
        input_tokens=session.input_tokens,
        output_tokens=session.output_tokens,
        total_tokens=session.total_tokens,
        cache_creation_input_tokens=session.cache_creation_input_tokens,
        cache_creation_5m_tokens=session.cache_creation_ephemeral_5m_input_tokens,
        cache_creation_1h_tokens=session.cache_creation_ephemeral_1h_input_tokens,
        cache_read_tokens=session.cache_read_input_tokens,
        token_coverage=token_coverage,
        user_messages=session.user_messages,
        assistant_messages=session.assistant_messages,
        duration_s=session.duration_s,
        has_tools=bool(flags["used_tools"]),
        has_web=bool(flags["used_web"]),
        has_task_agent=bool(flags["used_task_agent"]),
        has_subagent=False,
        has_edits=bool(flags["used_edits"]),
        has_mcp=bool(flags["used_mcp"]),
    )


def read_claude_session_flags(path: Path) -> dict[str, object]:
    payload = _read_json_object(path)
    if not payload:
        return _empty_flags()

    tool_counts = _dict_or_empty(payload.get("tool_counts"))
    languages = payload.get("languages")
    files_modified = payload.get("files_modified")

    used_task_agent = bool(payload.get("uses_task_agent"))
    used_mcp = bool(payload.get("uses_mcp"))
    used_web = bool(payload.get("uses_web_fetch")) or bool(payload.get("uses_web_search"))
    used_tools = bool(tool_counts)
    used_edits = bool(_non_empty_list(files_modified))
    used_edits = used_edits or int(tool_counts.get("Write", 0)) > 0
    used_edits = used_edits or int(tool_counts.get("Edit", 0)) > 0

    return {
        "used_tools": used_tools,
        "used_web": used_web,
        "used_task_agent": used_task_agent,
        "used_mcp": used_mcp,
        "used_edits": used_edits,
        "tool_counts_json": _json_string(tool_counts, "{}"),
        "languages_json": _json_string(languages, "{}"),
        "files_modified_json": _json_string(files_modified, "[]"),
    }


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError:
        return {}

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return {}

    if not isinstance(payload, dict):
        return {}

    return payload


def _empty_flags() -> dict[str, object]:
    return {
        "used_tools": False,
        "used_web": False,
        "used_task_agent": False,
        "used_mcp": False,
        "used_edits": False,
        "tool_counts_json": "{}",
        "languages_json": "{}",
        "files_modified_json": "[]",
    }


def _dict_or_empty(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    return {}


def _non_empty_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return []


def _json_string(value: object, empty_value: str) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return empty_value


def _anonymized_workspace_label(cwd: str) -> str:
    if not cwd:
        return "workspace-anon"

    digest = hashlib.sha1(cwd.encode("utf-8")).hexdigest()[:8]
    return f"workspace-{digest}"
