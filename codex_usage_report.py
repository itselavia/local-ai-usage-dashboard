#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from usage_report_common import DEFAULT_OUTPUT, PRICING_SNAPSHOT, UNKNOWN_LABEL, display_path, resolve_timezone
from usage_report_providers import (
    aggregate_claude,
    aggregate_openai,
    calculate_claude_spend,
    calculate_openai_spend,
    discover_claude_sessions,
    discover_openai_sessions,
    refresh_claude_pricing,
    refresh_openai_pricing,
)
from usage_report_render import render_html


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a static HTML usage dashboard from local AI session logs.",
    )
    parser.add_argument(
        "--codex-dir",
        default=str(Path.home() / ".codex"),
        help="Path to the Codex home directory. Default: %(default)s",
    )
    parser.add_argument(
        "--claude-dir",
        default=str(Path.home() / ".claude"),
        help="Path to the Claude home directory. Default: %(default)s",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="HTML report path. The file is overwritten on each run. Default: %(default)s",
    )
    parser.add_argument(
        "--timezone",
        default="local",
        help="IANA timezone name like America/Los_Angeles. Default: local system timezone.",
    )
    parser.add_argument(
        "--include-temp",
        action="store_true",
        help="Include temp and pytest workspaces in the main Codex/OpenAI totals.",
    )
    parser.add_argument(
        "--anonymize-workspaces",
        action="store_true",
        help="Replace rendered workspace and repo labels with placeholders like workspace-01.",
    )
    return parser.parse_args()


def build_openai_provider(codex_dir: Path, report_tz, include_temp: bool, snapshot_path: Path) -> tuple[dict | None, str | None]:
    if not codex_dir.is_dir():
        return None, f"Codex / OpenAI omitted: directory not found at {codex_dir}."

    all_sessions = discover_openai_sessions(codex_dir, report_tz)
    if not all_sessions:
        return None, f"Codex / OpenAI omitted: no session logs found under {codex_dir}."

    if include_temp:
        focus_sessions = all_sessions
    else:
        focus_sessions = [session for session in all_sessions if not session.is_temp]

    if not focus_sessions:
        return None, "Codex / OpenAI omitted: no non-temp sessions matched the current filter."

    pricing_info = refresh_openai_pricing(
        focus_sessions=focus_sessions,
        report_tz=report_tz,
        snapshot_path=snapshot_path,
    )

    spend_info = None
    if pricing_info["available"]:
        spend_info = calculate_openai_spend(
            focus_sessions=focus_sessions,
            pricing_by_model=pricing_info["models"],
            latest_day=focus_sessions[-1].local_day,
        )

    stats = aggregate_openai(
        all_sessions=all_sessions,
        focus_sessions=focus_sessions,
        report_tz=report_tz,
        include_temp=include_temp,
        codex_dir=codex_dir,
        pricing_info=pricing_info,
        spend_info=spend_info,
    )
    return stats, None


def build_claude_provider(claude_dir: Path, report_tz, snapshot_path: Path) -> tuple[dict | None, str | None]:
    if not claude_dir.is_dir():
        return None, f"Claude omitted: directory not found at {claude_dir}."

    sessions = discover_claude_sessions(claude_dir, report_tz)
    if not sessions:
        return None, f"Claude omitted: no session metadata found under {claude_dir}."

    pricing_info = refresh_claude_pricing(snapshot_path=snapshot_path)
    spend_info = calculate_claude_spend(sessions=sessions, pricing_info=pricing_info)

    stats = aggregate_claude(
        sessions=sessions,
        report_tz=report_tz,
        claude_dir=claude_dir,
        pricing_info=pricing_info,
        spend_info=spend_info,
    )
    return stats, None


def build_dashboard(
    openai_stats: dict | None,
    claude_stats: dict | None,
    include_temp: bool,
    snapshot_path: Path,
    page_notes: list[str],
    report_tz,
) -> dict:
    providers = []
    if openai_stats is not None:
        providers.append(openai_stats)
    if claude_stats is not None:
        providers.append(claude_stats)

    return {
        "generated_at": datetime.now(report_tz).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "include_temp": include_temp,
        "snapshot_path": display_path(snapshot_path),
        "providers": providers,
        "openai": openai_stats,
        "claude": claude_stats,
        "page_notes": page_notes,
    }


def build_workspace_aliases(provider_stats: list[dict]) -> dict[str, str]:
    labels: set[str] = set()

    for stats in provider_stats:
        for item in stats.get("top_workspaces", []):
            label = item.get("label")
            if label and label != UNKNOWN_LABEL:
                labels.add(label)

        for item in stats.get("largest_sessions", []):
            label = item.get("workspace")
            if label and label != UNKNOWN_LABEL:
                labels.add(label)

    aliases: dict[str, str] = {}
    for index, label in enumerate(sorted(labels), start=1):
        aliases[label] = f"workspace-{index:02d}"

    return aliases


def anonymize_provider_workspaces(stats: dict, aliases: dict[str, str]) -> None:
    for item in stats.get("top_workspaces", []):
        label = item.get("label")
        if label in aliases:
            item["label"] = aliases[label]

    for item in stats.get("largest_sessions", []):
        label = item.get("workspace")
        if label in aliases:
            item["workspace"] = aliases[label]

    notes = stats.setdefault("notes", [])
    notes.append("Workspace labels were anonymized on this run.")


def anonymize_provider_metadata(stats: dict) -> None:
    provider_key = stats.get("provider_key")

    if provider_key == "openai":
        stats["source"] = "local Codex logs"
    elif provider_key == "claude":
        stats["source"] = "local Claude metadata"
    else:
        stats["source"] = "local source"

    sanitized_notes: list[str] = []
    for note in stats.get("notes", []):
        if note == "Temp sessions are identified from paths under /tmp, /var/folders, or pytest temp directories.":
            sanitized_notes.append("Temp sessions are identified from ephemeral and pytest temp directories.")
            continue

        if note.startswith("Source of truth is JSON under "):
            sanitized_notes.append(
                "Source of truth is local Claude session metadata, enriched with API-level token data from matched project transcripts when available."
            )
            continue

        sanitized_notes.append(note)

    stats["notes"] = sanitized_notes


def anonymize_page_notes(page_notes: list[str]) -> list[str]:
    sanitized: list[str] = []

    for note in page_notes:
        if note.startswith("Codex / OpenAI omitted: directory not found at "):
            sanitized.append("Codex / OpenAI omitted: local directory not found.")
            continue

        if note.startswith("Codex / OpenAI omitted: no session logs found under "):
            sanitized.append("Codex / OpenAI omitted: no local session logs found.")
            continue

        if note.startswith("Claude omitted: directory not found at "):
            sanitized.append("Claude omitted: local directory not found.")
            continue

        if note.startswith("Claude omitted: no session metadata found under "):
            sanitized.append("Claude omitted: no local session metadata found.")
            continue

        sanitized.append(note)

    return sanitized


def anonymize_dashboard_workspaces(dashboard: dict) -> None:
    aliases = build_workspace_aliases(dashboard["providers"])
    dashboard["anonymized"] = True
    dashboard["output_label"] = "anonymized report"
    dashboard["snapshot_path"] = "anonymized"
    dashboard["page_notes"] = anonymize_page_notes(dashboard["page_notes"])

    for stats in dashboard["providers"]:
        anonymize_provider_metadata(stats)

    if not aliases:
        dashboard["page_notes"].append("Workspace anonymization was requested, but no workspace labels were present.")
        return

    for stats in dashboard["providers"]:
        anonymize_provider_workspaces(stats, aliases)

    last_alias = f"workspace-{len(aliases):02d}"
    dashboard["page_notes"].append(
        f"Workspace labels were anonymized on this run with placeholders from workspace-01 to {last_alias}."
    )


def main() -> int:
    args = parse_args()

    report_tz = resolve_timezone(args.timezone)
    codex_dir = Path(args.codex_dir).expanduser().resolve()
    claude_dir = Path(args.claude_dir).expanduser().resolve()
    snapshot_path = PRICING_SNAPSHOT

    page_notes: list[str] = []

    openai_stats, openai_note = build_openai_provider(
        codex_dir=codex_dir,
        report_tz=report_tz,
        include_temp=args.include_temp,
        snapshot_path=snapshot_path,
    )
    if openai_note:
        page_notes.append(openai_note)

    claude_stats, claude_note = build_claude_provider(
        claude_dir=claude_dir,
        report_tz=report_tz,
        snapshot_path=snapshot_path,
    )
    if claude_note:
        page_notes.append(claude_note)

    if openai_stats is None and claude_stats is None:
        print("No provider data found. Nothing to render.", file=sys.stderr)
        return 1

    dashboard = build_dashboard(
        openai_stats=openai_stats,
        claude_stats=claude_stats,
        include_temp=args.include_temp,
        snapshot_path=snapshot_path,
        page_notes=page_notes,
        report_tz=report_tz,
    )

    if args.anonymize_workspaces:
        anonymize_dashboard_workspaces(dashboard)

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(dashboard, output_path), encoding="utf-8")

    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
