from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import tzinfo
from pathlib import Path

from usage_report_common import UNKNOWN_LABEL, is_temp_workspace, workspace_label
from usage_report_providers import openai_session_files, read_openai_session
from . import NormalizedSession

SOURCE_APP = "codex"
PROVIDER = "openai"

WEB_FUNCTION_NAMES = {
    "mcp__duckduckgo__fetch_content",
    "mcp__duckduckgo__search",
}

SUBAGENT_FUNCTION_NAMES = {
    "close_agent",
    "spawn_agent",
    "wait_agent",
}

__all__ = [
    "OpenAIInspection",
    "discover_openai_rows",
    "inspect_openai_session",
    "read_openai_row",
]


@dataclass(frozen=True, slots=True)
class OpenAIInspection:
    session_id: str
    had_invalid_json: bool
    has_tools: bool
    has_web: bool
    has_task_agent: bool
    has_subagent: bool
    has_edits: bool
    has_mcp: bool


def discover_openai_rows(codex_dir: Path, report_tz: tzinfo) -> list[NormalizedSession]:
    rows: list[NormalizedSession] = []

    for path in openai_session_files(codex_dir):
        row = read_openai_row(path, report_tz)
        if row is None:
            continue
        rows.append(row)

    rows.sort(key=lambda item: item.started_at_local)
    return rows


def read_openai_row(path: Path, report_tz: tzinfo) -> NormalizedSession | None:
    session = read_openai_session(path, report_tz)
    if session is None:
        return None

    inspection = inspect_openai_session(path)
    model = session.model
    model_confidence = "exact" if model != UNKNOWN_LABEL else "unknown"
    parse_status = "partial" if inspection.had_invalid_json else "parsed"

    return NormalizedSession(
        provider=PROVIDER,
        session_id=inspection.session_id,
        source_app=SOURCE_APP,
        raw_path=str(path),
        started_at=session.timestamp_utc,
        started_at_local=session.timestamp_local,
        local_day=session.local_day,
        local_hour=session.local_hour,
        local_weekday=session.local_weekday,
        cwd=session.cwd,
        workspace_label=workspace_label(session.cwd),
        is_temp_workspace=is_temp_workspace(session.cwd),
        model=model,
        model_confidence=model_confidence,
        parse_status=parse_status,
        input_tokens=session.input_tokens,
        output_tokens=session.output_tokens,
        total_tokens=session.total_tokens,
        cached_input_tokens=session.cached_input_tokens,
        reasoning_output_tokens=session.reasoning_output_tokens,
        token_coverage="direct",
        user_messages=session.user_messages,
        assistant_messages=session.assistant_messages,
        reasoning_messages=session.reasoning_messages,
        duration_s=session.duration_s,
        has_tools=inspection.has_tools,
        has_web=inspection.has_web,
        has_task_agent=inspection.has_task_agent,
        has_subagent=inspection.has_subagent,
        has_edits=inspection.has_edits,
        has_mcp=inspection.has_mcp,
    )


def inspect_openai_session(path: Path) -> OpenAIInspection:
    session_id = path.stem
    had_invalid_json = False
    has_tools = False
    has_web = False
    has_task_agent = False
    has_subagent = False
    has_edits = False
    has_mcp = False

    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                had_invalid_json = True
                continue

            record_type = record.get("type")
            payload = record.get("payload") or {}

            if record_type == "session_meta":
                payload_session_id = payload.get("id")
                if isinstance(payload_session_id, str) and payload_session_id.strip():
                    session_id = payload_session_id.strip()
                continue

            if record_type == "event_msg":
                if payload.get("type") == "task_started":
                    has_task_agent = True
                if payload.get("type") == "web_search_call":
                    has_web = True
                    has_tools = True
                continue

            if record_type != "response_item":
                continue

            payload_type = payload.get("type")
            if payload_type == "function_call":
                has_tools = True
                function_name = payload.get("name") or ""
                if function_name in WEB_FUNCTION_NAMES:
                    has_web = True
                if function_name in SUBAGENT_FUNCTION_NAMES:
                    has_subagent = True
                if function_name == "apply_patch":
                    has_edits = True
                if str(function_name).startswith("mcp__"):
                    has_mcp = True
                continue

            if payload_type == "custom_tool_call":
                has_tools = True
                function_name = payload.get("name") or ""
                if function_name == "apply_patch":
                    has_edits = True
                if str(function_name).startswith("mcp__"):
                    has_mcp = True
                continue

            if payload_type == "web_search_call":
                has_tools = True
                has_web = True

    return OpenAIInspection(
        session_id=session_id,
        had_invalid_json=had_invalid_json,
        has_tools=has_tools or has_web or has_task_agent or has_subagent or has_edits or has_mcp,
        has_web=has_web,
        has_task_agent=has_task_agent,
        has_subagent=has_subagent,
        has_edits=has_edits,
        has_mcp=has_mcp,
    )
