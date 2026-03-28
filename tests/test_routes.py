from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.app import create_app
from dashboard.db import connect, initialize_database


class DashboardRouteTests(unittest.TestCase):
    def test_pages_render_and_filters_propagate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "dashboard.duckdb"
            self._seed_database(db_path)

            app = create_app(db_path)
            client = TestClient(app)

            overview = client.get("/")
            self.assertEqual(overview.status_code, 200)
            self.assertIn("Overview", overview.text)
            self.assertIn("Estimated cost", overview.text)
            self.assertIn("Pricing", overview.text)
            self.assertIn("Fresh", overview.text)
            self.assertIn("Snapshot", overview.text)

            filtered = client.get("/workspaces?provider=claude&metric=tokens&include_temp=1")
            self.assertEqual(filtered.status_code, 200)
            self.assertIn("option value=\"claude\" selected", filtered.text)
            self.assertIn("metric-toggle__item is-active", filtered.text)
            self.assertIn("Workspace ranking", filtered.text)
            self.assertIn("workspace-app", filtered.text)

            methodology = client.get("/methodology")
            self.assertEqual(methodology.status_code, 200)
            self.assertIn("OpenAI/Codex estimates charge uncached input", methodology.text)
            self.assertIn("Pricing snapshots", methodology.text)
            self.assertIn("Source paths", methodology.text)

    def _seed_database(self, db_path: Path) -> None:
        initialize_database(db_path).close()
        connection = connect(db_path)
        try:
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
                [
                    ("workspace-app", "workspace-app", "/Users/testuser/projects/app", "/Users/testuser/projects/app", "app", False, None),
                    ("workspace-temp", "workspace-temp", "/tmp/workspace-temp", "/tmp/workspace-temp", "workspace-temp", True, None),
                ],
            )
            connection.execute(
                """
                INSERT INTO ingest_runs (
                  ingest_id,
                  started_at,
                  completed_at,
                  timezone,
                  include_temp,
                  codex_path,
                  claude_path,
                  pricing_mode,
                  app_version,
                  schema_version,
                  status,
                  notes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ingest-1",
                    datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
                    datetime(2026, 3, 21, 12, 5, tzinfo=timezone.utc),
                    "UTC",
                    False,
                    "/Users/testuser/.codex",
                    "/Users/testuser/.claude",
                    "auto",
                    "0.1.0",
                    1,
                    "completed",
                    "[]",
                ),
            )
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
                [
                    (
                        "openai",
                        "openai-session",
                        "ingest-1",
                        "codex",
                        "/tmp/openai.jsonl",
                        datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc),
                        date(2026, 3, 21),
                        10,
                        "Sat",
                        "workspace-app",
                        "gpt-5.4",
                        "exact",
                        "parsed",
                        1,
                        1,
                        1,
                        60.0,
                        True,
                        True,
                        False,
                        False,
                        True,
                        True,
                    ),
                    (
                        "claude",
                        "claude-session",
                        "ingest-1",
                        "claude",
                        "/tmp/claude.json",
                        datetime(2026, 3, 21, 11, 0, tzinfo=timezone.utc),
                        date(2026, 3, 21),
                        11,
                        "Sat",
                        "workspace-app",
                        "claude-opus-4-6",
                        "inferred",
                        "ok",
                        1,
                        1,
                        0,
                        45.0,
                        True,
                        False,
                        True,
                        False,
                        True,
                        False,
                    ),
                    (
                        "openai",
                        "temp-session",
                        "ingest-1",
                        "codex",
                        "/tmp/temp.jsonl",
                        datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
                        date(2026, 3, 21),
                        12,
                        "Sat",
                        "workspace-temp",
                        "gpt-5.4",
                        "exact",
                        "parsed",
                        1,
                        1,
                        0,
                        30.0,
                        False,
                        False,
                        False,
                        False,
                        False,
                        False,
                    ),
                ],
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
                [
                    ("openai", "openai-session", 1000, 500, 1500, 200, 300, 0, 0, 0, 0, "direct"),
                    ("claude", "claude-session", 400, 200, 600, 0, 0, 50, 50, 0, 25, "enriched"),
                    ("openai", "temp-session", 50, 10, 60, 0, 0, 0, 0, 0, 0, "direct"),
                ],
            )
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
                [
                    ("openai", "openai-session", "snap-1", "token-based", "Direct", "Fresh", 0.005, 0.001, False, None, "[]"),
                    ("claude", "claude-session", "snap-1", "token-and-cache-based", "Approx", "Snapshot", 0.007, 0.0005, False, None, "[\"assumed_missing_cache_write_split_is_5m\"]"),
                    ("openai", "temp-session", None, "token-based", "Partial", "Unavailable", None, None, True, "unsupported_model", "[]"),
                ],
            )
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
                [
                    ("snap-1", "openai", "gpt-5.4", datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc), "Fresh", "https://example.com/openai", "USD", 1.0, 0.5, 2.0, None, None, None, str(db_path), "[]"),
                    ("snap-1", "claude", "claude-opus-4-6", datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc), "Snapshot", "https://example.com/claude", "USD", 5.0, None, 10.0, 6.25, 25.0, 0.5, str(db_path), "[]"),
                ],
            )
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
