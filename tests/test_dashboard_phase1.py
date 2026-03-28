from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from dashboard.providers.claude_local import normalize_claude_session, read_claude_session_flags
from usage_report_common import ClaudeSessionRecord


class ClaudeLocalAdapterTests(unittest.TestCase):
    def test_read_claude_session_flags_projects_stable_meta_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "session.json"
            path.write_text(
                json.dumps(
                    {
                        "uses_task_agent": True,
                        "uses_mcp": False,
                        "uses_web_fetch": True,
                        "uses_web_search": False,
                        "tool_counts": {"Read": 4, "Edit": 2},
                        "languages": {"python": 7},
                        "files_modified": ["a.py", "b.py"],
                    }
                ),
                encoding="utf-8",
            )

            flags = read_claude_session_flags(path)

            self.assertTrue(flags["used_tools"])
            self.assertTrue(flags["used_task_agent"])
            self.assertFalse(flags["used_mcp"])
            self.assertTrue(flags["used_web"])
            self.assertTrue(flags["used_edits"])
            self.assertEqual(json.loads(flags["tool_counts_json"]), {"Edit": 2, "Read": 4})
            self.assertEqual(json.loads(flags["languages_json"]), {"python": 7})
            self.assertEqual(json.loads(flags["files_modified_json"]), ["a.py", "b.py"])

    def test_normalize_claude_session_keeps_core_fields_and_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "session.json"
            path.write_text(
                json.dumps(
                    {
                        "uses_task_agent": True,
                        "uses_mcp": True,
                        "uses_web_fetch": False,
                        "uses_web_search": True,
                        "tool_counts": {"Read": 2, "Write": 1},
                        "languages": {"python": 3},
                        "files_modified": ["app.py"],
                    }
                ),
                encoding="utf-8",
            )

            session = ClaudeSessionRecord(
                session_id="session-123",
                path=path,
                timestamp_utc=datetime(2026, 3, 21, 8, 30, tzinfo=timezone.utc),
                timestamp_local=datetime(2026, 3, 21, 8, 30, tzinfo=timezone.utc),
                cwd="/Users/testuser/projects/sample/src",
                model="claude-opus-4-6",
                input_tokens=1200,
                output_tokens=300,
                total_tokens=1500,
                user_messages=2,
                assistant_messages=4,
                duration_s=60.0,
                cache_creation_input_tokens=50,
                cache_read_input_tokens=25,
                cache_creation_ephemeral_5m_input_tokens=10,
                cache_creation_ephemeral_1h_input_tokens=0,
                has_enriched_tokens=True,
                is_partial_parse=False,
            )

            row = normalize_claude_session(session)

            self.assertEqual(row.provider, "claude")
            self.assertEqual(row.session_id, "session-123")
            self.assertEqual(row.source_app, "claude")
            self.assertEqual(row.raw_path, str(path))
            self.assertEqual(row.model, "claude-opus-4-6")
            self.assertEqual(row.model_confidence, "inferred")
            self.assertEqual(row.parse_status, "ok")
            self.assertTrue(row.has_tools)
            self.assertTrue(row.has_web)
            self.assertTrue(row.has_task_agent)
            self.assertTrue(row.has_mcp)
            self.assertTrue(row.has_edits)
            self.assertEqual(row.total_tokens, 1500)
            self.assertEqual(row.cache_creation_input_tokens, 50)
            self.assertEqual(row.cache_read_tokens, 25)
            self.assertEqual(row.cache_creation_5m_tokens, 10)
            self.assertEqual(row.token_coverage, "enriched")


if __name__ == "__main__":
    unittest.main()
