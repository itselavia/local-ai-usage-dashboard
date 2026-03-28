from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from usage_report_common import (
    display_path,
    format_currency,
    format_int,
    format_pct,
    format_tokens,
)


@dataclass(frozen=True, slots=True)
class DashboardFilters:
    provider: str = "all"
    workspace: str | None = None
    include_temp: bool = False
    metric: str = "cost"
    date_from: date | None = None
    date_to: date | None = None
    anonymize: bool = False


def get_overview_context(db, filters: DashboardFilters) -> dict[str, Any]:
    filters = _coerce_filters(filters)
    alias_map = _workspace_alias_map(db) if filters.anonymize else {}
    sessions = _load_filtered_sessions(db, filters)
    trust_banner = get_trust_banner(db, filters, sessions=sessions)
    filter_options = get_filter_options(db, filters, alias_map=alias_map)

    totals = _totals(sessions)
    headline_metrics = _headline_metrics(totals)

    return {
        "filters": filter_options,
        "filter_options": filter_options,
        "trust_banner": trust_banner,
        "headline_metrics": headline_metrics,
        "cost_trend_series": _daily_series(sessions),
        "provider_mix_rows": _group_rows(sessions, key="provider", filters=filters),
        "model_mix_rows": _group_rows(sessions, key="model", filters=filters),
        "work_shape_rows": _work_shape_rows(sessions),
        "workspace_rows": _workspace_rows(sessions, filters, alias_map=alias_map)[:12],
        "empty_state": None if sessions else "No sessions match the current filters.",
    }


def get_workspaces_context(db, filters: DashboardFilters) -> dict[str, Any]:
    filters = _coerce_filters(filters)
    alias_map = _workspace_alias_map(db) if filters.anonymize else {}
    sessions = _load_filtered_sessions(db, filters)
    trust_banner = get_trust_banner(db, filters, sessions=sessions)
    filter_options = get_filter_options(db, filters, alias_map=alias_map)
    workspace_rows = _workspace_rows(sessions, filters, alias_map=alias_map)

    if not workspace_rows:
        return {
            "filters": filter_options,
            "trust_banner": trust_banner,
            "workspace_rows": [],
            "selected_workspace": None,
            "selected_workspace_metrics": [],
            "selected_workspace_trend": [],
            "selected_workspace_model_mix": [],
            "selected_workspace_provider_mix": [],
            "selected_workspace_work_shape": [],
            "empty_state": "No workspaces match the current filters.",
        }

    selected_workspace_id = filters.workspace or workspace_rows[0]["workspace_id"]
    selected_sessions = [session for session in sessions if session["workspace_id"] == selected_workspace_id]
    if not selected_sessions:
        selected_workspace_id = workspace_rows[0]["workspace_id"]
        selected_sessions = [session for session in sessions if session["workspace_id"] == selected_workspace_id]

    selected_workspace = next(
        row for row in workspace_rows if row["workspace_id"] == selected_workspace_id
    )
    for row in workspace_rows:
        row["selected"] = row["workspace_id"] == selected_workspace_id
    selected_totals = _totals(selected_sessions)
    selected_metrics = [
        {
            "label": "Estimated cost",
            "value": selected_totals["estimated_cost_usd"],
            "display_value": format_currency(selected_totals["estimated_cost_usd"]),
            "detail": f'{format_int(selected_totals["sessions"])} sessions',
        },
        {
            "label": "Sessions",
            "value": selected_totals["sessions"],
            "display_value": format_int(selected_totals["sessions"]),
            "detail": f'{format_int(selected_totals["active_days"])} active days',
        },
        {
            "label": "Total tokens",
            "value": selected_totals["total_tokens"],
            "display_value": format_tokens(selected_totals["total_tokens"]),
            "detail": f'{format_tokens(selected_totals["cached_tokens"])} cached',
        },
        {
            "label": "Cache delta",
            "value": selected_totals["estimated_cache_savings_usd"],
            "display_value": format_currency(selected_totals["estimated_cache_savings_usd"]),
            "detail": format_pct(selected_totals["cache_share"]),
        },
    ]

    return {
        "filters": filter_options,
        "filter_options": filter_options,
        "trust_banner": trust_banner,
        "workspace_rows": workspace_rows,
        "selected_workspace": selected_workspace,
        "selected_workspace_metrics": selected_metrics,
        "selected_workspace_trend": _daily_series(selected_sessions),
        "selected_workspace_model_mix": _group_rows(selected_sessions, key="model", filters=filters),
        "selected_workspace_provider_mix": _group_rows(selected_sessions, key="provider", filters=filters),
        "selected_workspace_work_shape": _work_shape_rows(selected_sessions),
        "empty_state": None,
    }


def get_methodology_context(db, filters: DashboardFilters) -> dict[str, Any]:
    filters = _coerce_filters(filters)
    alias_map = _workspace_alias_map(db) if filters.anonymize else {}
    sessions = _load_filtered_sessions(db, filters)
    trust_banner = get_trust_banner(db, filters, sessions=sessions)
    filter_options = get_filter_options(db, filters, alias_map=alias_map)
    latest_ingest = _latest_ingest_run(db)
    db_path = _fetch_database_path(db)
    doctor_summary = get_doctor_summary(
        db,
        {
            "db_path": db_path,
            "codex_dir": latest_ingest["codex_path"] if latest_ingest else "",
            "claude_dir": latest_ingest["claude_path"] if latest_ingest else "",
        },
    )
    if filters.anonymize:
        doctor_summary = _redact_doctor_summary(doctor_summary)

    pricing_summary = _fetch_all(
        db,
        """
        SELECT provider, model, freshness_label, checked_at, source_url
        FROM pricing_snapshots
        ORDER BY provider, model
        """,
    )
    pricing_rows = [
        {
            "provider": _provider_label(row["provider"]),
            "model": row["model"],
            "freshness": row["freshness_label"],
            "freshness_label": row["freshness_label"],
            "checked_at": _format_timestamp(row["checked_at"]),
            "source_url": row["source_url"],
        }
        for row in pricing_summary
    ]

    exclusions = Counter()
    estimate_labels = Counter()
    parse_statuses = Counter()
    token_coverage = Counter()
    unsupported_models = Counter()
    for session in sessions:
        estimate_labels[session["estimate_label"] or "Partial"] += 1
        parse_statuses[session["parse_status"]] += 1
        token_coverage[session["token_coverage"]] += 1
        if session["excluded"]:
            exclusions[session["exclusion_reason"] or "unknown"] += 1
        if session["excluded"] and session["exclusion_reason"] == "unsupported_model":
            unsupported_models[session["model"]] += 1

    coverage_summary = [
        {"label": "Direct", "sessions": estimate_labels["Direct"]},
        {"label": "Approx", "sessions": estimate_labels["Approx"]},
        {"label": "Partial", "sessions": estimate_labels["Partial"]},
        {"label": "Partial parses", "sessions": parse_statuses["partial"]},
        {"label": "Enriched tokens", "sessions": token_coverage["enriched"]},
        {"label": "Meta-only tokens", "sessions": token_coverage["meta"]},
    ]
    for row in coverage_summary:
        row["value"] = format_int(row["sessions"])

    return {
        "filters": filter_options,
        "filter_options": filter_options,
        "trust_banner": trust_banner,
        "pricing_summary": pricing_rows,
        "estimate_rules": _estimate_rules(),
        "coverage_summary": coverage_summary,
        "exclusions_summary": [
            {
                "reason": reason,
                "label": reason.replace("_", " "),
                "sessions": count,
                "value": format_int(count),
            }
            for reason, count in sorted(exclusions.items(), key=lambda item: (-item[1], item[0]))
        ],
        "doctor_summary": doctor_summary,
        "doctor_rows": doctor_summary["rows"],
        "doctor_summary_details": doctor_summary,
        "source_paths": doctor_summary["source_paths"],
        "unsupported_models": [
            {"label": model, "model": model, "count": count, "value": format_int(count)}
            for model, count in sorted(unsupported_models.items(), key=lambda item: (-item[1], item[0]))
        ],
        "empty_state": None if sessions else "No sessions match the current filters.",
    }


def get_trust_banner(
    db,
    filters: DashboardFilters,
    *,
    sessions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    filters = _coerce_filters(filters)
    if sessions is None:
        sessions = _load_filtered_sessions(db, filters)

    if not sessions:
        return {
            "summary": "Pricing freshness and coverage for the current view.",
            "summary_label": "No data",
            "coverage_ratio": 0.0,
            "chips": [],
            "notes": [],
            "coverage_summary": {"coverage_ratio": 0.0},
            "exclusions_summary": {"excluded_sessions": 0},
        }

    estimate_labels = Counter(session["estimate_label"] or "Partial" for session in sessions)
    coverage_ratio = _coverage_ratio(estimate_labels, len(sessions))
    freshness = Counter(
        session["pricing_freshness"]
        for session in sessions
        if not session["excluded"] and session["pricing_freshness"]
    )
    excluded_sessions = sum(1 for session in sessions if session["excluded"])
    partial_parses = sum(1 for session in sessions if session["parse_status"] == "partial")

    notes = []
    if excluded_sessions:
        notes.append(f"{format_int(excluded_sessions)} sessions are excluded from estimated cost.")
    if partial_parses:
        notes.append(f"{format_int(partial_parses)} sessions were recovered from partial parses.")
    if freshness:
        freshness_labels = []
        for freshness_label, count in sorted(freshness.items()):
            freshness_labels.append(freshness_label)
            notes.append(f"{freshness_label}: {format_int(count)} estimated sessions.")
        notes.append(f"Pricing labels in view: {', '.join(freshness_labels)}.")

    chips = [
        {"label": "Direct", "value": format_int(estimate_labels["Direct"])},
        {"label": "Approx", "value": format_int(estimate_labels["Approx"])},
        {"label": "Partial", "value": format_int(estimate_labels["Partial"] + excluded_sessions)},
    ]

    if coverage_ratio >= 0.85:
        summary_label = "High coverage"
    elif coverage_ratio >= 0.5:
        summary_label = "Partial coverage"
    else:
        summary_label = "Low coverage"

    return {
        "summary": "Pricing freshness and coverage for the current view.",
        "summary_label": summary_label,
        "coverage_ratio": coverage_ratio,
        "chips": chips,
        "notes": notes,
        "coverage_summary": {"coverage_ratio": coverage_ratio},
        "exclusions_summary": {"excluded_sessions": excluded_sessions},
    }


def get_filter_options(
    db,
    filters: DashboardFilters,
    *,
    alias_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    filters = _coerce_filters(filters)
    if alias_map is None:
        alias_map = _workspace_alias_map(db) if filters.anonymize else {}
    date_bounds = _fetch_one(
        db,
        """
        SELECT MIN(local_day) AS min_day, MAX(local_day) AS max_day
        FROM session_summary
        """,
    )
    workspace_rows = _fetch_all(
        db,
        """
        SELECT workspace_id, workspace_label, display_workspace_label
        FROM session_summary
        GROUP BY 1, 2, 3
        ORDER BY 3
        """,
    )
    where_sql, params = _where_clause(filters, alias="s")
    model_rows = _fetch_all(
        db,
        f"""
        SELECT model, COUNT(*) AS sessions
        FROM session_summary s
        {where_sql}
        GROUP BY 1
        ORDER BY 2 DESC, 1
        """,
        params,
    )

    provider_options = [
        {"value": "all", "label": "All providers"},
        {"value": "claude", "label": "Claude"},
        {"value": "openai", "label": "Codex / OpenAI"},
    ]
    workspace_options = [
        {"value": "", "label": "All workspaces"},
    ]
    workspace_options.extend([
        {"value": row["workspace_id"], "label": _workspace_display(row, filters, alias_map=alias_map)}
        for row in workspace_rows
    ])
    model_options = [{"value": "all", "label": "All models"}]
    model_options.extend(
        {"value": row["model"], "label": row["model"]}
        for row in model_rows
    )

    return {
        "provider": filters.provider,
        "workspace": filters.workspace,
        "include_temp": filters.include_temp,
        "metric": filters.metric,
        "date_from": filters.date_from.isoformat() if filters.date_from else "",
        "date_to": filters.date_to.isoformat() if filters.date_to else "",
        "anonymize": filters.anonymize,
        "providers": provider_options,
        "provider_options": provider_options,
        "workspaces": workspace_options,
        "workspace_options": workspace_options,
        "model_options": model_options,
        "min_day": date_bounds["min_day"].isoformat() if date_bounds and date_bounds["min_day"] else "",
        "max_day": date_bounds["max_day"].isoformat() if date_bounds and date_bounds["max_day"] else "",
        "metric_options": [
            {"value": "cost", "label": "Cost"},
            {"value": "tokens", "label": "Tokens"},
            {"value": "sessions", "label": "Sessions"},
        ],
    }


def get_doctor_summary(db, context: dict[str, Any] | None = None) -> dict[str, Any]:
    latest_ingest = _latest_ingest_run(db)
    counts = _fetch_one(
        db,
        """
        SELECT
          COUNT(*) AS sessions,
          SUM(CASE WHEN parse_status = 'partial' THEN 1 ELSE 0 END) AS partial_parses,
          SUM(CASE WHEN excluded THEN 1 ELSE 0 END) AS excluded_sessions,
          SUM(CASE WHEN exclusion_reason = 'unsupported_model' THEN 1 ELSE 0 END) AS unsupported_sessions
        FROM session_summary
        """,
    )
    freshness_rows = _fetch_all(
        db,
        """
        SELECT freshness_label AS pricing_freshness, COUNT(*) AS sessions
        FROM pricing_snapshots
        GROUP BY 1
        ORDER BY 2 DESC, 1
        """,
    )
    unsupported_models = _fetch_all(
        db,
        """
        SELECT model, COUNT(*) AS count
        FROM session_summary
        WHERE excluded = TRUE
          AND exclusion_reason = 'unsupported_model'
        GROUP BY 1
        ORDER BY 2 DESC, 1
        """,
    )

    db_path = None
    metadata_path = None
    pricing_path = None
    if context:
        db_path = context.get("db") or context.get("db_path")
        metadata_path = context.get("metadata_path")
        pricing_path = context.get("pricing_snapshot_path")
    if db_path is None:
        db_path = _fetch_database_path(db)
    if metadata_path is None and db_path:
        metadata_path = _guess_metadata_path(db_path)
    if pricing_path is None and db_path:
        pricing_path = _guess_pricing_snapshot_path(db_path)

    source_paths = []
    seen_labels: set[str] = set()
    if db_path:
        source_paths.append(_source_path_row("DuckDB", db_path))
        seen_labels.add("DuckDB")
    if context and (context.get("codex_dir") or context.get("claude_dir")):
        for label, raw_path in (
            ("Codex", context.get("codex_dir")),
            ("Claude", context.get("claude_dir")),
        ):
            if not raw_path:
                continue
            source_paths.append(_source_path_row(label, raw_path))
            seen_labels.add(label)
    elif latest_ingest is not None:
        for label, raw_path in (
            ("Codex", latest_ingest["codex_path"]),
            ("Claude", latest_ingest["claude_path"]),
        ):
            source_paths.append(_source_path_row(label, raw_path))
            seen_labels.add(label)
    if pricing_path:
        source_paths.append(_source_path_row("Pricing snapshot", pricing_path))
        seen_labels.add("Pricing snapshot")
    if metadata_path and "Metadata" not in seen_labels:
        source_paths.append(_source_path_row("Metadata", metadata_path))

    freshness_labels = [row["pricing_freshness"] for row in freshness_rows]
    pricing_state = "Unavailable"
    if freshness_labels:
        pricing_state = freshness_labels[0] if len(set(freshness_labels)) == 1 else "Mixed"

    provider_rows = _fetch_all(
        db,
        """
        SELECT
          provider,
          COUNT(*) AS sessions,
          SUM(CASE WHEN parse_status = 'partial' THEN 1 ELSE 0 END) AS partial_sessions,
          SUM(CASE WHEN exclusion_reason = 'unsupported_model' THEN 1 ELSE 0 END) AS unknown_models
        FROM session_summary
        GROUP BY 1
        ORDER BY provider
        """,
    )

    session_count = counts["sessions"] or 0
    partial_sessions = counts["partial_parses"] or 0
    excluded_sessions = counts["excluded_sessions"] or 0
    unsupported_sessions = counts["unsupported_sessions"] or 0

    return {
        "generated_at": _format_timestamp(datetime.now()),
        "latest_ingest_at": _format_timestamp(latest_ingest["completed_at"]) if latest_ingest else "n/a",
        "session_count": session_count,
        "partial_parses": partial_sessions,
        "excluded_sessions": excluded_sessions,
        "unsupported_sessions": unsupported_sessions,
        "session_counts": {
            "sessions": session_count,
            "partial_sessions": partial_sessions,
            "excluded_sessions": excluded_sessions,
            "unsupported_sessions": unsupported_sessions,
        },
        "pricing_state": pricing_state,
        "pricing_freshness": [
            {"label": row["pricing_freshness"], "value": row["sessions"], "display_value": format_int(row["sessions"])}
            for row in freshness_rows
        ],
        "source_paths": source_paths,
        "db_path": db_path or "",
        "metadata_path": metadata_path,
        "pricing_snapshot_path": pricing_path,
        "unsupported_models": [
            {"model": row["model"], "count": row["count"]}
            for row in unsupported_models
        ],
        "rows": [
            {
                "provider": _provider_label(row["provider"]),
                "sessions": int(row["sessions"] or 0),
                "partial_sessions": int(row["partial_sessions"] or 0),
                "unknown_models": int(row["unknown_models"] or 0),
            }
            for row in provider_rows
        ],
    }


def _load_filtered_sessions(db, filters: DashboardFilters) -> list[dict[str, Any]]:
    where_sql, params = _where_clause(filters, alias="s")
    return _fetch_all(
        db,
        f"""
        SELECT *
        FROM session_summary s
        {where_sql}
        ORDER BY started_at
        """,
        params,
    )


def _where_clause(filters: DashboardFilters, *, alias: str) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if filters.provider != "all":
        clauses.append(f"{alias}.provider = ?")
        params.append(filters.provider)
    if filters.workspace:
        clauses.append(f"{alias}.workspace_id = ?")
        params.append(filters.workspace)
    if not filters.include_temp:
        clauses.append(f"{alias}.is_temp = FALSE")
    if filters.date_from is not None:
        clauses.append(f"{alias}.local_day >= ?")
        params.append(filters.date_from)
    if filters.date_to is not None:
        clauses.append(f"{alias}.local_day <= ?")
        params.append(filters.date_to)

    if not clauses:
        return "", params

    return "WHERE " + " AND ".join(clauses), params


def _totals(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    active_days = {session["local_day"] for session in sessions}
    total_tokens = sum(int(session["total_tokens"] or 0) for session in sessions)
    cached_tokens = sum(
        int(session["cached_input_tokens"] or 0) + int(session["cache_read_tokens"] or 0)
        for session in sessions
    )
    input_tokens = sum(int(session["input_tokens"] or 0) for session in sessions)

    return {
        "sessions": len(sessions),
        "active_days": len(active_days),
        "total_tokens": total_tokens,
        "cached_tokens": cached_tokens,
        "cache_share": cached_tokens / input_tokens if input_tokens else 0,
        "estimated_cost_usd": sum(float(session["estimated_cost_usd"] or 0) for session in sessions),
        "estimated_cache_savings_usd": sum(
            float(session["estimated_cache_savings_usd"] or 0) for session in sessions
        ),
        "excluded_sessions": sum(1 for session in sessions if session["excluded"]),
    }


def _headline_metrics(totals: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "label": "Estimated cost",
            "value": totals["estimated_cost_usd"],
            "display_value": format_currency(totals["estimated_cost_usd"]),
            "detail": f'{format_int(totals["excluded_sessions"])} excluded from estimate',
        },
        {
            "label": "Sessions",
            "value": totals["sessions"],
            "display_value": format_int(totals["sessions"]),
            "detail": f'{format_int(totals["active_days"])} active days',
        },
        {
            "label": "Total Tokens",
            "value": totals["total_tokens"],
            "display_value": format_tokens(totals["total_tokens"]),
            "detail": f'{format_tokens(totals["cached_tokens"])} cached',
        },
        {
            "label": "Cache Delta",
            "value": totals["estimated_cache_savings_usd"],
            "display_value": format_currency(totals["estimated_cache_savings_usd"]),
            "detail": format_pct(totals["cache_share"]),
        },
    ]


def _daily_series(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_day: dict[str, dict[str, Any]] = {}
    for session in sessions:
        day = session["local_day"].isoformat()
        row = by_day.setdefault(
            day,
            {"label": day, "day": day, "cost": 0.0, "tokens": 0, "sessions": 0},
        )
        row["cost"] += float(session["estimated_cost_usd"] or 0)
        row["tokens"] += int(session["total_tokens"] or 0)
        row["sessions"] += 1

    rows = [by_day[key] for key in sorted(by_day)]
    total_cost = sum(float(row["cost"]) for row in rows) or 1.0
    for row in rows:
        row["bar_share"] = float(row["cost"]) / total_cost
        row["cost_label"] = format_currency(row["cost"])
        row["tokens_label"] = format_tokens(row["tokens"])
        row["sessions_label"] = format_int(row["sessions"])
    return rows


def _group_rows(
    sessions: list[dict[str, Any]],
    *,
    key: str,
    filters: DashboardFilters,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for session in sessions:
        group_key = str(session[key] or "(unknown)")
        row = grouped.setdefault(
            group_key,
            {"key": group_key, "label": group_key, "cost": 0.0, "tokens": 0, "sessions": 0},
        )
        row["cost"] += float(session["estimated_cost_usd"] or 0)
        row["tokens"] += int(session["total_tokens"] or 0)
        row["sessions"] += 1

    rows = list(grouped.values())
    for row in rows:
        row["display_label"] = row["label"]
        row["value"] = _metric_value(row, filters.metric)
        row["display_value"] = _metric_display_value(row, filters.metric)

    rows.sort(key=lambda item: (_metric_value(item, filters.metric), item["label"]), reverse=True)
    total_metric = sum(_metric_value(row, filters.metric) for row in rows) or 1
    for row in rows:
        row["share"] = _metric_value(row, filters.metric) / total_metric
        row["bar_share"] = row["share"]
    return rows[:10]


def _work_shape_rows(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    definitions = [
        ("tools", "has_tools"),
        ("web", "has_web"),
        ("edits", "has_edits"),
        ("task_agent", "has_task_agent"),
        ("subagent", "has_subagent"),
        ("mcp", "has_mcp"),
    ]

    rows = []
    total_sessions = len(sessions) or 1
    for label, field in definitions:
        matching = [session for session in sessions if session[field]]
        rows.append(
            {
                "label": label,
                "display_label": label.replace("_", " ").title(),
                "cost": sum(float(session["estimated_cost_usd"] or 0) for session in matching),
                "tokens": sum(int(session["total_tokens"] or 0) for session in matching),
                "sessions": len(matching),
                "share": len(matching) / total_sessions,
            }
        )

    return rows


def _workspace_rows(
    sessions: list[dict[str, Any]],
    filters: DashboardFilters,
    *,
    alias_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    model_counts: dict[str, Counter] = defaultdict(Counter)
    provider_counts: dict[str, Counter] = defaultdict(Counter)

    for session in sessions:
        workspace_id = session["workspace_id"]
        label = _workspace_display(session, filters, alias_map=alias_map)
        row = grouped.setdefault(
            workspace_id,
            {
                "workspace_id": workspace_id,
                "label": label,
                "display_label": label,
                "workspace_label": session["workspace_label"],
                "display_workspace_label": session["display_workspace_label"],
                "repo_name": session["repo_name"],
                "cwd": session["cwd"],
                "is_temp": bool(session["is_temp"]),
                "cost": 0.0,
                "tokens": 0,
                "sessions": 0,
                "cached_tokens": 0,
                "last_active_at": session["started_at"],
                "web_sessions": 0,
                "agent_sessions": 0,
                "edit_sessions": 0,
            },
        )
        row["cost"] += float(session["estimated_cost_usd"] or 0)
        row["tokens"] += int(session["total_tokens"] or 0)
        row["sessions"] += 1
        row["cached_tokens"] += int(session["cached_input_tokens"] or 0) + int(session["cache_read_tokens"] or 0)
        if session["started_at"] > row["last_active_at"]:
            row["last_active_at"] = session["started_at"]
        if session["has_web"]:
            row["web_sessions"] += 1
        if session["has_task_agent"] or session["has_subagent"]:
            row["agent_sessions"] += 1
        if session["has_edits"]:
            row["edit_sessions"] += 1

        model_counts[workspace_id][session["model"]] += int(session["total_tokens"] or 0)
        provider_counts[workspace_id][session["provider"]] += int(session["total_tokens"] or 0)

    rows = list(grouped.values())
    for row in rows:
        row["cache_share"] = row["cached_tokens"] / row["tokens"] if row["tokens"] else 0
        row["dominant_model"] = model_counts[row["workspace_id"]].most_common(1)[0][0]
        dominant_provider = provider_counts[row["workspace_id"]].most_common(1)[0][0]
        row["provider_label"] = _provider_label(dominant_provider)
        row["work_shape"] = _workspace_shape_summary(row)
        row["display_value"] = _metric_value(row, filters.metric)
        row["sessions_label"] = format_int(row["sessions"])
        row["total_tokens_label"] = format_tokens(row["tokens"])
        row["estimated_cost_label"] = format_currency(row["cost"])
        row["last_active_label"] = _format_timestamp(row["last_active_at"])
        row["selected"] = bool(filters.workspace and row["workspace_id"] == filters.workspace)

    rows.sort(key=lambda item: (_metric_value(item, filters.metric), item["label"]), reverse=True)
    return rows


def _workspace_shape_summary(row: dict[str, Any]) -> str:
    tags = []
    if row["agent_sessions"]:
        tags.append("agent")
    if row["web_sessions"]:
        tags.append("web")
    if row["edit_sessions"]:
        tags.append("edits")
    if not tags:
        return "steady"
    return ", ".join(tags)


def _estimate_rules() -> list[dict[str, str]]:
    return [
        {
            "title": "OpenAI / Codex",
            "body": "OpenAI/Codex estimates charge uncached input, cached input, and output tokens against official OpenAI pricing.",
        },
        {
            "title": "Claude",
            "body": "Estimated from base input, cache writes, cache reads, and output tokens against official Anthropic pricing.",
        },
        {
            "title": "Trust labels",
            "body": "Direct means model and token classes are present. Approx means an assumption was required. Partial means the session was excluded or incomplete.",
        },
    ]


def _workspace_display(
    source: dict[str, Any],
    filters: DashboardFilters,
    *,
    alias_map: dict[str, str] | None = None,
) -> str:
    if filters.anonymize:
        workspace_id = str(source.get("workspace_id") or "")
        if alias_map and workspace_id in alias_map:
            return alias_map[workspace_id]
        return _fallback_workspace_alias(str(source.get("workspace_label") or ""))
    return source.get("workspace_label") or source.get("display_workspace_label") or "(unknown)"


def _provider_label(provider: str) -> str:
    if provider in {"openai", "codex"}:
        return "Codex / OpenAI"
    if provider in {"claude", "anthropic"}:
        return "Claude"
    return provider


def _workspace_alias_map(db) -> dict[str, str]:
    rows = _fetch_all(
        db,
        """
        SELECT workspace_id, workspace_label
        FROM session_summary
        GROUP BY 1, 2
        ORDER BY 2, 1
        """,
    )

    aliases: dict[str, str] = {}
    next_index = 1
    for row in rows:
        workspace_id = str(row["workspace_id"] or "")
        workspace_label = str(row["workspace_label"] or "")
        if not workspace_id:
            continue
        if workspace_label == "(unknown)":
            aliases[workspace_id] = "workspace-unknown"
            continue
        aliases[workspace_id] = f"workspace-{next_index:02d}"
        next_index += 1
    return aliases


def _fallback_workspace_alias(workspace_label: str) -> str:
    if not workspace_label or workspace_label == "(unknown)":
        return "workspace-unknown"
    return "workspace-anon"


def _redact_doctor_summary(summary: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(summary)
    redacted["source_paths"] = [
        {
            "label": row["label"],
            "path": _redacted_source_path(str(row["label"])),
            "exists": row["exists"],
        }
        for row in summary.get("source_paths", [])
    ]
    return redacted


def _redacted_source_path(label: str) -> str:
    if label == "Codex":
        return "local Codex directory"
    if label == "Claude":
        return "local Claude directory"
    if label == "DuckDB":
        return "local dashboard database"
    if label == "Metadata":
        return "local metadata file"
    if label == "Pricing snapshot":
        return "local pricing snapshot"
    return "redacted"


def _source_path_row(label: str, raw_path: str | Path) -> dict[str, Any]:
    path = Path(raw_path).expanduser()
    return {
        "label": label,
        "path": display_path(path),
        "exists": path.exists(),
    }


def _metric_value(row: dict[str, Any], metric: str) -> float:
    if metric == "tokens":
        return float(row.get("tokens") or 0)
    if metric == "sessions":
        return float(row.get("sessions") or 0)
    return float(row.get("cost") or 0)


def _metric_display_value(row: dict[str, Any], metric: str) -> str:
    if metric == "tokens":
        return format_tokens(int(row.get("tokens") or 0))
    if metric == "sessions":
        return format_int(int(row.get("sessions") or 0))
    return format_currency(float(row.get("cost") or 0))


def _coverage_ratio(estimate_labels: Counter, session_count: int) -> float:
    if session_count <= 0:
        return 0.0

    weighted = 0.0
    for label, count in estimate_labels.items():
        if label == "Direct":
            weight = 1.0
        elif label == "Approx":
            weight = 0.6
        elif label == "Partial":
            weight = 0.3
        else:
            weight = 0.0
        weighted += weight * count
    return weighted / session_count


def _latest_ingest_run(db) -> dict[str, Any] | None:
    return _fetch_one(
        db,
        """
        SELECT *
        FROM ingest_runs
        ORDER BY started_at DESC
        LIMIT 1
        """,
    )


def _fetch_database_path(db) -> str | None:
    try:
        row = db.execute("PRAGMA database_list").fetchall()
    except Exception:
        return None

    for _, name, path in row:
        if name == "main":
            return path
    return None


def _guess_metadata_path(db_path: str | None) -> str:
    if not db_path:
        return ""
    return str(Path(db_path).with_name("metadata.json"))


def _guess_pricing_snapshot_path(db_path: str | None) -> str:
    if not db_path:
        return ""
    return str(Path(db_path).with_name("pricing_snapshot.json"))


def _fetch_all(db, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    if params is None:
        params = []
    cursor = db.execute(sql, params)
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]


def _fetch_one(db, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> dict[str, Any] | None:
    rows = _fetch_all(db, sql, params)
    if not rows:
        return None
    return rows[0]


def _format_timestamp(value: datetime | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, str):
        return value
    return value.strftime("%Y-%m-%d %H:%M")


def _coerce_filters(filters: DashboardFilters | dict[str, Any] | None) -> DashboardFilters:
    if isinstance(filters, DashboardFilters):
        return filters

    incoming = filters or {}
    return DashboardFilters(
        provider=str(incoming.get("provider") or "all"),
        workspace=_coerce_workspace(incoming.get("workspace")),
        include_temp=_coerce_bool(incoming.get("include_temp"), False),
        metric=str(incoming.get("metric") or "cost"),
        date_from=_coerce_date(incoming.get("from")),
        date_to=_coerce_date(incoming.get("to")),
        anonymize=_coerce_bool(incoming.get("anonymize"), False),
    )


def _coerce_workspace(value: Any) -> str | None:
    if value in (None, "", "all"):
        return None
    return str(value)


def _coerce_bool(value: Any, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


def _coerce_date(value: Any) -> date | None:
    if value in (None, "", "all"):
        return None
    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
