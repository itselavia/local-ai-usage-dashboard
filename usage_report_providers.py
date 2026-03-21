from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, tzinfo
from pathlib import Path

from usage_report_common import (
    ANTHROPIC_BILLING_URL,
    ANTHROPIC_PRICING_URL,
    ClaudeSessionRecord,
    ModelPricing,
    OPENAI_MODEL_PRICING_URLS,
    OPENAI_PRICING_URL,
    UNKNOWN_LABEL,
    SessionRecord,
    build_day_map,
    collapse_html_text,
    current_and_longest_streak,
    display_path,
    fetch_live_page,
    format_duration,
    is_temp_workspace,
    load_pricing_snapshot,
    monthly_projection,
    monthly_projection_value,
    parse_timestamp,
    percentile,
    sum_days,
    write_provider_snapshots,
)


def openai_session_files(codex_dir: Path) -> list[Path]:
    paths = list(codex_dir.glob("sessions/**/*.jsonl"))
    paths.extend(codex_dir.glob("archived_sessions/*.jsonl"))
    return sorted(paths)


def read_openai_session(path: Path, report_tz: tzinfo) -> SessionRecord | None:
    meta = None
    turn_context = None
    first_ts = None
    last_ts = None
    final_usage = None
    user_messages = 0
    assistant_messages = 0
    reasoning_messages = 0

    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            timestamp = parse_timestamp(record.get("timestamp"))
            if timestamp is not None:
                if first_ts is None or timestamp < first_ts:
                    first_ts = timestamp
                if last_ts is None or timestamp > last_ts:
                    last_ts = timestamp

            record_type = record.get("type")
            payload = record.get("payload") or {}

            if record_type == "session_meta":
                meta = payload
                continue
            if record_type == "turn_context":
                turn_context = payload
                continue
            if record_type == "event_msg" and payload.get("type") == "user_message":
                user_messages += 1
                continue
            if record_type == "event_msg" and payload.get("type") == "agent_message":
                assistant_messages += 1
                continue
            if record_type == "response_item" and payload.get("type") == "reasoning":
                reasoning_messages += 1
                continue
            if record_type == "event_msg" and payload.get("type") == "token_count":
                info = payload.get("info") or {}
                usage = info.get("total_token_usage") or info.get("last_token_usage")
                if usage:
                    final_usage = usage

    if meta is None:
        return None

    timestamp_utc = parse_timestamp(meta.get("timestamp"))
    if timestamp_utc is None:
        timestamp_utc = first_ts or last_ts
    if timestamp_utc is None:
        return None

    usage = final_usage or {}
    cwd = meta.get("cwd") or ""

    duration_s = None
    if first_ts is not None and last_ts is not None:
        duration_s = (last_ts - first_ts).total_seconds()

    total_tokens = int(
        usage.get("total_tokens")
        or (usage.get("input_tokens") or 0)
        + (usage.get("output_tokens") or 0)
        + (usage.get("reasoning_output_tokens") or 0)
    )

    return SessionRecord(
        path=path,
        timestamp_utc=timestamp_utc,
        timestamp_local=timestamp_utc.astimezone(report_tz),
        cwd=cwd,
        model=(turn_context or {}).get("model") or UNKNOWN_LABEL,
        input_tokens=int(usage.get("input_tokens") or 0),
        cached_input_tokens=int(usage.get("cached_input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        reasoning_output_tokens=int(usage.get("reasoning_output_tokens") or 0),
        total_tokens=total_tokens,
        user_messages=user_messages,
        assistant_messages=assistant_messages,
        reasoning_messages=reasoning_messages,
        duration_s=duration_s,
        is_temp=is_temp_workspace(cwd),
    )


def discover_openai_sessions(codex_dir: Path, report_tz: tzinfo) -> list[SessionRecord]:
    sessions: list[SessionRecord] = []

    for path in openai_session_files(codex_dir):
        session = read_openai_session(path, report_tz)
        if session is None:
            continue
        sessions.append(session)

    sessions.sort(key=lambda item: item.timestamp_local)
    return sessions


def accumulate_openai_totals(sessions: list[SessionRecord]) -> Counter:
    totals = Counter()

    for session in sessions:
        totals["input_tokens"] += session.input_tokens
        totals["cached_input_tokens"] += session.cached_input_tokens
        totals["output_tokens"] += session.output_tokens
        totals["reasoning_output_tokens"] += session.reasoning_output_tokens
        totals["total_tokens"] += session.total_tokens
        totals["user_messages"] += session.user_messages
        totals["assistant_messages"] += session.assistant_messages
        totals["reasoning_messages"] += session.reasoning_messages

    return totals


def parse_standard_model_rates(page_text: str) -> tuple[float, float, float] | None:
    match = re.search(
        r"Text tokens\s+Per 1M tokens(?:\s+∙\s+Batch API price)?\s+Input\s+\$(\d+(?:\.\d+)?)\s+Cached input\s+\$(\d+(?:\.\d+)?)\s+Output\s+\$(\d+(?:\.\d+)?)",
        page_text,
    )
    if match is None:
        return None

    input_rate, cached_rate, output_rate = match.groups()
    return float(input_rate), float(cached_rate), float(output_rate)


def parse_gpt54_long_context_rates(page_text: str) -> tuple[float, float, float] | None:
    match = re.search(
        r"Flagship models .*? Standard .*? Short context\s+Long context\s+Model\s+Input\s+Cached input\s+Output\s+Input\s+Cached input\s+Output\s+gpt-5\.4\s+\$(\d+(?:\.\d+)?)\s+\$(\d+(?:\.\d+)?)\s+\$(\d+(?:\.\d+)?)\s+\$(\d+(?:\.\d+)?)\s+\$(\d+(?:\.\d+)?)\s+\$(\d+(?:\.\d+)?)",
        page_text,
        flags=re.S,
    )
    if match is None:
        return None

    _, _, _, long_input, long_cached, long_output = match.groups()
    return float(long_input), float(long_cached), float(long_output)


def refresh_openai_pricing(
    focus_sessions: list[SessionRecord],
    report_tz: tzinfo,
    snapshot_path: Path,
) -> dict:
    models_in_use = sorted({session.model for session in focus_sessions if session.total_tokens > 0})
    supported_models = [model for model in models_in_use if model in OPENAI_MODEL_PRICING_URLS]
    unsupported_models = [model for model in models_in_use if model not in OPENAI_MODEL_PRICING_URLS]

    previous_snapshot = load_pricing_snapshot(snapshot_path)
    previous_openai = previous_snapshot.get("providers", {}).get("openai") or {}
    previous_models = previous_openai.get("models") or {}
    pricing_by_model: dict[str, ModelPricing] = {}
    errors: list[str] = []
    warnings: list[str] = []

    # Fetch all pages in parallel. Pre-fetch the main pricing page when gpt-5.4 is
    # in scope because long-context rates only appear there.
    fetch_keys = list(supported_models)
    fetch_urls = [OPENAI_MODEL_PRICING_URLS[m] for m in supported_models]
    include_main = "gpt-5.4" in supported_models
    if include_main:
        fetch_keys.append("__main__")
        fetch_urls.append(OPENAI_PRICING_URL)

    raw_pages: dict[str, tuple[str | None, str | None]] = {}
    if fetch_keys:
        with ThreadPoolExecutor(max_workers=len(fetch_keys)) as executor:
            raw_pages = dict(zip(fetch_keys, executor.map(fetch_live_page, fetch_urls)))

    for model in supported_models:
        raw_page, error = raw_pages.get(model, (None, "not fetched"))
        if error is not None:
            errors.append(f"{model}: {error}")
            continue

        page_text = collapse_html_text(raw_page)
        rates = parse_standard_model_rates(page_text)
        if rates is None:
            errors.append(f"{model}: could not parse standard token pricing (page snippet: {page_text[:120]!r})")
            continue

        input_rate, cached_rate, output_rate = rates
        pricing_by_model[model] = ModelPricing(
            model=model,
            input_per_million=input_rate,
            cached_input_per_million=cached_rate,
            output_per_million=output_rate,
            source_url=OPENAI_MODEL_PRICING_URLS[model],
        )

    if "gpt-5.4" in pricing_by_model and include_main:
        raw_page, error = raw_pages.get("__main__", (None, "not fetched"))
        if error is not None:
            warnings.append(f"gpt-5.4 long-context pricing unavailable: {error}")
        else:
            long_rates = parse_gpt54_long_context_rates(collapse_html_text(raw_page))
            if long_rates is None:
                warnings.append("gpt-5.4 long-context pricing unavailable: could not parse official pricing table")
            else:
                long_input, long_cached, long_output = long_rates
                pricing_by_model["gpt-5.4"] = ModelPricing(
                    model="gpt-5.4",
                    input_per_million=pricing_by_model["gpt-5.4"].input_per_million,
                    cached_input_per_million=pricing_by_model["gpt-5.4"].cached_input_per_million,
                    output_per_million=pricing_by_model["gpt-5.4"].output_per_million,
                    source_url=pricing_by_model["gpt-5.4"].source_url,
                    long_input_per_million=long_input,
                    long_cached_input_per_million=long_cached,
                    long_output_per_million=long_output,
                )

    if unsupported_models:
        errors.append("unsupported models: " + ", ".join(unsupported_models))

    live_ok = not errors and len(pricing_by_model) == len(models_in_use)
    checked_at = datetime.now(report_tz).strftime("%Y-%m-%d %H:%M:%S %Z")

    if not live_ok:
        last_success = previous_openai.get("fetched_at")
        if last_success:
            detail = f"Live refresh failed on this run. Last successful check was {last_success}. Spend is hidden."
        else:
            detail = "Live refresh failed on this run. No prior pricing snapshot is available. Spend is hidden."

        return {
            "available": False,
            "status_label": "Unavailable",
            "status_detail": detail,
            "checked_at": None,
            "changed_models": [],
            "warnings": warnings,
            "errors": errors,
            "snapshot_path": display_path(snapshot_path),
            "source_url": OPENAI_PRICING_URL,
            "models": {},
        }

    snapshot = {
        "fetched_at": checked_at,
        "source_url": OPENAI_PRICING_URL,
        "models": {model: pricing.to_dict() for model, pricing in pricing_by_model.items()},
    }
    changed_models = sorted(
        model for model, values in snapshot["models"].items() if previous_models.get(model) != values
    )
    write_provider_snapshots(snapshot_path, {**previous_snapshot.get("providers", {}), "openai": snapshot})

    if not previous_models:
        status_label = "First check"
        status_detail = "Official OpenAI docs were checked live on this run. No previous snapshot existed."
    elif changed_models:
        status_label = "Changed"
        status_detail = "Official OpenAI docs were checked live on this run. Changed: " + ", ".join(changed_models)
    else:
        status_label = "Unchanged"
        status_detail = "Official OpenAI docs were checked live on this run. Rates match the previous snapshot."

    return {
        "available": True,
        "status_label": status_label,
        "status_detail": status_detail,
        "checked_at": checked_at,
        "changed_models": changed_models,
        "warnings": warnings,
        "errors": [],
        "snapshot_path": display_path(snapshot_path),
        "source_url": OPENAI_PRICING_URL,
        "models": pricing_by_model,
    }


def openai_session_spend(session: SessionRecord, pricing: ModelPricing, use_long_context: bool = False) -> float:
    input_rate = pricing.input_per_million
    cached_rate = pricing.cached_input_per_million
    output_rate = pricing.output_per_million

    if use_long_context and pricing.long_input_per_million is not None:
        input_rate = pricing.long_input_per_million
        cached_rate = pricing.long_cached_input_per_million or cached_rate
        output_rate = pricing.long_output_per_million or output_rate

    uncached_input = max(session.input_tokens - session.cached_input_tokens, 0)
    total = (
        uncached_input * input_rate
        + session.cached_input_tokens * cached_rate
        + session.output_tokens * output_rate
    )
    return total / 1_000_000


def calculate_openai_spend(
    focus_sessions: list[SessionRecord],
    pricing_by_model: dict[str, ModelPricing],
    latest_day,
) -> dict:
    by_day = defaultdict(Counter)
    by_month = defaultdict(Counter)
    by_model = defaultdict(Counter)
    long_context_available = False

    for session in focus_sessions:
        pricing = pricing_by_model.get(session.model)
        if pricing is None:
            continue

        base_cost = openai_session_spend(session, pricing)
        no_cache_cost = (
            session.input_tokens * pricing.input_per_million
            + session.output_tokens * pricing.output_per_million
        ) / 1_000_000
        long_cost = base_cost
        if pricing.long_input_per_million is not None:
            long_cost = openai_session_spend(session, pricing, use_long_context=True)
            long_context_available = True

        day_entry = by_day[session.local_day]
        day_entry["cost"] += base_cost

        month_key = session.timestamp_local.strftime("%Y-%m")
        month_entry = by_month[month_key]
        month_entry["sessions"] += 1
        month_entry["cost"] += base_cost
        month_entry["long_cost"] += long_cost

        model_entry = by_model[session.model]
        model_entry["sessions"] += 1
        model_entry["tokens"] += session.total_tokens
        model_entry["cost"] += base_cost
        model_entry["cache_savings"] += no_cache_cost - base_cost

    total_cost = sum(item["cost"] for item in by_model.values())
    total_long_cost = sum(item["long_cost"] for item in by_month.values()) if long_context_available else None
    total_cache_savings = sum(item["cache_savings"] for item in by_model.values())

    last7 = sum_days(by_day, latest_day - timedelta(days=6), latest_day)
    prev7 = sum_days(by_day, latest_day - timedelta(days=13), latest_day - timedelta(days=7))
    last30 = sum_days(by_day, latest_day - timedelta(days=29), latest_day)

    monthly = []
    for month_key in sorted(by_month):
        month_totals = by_month[month_key]
        projection, daily_rate = monthly_projection_value(month_key, month_totals["cost"], latest_day)
        monthly.append(
            {
                "month": month_key,
                "sessions": month_totals["sessions"],
                "cost": month_totals["cost"],
                "share": month_totals["cost"] / total_cost if total_cost else 0,
                "projection": projection,
                "daily_rate": daily_rate,
                "long_cost": month_totals["long_cost"] if long_context_available else None,
            }
        )

    model_rows = []
    for model, totals in sorted(by_model.items(), key=lambda item: item[1]["cost"], reverse=True):
        token_total = totals["tokens"]
        effective_rate = totals["cost"] / (token_total / 1_000_000) if token_total else None
        model_rows.append(
            {
                "label": model,
                "sessions": totals["sessions"],
                "tokens": token_total,
                "cost": totals["cost"],
                "share": totals["cost"] / total_cost if total_cost else 0,
                "cache_savings": totals["cache_savings"],
                "effective_rate": effective_rate,
            }
        )

    current_month = next((item for item in monthly if item["month"] == latest_day.strftime("%Y-%m")), None)

    return {
        "total_cost": total_cost,
        "total_long_cost": total_long_cost,
        "long_context_delta": (total_long_cost - total_cost) if total_long_cost is not None else None,
        "cache_savings": total_cache_savings,
        "last7_cost": last7["cost"],
        "prev7_cost": prev7["cost"],
        "last30_cost": last30["cost"],
        "monthly": monthly,
        "models": model_rows,
        "current_month": current_month,
        "top_model": model_rows[0] if model_rows else None,
        "long_context_available": long_context_available,
    }


def build_recent_14_days(by_day: dict, latest_day) -> list[dict]:
    recent_14_days = []

    for offset in range(13, -1, -1):
        day = latest_day - timedelta(days=offset)
        totals = by_day.get(day, Counter())
        recent_14_days.append(
            {
                "day": day.isoformat(),
                "tokens": totals.get("total_tokens", 0),
            }
        )

    return recent_14_days


def aggregate_openai(
    all_sessions: list[SessionRecord],
    focus_sessions: list[SessionRecord],
    report_tz: tzinfo,
    include_temp: bool,
    codex_dir: Path,
    pricing_info: dict,
    spend_info: dict | None,
) -> dict:
    latest_day = focus_sessions[-1].local_day

    all_totals = accumulate_openai_totals(all_sessions)
    focus_totals = accumulate_openai_totals(focus_sessions)
    by_day = build_day_map(focus_sessions)

    last7 = sum_days(by_day, latest_day - timedelta(days=6), latest_day)
    prev7 = sum_days(by_day, latest_day - timedelta(days=13), latest_day - timedelta(days=7))
    last30 = sum_days(by_day, latest_day - timedelta(days=29), latest_day)

    streak_current, streak_longest = current_and_longest_streak(by_day.keys(), latest_day)
    recent_14_days = build_recent_14_days(by_day, latest_day)

    by_month = defaultdict(Counter)
    by_model = defaultdict(Counter)
    by_workspace = defaultdict(Counter)
    by_hour = defaultdict(Counter)
    by_weekday = defaultdict(Counter)

    for session in focus_sessions:
        month_key = session.timestamp_local.strftime("%Y-%m")
        by_month[month_key]["sessions"] += 1
        by_month[month_key]["total_tokens"] += session.total_tokens
        by_month[month_key]["input_tokens"] += session.input_tokens
        by_month[month_key]["cached_input_tokens"] += session.cached_input_tokens

        by_model[session.model]["sessions"] += 1
        by_model[session.model]["total_tokens"] += session.total_tokens

        by_workspace[session.workspace]["sessions"] += 1
        by_workspace[session.workspace]["total_tokens"] += session.total_tokens

        by_hour[session.local_hour]["sessions"] += 1
        by_hour[session.local_hour]["total_tokens"] += session.total_tokens

        by_weekday[session.local_weekday]["sessions"] += 1
        by_weekday[session.local_weekday]["total_tokens"] += session.total_tokens

    monthly = []
    for month_key in sorted(by_month):
        month_totals = by_month[month_key]
        projection, daily_rate = monthly_projection(month_key, month_totals["total_tokens"], latest_day)
        monthly.append(
            {
                "month": month_key,
                "sessions": month_totals["sessions"],
                "tokens": month_totals["total_tokens"],
                "share": month_totals["total_tokens"] / focus_totals["total_tokens"] if focus_totals["total_tokens"] else 0,
                "cache_share": month_totals["cached_input_tokens"] / month_totals["input_tokens"] if month_totals["input_tokens"] else 0,
                "projection": projection,
                "daily_rate": daily_rate,
            }
        )

    top_models = []
    for model, totals in sorted(by_model.items(), key=lambda item: item[1]["total_tokens"], reverse=True)[:5]:
        top_models.append(
            {
                "label": model,
                "sessions": totals["sessions"],
                "tokens": totals["total_tokens"],
                "share": totals["total_tokens"] / focus_totals["total_tokens"] if focus_totals["total_tokens"] else 0,
            }
        )

    top_workspaces = []
    for workspace, totals in sorted(by_workspace.items(), key=lambda item: item[1]["total_tokens"], reverse=True)[:5]:
        top_workspaces.append(
            {
                "label": workspace,
                "sessions": totals["sessions"],
                "tokens": totals["total_tokens"],
                "share": totals["total_tokens"] / focus_totals["total_tokens"] if focus_totals["total_tokens"] else 0,
            }
        )

    top_hours = []
    for hour, totals in sorted(by_hour.items(), key=lambda item: item[1]["total_tokens"], reverse=True)[:5]:
        top_hours.append(
            {
                "label": f"{hour:02d}:00",
                "sessions": totals["sessions"],
                "tokens": totals["total_tokens"],
            }
        )

    top_weekdays = []
    for weekday, totals in sorted(by_weekday.items(), key=lambda item: item[1]["total_tokens"], reverse=True):
        top_weekdays.append(
            {
                "label": weekday,
                "sessions": totals["sessions"],
                "tokens": totals["total_tokens"],
            }
        )

    top_days = []
    for day, totals in sorted(by_day.items(), key=lambda item: item[1]["total_tokens"], reverse=True)[:6]:
        top_days.append(
            {
                "day": day.isoformat(),
                "sessions": totals["sessions"],
                "tokens": totals["total_tokens"],
            }
        )

    largest_sessions = []
    for session in sorted(focus_sessions, key=lambda item: item.total_tokens, reverse=True)[:6]:
        largest_sessions.append(
            {
                "start": session.timestamp_local.strftime("%Y-%m-%d %H:%M %Z"),
                "workspace": session.workspace,
                "model": session.model,
                "tokens": session.total_tokens,
                "duration": format_duration(session.duration_s),
            }
        )

    durations = [session.duration_s for session in focus_sessions if session.duration_s is not None]

    temp_sessions = len(all_sessions) - len(focus_sessions)
    temp_tokens = all_totals["total_tokens"] - focus_totals["total_tokens"]
    temp_share = temp_tokens / all_totals["total_tokens"] if all_totals["total_tokens"] else 0
    uncached_input = focus_totals["input_tokens"] - focus_totals["cached_input_tokens"]
    cache_share = focus_totals["cached_input_tokens"] / focus_totals["input_tokens"] if focus_totals["input_tokens"] else 0
    all_in_total = focus_totals["total_tokens"]
    latest_projection = next((item["projection"] for item in monthly if item["month"] == latest_day.strftime("%Y-%m")), None)

    notes = [
        "Source of truth is each session log's final token_count event.",
        "Recorded total uses the log's total_tokens field.",
        "Temp sessions are identified from paths under /tmp, /var/folders, or pytest temp directories.",
        "Spend is shown only when official OpenAI pricing was refreshed live on the current run.",
        "Spend charges uncached input at the input rate, cached input at the cached-input rate, and output at the published output rate.",
        "Reasoning tokens are shown in the local logs but are not billed as a separate line item in this report because the public pricing pages list input and output rates only.",
    ]

    if pricing_info["available"] and pricing_info["warnings"]:
        notes.extend(pricing_info["warnings"])
    if not pricing_info["available"] and pricing_info["errors"]:
        notes.extend("Pricing refresh error: " + error for error in pricing_info["errors"])
    if spend_info and spend_info["long_context_available"]:
        notes.append(
            "The long-context spend scenario assumes every gpt-5.4 session crossed the >272K prompt threshold. Real spend is usually lower unless that was common."
        )

    now = datetime.now(report_tz)
    return {
        "provider_key": "openai",
        "title": "Codex / OpenAI",
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "timezone": now.strftime("%Z"),
        "usage_source_label": "Local Codex session logs",
        "source": display_path(codex_dir),
        "include_temp": include_temp,
        "window_start": focus_sessions[0].timestamp_local.strftime("%Y-%m-%d %H:%M %Z"),
        "window_end": focus_sessions[-1].timestamp_local.strftime("%Y-%m-%d %H:%M %Z"),
        "session_count": len(focus_sessions),
        "temp_session_count": temp_sessions,
        "recorded_total": focus_totals["total_tokens"],
        "all_in_total": all_in_total,
        "input_tokens": focus_totals["input_tokens"],
        "cached_input_tokens": focus_totals["cached_input_tokens"],
        "uncached_input_tokens": uncached_input,
        "cache_share": cache_share,
        "output_tokens": focus_totals["output_tokens"],
        "reasoning_output_tokens": focus_totals["reasoning_output_tokens"],
        "user_messages": focus_totals["user_messages"],
        "assistant_messages": focus_totals["assistant_messages"],
        "reasoning_messages": focus_totals["reasoning_messages"],
        "avg_session_tokens": sum(token_values := [s.total_tokens for s in focus_sessions]) / len(token_values),
        "median_session_tokens": percentile(token_values, 0.5),
        "p90_session_tokens": percentile(token_values, 0.9),
        "avg_duration": (sum(durations) / len(durations)) if durations else None,
        "median_duration": percentile(durations, 0.5),
        "streak_current": streak_current,
        "streak_longest": streak_longest,
        "last7_tokens": last7["total_tokens"],
        "prev7_tokens": prev7["total_tokens"],
        "last7_sessions": last7["sessions"],
        "prev7_sessions": prev7["sessions"],
        "last30_tokens": last30["total_tokens"],
        "last30_sessions": last30["sessions"],
        "last30_share": last30["total_tokens"] / focus_totals["total_tokens"] if focus_totals["total_tokens"] else 0,
        "temp_share": temp_share,
        "recent_14_days": recent_14_days,
        "monthly": monthly,
        "top_models": top_models,
        "top_workspaces": top_workspaces,
        "top_hours": top_hours,
        "top_weekdays": top_weekdays,
        "top_days": top_days,
        "largest_sessions": largest_sessions,
        "pricing": {
            "available": pricing_info["available"],
            "status_label": pricing_info["status_label"],
            "status_detail": pricing_info["status_detail"],
            "checked_at": pricing_info["checked_at"],
            "changed_models": pricing_info["changed_models"],
            "snapshot_path": pricing_info["snapshot_path"],
            "source_url": pricing_info["source_url"],
        },
        "spend": spend_info,
        "notes": notes,
    }


def build_claude_project_index(projects_dir: Path) -> dict[str, Path]:
    project_index: dict[str, Path] = {}

    if not projects_dir.is_dir():
        return project_index

    for path in projects_dir.glob("**/*.jsonl"):
        if path.stem not in project_index:
            project_index[path.stem] = path

    return project_index


def read_claude_session_enrichment(path: Path | None) -> dict:
    enrichment = {
        "model": UNKNOWN_LABEL,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_ephemeral_5m_input_tokens": 0,
        "cache_creation_ephemeral_1h_input_tokens": 0,
    }

    if path is None or not path.is_file():
        return enrichment

    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            message = record.get("message")
            if not isinstance(message, dict):
                continue

            model = message.get("model")
            if isinstance(model, str) and model:
                enrichment["model"] = model

            usage = message.get("usage")
            if not isinstance(usage, dict):
                continue

            enrichment["cache_creation_input_tokens"] += int(usage.get("cache_creation_input_tokens") or 0)
            enrichment["cache_read_input_tokens"] += int(usage.get("cache_read_input_tokens") or 0)

            cache_creation = usage.get("cache_creation") or {}
            if isinstance(cache_creation, dict):
                enrichment["cache_creation_ephemeral_5m_input_tokens"] += int(cache_creation.get("ephemeral_5m_input_tokens") or 0)
                enrichment["cache_creation_ephemeral_1h_input_tokens"] += int(cache_creation.get("ephemeral_1h_input_tokens") or 0)

    return enrichment


def read_claude_session(
    path: Path,
    report_tz: tzinfo,
    project_index: dict[str, Path],
) -> ClaudeSessionRecord | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        return None

    timestamp_utc = parse_timestamp(payload.get("start_time"))
    if timestamp_utc is None:
        return None

    duration_minutes = payload.get("duration_minutes")
    duration_s = None
    if isinstance(duration_minutes, (int, float)):
        duration_s = float(duration_minutes) * 60

    enrichment = read_claude_session_enrichment(project_index.get(session_id))
    cwd = str(payload.get("project_path") or "")

    input_tokens = int(payload.get("input_tokens") or 0)
    output_tokens = int(payload.get("output_tokens") or 0)

    return ClaudeSessionRecord(
        session_id=session_id,
        path=path,
        timestamp_utc=timestamp_utc,
        timestamp_local=timestamp_utc.astimezone(report_tz),
        cwd=cwd,
        model=enrichment["model"],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        user_messages=int(payload.get("user_message_count") or 0),
        assistant_messages=int(payload.get("assistant_message_count") or 0),
        duration_s=duration_s,
        cache_creation_input_tokens=enrichment["cache_creation_input_tokens"],
        cache_read_input_tokens=enrichment["cache_read_input_tokens"],
        cache_creation_ephemeral_5m_input_tokens=enrichment["cache_creation_ephemeral_5m_input_tokens"],
        cache_creation_ephemeral_1h_input_tokens=enrichment["cache_creation_ephemeral_1h_input_tokens"],
    )


def discover_claude_sessions(claude_dir: Path, report_tz: tzinfo) -> list[ClaudeSessionRecord]:
    session_meta_dir = claude_dir / "usage-data" / "session-meta"
    if not session_meta_dir.is_dir():
        return []

    project_index = build_claude_project_index(claude_dir / "projects")
    sessions: list[ClaudeSessionRecord] = []

    for path in sorted(session_meta_dir.glob("*.json")):
        session = read_claude_session(path, report_tz, project_index)
        if session is None:
            continue
        sessions.append(session)

    sessions.sort(key=lambda item: item.timestamp_local)
    return sessions


def refresh_claude_pricing(snapshot_path: Path) -> dict:
    return {
        "available": False,
        "status_label": "Not used",
        "status_detail": "This dashboard does not claim billable Claude dollars in v1. Spend is hidden by design.",
        "checked_at": None,
        "changed_models": [],
        "warnings": [],
        "errors": [],
        "snapshot_path": display_path(snapshot_path),
        "source_url": ANTHROPIC_PRICING_URL,
        "billing_url": ANTHROPIC_BILLING_URL,
        "models": {},
    }


def calculate_claude_spend(*_args, **_kwargs):
    return None


def accumulate_claude_totals(sessions: list[ClaudeSessionRecord]) -> Counter:
    totals = Counter()

    for session in sessions:
        totals["input_tokens"] += session.input_tokens
        totals["output_tokens"] += session.output_tokens
        totals["total_tokens"] += session.total_tokens
        totals["user_messages"] += session.user_messages
        totals["assistant_messages"] += session.assistant_messages
        totals["cache_creation_input_tokens"] += session.cache_creation_input_tokens
        totals["cache_read_input_tokens"] += session.cache_read_input_tokens
        totals["cache_creation_ephemeral_5m_input_tokens"] += session.cache_creation_ephemeral_5m_input_tokens
        totals["cache_creation_ephemeral_1h_input_tokens"] += session.cache_creation_ephemeral_1h_input_tokens

    return totals


def aggregate_claude(
    sessions: list[ClaudeSessionRecord],
    report_tz: tzinfo,
    claude_dir: Path,
    pricing_info: dict,
    spend_info,
) -> dict:
    latest_day = sessions[-1].local_day
    totals = accumulate_claude_totals(sessions)
    by_day = build_day_map(sessions)

    last7 = sum_days(by_day, latest_day - timedelta(days=6), latest_day)
    prev7 = sum_days(by_day, latest_day - timedelta(days=13), latest_day - timedelta(days=7))
    last30 = sum_days(by_day, latest_day - timedelta(days=29), latest_day)

    streak_current, streak_longest = current_and_longest_streak(by_day.keys(), latest_day)
    recent_14_days = build_recent_14_days(by_day, latest_day)

    by_month = defaultdict(Counter)
    by_model = defaultdict(Counter)
    by_workspace = defaultdict(Counter)

    unknown_model_sessions = 0
    cache_observed_sessions = 0

    for session in sessions:
        month_key = session.timestamp_local.strftime("%Y-%m")
        by_month[month_key]["sessions"] += 1
        by_month[month_key]["total_tokens"] += session.total_tokens

        by_model[session.model]["sessions"] += 1
        by_model[session.model]["total_tokens"] += session.total_tokens

        by_workspace[session.workspace]["sessions"] += 1
        by_workspace[session.workspace]["total_tokens"] += session.total_tokens

        if session.model == UNKNOWN_LABEL:
            unknown_model_sessions += 1
        if session.cache_creation_input_tokens or session.cache_read_input_tokens:
            cache_observed_sessions += 1

    monthly = []
    for month_key in sorted(by_month):
        month_totals = by_month[month_key]
        projection, daily_rate = monthly_projection(month_key, month_totals["total_tokens"], latest_day)
        monthly.append(
            {
                "month": month_key,
                "sessions": month_totals["sessions"],
                "tokens": month_totals["total_tokens"],
                "share": month_totals["total_tokens"] / totals["total_tokens"] if totals["total_tokens"] else 0,
                "projection": projection,
                "daily_rate": daily_rate,
            }
        )

    top_models = []
    for model, model_totals in sorted(by_model.items(), key=lambda item: item[1]["total_tokens"], reverse=True)[:5]:
        top_models.append(
            {
                "label": model,
                "sessions": model_totals["sessions"],
                "tokens": model_totals["total_tokens"],
                "share": model_totals["total_tokens"] / totals["total_tokens"] if totals["total_tokens"] else 0,
            }
        )

    top_workspaces = []
    for workspace, workspace_totals in sorted(by_workspace.items(), key=lambda item: item[1]["total_tokens"], reverse=True)[:5]:
        top_workspaces.append(
            {
                "label": workspace,
                "sessions": workspace_totals["sessions"],
                "tokens": workspace_totals["total_tokens"],
                "share": workspace_totals["total_tokens"] / totals["total_tokens"] if totals["total_tokens"] else 0,
            }
        )

    top_days = []
    for day, day_totals in sorted(by_day.items(), key=lambda item: item[1]["total_tokens"], reverse=True)[:6]:
        top_days.append(
            {
                "day": day.isoformat(),
                "sessions": day_totals["sessions"],
                "tokens": day_totals["total_tokens"],
            }
        )

    durations = [session.duration_s for session in sessions if session.duration_s is not None]

    notes = [
        f"Source of truth is JSON under {display_path(claude_dir / 'usage-data' / 'session-meta')}.",
        "Model and cache enrichment come from matching Claude project transcripts under ~/.claude/projects when available.",
        "Spend is unavailable in v1. This dashboard does not claim billable Claude dollars from local usage alone.",
        "Cache token fields are shown only when the matched Claude transcript exposed them.",
    ]

    if unknown_model_sessions:
        notes.append(f"{unknown_model_sessions} sessions did not have a matching Claude transcript with a model name.")
    if cache_observed_sessions == 0:
        notes.append("No Claude cache token fields were observed in the matched transcripts on this run.")

    now = datetime.now(report_tz)
    return {
        "provider_key": "claude",
        "title": "Claude",
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "timezone": now.strftime("%Z"),
        "usage_source_label": "Local Claude session metadata",
        "source": display_path(claude_dir),
        "window_start": sessions[0].timestamp_local.strftime("%Y-%m-%d %H:%M %Z"),
        "window_end": sessions[-1].timestamp_local.strftime("%Y-%m-%d %H:%M %Z"),
        "session_count": len(sessions),
        "recorded_total": totals["total_tokens"],
        "input_tokens": totals["input_tokens"],
        "output_tokens": totals["output_tokens"],
        "cache_creation_input_tokens": totals["cache_creation_input_tokens"],
        "cache_read_input_tokens": totals["cache_read_input_tokens"],
        "cache_creation_ephemeral_5m_input_tokens": totals["cache_creation_ephemeral_5m_input_tokens"],
        "cache_creation_ephemeral_1h_input_tokens": totals["cache_creation_ephemeral_1h_input_tokens"],
        "cache_observed_sessions": cache_observed_sessions,
        "cache_observed": cache_observed_sessions > 0,
        "user_messages": totals["user_messages"],
        "assistant_messages": totals["assistant_messages"],
        "avg_session_tokens": sum(token_values := [s.total_tokens for s in sessions]) / len(token_values),
        "median_session_tokens": percentile(token_values, 0.5),
        "p90_session_tokens": percentile(token_values, 0.9),
        "avg_duration": (sum(durations) / len(durations)) if durations else None,
        "median_duration": percentile(durations, 0.5),
        "streak_current": streak_current,
        "streak_longest": streak_longest,
        "last7_tokens": last7["total_tokens"],
        "prev7_tokens": prev7["total_tokens"],
        "last7_sessions": last7["sessions"],
        "prev7_sessions": prev7["sessions"],
        "last30_tokens": last30["total_tokens"],
        "last30_sessions": last30["sessions"],
        "last30_share": last30["total_tokens"] / totals["total_tokens"] if totals["total_tokens"] else 0,
        "recent_14_days": recent_14_days,
        "monthly": monthly,
        "top_models": top_models,
        "top_workspaces": top_workspaces,
        "top_days": top_days,
        "pricing": {
            "available": pricing_info["available"],
            "status_label": pricing_info["status_label"],
            "status_detail": pricing_info["status_detail"],
            "checked_at": pricing_info["checked_at"],
            "changed_models": pricing_info["changed_models"],
            "snapshot_path": pricing_info["snapshot_path"],
            "source_url": pricing_info["source_url"],
            "billing_url": pricing_info["billing_url"],
        },
        "spend": spend_info,
        "notes": notes,
        "unknown_model_sessions": unknown_model_sessions,
    }
