from __future__ import annotations

import math
from pathlib import Path

from usage_report_common import (
    display_path,
    escape,
    format_currency,
    format_growth,
    format_int,
    format_pct,
    format_tokens,
)


def render_hbar_chart(
    items: list[dict],
    label_key: str,
    value_key: str,
    format_fn,
    max_val: float,
    label_format_fn=None,
    row_class: str = "",
) -> str:
    if label_format_fn is None:
        label_format_fn = lambda value: value

    rows = []

    for item in items:
        label = str(item.get(label_key, ""))
        display_label = str(label_format_fn(label))
        value = item.get(value_key, 0) or 0
        pct = min(100.0, (value / max_val * 100) if max_val > 0 else 0)
        classes = ["hbar-row"]
        if row_class:
            classes.append(row_class)
        rows.append(
            f'<div class="{" ".join(classes)}">'
            f'<div class="hbar-label" title="{escape(label)}">{escape(display_label)}</div>'
            f'<div class="hbar-track"><div class="hbar-fill" style="width:{pct:.1f}%"></div></div>'
            f'<div class="hbar-value">{escape(format_fn(value))}</div>'
            "</div>"
        )

    return '<div class="hbar-chart">' + "".join(rows) + "</div>"


_MONTH_ABBR = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}


def render_full_series_chart(daily_series: list[dict]) -> str:
    if not daily_series:
        return '<p class="muted-note">No activity data.</p>'

    count = len(daily_series)
    maximum = max((item["tokens"] for item in daily_series), default=0)
    columns = []

    for index, item in enumerate(daily_series):
        tokens = item["tokens"]
        if maximum > 0 and tokens > 0:
            height = max(2, round((tokens / maximum) * 100))
        else:
            height = 0

        date_str = item["day"]
        label = ""
        if index == 0 or date_str[8:10] == "01":
            label = _MONTH_ABBR[int(date_str[5:7])]

        fill_html = ""
        if height:
            fill_html = f'<div class="series-fill" style="height:{height}%"></div>'

        columns.append(
            f'<div class="series-col" title="{escape(f"{date_str}: {format_tokens(tokens)}")}">'
            f'<div class="series-bar">{fill_html}</div>'
            f'<div class="series-label">{escape(label)}</div>'
            "</div>"
        )

    tick_specs = [
        (format_tokens(maximum), "0%", "translateY(0)"),
        (format_tokens(maximum / 2), "50%", "translateY(-50%)"),
        ("0", "100%", "translateY(-100%)"),
    ]
    axis_ticks = "".join(
        f'<div class="axis-tick" style="top:{top};transform:{transform}">{escape(label)}</div>'
        for label, top, transform in tick_specs
    )

    chart_html = (
        f'<div class="full-series-chart" style="grid-template-columns:repeat({count},minmax(0,1fr))">'
        + "".join(columns)
        + "</div>"
    )
    return (
        '<div class="series-shell">'
        f'<div class="series-axis">{axis_ticks}</div>'
        f'<div class="series-plot">{chart_html}</div>'
        "</div>"
    )


def metric_card(title: str, value: str, detail: str) -> str:
    return (
        '<article class="metric-card">'
        f'<div class="metric-title">{escape(title)}</div>'
        f'<div class="metric-value">{escape(value)}</div>'
        f'<div class="metric-detail">{escape(detail)}</div>'
        "</article>"
    )


def panel(title: str, subtitle: str, body: str, full_width: bool = False) -> str:
    classes = ["panel"]
    if full_width:
        classes.append("panel-full")

    return (
        f'<article class="{" ".join(classes)}">'
        '<div class="panel-header">'
        f'<h2 class="panel-title">{escape(title)}</h2>'
        f'<p class="panel-subtitle">{escape(subtitle)}</p>'
        "</div>"
        + body
        + "</article>"
    )


def panel_block(title: str, body: str, subtitle: str = "") -> str:
    subtitle_html = ""
    if subtitle:
        subtitle_html = f'<p class="block-subtitle">{escape(subtitle)}</p>'

    return (
        '<section class="panel-block">'
        f'<div class="block-title">{escape(title)}</div>'
        f"{subtitle_html}"
        + body
        + "</section>"
    )


def render_summary_items(items: list[tuple[str, str]]) -> str:
    rows = "".join(
        '<div class="summary-item">'
        f'<strong>{escape(label)}</strong>'
        f'<span>{escape(value)}</span>'
        "</div>"
        for label, value in items
    )
    return f'<div class="summary-list">{rows}</div>'


def render_spotlight(label: str, value: str, detail: str) -> str:
    return (
        '<div class="spotlight">'
        f'<div class="spotlight-label">{escape(label)}</div>'
        f'<div class="spotlight-value">{escape(value)}</div>'
        f'<div class="spotlight-detail">{escape(detail)}</div>'
        "</div>"
    )


def render_trend_stat(label: str, value: str, detail: str) -> str:
    return (
        '<div class="trend-stat">'
        f'<div class="trend-label">{escape(label)}</div>'
        f'<div class="trend-value">{escape(value)}</div>'
        f'<div class="trend-detail">{escape(detail)}</div>'
        "</div>"
    )


def render_notes(notes: list[str]) -> str:
    if not notes:
        return ""

    items = "".join(f'<li class="note-item">{escape(note)}</li>' for note in notes)
    return (
        '<details class="notes-details">'
        '<summary class="notes-summary">Notes and caveats</summary>'
        f'<ul class="notes-list">{items}</ul>'
        "</details>"
    )


def top_value_item(items: list[dict], value_key: str) -> dict | None:
    if not items:
        return None
    return max(items, key=lambda item: item.get(value_key, 0) or 0)


def compact_path_label(label: str) -> str:
    if label == "(unknown)" or not label.startswith("/"):
        return label

    path = Path(label)

    try:
        relative = path.relative_to(Path.home())
    except ValueError:
        return label

    parts = relative.parts
    if not parts:
        return "~"
    if len(parts) == 1:
        return f"~/{parts[0]}"

    return "~/" + "/".join(parts[-2:])


def render_hero(dashboard: dict, output_path: Path) -> str:
    providers = dashboard["providers"]
    total_recorded = sum(stats["recorded_total"] for stats in providers)
    total_sessions = sum(stats["session_count"] for stats in providers)
    provider_names = ", ".join(stats["title"] for stats in providers)
    codex_filter = "All sessions" if dashboard["include_temp"] else "Non-temp only"
    output_label = dashboard.get("output_label") or display_path(output_path)

    return "\n".join(
        [
            '<section class="hero">',
            "<h1>Local AI Usage</h1>",
            (
                '<p class="hero-lede">'
                f"{format_tokens(total_recorded)} recorded tokens across "
                f"{format_int(total_sessions)} sessions from {escape(provider_names)}."
                "</p>"
            ),
            '<div class="hero-meta">',
            f'<div class="pill">Generated {escape(dashboard["generated_at"])}</div>',
            f'<div class="pill">Codex {escape(codex_filter)}</div>',
            f'<div class="pill">Output {escape(output_label)}</div>',
            "</div>",
            "</section>",
        ]
    )


def render_provider_header(stats: dict, subtitle: str) -> str:
    return (
        f'<section class="provider-header provider-header-{escape(stats["provider_key"])}">'
        f'<div class="eyebrow">{escape(stats["title"])}</div>'
        f'<h2 class="provider-title">{escape(stats["title"])}</h2>'
        f'<p class="provider-subtitle">{escape(subtitle)}</p>'
        '<div class="provider-pills">'
        f'<div class="pill">Window {escape(stats["window_start"])} -> {escape(stats["window_end"])}</div>'
        f'<div class="pill">Source {escape(stats["source"])}</div>'
        "</div>"
        "</section>"
    )


def render_openai_activity_panel(stats: dict) -> str:
    peak_day = stats["top_days"][0] if stats["top_days"] else None
    peak_hour = top_value_item(stats["hour_chart"], "tokens")

    trend_html = (
        '<div class="trend-grid">'
        + render_trend_stat(
            "7d tokens",
            format_tokens(stats["last7_tokens"]),
            f'{format_growth(stats["last7_tokens"], stats["prev7_tokens"])} vs previous 7d',
        )
        + render_trend_stat(
            "7d sessions",
            format_int(stats["last7_sessions"]),
            f'{format_growth(stats["last7_sessions"], stats["prev7_sessions"])} vs previous 7d',
        )
        + render_trend_stat(
            "Peak day",
            format_tokens(peak_day["tokens"]) if peak_day else "n/a",
            peak_day["day"] if peak_day else "No day-level data",
        )
        + render_trend_stat(
            "Peak hour",
            format_tokens(peak_hour["tokens"]) if peak_hour else "n/a",
            peak_hour["label"] if peak_hour else "No hour-level data",
        )
        + "</div>"
    )

    return panel(
        "Activity",
        "Daily recorded tokens across the full local window.",
        render_full_series_chart(stats["daily_series"]) + trend_html,
        full_width=True,
    )


def render_distribution_panel(stats: dict, title: str, subtitle: str) -> str:
    monthly_max = max((item["tokens"] for item in stats["monthly"]), default=0)
    model_max = max((item["tokens"] for item in stats["top_models"]), default=0)
    workspace_max = max((item["tokens"] for item in stats["top_workspaces"]), default=0)

    monthly_items = [
        {
            "label": item["month"],
            "tokens": item["tokens"],
        }
        for item in stats["monthly"]
    ]

    body = "".join(
        [
            panel_block(
                "Monthly volume",
                render_hbar_chart(monthly_items, "label", "tokens", format_tokens, monthly_max),
                "Each month keeps its actual recorded total.",
            ),
            panel_block(
                "Top models",
                render_hbar_chart(stats["top_models"], "label", "tokens", format_tokens, model_max),
                "Where the token volume is landing.",
            ),
            panel_block(
                "Top workspaces",
                render_hbar_chart(
                    stats["top_workspaces"],
                    "label",
                    "tokens",
                    format_tokens,
                    workspace_max,
                    label_format_fn=compact_path_label,
                    row_class="workspace-row",
                ),
                "Projects driving the most local usage.",
            ),
        ]
    )

    return panel(title, subtitle, body)


def render_openai_spend_panel(stats: dict) -> str:
    spend = stats["spend"]

    if spend:
        current_month = spend["current_month"]
        current_month_value = "n/a"
        if current_month and current_month["projection"] is not None:
            current_month_value = (
                f'{format_currency(current_month["cost"])} so far, pacing '
                f'{format_currency(current_month["projection"])}'
            )
        elif current_month:
            current_month_value = f'{format_currency(current_month["cost"])} so far'

        items = [
            ("Total", format_currency(spend["total_cost"])),
            ("Current month", current_month_value),
            ("Last 30 days", format_currency(spend["last30_cost"])),
            ("Cache savings", format_currency(spend["cache_savings"])),
        ]

        spend_chart = panel_block(
            "By model",
            render_hbar_chart(
                spend["models"],
                "label",
                "cost",
                format_currency,
                max((item["cost"] for item in spend["models"]), default=0),
            ),
            "Estimated from the live pricing refresh on this run.",
        )
    else:
        items = [
            ("Spend hidden", "This run could not refresh official pricing."),
            ("Pricing status", stats["pricing"]["status_detail"]),
        ]

        spend_chart = panel_block(
            "By model",
            (
                '<p class="muted-note">'
                "Spend tables are intentionally omitted until pricing can be checked live. "
                "Model spend will appear after a live pricing refresh."
                "</p>"
            ),
            "This dashboard refuses to guess with stale prices.",
        )

    body = render_summary_items(items) + spend_chart

    return panel(
        "Spend",
        "Estimated from live pricing when available.",
        body,
    )


def render_openai_section(stats: dict) -> str:
    spend = stats["spend"]
    spend_value = "Unavailable"
    spend_detail = "Live pricing refresh required"
    if spend:
        spend_value = format_currency(spend["total_cost"])
        if spend["current_month"] and spend["current_month"]["projection"] is not None:
            spend_detail = f'Pacing {format_currency(spend["current_month"]["projection"])} this month'
        elif spend["current_month"]:
            spend_detail = f'{format_currency(spend["current_month"]["cost"])} so far this month'

    cards = [
        metric_card(
            "Recorded",
            format_tokens(stats["recorded_total"]),
            f'All-in {format_tokens(stats["all_in_total"])}',
        ),
        metric_card(
            "Sessions",
            format_int(stats["session_count"]),
            f'{format_int(stats["temp_session_count"])} temp excluded',
        ),
        metric_card(
            "Cache hit",
            format_pct(stats["cache_share"]),
            f'{format_tokens(stats["uncached_input_tokens"])} uncached input',
        ),
        metric_card(
            "Spend",
            spend_value,
            spend_detail,
        ),
    ]

    section_parts = [
        render_provider_header(
            stats,
            "Local Codex session logs.",
        ),
        f'<div class="grid metrics">{"".join(cards)}</div>',
        render_openai_activity_panel(stats),
        '<div class="grid two-up">',
        render_distribution_panel(
            stats,
            "Volume Breakdown",
            "Monthly totals, model mix, and workspace concentration in one place.",
        ),
        render_openai_spend_panel(stats),
        "</div>",
        render_notes(stats["notes"]),
    ]

    return "\n".join(section_parts)


def render_claude_activity_panel(stats: dict) -> str:
    peak_day = stats["top_days"][0] if stats["top_days"] else None
    coverage_share = stats["enriched_token_sessions"] / stats["session_count"] if stats["session_count"] else 0

    trend_html = (
        '<div class="trend-grid">'
        + render_trend_stat(
            "7d tokens",
            format_tokens(stats["last7_tokens"]),
            f'{format_growth(stats["last7_tokens"], stats["prev7_tokens"])} vs previous 7d',
        )
        + render_trend_stat(
            "7d sessions",
            format_int(stats["last7_sessions"]),
            f'{format_growth(stats["last7_sessions"], stats["prev7_sessions"])} vs previous 7d',
        )
        + render_trend_stat(
            "Peak day",
            format_tokens(peak_day["tokens"]) if peak_day else "n/a",
            peak_day["day"] if peak_day else "No day-level data",
        )
        + render_trend_stat(
            "Transcript matched",
            format_pct(coverage_share),
            f'{format_int(stats["enriched_token_sessions"])} of {format_int(stats["session_count"])} sessions',
        )
        + "</div>"
    )

    return panel(
        "Activity",
        "Daily recorded tokens across the observed Claude window.",
        render_full_series_chart(stats["daily_series"]) + trend_html,
        full_width=True,
    )


def render_claude_coverage_panel(stats: dict) -> str:
    coverage_share = stats["enriched_token_sessions"] / stats["session_count"] if stats["session_count"] else 0
    cache_share = stats["cache_observed_sessions"] / stats["session_count"] if stats["session_count"] else 0

    summary_items = [
        (
            "Matched transcripts",
            f'{format_int(stats["enriched_token_sessions"])} sessions used transcript-level API tokens.',
        ),
        (
            "Metadata only",
            f'{format_int(stats["session_count"] - stats["enriched_token_sessions"])} sessions rely on session-meta totals only.',
        ),
        (
            "Unknown model",
            f'{format_int(stats["unknown_model_sessions"])} sessions had no matched transcript with a model name.',
        ),
        (
            "Partial parse",
            f'{format_int(stats["partial_parse_sessions"])} truncated metadata files were recovered by field extraction.',
        ),
        (
            "Cache fields",
            f'{format_int(stats["cache_observed_sessions"])} sessions exposed Claude cache tokens ({format_pct(cache_share)}).',
        ),
        (
            "Spend Unavailable",
            "Claude dollars are intentionally omitted in v1.",
        ),
    ]

    body = (
        render_spotlight(
            "Transcript matched",
            format_pct(coverage_share),
            "Share of sessions upgraded from metadata totals to transcript-level API token data.",
        )
        + render_summary_items(summary_items)
        + '<p class="muted-note" style="margin-top:14px">This dashboard does not claim billable Claude dollars in v1.</p>'
    )

    return panel(
        "Coverage",
        "How much of Claude usage comes from matched transcripts versus metadata only.",
        body,
    )


def render_claude_section(stats: dict) -> str:
    coverage_share = stats["enriched_token_sessions"] / stats["session_count"] if stats["session_count"] else 0

    cards = [
        metric_card(
            "Recorded",
            format_tokens(stats["recorded_total"]),
            f'Input {format_tokens(stats["input_tokens"])} | Output {format_tokens(stats["output_tokens"])}',
        ),
        metric_card(
            "Sessions",
            format_int(stats["session_count"]),
            f'{stats["window_start"]} -> {stats["window_end"]}',
        ),
        metric_card(
            "Cache read",
            format_tokens(stats["cache_read_input_tokens"]) if stats["cache_observed"] else "Unavailable",
            (
                f'{format_tokens(stats["cache_creation_input_tokens"])} cache creation tokens'
                if stats["cache_observed"]
                else "No cache fields observed in matched transcripts"
            ),
        ),
        metric_card(
            "Transcript matched",
            format_pct(coverage_share),
            f'{format_int(stats["enriched_token_sessions"])} of {format_int(stats["session_count"])} sessions',
        ),
    ]

    section_parts = [
        render_provider_header(
            stats,
            "Local Claude session metadata with transcript enrichment when a matching project log exists.",
        ),
        f'<div class="grid metrics">{"".join(cards)}</div>',
        render_claude_activity_panel(stats),
        '<div class="grid two-up">',
        render_distribution_panel(
            stats,
            "Volume Breakdown",
            "Monthly totals, model mix, and workspace concentration without claiming unsupported dollars.",
        ),
        render_claude_coverage_panel(stats),
        "</div>",
        render_notes(stats["notes"]),
    ]

    return "\n".join(section_parts)


def render_page_notes(notes: list[str]) -> str:
    if not notes:
        return ""

    return panel(
        "Page Notes",
        "Whole-report caveats and provider omissions.",
        render_notes(notes),
    )


_CSS = """
:root { --bg:#efe6da; --panel:rgba(255,252,247,.94); --panel-strong:#f8f1e6; --text:#1f1a14; --muted:#64594c; --border:rgba(86,67,44,.14); --accent:#1f6b72; --accent-soft:rgba(31,107,114,.12); --accent-claude:#8b6844; --shadow:0 12px 40px rgba(55,39,25,.08); }
* { box-sizing:border-box; }
body { margin:0; background:radial-gradient(circle at top left, rgba(31,107,114,.18), transparent 28%), radial-gradient(circle at top right, rgba(139,104,68,.14), transparent 24%), linear-gradient(180deg, #f7f1e8 0%, var(--bg) 38%, #f3ecdf 100%); color:var(--text); font-family:"Avenir Next","Segoe UI","Helvetica Neue",sans-serif; font-size:15px; line-height:1.5; }
h1, h2, h3 { font-family:"Iowan Old Style","Palatino Linotype","Book Antiqua",serif; font-weight:600; letter-spacing:-.03em; margin:0; }
p { margin:0; }
code { font-family:"SFMono-Regular",Menlo,Consolas,monospace; font-size:.9em; background:#efe6da; padding:.12rem .34rem; border-radius:4px; }
.page { max-width:1180px; margin:0 auto; padding:30px 20px 72px; }
.hero { border:1px solid var(--border); border-radius:24px; background:linear-gradient(135deg, rgba(255,255,255,.9), rgba(250,245,237,.96)), var(--panel); box-shadow:var(--shadow); padding:26px 28px; }
.eyebrow { color:var(--accent); font-size:.72rem; font-weight:700; letter-spacing:.14em; text-transform:uppercase; margin-bottom:12px; }
.hero h1 { font-size:clamp(2.2rem, 4vw, 3.8rem); line-height:.96; max-width:700px; }
.hero-lede { color:var(--muted); font-size:1rem; line-height:1.65; max-width:760px; margin-top:10px; }
.hero-meta, .provider-pills { display:flex; flex-wrap:wrap; gap:8px; margin-top:18px; }
.pill { padding:7px 12px; border-radius:999px; border:1px solid var(--border); background:rgba(255,250,243,.86); color:var(--muted); font-size:.86rem; }
.metric-card, .panel { border:1px solid var(--border); background:var(--panel); box-shadow:var(--shadow); }
.metric-title, .trend-label, .block-title, .summary-item strong, .spotlight-label { color:var(--muted); font-size:.74rem; font-weight:700; letter-spacing:.09em; text-transform:uppercase; }
.provider-header { margin-top:30px; border:1px solid var(--border); border-radius:22px; background:var(--panel); box-shadow:var(--shadow); padding:22px 24px 20px; }
.provider-header-openai { background:linear-gradient(135deg, rgba(31,107,114,.08), transparent 45%), var(--panel); }
.provider-header-claude { background:linear-gradient(135deg, rgba(139,104,68,.08), transparent 45%), var(--panel); }
.provider-title { font-size:2rem; margin-bottom:6px; }
.provider-subtitle { color:var(--muted); max-width:900px; font-size:.95rem; }
.grid { display:grid; gap:16px; margin-top:16px; }
.metrics { grid-template-columns:repeat(4, minmax(0,1fr)); }
.two-up { grid-template-columns:minmax(0,1.08fr) minmax(0,.92fr); }
.metric-card { border-radius:18px; padding:18px; min-height:118px; }
.metric-value { font-size:1.72rem; line-height:1; margin-top:12px; }
.metric-detail { color:var(--muted); font-size:.9rem; line-height:1.45; margin-top:10px; }
.panel { border-radius:20px; padding:22px; }
.panel-full { grid-column:1 / -1; }
.panel-header { margin-bottom:16px; }
.panel-title { font-size:1.35rem; }
.panel-subtitle { color:var(--muted); font-size:.92rem; line-height:1.55; margin-top:4px; }
.panel-block + .panel-block { margin-top:20px; padding-top:18px; border-top:1px solid var(--border); }
.block-subtitle { color:var(--muted); font-size:.88rem; line-height:1.5; margin:8px 0 12px; }
.spotlight { padding:16px 18px; border:1px solid var(--border); border-radius:16px; background:linear-gradient(135deg, var(--accent-soft), transparent 80%), var(--panel-strong); margin-bottom:16px; }
.spotlight-value { font-size:1.9rem; line-height:1; margin-top:8px; }
.spotlight-detail { color:var(--muted); font-size:.9rem; line-height:1.5; margin-top:8px; }
.summary-list { display:grid; gap:10px; }
.summary-item { display:grid; gap:5px; padding:12px 14px; border:1px solid var(--border); border-radius:14px; background:var(--panel-strong); }
.summary-item span { font-size:.92rem; line-height:1.5; }
.series-shell { display:grid; grid-template-columns:56px 1fr; gap:10px; align-items:start; }
.series-axis { position:relative; height:170px; }
.axis-tick { position:absolute; right:0; color:var(--muted); font-size:.72rem; line-height:1; }
.axis-tick::after { content:""; position:absolute; top:50%; left:calc(100% + 6px); width:8px; border-top:1px solid var(--border); }
.series-plot { min-width:0; }
.full-series-chart { display:grid; gap:2px; align-items:end; height:200px; }
.series-col { display:flex; flex-direction:column; align-items:center; justify-content:flex-end; gap:4px; min-width:0; }
.series-bar { position:relative; width:100%; height:170px; border-radius:6px 6px 0 0; background:#ebdfd0; overflow:hidden; }
.series-fill { position:absolute; inset:auto 0 0; width:100%; background:linear-gradient(180deg, #76a4aa 0%, var(--accent) 100%); }
.series-label { color:var(--muted); font-size:.68rem; font-variant-numeric:tabular-nums; }
.trend-grid { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:10px; margin-top:16px; }
.trend-stat { padding:12px 14px; border:1px solid var(--border); border-radius:14px; background:var(--panel-strong); }
.trend-value { font-size:1.2rem; margin-top:8px; }
.trend-detail { color:var(--muted); font-size:.86rem; line-height:1.45; margin-top:6px; }
.hbar-chart { display:grid; gap:8px; }
.hbar-row { display:grid; grid-template-columns:180px 1fr 86px; gap:10px; align-items:center; }
.hbar-label, .hbar-value { font-size:.86rem; font-variant-numeric:tabular-nums; }
.hbar-label { color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.workspace-row { grid-template-columns:230px 1fr 86px; align-items:start; }
.workspace-row .hbar-label { white-space:normal; overflow:visible; text-overflow:clip; line-height:1.35; }
.hbar-track { height:18px; border-radius:999px; background:#eadfce; overflow:hidden; }
.hbar-fill { height:100%; border-radius:999px; background:linear-gradient(90deg, #8db5ba 0%, var(--accent) 100%); }
.hbar-value { text-align:right; }
.muted-note { color:var(--muted); font-size:.92rem; line-height:1.6; }
.notes-details { margin-top:16px; border:1px solid var(--border); border-radius:16px; background:var(--panel-strong); overflow:hidden; }
.notes-summary { cursor:pointer; padding:12px 16px; color:var(--muted); font-size:.88rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase; list-style:none; }
.notes-summary::-webkit-details-marker { display:none; }
.notes-summary::before { content:"+ "; }
details[open] .notes-summary::before { content:"- "; }
.notes-list { margin:0; padding:4px 18px 16px 32px; display:grid; gap:8px; }
.note-item { color:var(--muted); font-size:.9rem; line-height:1.55; }
@media (max-width:1040px) { .two-up { grid-template-columns:1fr; } .metrics, .trend-grid { grid-template-columns:repeat(2, minmax(0,1fr)); } }
@media (max-width:760px) { .page { padding:16px 12px 48px; } .hero, .provider-header, .panel { padding:18px; } .metrics, .trend-grid { grid-template-columns:1fr; } .series-shell { grid-template-columns:40px 1fr; gap:8px; } .hbar-row, .workspace-row { grid-template-columns:110px 1fr 72px; } .full-series-chart { height:160px; } .series-axis, .series-bar { height:132px; } .hero h1 { font-size:2.5rem; } }
"""


def render_html(dashboard: dict, output_path: Path) -> str:
    page_notes_html = render_page_notes(dashboard["page_notes"])

    body_parts: list[str] = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        "<title>Local AI Usage Dashboard</title>",
        f"<style>{_CSS}</style>",
        "</head>",
        "<body>",
        '<main class="page">',
        render_hero(dashboard, output_path),
    ]

    if dashboard.get("openai") is not None:
        body_parts.append(render_openai_section(dashboard["openai"]))
    if dashboard.get("claude") is not None:
        body_parts.append(render_claude_section(dashboard["claude"]))
    if page_notes_html:
        body_parts.append(page_notes_html)

    body_parts.extend(["</main>", "</body>", "</html>"])
    return "\n".join(body_parts) + "\n"
