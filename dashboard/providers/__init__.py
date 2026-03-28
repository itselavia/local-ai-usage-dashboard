from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class NormalizedSession:
    provider: str
    session_id: str
    source_app: str
    raw_path: str
    started_at: datetime
    started_at_local: datetime
    local_day: date
    local_hour: int
    local_weekday: str
    cwd: str
    workspace_label: str
    is_temp_workspace: bool
    model: str
    model_confidence: str
    parse_status: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_input_tokens: int = 0
    reasoning_output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_creation_5m_tokens: int = 0
    cache_creation_1h_tokens: int = 0
    cache_read_tokens: int = 0
    token_coverage: str = "direct"
    user_messages: int = 0
    assistant_messages: int = 0
    reasoning_messages: int = 0
    duration_s: float | None = None
    has_tools: bool = False
    has_web: bool = False
    has_task_agent: bool = False
    has_subagent: bool = False
    has_edits: bool = False
    has_mcp: bool = False


__all__ = ["NormalizedSession"]
