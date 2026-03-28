from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

try:
    import duckdb  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - environment dependent
    HAS_DUCKDB = False
else:  # pragma: no cover - environment dependent
    HAS_DUCKDB = True

from dashboard import queries as queries_module
from dashboard.cli import main as dashboard_main
from dashboard.db import connect, initialize_database

ORIGINAL_GET_FILTER_OPTIONS = queries_module.get_filter_options


@unittest.skipUnless(HAS_DUCKDB, "duckdb is required for dashboard privacy tests")
class DashboardPrivacyTests(unittest.TestCase):
    def test_generate_anonymize_workspaces_redacts_raw_paths_and_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            db_path = tmp_root / "dashboard.duckdb"
            output_dir = tmp_root / "public-snapshot"

            self._seed_private_database(db_path)

            with patch.object(
                queries_module,
                "get_filter_options",
                side_effect=self._compat_get_filter_options,
            ):
                result = dashboard_main(
                    [
                        "generate",
                        "--db",
                        str(db_path),
                        "--output-dir",
                        str(output_dir),
                        "--anonymize-workspaces",
                    ]
                )

            self.assertEqual(result, 0)

            rendered = self._read_rendered_snapshot(output_dir)

            self.assertNotIn("/Users/", rendered)
            self.assertNotIn("private-user", rendered)
            self.assertNotIn("secret-alpha", rendered)
            self.assertNotIn("secret-beta", rendered)

    def _seed_private_database(self, db_path: Path) -> None:
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
                    (
                        "workspace-alpha",
                        "/Users/private-user/projects/secret-alpha",
                        "/Users/private-user/projects/secret-alpha",
                        "/Users/private-user/projects/secret-alpha",
                        "secret-alpha",
                        False,
                        None,
                    ),
                    (
                        "workspace-beta",
                        "/Users/private-user/projects/secret-beta",
                        "/Users/private-user/projects/secret-beta",
                        "/Users/private-user/projects/secret-beta",
                        "secret-beta",
                        False,
                        None,
                    ),
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
                    "ingest-privacy",
                    datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
                    datetime(2026, 3, 21, 12, 5, tzinfo=timezone.utc),
                    "UTC",
                    False,
                    "/Users/private-user/.codex",
                    "/Users/private-user/.claude",
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
                        "openai-private",
                        "ingest-privacy",
                        "codex",
                        "/tmp/openai-private.jsonl",
                        datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc),
                        date(2026, 3, 21),
                        10,
                        "Sat",
                        "workspace-alpha",
                        "gpt-5.4",
                        "exact",
                        "parsed",
                        1,
                        1,
                        0,
                        60.0,
                        True,
                        False,
                        False,
                        False,
                        True,
                        False,
                    ),
                    (
                        "claude",
                        "claude-private",
                        "ingest-privacy",
                        "claude",
                        "/tmp/claude-private.json",
                        datetime(2026, 3, 21, 11, 0, tzinfo=timezone.utc),
                        date(2026, 3, 21),
                        11,
                        "Sat",
                        "workspace-beta",
                        "claude-opus-4-6",
                        "inferred",
                        "ok",
                        1,
                        1,
                        0,
                        45.0,
                        True,
                        True,
                        False,
                        False,
                        True,
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
                    ("openai", "openai-private", 1000, 500, 1500, 200, 0, 0, 0, 0, 0, "direct"),
                    ("claude", "claude-private", 400, 200, 600, 0, 0, 50, 50, 0, 25, "enriched"),
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
                    ("openai", "openai-private", "snap-private", "token-based", "Direct", "Fresh", 0.005, 0.001, False, None, "[]"),
                    ("claude", "claude-private", "snap-private", "token-and-cache-based", "Approx", "Snapshot", 0.007, 0.0005, False, None, "[\"assumed_missing_cache_write_split_is_5m\"]"),
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
                    ("snap-private", "openai", "gpt-5.4", datetime(2026, 3, 21, 9, 0, tzinfo=timezone.utc), "Fresh", "https://example.com/openai", "USD", 1.0, 0.1, 5.0, None, None, None, None, "[]"),
                    ("snap-private", "anthropic", "claude-opus-4-6", datetime(2026, 3, 21, 9, 0, tzinfo=timezone.utc), "Snapshot", "https://example.com/claude", "USD", 5.0, None, 25.0, 6.25, 10.0, 0.5, None, "[]"),
                ],
            )
        finally:
            connection.close()

    def _read_rendered_snapshot(self, output_dir: Path) -> str:
        parts: list[str] = []
        for path in sorted(output_dir.rglob("*")):
            if path.is_dir():
                continue
            parts.append(path.read_text(encoding="utf-8"))
        return "\n".join(parts)

    def _compat_get_filter_options(self, db, filters, alias_map=None):
        del alias_map
        return ORIGINAL_GET_FILTER_OPTIONS(db, filters)


if __name__ == "__main__":
    unittest.main()
