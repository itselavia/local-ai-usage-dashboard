from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from dashboard.estimates import _parse_claude_pricing_page, estimate_claude_sessions
from dashboard.ingest import _dedupe_sessions
from dashboard.providers import NormalizedSession


class DashboardEstimateTests(unittest.TestCase):
    def test_claude_pricing_parser_handles_live_table_spacing(self) -> None:
        page_text = (
            "Model Base Input Tokens 5m Cache Writes 1h Cache Writes Cache Hits & Refreshes Output Tokens "
            "Claude Opus 4.6 $5 / MTok $6.25 / MTok $10 / MTok $0.50 / MTok $25 / MTok "
            "Claude Sonnet 3.7 ( deprecated ) $3 / MTok $3.75 / MTok $6 / MTok $0.30 / MTok $15 / MTok "
            "Claude Haiku 4.5 $1 / MTok $1.25 / MTok $2 / MTok $0.10 / MTok $5 / MTok "
        )

        pricing = _parse_claude_pricing_page(page_text)

        self.assertEqual(pricing["claude-opus-4-6"].input_per_million, 5.0)
        self.assertEqual(pricing["claude-opus-4-6"].cache_write_5m_per_million, 6.25)
        self.assertEqual(pricing["claude-sonnet-3-7"].output_per_million, 15.0)
        self.assertEqual(pricing["claude-haiku-4-5"].cache_read_per_million, 0.10)

    def test_unknown_claude_model_is_excluded(self) -> None:
        session = NormalizedSession(
            provider="claude",
            session_id="session-1",
            source_app="claude",
            raw_path="/tmp/session.json",
            started_at=datetime(2026, 3, 28, 10, 0, tzinfo=timezone.utc),
            started_at_local=datetime(2026, 3, 28, 10, 0, tzinfo=timezone.utc),
            local_day=datetime(2026, 3, 28, 10, 0, tzinfo=timezone.utc).date(),
            local_hour=10,
            local_weekday="Sat",
            cwd="/Users/testuser/project",
            workspace_label="/Users/testuser/project",
            is_temp_workspace=False,
            model="(unknown)",
            model_confidence="unknown",
            parse_status="ok",
            input_tokens=100,
            output_tokens=20,
            total_tokens=120,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pricing_rows, estimate_rows = estimate_claude_sessions(
                sessions=[session],
                snapshot_path=Path(tmpdir) / "pricing_snapshot.json",
                report_tz=timezone.utc,
                pricing_mode="snapshot",
                snapshot_id="snapshot-1",
            )

        self.assertEqual(pricing_rows, [])
        self.assertEqual(len(estimate_rows), 1)
        self.assertTrue(estimate_rows[0].excluded)
        self.assertEqual(estimate_rows[0].exclusion_reason, "unsupported_model")


class DashboardIngestDedupeTests(unittest.TestCase):
    def test_dedupe_prefers_session_with_more_complete_usage(self) -> None:
        older = NormalizedSession(
            provider="openai",
            session_id="session-1",
            source_app="codex",
            raw_path="/tmp/older.jsonl",
            started_at=datetime(2026, 3, 28, 9, 0, tzinfo=timezone.utc),
            started_at_local=datetime(2026, 3, 28, 9, 0, tzinfo=timezone.utc),
            local_day=datetime(2026, 3, 28, 9, 0, tzinfo=timezone.utc).date(),
            local_hour=9,
            local_weekday="Sat",
            cwd="/Users/testuser/project",
            workspace_label="/Users/testuser/project",
            is_temp_workspace=False,
            model="gpt-5.4",
            model_confidence="exact",
            parse_status="ok",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
        )
        newer = NormalizedSession(
            provider="openai",
            session_id="session-1",
            source_app="codex",
            raw_path="/tmp/newer.jsonl",
            started_at=datetime(2026, 3, 28, 10, 0, tzinfo=timezone.utc),
            started_at_local=datetime(2026, 3, 28, 10, 0, tzinfo=timezone.utc),
            local_day=datetime(2026, 3, 28, 10, 0, tzinfo=timezone.utc).date(),
            local_hour=10,
            local_weekday="Sat",
            cwd="/Users/testuser/project",
            workspace_label="/Users/testuser/project",
            is_temp_workspace=False,
            model="gpt-5.4",
            model_confidence="exact",
            parse_status="ok",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
        )

        deduped = _dedupe_sessions([older, newer])

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].raw_path, "/tmp/newer.jsonl")


if __name__ == "__main__":
    unittest.main()
