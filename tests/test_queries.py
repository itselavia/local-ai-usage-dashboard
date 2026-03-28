from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from dashboard.db import open_database
from dashboard.queries import (
    get_filter_options,
    get_methodology_context,
    get_overview_context,
    get_trust_banner,
    get_workspaces_context,
)


class QueryLayerTests(unittest.TestCase):
    def test_overview_context_returns_ranked_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self._build_db(Path(tmpdir) / "dashboard.duckdb")
            try:
                context = get_overview_context(
                    db,
                    {
                        "from": "2026-03-20",
                        "to": "2026-03-21",
                        "provider": "all",
                        "workspace": "all",
                        "model": "all",
                        "include_temp": False,
                    },
                )

                self.assertEqual(context["headline_metrics"][0]["value"], 3.25)
                self.assertEqual(context["headline_metrics"][1]["value"], 3)
                self.assertEqual(context["headline_metrics"][2]["value"], 2330)
                self.assertEqual([row["label"] for row in context["provider_mix_rows"]], ["claude", "openai"])
                self.assertEqual(len(context["cost_trend_series"]), 2)
                self.assertEqual(context["workspace_rows"][0]["workspace_id"], "ws-beta")
                self.assertFalse(context["workspace_rows"][0]["selected"])

                banner = get_trust_banner(db, {"from": "2026-03-20", "to": "2026-03-21"})
                self.assertEqual(banner["summary_label"], "Partial coverage")
                self.assertAlmostEqual(banner["coverage_ratio"], 0.6333333333333333)
            finally:
                db.close()

    def test_workspaces_context_selects_workspace_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self._build_db(Path(tmpdir) / "dashboard.duckdb")
            try:
                context = get_workspaces_context(
                    db,
                    {
                        "from": "2026-03-20",
                        "to": "2026-03-21",
                        "provider": "all",
                        "workspace": "ws-alpha",
                        "model": "all",
                        "include_temp": False,
                    },
                )

                self.assertEqual(context["selected_workspace"]["workspace_id"], "ws-alpha")
                self.assertEqual(context["selected_workspace_metrics"][1]["value"], 2)
                self.assertEqual([row["label"] for row in context["selected_workspace_provider_mix"]], ["openai"])
                self.assertEqual({row["label"] for row in context["selected_workspace_work_shape"][:3]}, {"tools", "web", "edits"})
            finally:
                db.close()

    def test_empty_state_returns_empty_lists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = open_database(Path(tmpdir) / "empty.duckdb")
            try:
                context = get_overview_context(db, None)

                self.assertEqual(context["headline_metrics"][0]["value"], 0)
                self.assertEqual(context["cost_trend_series"], [])
                self.assertEqual(context["provider_mix_rows"], [])
                self.assertEqual(context["workspace_rows"], [])
            finally:
                db.close()

    def test_filter_options_expose_current_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self._build_db(Path(tmpdir) / "dashboard.duckdb")
            try:
                options = get_filter_options(db, {"include_temp": False})

                self.assertEqual(options["provider_options"][0]["label"], "All providers")
                self.assertEqual([row["value"] for row in options["provider_options"][1:]], ["claude", "openai"])
                self.assertEqual(options["workspace_options"][0]["label"], "All workspaces")
                self.assertEqual(options["model_options"][0]["label"], "All models")
            finally:
                db.close()

    def test_methodology_context_includes_rules_and_pricing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = self._build_db(Path(tmpdir) / "dashboard.duckdb")
            try:
                context = get_methodology_context(db, {"db": str(Path(tmpdir) / "dashboard.duckdb")})

                self.assertTrue(context["estimate_rules"])
                self.assertTrue(context["pricing_summary"])
                self.assertIn("doctor_summary", context)
                self.assertIn("source_paths", context)
            finally:
                db.close()

    def _build_db(self, path: Path):
        db = open_database(path)
        self._insert_fixture_data(db)
        return db

    def _insert_fixture_data(self, db) -> None:
        db.executemany(
            """
            INSERT INTO workspaces (
              workspace_id, workspace_label, cwd, repo_root, repo_name, is_temp, anonymized_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("ws-alpha", "/Users/testuser/projects/alpha", "/Users/testuser/projects/alpha", "/Users/testuser/projects/alpha", "alpha", False, None),
                ("ws-beta", "/Users/testuser/projects/beta", "/Users/testuser/projects/beta", "/Users/testuser/projects/beta", "beta", False, None),
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
                    "claude",
                    "claude-1",
                    "ingest-1",
                    "claude",
                    "/tmp/claude-1.json",
                    datetime(2026, 3, 21, 9, 0, tzinfo=timezone.utc),
                    date(2026, 3, 21),
                    9,
                    "Sat",
                    "ws-beta",
                    "claude-opus-4-6",
                    "inferred",
                    "ok",
                    2,
                    2,
                    0,
                    90.0,
                    True,
                    True,
                    True,
                    False,
                    True,
                    True,
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
                ("claude", "claude-1", 600, 200, 800, 0, 0, 50, 50, 0, 25, "enriched"),
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
                ("claude", "claude-1", "snap-1", "token-and-cache-based", "Approx", "Snapshot", 2.0, 0.10, False, None, "[]"),
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
                ("snap-1", "claude", "claude-opus-4-6", datetime(2026, 3, 21, 9, 0, tzinfo=timezone.utc), "Snapshot", "https://example.com/claude", "USD", 5.0, None, 25.0, 6.25, 10.0, 0.5, None, "[]"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
