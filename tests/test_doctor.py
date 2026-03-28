from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from dashboard.db import open_database
from dashboard.queries import get_doctor_summary


class DoctorSummaryTests(unittest.TestCase):
    def test_doctor_summary_reports_missing_sources_and_exclusions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            db_path = tmp_root / "dashboard.duckdb"
            codex_dir = tmp_root / ".codex"
            claude_dir = tmp_root / ".claude"
            db = self._build_db(db_path)
            try:
                summary = get_doctor_summary(
                    db,
                    {
                        "db": str(db_path),
                        "codex_dir": str(codex_dir),
                        "claude_dir": str(claude_dir),
                    },
                )

                self.assertEqual(summary["session_counts"]["sessions"], 2)
                self.assertEqual(summary["session_counts"]["partial_sessions"], 1)
                self.assertEqual(summary["session_counts"]["excluded_sessions"], 1)
                self.assertEqual(summary["unsupported_models"][0]["model"], "gpt-unknown")
                self.assertEqual(summary["pricing_state"], "Mixed")
                source_paths = {item["label"]: item["exists"] for item in summary["source_paths"]}
                self.assertFalse(source_paths["Codex"])
                self.assertFalse(source_paths["Claude"])
                self.assertTrue(source_paths["DuckDB"])
            finally:
                db.close()

    def _build_db(self, path: Path):
        db = open_database(path)
        db.executemany(
            """
            INSERT INTO workspaces (
              workspace_id, workspace_label, cwd, repo_root, repo_name, is_temp, anonymized_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("ws-alpha", "/Users/testuser/projects/alpha", "/Users/testuser/projects/alpha", "/Users/testuser/projects/alpha", "alpha", False, None),
            ],
        )
        db.executemany(
            """
            INSERT INTO session_facts (
              provider, session_id, ingest_id, source_app, raw_path, started_at, local_day, local_hour, local_weekday,
              workspace_id, model, model_confidence, parse_status, user_messages, assistant_messages, reasoning_messages,
              duration_s, has_tools, has_web, has_task_agent, has_subagent, has_edits, has_mcp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "openai",
                    "openai-1",
                    "ingest-1",
                    "codex",
                    "/tmp/openai-1.jsonl",
                    datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc),
                    date(2026, 3, 20),
                    10,
                    "Fri",
                    "ws-alpha",
                    "gpt-5.4",
                    "exact",
                    "parsed",
                    1,
                    1,
                    1,
                    30.0,
                    True,
                    True,
                    False,
                    False,
                    True,
                    False,
                ),
                (
                    "openai",
                    "openai-unsupported",
                    "ingest-1",
                    "codex",
                    "/tmp/openai-unsupported.jsonl",
                    datetime(2026, 3, 21, 11, 0, tzinfo=timezone.utc),
                    date(2026, 3, 21),
                    11,
                    "Sat",
                    "ws-alpha",
                    "gpt-unknown",
                    "unknown",
                    "partial",
                    0,
                    0,
                    0,
                    10.0,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                ),
            ],
        )
        db.executemany(
            """
            INSERT INTO session_usage (
              provider, session_id, input_tokens, output_tokens, total_tokens, cached_input_tokens,
              reasoning_output_tokens, cache_creation_input_tokens, cache_creation_5m_tokens,
              cache_creation_1h_tokens, cache_read_tokens, token_coverage
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("openai", "openai-1", 1000, 500, 1500, 200, 300, 0, 0, 0, 0, "direct"),
                ("openai", "openai-unsupported", 20, 10, 30, 0, 0, 0, 0, 0, 0, "direct"),
            ],
        )
        db.executemany(
            """
            INSERT INTO session_estimates (
              provider, session_id, snapshot_id, estimation_method, estimate_label, pricing_freshness,
              estimated_cost_usd, estimated_cache_savings_usd, excluded, exclusion_reason, assumption_flags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("openai", "openai-1", "snap-1", "token-based", "Direct", "Fresh", 1.25, 0.15, False, None, "[]"),
                ("openai", "openai-unsupported", None, "token-based", "Partial", "Unavailable", None, None, True, "unsupported_model", "[]"),
            ],
        )
        db.executemany(
            """
            INSERT INTO pricing_snapshots (
              snapshot_id, provider, model, checked_at, freshness_label, source_url, currency,
              input_per_million, cached_input_per_million, output_per_million,
              cache_write_5m_per_million, cache_write_1h_per_million, cache_read_per_million,
              snapshot_path, notes_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("snap-1", "openai", "gpt-5.4", datetime(2026, 3, 21, 9, 0, tzinfo=timezone.utc), "Fresh", "https://example.com/openai", "USD", 1.0, 0.1, 5.0, None, None, None, None, "[]"),
                ("snap-1", "anthropic", "claude-opus-4-6", datetime(2026, 3, 21, 9, 0, tzinfo=timezone.utc), "Snapshot", "https://example.com/claude", "USD", 5.0, None, 25.0, 6.25, 10.0, 0.5, None, "[]"),
            ],
        )
        return db


if __name__ == "__main__":
    unittest.main()
