from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from codex_usage_report import anonymize_dashboard_workspaces
from usage_report_common import (
    SessionRecord,
    load_pricing_snapshot,
    write_provider_snapshots,
)
from usage_report_providers import (
    aggregate_claude,
    aggregate_openai,
    calculate_claude_spend,
    discover_claude_sessions,
    read_claude_session_enrichment,
    read_openai_session,
    refresh_claude_pricing,
    refresh_openai_pricing,
)
from usage_report_render import render_html


class PricingSnapshotTests(unittest.TestCase):
    def test_old_openai_snapshot_reads_as_nested_providers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / ".pricing_snapshot.json"
            snapshot_path.write_text(
                json.dumps(
                    {
                        "fetched_at": "2026-03-20 10:00:00 PDT",
                        "source_url": "https://developers.openai.com/api/docs/pricing",
                        "models": {"gpt-5.4": {"input_per_million": 2.0}},
                    }
                ),
                encoding="utf-8",
            )

            snapshot = load_pricing_snapshot(snapshot_path)

            self.assertIn("providers", snapshot)
            self.assertIn("openai", snapshot["providers"])
            self.assertEqual(snapshot["providers"]["openai"]["fetched_at"], "2026-03-20 10:00:00 PDT")

    def test_new_snapshot_writes_provider_nesting(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / ".pricing_snapshot.json"
            write_provider_snapshots(
                snapshot_path,
                {
                    "openai": {"fetched_at": "2026-03-21 09:00:00 PDT", "models": {}},
                    "anthropic": {"fetched_at": "2026-03-21 09:05:00 PDT", "models": {}},
                },
            )

            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

            self.assertEqual(sorted(payload.keys()), ["providers"])
            self.assertEqual(sorted(payload["providers"].keys()), ["anthropic", "openai"])


class OpenAIFailClosedTests(unittest.TestCase):
    def test_pricing_failure_hides_openai_spend(self) -> None:
        report_tz = timezone.utc
        session = SessionRecord(
            path=Path("/tmp/session.jsonl"),
            timestamp_utc=datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc),
            timestamp_local=datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc),
            cwd="/Users/testuser/projects/my-project",
            model="gpt-5.4",
            input_tokens=1000,
            cached_input_tokens=250,
            output_tokens=500,
            reasoning_output_tokens=50,
            total_tokens=1550,
            user_messages=2,
            assistant_messages=2,
            reasoning_messages=1,
            duration_s=120,
            is_temp=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / ".pricing_snapshot.json"
            with patch("usage_report_providers.fetch_live_page", return_value=(None, "network blocked")):
                pricing_info = refresh_openai_pricing([session], report_tz, snapshot_path)

            self.assertFalse(pricing_info["available"])

            stats = aggregate_openai(
                all_sessions=[session],
                focus_sessions=[session],
                report_tz=report_tz,
                include_temp=False,
                codex_dir=Path("/Users/testuser/.codex"),
                pricing_info=pricing_info,
                spend_info=None,
            )

            html = render_html(
                {
                    "generated_at": "2026-03-21 10:00:00 UTC",
                    "include_temp": False,
                    "snapshot_path": str(snapshot_path),
                    "providers": [stats],
                    "openai": stats,
                    "claude": None,
                    "page_notes": [],
                },
                Path(tmpdir) / "index.html",
            )

            self.assertIn("Spend hidden", html)
            self.assertIn("Spend tables are intentionally omitted", html)
            self.assertNotIn("$", html)


class ClaudeProviderTests(unittest.TestCase):
    def test_claude_session_parsing_uses_meta_and_project_enrichment(self) -> None:
        report_tz = timezone.utc

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / ".claude"
            session_meta_dir = claude_dir / "usage-data" / "session-meta"
            projects_dir = claude_dir / "projects" / "sample-project"
            session_meta_dir.mkdir(parents=True)
            projects_dir.mkdir(parents=True)

            session_id = "session-123"
            (session_meta_dir / f"{session_id}.json").write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "start_time": "2026-03-11T07:00:03.226Z",
                        "duration_minutes": 2,
                        "project_path": "/Users/testuser/projects/my-project",
                        "user_message_count": 6,
                        "assistant_message_count": 14,
                        "input_tokens": 30,
                        "output_tokens": 443,
                    }
                ),
                encoding="utf-8",
            )
            (projects_dir / f"{session_id}.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"message": {}}),
                        json.dumps(
                            {
                                "message": {
                                    "model": "claude-opus-4-6",
                                    "usage": {
                                        "input_tokens": 3,
                                        "cache_creation_input_tokens": 6811,
                                        "cache_read_input_tokens": 90,
                                        "cache_creation": {
                                            "ephemeral_5m_input_tokens": 6800,
                                            "ephemeral_1h_input_tokens": 11,
                                        },
                                        "output_tokens": 11,
                                    },
                                }
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            sessions = discover_claude_sessions(claude_dir, report_tz)

            self.assertEqual(len(sessions), 1)
            session = sessions[0]
            self.assertEqual(session.model, "claude-opus-4-6")
            self.assertEqual(session.cwd, "/Users/testuser/projects/my-project")
            # API-level tokens from enrichment: input=3+6811+90=6904, output=11
            self.assertEqual(session.input_tokens, 6904)
            self.assertEqual(session.output_tokens, 11)
            self.assertEqual(session.total_tokens, 6915)
            self.assertTrue(session.has_enriched_tokens)
            self.assertEqual(session.cache_creation_input_tokens, 6811)
            self.assertEqual(session.cache_read_input_tokens, 90)
            self.assertEqual(session.cache_creation_ephemeral_5m_input_tokens, 6800)
            self.assertEqual(session.cache_creation_ephemeral_1h_input_tokens, 11)
            self.assertEqual(session.user_messages, 6)
            self.assertEqual(session.assistant_messages, 14)
            self.assertEqual(session.duration_s, 120.0)

    def test_claude_render_marks_spend_unavailable(self) -> None:
        report_tz = timezone.utc

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / ".claude"
            session_meta_dir = claude_dir / "usage-data" / "session-meta"
            projects_dir = claude_dir / "projects" / "sample-project"
            session_meta_dir.mkdir(parents=True)
            projects_dir.mkdir(parents=True)

            session_id = "session-456"
            (session_meta_dir / f"{session_id}.json").write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "start_time": "2026-03-11T07:00:03.226Z",
                        "duration_minutes": 1,
                        "project_path": "/Users/testuser/projects/my-project",
                        "user_message_count": 1,
                        "assistant_message_count": 2,
                        "input_tokens": 10,
                        "output_tokens": 20,
                    }
                ),
                encoding="utf-8",
            )
            (projects_dir / f"{session_id}.jsonl").write_text(
                json.dumps(
                    {
                        "message": {
                            "model": "claude-opus-4-6",
                            "usage": {
                                "cache_creation_input_tokens": 5,
                                "cache_read_input_tokens": 0,
                                "cache_creation": {
                                    "ephemeral_5m_input_tokens": 5,
                                    "ephemeral_1h_input_tokens": 0,
                                },
                            },
                        }
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            sessions = discover_claude_sessions(claude_dir, report_tz)
            pricing_info = refresh_claude_pricing(Path(tmpdir) / ".pricing_snapshot.json")
            spend_info = calculate_claude_spend(sessions=sessions, pricing_info=pricing_info)
            stats = aggregate_claude(
                sessions=sessions,
                report_tz=report_tz,
                claude_dir=claude_dir,
                pricing_info=pricing_info,
                spend_info=spend_info,
            )

            html = render_html(
                {
                    "generated_at": "2026-03-21 10:00:00 UTC",
                    "include_temp": False,
                    "snapshot_path": str(Path(tmpdir) / ".pricing_snapshot.json"),
                    "providers": [stats],
                    "openai": None,
                    "claude": stats,
                    "page_notes": [],
                },
                Path(tmpdir) / "index.html",
            )

            self.assertIn("This dashboard does not claim billable Claude dollars in v1", html)
            self.assertIn("Spend Unavailable", html)
            self.assertNotIn("$", html)


class OpenAITotalTokensFallbackTests(unittest.TestCase):
    def test_total_tokens_always_derived_from_input_plus_output(self) -> None:
        """total_tokens is always input + output, regardless of the total_tokens field.

        The total_tokens field in Codex logs can carry a stale offset when a session
        is resumed after an interrupted one. Using input + output directly is always
        correct because reasoning_output_tokens is a subset of output_tokens.
        """
        report_tz = timezone.utc

        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "sessions" / "2026" / "03" / "21"
            session_dir.mkdir(parents=True)
            session_path = session_dir / "test-session.jsonl"

            # total_tokens is inflated by a 258400 carry-over from a prior session,
            # but input + output are accurate.
            lines = [
                json.dumps({
                    "type": "session_meta",
                    "timestamp": "2026-03-21T10:00:00.000Z",
                    "payload": {"id": "test", "timestamp": "2026-03-21T10:00:00.000Z", "cwd": "/tmp/test"},
                }),
                json.dumps({
                    "type": "turn_context",
                    "timestamp": "2026-03-21T10:00:01.000Z",
                    "payload": {"model": "gpt-5.4"},
                }),
                json.dumps({
                    "type": "event_msg",
                    "timestamp": "2026-03-21T10:01:00.000Z",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {
                                "input_tokens": 1000,
                                "cached_input_tokens": 200,
                                "output_tokens": 500,
                                "reasoning_output_tokens": 300,
                                "total_tokens": 1758400,  # inflated by 258400 stale offset
                            },
                        },
                    },
                }),
            ]
            session_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            session = read_openai_session(session_path, report_tz)

            self.assertIsNotNone(session)
            # Correct: input(1000) + output(500) = 1500, ignoring the inflated total_tokens
            self.assertEqual(session.total_tokens, 1500)
            self.assertEqual(session.input_tokens, 1000)
            self.assertEqual(session.output_tokens, 500)
            self.assertEqual(session.reasoning_output_tokens, 300)

    def test_corrupt_final_event_falls_back_to_peak_valid_event(self) -> None:
        """Selects the event with the highest input+output sum, not the last event.

        Corrupt final events zero out input/output while retaining a stale
        total_tokens value. The last valid peak event is always the correct one.
        """
        report_tz = timezone.utc

        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "sessions" / "2026" / "03" / "21"
            session_dir.mkdir(parents=True)
            session_path = session_dir / "test-corrupt-session.jsonl"

            lines = [
                json.dumps({
                    "type": "session_meta",
                    "timestamp": "2026-03-21T10:00:00.000Z",
                    "payload": {"id": "test", "timestamp": "2026-03-21T10:00:00.000Z", "cwd": "/tmp/test"},
                }),
                json.dumps({
                    "type": "turn_context",
                    "timestamp": "2026-03-21T10:00:01.000Z",
                    "payload": {"model": "gpt-5.4"},
                }),
                # Valid peak event
                json.dumps({
                    "type": "event_msg",
                    "timestamp": "2026-03-21T10:01:00.000Z",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {
                                "input_tokens": 50000,
                                "cached_input_tokens": 40000,
                                "output_tokens": 2000,
                                "reasoning_output_tokens": 500,
                                "total_tokens": 52000,
                            },
                        },
                    },
                }),
                # Corrupt final event: zeroed input/output with stale total_tokens
                json.dumps({
                    "type": "event_msg",
                    "timestamp": "2026-03-21T10:02:00.000Z",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {
                                "input_tokens": 0,
                                "cached_input_tokens": 0,
                                "output_tokens": 0,
                                "reasoning_output_tokens": 0,
                                "total_tokens": 258400,
                            },
                        },
                    },
                }),
            ]
            session_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            session = read_openai_session(session_path, report_tz)

            self.assertIsNotNone(session)
            # Should use the valid peak event (50000+2000=52000), not the corrupt last event
            self.assertEqual(session.input_tokens, 50000)
            self.assertEqual(session.cached_input_tokens, 40000)
            self.assertEqual(session.output_tokens, 2000)
            self.assertEqual(session.total_tokens, 52000)


class ClaudeModelAttributionTests(unittest.TestCase):
    def test_enrichment_picks_most_frequent_model(self) -> None:
        """Model attribution should use the most frequent model, not the last one."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "session.jsonl"
            lines = []
            # 5 messages with opus
            for _ in range(5):
                lines.append(json.dumps({"message": {"model": "claude-opus-4-6", "usage": {"input_tokens": 10, "output_tokens": 5}}}))
            # 2 messages with sonnet (last model)
            for _ in range(2):
                lines.append(json.dumps({"message": {"model": "claude-sonnet-4-6", "usage": {"input_tokens": 10, "output_tokens": 5}}}))
            jsonl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            enrichment = read_claude_session_enrichment(jsonl_path)

            # Should pick opus (5 occurrences) not sonnet (2 occurrences, but last)
            self.assertEqual(enrichment["model"], "claude-opus-4-6")

    def test_enrichment_falls_back_to_meta_tokens_without_api_data(self) -> None:
        """When enrichment has only cache fields (no input/output), use session-meta tokens."""
        report_tz = timezone.utc

        with tempfile.TemporaryDirectory() as tmpdir:
            claude_dir = Path(tmpdir) / ".claude"
            session_meta_dir = claude_dir / "usage-data" / "session-meta"
            projects_dir = claude_dir / "projects" / "sample-project"
            session_meta_dir.mkdir(parents=True)
            projects_dir.mkdir(parents=True)

            session_id = "session-fallback"
            (session_meta_dir / f"{session_id}.json").write_text(
                json.dumps({
                    "session_id": session_id,
                    "start_time": "2026-03-11T07:00:00.000Z",
                    "duration_minutes": 1,
                    "project_path": "/Users/testuser/projects/test",
                    "user_message_count": 1,
                    "assistant_message_count": 1,
                    "input_tokens": 500,
                    "output_tokens": 200,
                }),
                encoding="utf-8",
            )
            # Enrichment with cache fields only, no input/output tokens
            (projects_dir / f"{session_id}.jsonl").write_text(
                json.dumps({
                    "message": {
                        "model": "claude-opus-4-6",
                        "usage": {
                            "cache_creation_input_tokens": 100,
                            "cache_read_input_tokens": 50,
                        },
                    }
                }) + "\n",
                encoding="utf-8",
            )

            sessions = discover_claude_sessions(claude_dir, report_tz)

            self.assertEqual(len(sessions), 1)
            session = sessions[0]
            # Should fall back to meta values since enrichment has no input/output tokens
            self.assertEqual(session.input_tokens, 500)
            self.assertEqual(session.output_tokens, 200)
            self.assertEqual(session.total_tokens, 700)
            self.assertFalse(session.has_enriched_tokens)


class WorkspaceAnonymizationTests(unittest.TestCase):
    def test_anonymize_dashboard_workspaces_replaces_rendered_labels(self) -> None:
        dashboard = {
            "generated_at": "2026-03-21 10:00:00 UTC",
            "include_temp": False,
            "snapshot_path": "/tmp/.pricing_snapshot.json",
            "page_notes": [],
            "providers": [
                {
                    "title": "Codex / OpenAI",
                    "top_workspaces": [
                        {"label": "/Users/testuser/private-one", "sessions": 2, "tokens": 100, "share": 1.0}
                    ],
                    "largest_sessions": [
                        {
                            "start": "2026-03-21 10:00 UTC",
                            "workspace": "/Users/testuser/private-one",
                            "model": "gpt-5.4",
                            "tokens": 100,
                            "duration": "1m 00s",
                        }
                    ],
                    "notes": [],
                },
                {
                    "title": "Claude",
                    "top_workspaces": [
                        {"label": "/Users/testuser/private-two", "sessions": 1, "tokens": 50, "share": 1.0},
                        {"label": "/Users/testuser/private-one", "sessions": 1, "tokens": 25, "share": 0.5},
                    ],
                    "notes": [],
                },
            ],
        }

        anonymize_dashboard_workspaces(dashboard)

        self.assertEqual(dashboard["providers"][0]["top_workspaces"][0]["label"], "workspace-01")
        self.assertEqual(dashboard["providers"][0]["largest_sessions"][0]["workspace"], "workspace-01")
        self.assertEqual(dashboard["providers"][1]["top_workspaces"][0]["label"], "workspace-02")
        self.assertEqual(dashboard["providers"][1]["top_workspaces"][1]["label"], "workspace-01")
        self.assertIn("Workspace labels were anonymized on this run.", dashboard["providers"][0]["notes"])
        self.assertIn("Workspace labels were anonymized on this run.", dashboard["providers"][1]["notes"])
        self.assertTrue(dashboard["page_notes"])


if __name__ == "__main__":
    unittest.main()
