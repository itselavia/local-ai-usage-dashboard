from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    import duckdb  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - environment dependent
    HAS_DUCKDB = False
else:  # pragma: no cover - environment dependent
    HAS_DUCKDB = True

from dashboard.db import open_database
from dashboard.ingest import run as run_ingest


def _fake_fetch_live_page(url: str, timeout_seconds: int = 20) -> tuple[str | None, str | None]:
    del timeout_seconds

    if url == "https://developers.openai.com/api/docs/pricing":
        return "Pricing overview", None

    if url == "https://developers.openai.com/api/docs/models/gpt-5.4":
        return "Text tokens Per 1M tokens Input $1.25 Cached input $0.125 Output $10", None

    if url == "https://platform.claude.com/docs/en/about-claude/pricing":
        return "Claude Opus 4.6$5 / MTok$6.25 / MTok$10 / MTok$0.50 / MTok$25 / MTok", None

    return None, f"unexpected url: {url}"


@unittest.skipUnless(HAS_DUCKDB, "duckdb is required for ingest tests")
class DashboardIngestTests(unittest.TestCase):
    def test_ingest_writes_sessions_estimates_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            codex_dir = tmp_root / ".codex"
            claude_dir = tmp_root / ".claude"
            db_path = tmp_root / ".dashboard" / "dashboard.duckdb"
            pricing_snapshot_path = tmp_root / ".dashboard" / "pricing_snapshot.json"
            metadata_path = tmp_root / ".dashboard" / "metadata.json"

            self._write_openai_session(codex_dir)
            self._write_claude_session(claude_dir)

            args = SimpleNamespace(
                codex_dir=codex_dir,
                claude_dir=claude_dir,
                timezone="UTC",
                db=db_path,
                include_temp=False,
                anonymize_workspaces=False,
                pricing_mode="fresh",
            )

            with (
                patch("dashboard.ingest.config.default_pricing_snapshot_path", return_value=pricing_snapshot_path),
                patch("dashboard.ingest.config.default_metadata_path", return_value=metadata_path),
                patch("dashboard.estimates.fetch_live_page", side_effect=_fake_fetch_live_page),
            ):
                result = run_ingest(args)

            self.assertEqual(result, 0)
            self.assertTrue(db_path.is_file())
            self.assertTrue(pricing_snapshot_path.is_file())
            self.assertTrue(metadata_path.is_file())

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["providers"], {"claude": 1, "openai": 1})

            connection = open_database(db_path)
            try:
                session_count = connection.execute("SELECT COUNT(*) FROM session_facts").fetchone()[0]
                estimate_count = connection.execute("SELECT COUNT(*) FROM session_estimates").fetchone()[0]
                pricing_count = connection.execute("SELECT COUNT(*) FROM pricing_snapshots").fetchone()[0]
                total_cost = connection.execute(
                    "SELECT ROUND(SUM(estimated_cost_usd), 6) FROM session_estimates WHERE excluded = FALSE"
                ).fetchone()[0]
                provider_costs = connection.execute(
                    """
                    SELECT provider, ROUND(SUM(estimated_cost_usd), 6)
                    FROM session_estimates
                    WHERE excluded = FALSE
                    GROUP BY provider
                    ORDER BY provider
                    """
                ).fetchall()
            finally:
                connection.close()

            self.assertEqual(session_count, 2)
            self.assertEqual(estimate_count, 2)
            self.assertEqual(pricing_count, 2)
            self.assertAlmostEqual(total_cost, 0.01335, places=6)
            self.assertEqual(provider_costs, [("claude", 0.007325), ("openai", 0.006025)])

    def _write_openai_session(self, codex_dir: Path) -> None:
        session_dir = codex_dir / "sessions" / "2026" / "03" / "21"
        session_dir.mkdir(parents=True)
        session_path = session_dir / "openai-session.jsonl"
        session_path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "session_meta",
                            "timestamp": "2026-03-21T10:00:00.000Z",
                            "payload": {
                                "id": "openai-session",
                                "timestamp": "2026-03-21T10:00:00.000Z",
                                "cwd": "/Users/testuser/projects/local-ai-usage-dashboard",
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "turn_context",
                            "timestamp": "2026-03-21T10:00:01.000Z",
                            "payload": {"model": "gpt-5.4"},
                        }
                    ),
                    json.dumps(
                        {
                            "type": "event_msg",
                            "timestamp": "2026-03-21T10:00:02.000Z",
                            "payload": {
                                "type": "token_count",
                                "info": {
                                    "total_token_usage": {
                                        "input_tokens": 1000,
                                        "cached_input_tokens": 200,
                                        "output_tokens": 500,
                                        "reasoning_output_tokens": 300,
                                        "total_tokens": 1500,
                                    }
                                },
                            },
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def _write_claude_session(self, claude_dir: Path) -> None:
        session_meta_dir = claude_dir / "usage-data" / "session-meta"
        project_dir = claude_dir / "projects" / "sample-project"
        session_meta_dir.mkdir(parents=True)
        project_dir.mkdir(parents=True)

        session_id = "claude-session"
        (session_meta_dir / f"{session_id}.json").write_text(
            json.dumps(
                {
                    "session_id": session_id,
                    "start_time": "2026-03-21T11:00:00.000Z",
                    "duration_minutes": 2,
                    "project_path": "/Users/testuser/projects/local-ai-usage-dashboard",
                    "user_message_count": 1,
                    "assistant_message_count": 1,
                    "input_tokens": 475,
                    "output_tokens": 200,
                    "tool_counts": {"Read": 2},
                    "uses_web_search": True,
                }
            ),
            encoding="utf-8",
        )
        (project_dir / f"{session_id}.jsonl").write_text(
            json.dumps(
                {
                    "message": {
                        "model": "claude-opus-4-6",
                        "usage": {
                            "input_tokens": 400,
                            "output_tokens": 200,
                            "cache_creation_input_tokens": 50,
                            "cache_read_input_tokens": 25,
                            "cache_creation": {"ephemeral_5m_input_tokens": 50},
                        },
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
