from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timezone
from pathlib import Path

from dashboard.providers.openai_local import discover_openai_rows, read_openai_row


class OpenAILocalAdapterTests(unittest.TestCase):
    def test_row_preserves_core_token_semantics_and_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_dir = Path(tmpdir) / ".codex"
            session_dir = codex_dir / "sessions" / "2026" / "03" / "21"
            session_dir.mkdir(parents=True)
            session_path = session_dir / "session.jsonl"

            lines = [
                json.dumps({
                    "type": "session_meta",
                    "timestamp": "2026-03-21T10:00:00.000Z",
                    "payload": {
                        "id": "session-123",
                        "timestamp": "2026-03-21T10:00:00.000Z",
                        "cwd": "/Users/testuser/projects/my-project",
                    },
                }),
                json.dumps({
                    "type": "turn_context",
                    "timestamp": "2026-03-21T10:00:01.000Z",
                    "payload": {"model": "gpt-5.4"},
                }),
                json.dumps({
                    "type": "event_msg",
                    "timestamp": "2026-03-21T10:00:02.000Z",
                    "payload": {"type": "user_message"},
                }),
                json.dumps({
                    "type": "event_msg",
                    "timestamp": "2026-03-21T10:00:03.000Z",
                    "payload": {"type": "agent_message"},
                }),
                json.dumps({
                    "type": "response_item",
                    "timestamp": "2026-03-21T10:00:04.000Z",
                    "payload": {"type": "reasoning"},
                }),
                json.dumps({
                    "type": "event_msg",
                    "timestamp": "2026-03-21T10:00:05.000Z",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {
                                "input_tokens": 1000,
                                "cached_input_tokens": 200,
                                "output_tokens": 500,
                                "reasoning_output_tokens": 300,
                                "total_tokens": 1500,
                            },
                        },
                    },
                }),
                json.dumps({
                    "type": "response_item",
                    "timestamp": "2026-03-21T10:00:06.000Z",
                    "payload": {"type": "function_call", "name": "spawn_agent"},
                }),
                json.dumps({
                    "type": "response_item",
                    "timestamp": "2026-03-21T10:00:07.000Z",
                    "payload": {"type": "function_call", "name": "apply_patch"},
                }),
                json.dumps({
                    "type": "response_item",
                    "timestamp": "2026-03-21T10:00:08.000Z",
                    "payload": {"type": "function_call", "name": "mcp__duckduckgo__fetch_content"},
                }),
                json.dumps({
                    "type": "event_msg",
                    "timestamp": "2026-03-21T10:00:09.000Z",
                    "payload": {"type": "task_started"},
                }),
                json.dumps({
                    "type": "event_msg",
                    "timestamp": "2026-03-21T10:00:10.000Z",
                    "payload": {"type": "web_search_call"},
                }),
                "{bad json",
            ]
            session_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            rows = discover_openai_rows(codex_dir, timezone.utc)

            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row.provider, "openai")
            self.assertEqual(row.session_id, "session-123")
            self.assertEqual(row.model, "gpt-5.4")
            self.assertEqual(row.started_at.isoformat(), "2026-03-21T10:00:00+00:00")
            self.assertEqual(row.input_tokens, 1000)
            self.assertEqual(row.cached_input_tokens, 200)
            self.assertEqual(row.output_tokens, 500)
            self.assertEqual(row.reasoning_output_tokens, 300)
            self.assertEqual(row.total_tokens, 1500)
            self.assertEqual(row.user_messages, 1)
            self.assertEqual(row.assistant_messages, 1)
            self.assertEqual(row.reasoning_messages, 1)
            self.assertTrue(row.has_tools)
            self.assertTrue(row.has_web)
            self.assertTrue(row.has_task_agent)
            self.assertTrue(row.has_subagent)
            self.assertTrue(row.has_edits)
            self.assertTrue(row.has_mcp)
            self.assertEqual(row.parse_status, "partial")
            self.assertEqual(row.model_confidence, "exact")
            self.assertEqual(row.token_coverage, "direct")

    def test_missing_session_meta_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_dir = Path(tmpdir) / ".codex"
            session_dir = codex_dir / "sessions" / "2026" / "03" / "21"
            session_dir.mkdir(parents=True)
            session_path = session_dir / "session.jsonl"
            session_path.write_text(
                json.dumps({
                    "type": "event_msg",
                    "timestamp": "2026-03-21T10:00:05.000Z",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {
                                "input_tokens": 10,
                                "cached_input_tokens": 0,
                                "output_tokens": 5,
                                "reasoning_output_tokens": 0,
                                "total_tokens": 15,
                            },
                        },
                    },
                })
                + "\n",
                encoding="utf-8",
            )

            row = read_openai_row(session_path, timezone.utc)

            self.assertIsNone(row)
