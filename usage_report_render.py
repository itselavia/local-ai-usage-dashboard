from __future__ import annotations

from pathlib import Path

from usage_report_common import (
    display_path,
    escape,
    format_currency,
    format_duration,
    format_growth,
    format_int,
    format_pct,
    format_tokens,
)


def render_progress(value: float, label: str = "") -> str:
    pct = max(0.0, min(value * 100.0, 100.0))
    label_html = f"<span>{escape(label)}</span>" if label else ""
    return (
        '<div class="progress">'
        f'<div class="progress-fill" style="width:{pct:.2f}%"></div>'
        f"{label_html}"
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


def chart_day_column(item: dict, maximum: int) -> str:
    height = 10
    if maximum > 0:
        height = max(10, round((item["tokens"] / maximum) * 100))
    label = item["day"][5:]
    tooltip = f'{item["day"]}: {format_tokens(item["tokens"])}'
    return (
        '<div class="day-column">'
        f'<div class="day-bar" title="{escape(tooltip)}">'
        f'<div class="day-bar-fill" style="height:{height}%"></div>'
        "</div>"
        f'<div class="day-label">{escape(label)}</div>'
        "</div>"
    )


def render_table(rows: list[str]) -> str:
    return "<table>" + "".join(rows) + "</table>"


def provider_header(
    stats: dict,
    subtitle: str,
    spend_label: str,
) -> str:
    pricing_label = stats["pricing"]["checked_at"] or stats["pricing"]["status_label"]
    return "\n".join(
        [
            '<section class="panel provider-header-panel">',
            '<div class="panel-header">',
            "<div>",
            f'<div class="eyebrow">{escape(stats["title"])}</div>',
            f'<h2 class="panel-title">{escape(stats["title"])}</h2>',
            f'<p class="panel-subtitle">{escape(subtitle)}</p>',
            "</div>",
            "</div>",
            '<div class="provider-pills">',
            f'<div class="pill">Window {escape(stats["window_start"])} to {escape(stats["window_end"])}</div>',
            f'<div class="pill">Usage {escape(stats["usage_source_label"])}</div>',
            f'<div class="pill">Source {escape(stats["source"])}</div>',
            f'<div class="pill">Pricing {escape(pricing_label)}</div>',
            f'<div class="pill">Spend {escape(spend_label)}</div>',
            "</div>",
            "</section>",
        ]
    )


def render_provider_summary(provider_stats: list[dict]) -> str:
    cards = []

    for stats in provider_stats:
        spend_detail = "Spend visible" if stats.get("spend") else "Spend unavailable"
        pricing_label = stats["pricing"]["checked_at"] or stats["pricing"]["status_label"]
        cards.append(
            metric_card(
                stats["title"],
                format_tokens(stats["recorded_total"]),
                f"{format_int(stats['session_count'])} sessions • Pricing {pricing_label} • {spend_detail}",
            )
        )

    return "\n".join(
        [
            '<section class="panel">',
            '<div class="panel-header">',
            "<div>",
            '<h2 class="panel-title">Providers</h2>',
            '<p class="panel-subtitle">Each provider keeps its own source, pricing status, and spend honesty.</p>',
            "</div>",
            "</div>",
            f'<section class="grid provider-summary">{"".join(cards)}</section>',
            "</section>",
        ]
    )


def render_openai_section(stats: dict) -> str:
    recent_max = max((item["tokens"] for item in stats["recent_14_days"]), default=0)
    monthly_max = max((item["tokens"] for item in stats["monthly"]), default=0)
    model_max = max((item["tokens"] for item in stats["top_models"]), default=0)
    workspace_max = max((item["tokens"] for item in stats["top_workspaces"]), default=0)
    hour_max = max((item["tokens"] for item in stats["top_hours"]), default=0)
    weekday_max = max((item["tokens"] for item in stats["top_weekdays"]), default=0)
    spend = stats["spend"]
    spend_model_max = max((item["cost"] for item in spend["models"]), default=0) if spend else 0

    if spend:
        spend_projection = spend["current_month"]["projection"] if spend["current_month"] else None
        spend_detail = format_currency(spend_projection) + " projected this month" if spend_projection else "Published input/output pricing only"
        spend_cards = [
            metric_card("Est. Spend", format_currency(spend["total_cost"]), spend_detail),
            metric_card("7d Spend", format_currency(spend["last7_cost"]), f"{format_growth(spend['last7_cost'], spend['prev7_cost'])} vs previous 7d"),
            metric_card("Cache Savings", format_currency(spend["cache_savings"]), "Compared to charging all input at the full input rate"),
            metric_card("Pricing", stats["pricing"]["status_label"], stats["pricing"]["status_detail"]),
        ]
    else:
        spend_cards = [
            metric_card("Est. Spend", "Unavailable", "Hidden until official pricing refresh succeeds on this run"),
            metric_card("7d Spend", "Unavailable", "Live pricing is required before dollars are shown"),
            metric_card("Cache Savings", "Unavailable", "This report does not reuse stale pricing for spend"),
            metric_card("Pricing", stats["pricing"]["status_label"], stats["pricing"]["status_detail"]),
        ]

    hero_cards = [
        metric_card("Recorded", format_tokens(stats["recorded_total"]), f"All-in {format_tokens(stats['all_in_total'])}"),
        metric_card("Sessions", format_int(stats["session_count"]), f"{format_int(stats['temp_session_count'])} temp sessions excluded"),
        metric_card("Cache Hit", format_pct(stats["cache_share"]), f"{format_tokens(stats['uncached_input_tokens'])} uncached input"),
        metric_card("7d Tokens", format_tokens(stats["last7_tokens"]), f"{format_growth(stats['last7_tokens'], stats['prev7_tokens'])} vs previous 7d"),
        *spend_cards,
    ]

    monthly_rows = []
    for item in stats["monthly"]:
        note = f"Projected {format_tokens(item['projection'])} at {format_tokens(item['daily_rate'])}/day" if item["projection"] else f"Cache {format_pct(item['cache_share'])}"
        monthly_rows.append(
            "<tr>"
            f"<td>{escape(item['month'])}</td>"
            f"<td>{format_int(item['sessions'])}</td>"
            f"<td>{format_tokens(item['tokens'])}</td>"
            f"<td>{format_pct(item['share'])}</td>"
            f"<td>{render_progress(item['tokens'] / monthly_max if monthly_max else 0)}</td>"
            f"<td>{escape(note)}</td>"
            "</tr>"
        )

    if spend:
        current_month = spend["current_month"]
        if current_month and current_month["projection"] is not None:
            current_month_detail = (
                f"{format_currency(current_month['cost'])} so far, pacing {format_currency(current_month['projection'])}"
            )
        elif current_month:
            current_month_detail = f"{format_currency(current_month['cost'])} so far"
        else:
            current_month_detail = "n/a"

        long_context_detail = "No long-context pricing scenario available"
        if spend["long_context_available"] and spend["total_long_cost"] is not None:
            long_context_detail = (
                f"{format_currency(spend['total_long_cost'])} if every gpt-5.4 session hit long-context pricing"
            )

        spend_summary_items = [
            f'<div class="summary-item"><strong>Total</strong><span>{escape(format_currency(spend["total_cost"]))} based on published input and output rates.</span></div>',
            f'<div class="summary-item"><strong>Last 7 days</strong><span>{escape(format_currency(spend["last7_cost"]))} across your most recent week of non-temp sessions.</span></div>',
            f'<div class="summary-item"><strong>Last 30 days</strong><span>{escape(format_currency(spend["last30_cost"]))} from the latest rolling 30-day window.</span></div>',
            f'<div class="summary-item"><strong>Current month</strong><span>{escape(current_month_detail)}.</span></div>',
            f'<div class="summary-item"><strong>Cache savings</strong><span>{escape(format_currency(spend["cache_savings"]))} saved by cached input pricing.</span></div>',
            f'<div class="summary-item"><strong>Long-context ceiling</strong><span>{escape(long_context_detail)}.</span></div>',
        ]
    else:
        spend_summary_items = [
            '<div class="summary-item"><strong>Spend hidden</strong><span>This run could not refresh official pricing, so the dashboard keeps dollar figures out of the report.</span></div>',
            f'<div class="summary-item"><strong>Pricing status</strong><span>{escape(stats["pricing"]["status_detail"])}</span></div>',
            f'<div class="summary-item"><strong>Snapshot path</strong><span><code>{escape(stats["pricing"]["snapshot_path"])}</code></span></div>',
        ]

    spend_model_rows = []
    if spend:
        for item in spend["models"]:
            spend_model_rows.append(
                "<tr>"
                f"<td><code>{escape(item['label'])}</code></td>"
                f"<td class=\"number\">{format_int(item['sessions'])}</td>"
                f"<td class=\"number\">{format_currency(item['cost'])}</td>"
                f"<td class=\"number\">{format_pct(item['share'])}</td>"
                f"<td class=\"number\">{format_currency(item['cache_savings'])}</td>"
                f"<td>{render_progress(item['cost'] / spend_model_max if spend_model_max else 0)}</td>"
                "</tr>"
            )

    model_rows = []
    for item in stats["top_models"]:
        model_rows.append(
            "<tr>"
            f"<td><code>{escape(item['label'])}</code></td>"
            f"<td>{format_int(item['sessions'])}</td>"
            f"<td>{format_tokens(item['tokens'])}</td>"
            f"<td>{format_pct(item['share'])}</td>"
            f"<td>{render_progress(item['tokens'] / model_max if model_max else 0)}</td>"
            "</tr>"
        )

    workspace_rows = []
    for item in stats["top_workspaces"]:
        workspace_rows.append(
            "<tr>"
            f"<td><code>{escape(item['label'])}</code></td>"
            f"<td>{format_int(item['sessions'])}</td>"
            f"<td>{format_tokens(item['tokens'])}</td>"
            f"<td>{format_pct(item['share'])}</td>"
            f"<td>{render_progress(item['tokens'] / workspace_max if workspace_max else 0)}</td>"
            "</tr>"
        )

    hour_rows = []
    for item in stats["top_hours"]:
        hour_rows.append(
            "<tr>"
            f"<td>{escape(item['label'])}</td>"
            f"<td>{format_int(item['sessions'])}</td>"
            f"<td>{format_tokens(item['tokens'])}</td>"
            f"<td>{render_progress(item['tokens'] / hour_max if hour_max else 0)}</td>"
            "</tr>"
        )

    weekday_rows = []
    for item in stats["top_weekdays"]:
        weekday_rows.append(
            "<tr>"
            f"<td>{escape(item['label'])}</td>"
            f"<td>{format_int(item['sessions'])}</td>"
            f"<td>{format_tokens(item['tokens'])}</td>"
            f"<td>{render_progress(item['tokens'] / weekday_max if weekday_max else 0)}</td>"
            "</tr>"
        )

    top_day_rows = []
    for item in stats["top_days"]:
        top_day_rows.append(
            "<tr>"
            f"<td>{escape(item['day'])}</td>"
            f"<td>{format_int(item['sessions'])}</td>"
            f"<td>{format_tokens(item['tokens'])}</td>"
            "</tr>"
        )

    session_rows = []
    for item in stats["largest_sessions"]:
        session_rows.append(
            "<tr>"
            f"<td>{escape(item['start'])}</td>"
            f"<td><code>{escape(item['workspace'])}</code></td>"
            f"<td><code>{escape(item['model'])}</code></td>"
            f"<td>{format_tokens(item['tokens'])}</td>"
            f"<td>{escape(item['duration'])}</td>"
            "</tr>"
        )

    notes = list(stats["notes"])

    recent_chart = "".join(chart_day_column(item, recent_max) for item in stats["recent_14_days"])

    parts = [
        provider_header(
            stats,
            "Local Codex usage with live-priced spend only. If official docs fail on this run, dollars stay hidden.",
            "Visible" if spend else "Hidden",
        ),
        f'<section class="grid metrics">{"".join(hero_cards)}</section>',
        '<section class="grid two-up">',
        '<article class="panel">',
        '<div class="panel-header">',
        '<div>',
        '<h2 class="panel-title">Trend</h2>',
        '<p class="panel-subtitle">Fourteen days of daily tokens, plus the short-term movement that actually matters.</p>',
        "</div>",
        "</div>",
        f'<div class="day-chart">{recent_chart}</div>',
        '<div class="trend-grid">',
        '<div class="trend-stat"><div class="trend-label">7d tokens</div>'
        f'<div class="trend-value">{escape(format_tokens(stats["last7_tokens"]))}</div>'
        f'<div class="trend-detail">{escape(format_growth(stats["last7_tokens"], stats["prev7_tokens"]))} vs previous 7 days</div></div>',
        '<div class="trend-stat"><div class="trend-label">7d sessions</div>'
        f'<div class="trend-value">{escape(format_int(stats["last7_sessions"]))}</div>'
        f'<div class="trend-detail">{escape(format_growth(stats["last7_sessions"], stats["prev7_sessions"]))} vs previous 7 days</div></div>',
        '<div class="trend-stat"><div class="trend-label">30d footprint</div>'
        f'<div class="trend-value">{escape(format_tokens(stats["last30_tokens"]))}</div>'
        f'<div class="trend-detail">{escape(format_pct(stats["last30_share"]))} of lifetime non-temp usage</div></div>',
        '<div class="trend-stat"><div class="trend-label">Temp share</div>'
        f'<div class="trend-value">{escape(format_pct(stats["temp_share"]))}</div>'
        f'<div class="trend-detail">{escape(format_int(stats["temp_session_count"]))} temp sessions excluded</div></div>',
        "</div>",
        "</article>",
        '<article class="panel">',
        '<div class="panel-header">',
        '<div>',
        '<h2 class="panel-title">Highlights</h2>',
        '<p class="panel-subtitle">Short reads, not a wall of explanation.</p>',
        "</div>",
        "</div>",
        '<div class="summary-list">',
        f'<div class="summary-item"><strong>Messages</strong><span>{escape(format_int(stats["user_messages"]))} user, {escape(format_int(stats["assistant_messages"]))} assistant, {escape(format_int(stats["reasoning_messages"]))} reasoning summaries.</span></div>',
        f'<div class="summary-item"><strong>Per session</strong><span>{escape(format_tokens(stats["avg_session_tokens"]))} average, {escape(format_tokens(stats["median_session_tokens"]))} median, {escape(format_tokens(stats["p90_session_tokens"]))} p90.</span></div>',
        f'<div class="summary-item"><strong>Session duration</strong><span>{escape(format_duration(stats["avg_duration"]))} average, {escape(format_duration(stats["median_duration"]))} median.</span></div>',
        f'<div class="summary-item"><strong>Peak day</strong><span>{escape(stats["top_days"][0]["day"])} at {escape(format_tokens(stats["top_days"][0]["tokens"]))}.</span></div>',
        f'<div class="summary-item"><strong>Top model</strong><span><code>{escape(stats["top_models"][0]["label"])}</code> at {escape(format_tokens(stats["top_models"][0]["tokens"]))}, {escape(format_pct(stats["top_models"][0]["share"]))} of total usage.</span></div>',
        f'<div class="summary-item"><strong>Top workspace</strong><span><code>{escape(stats["top_workspaces"][0]["label"])}</code> at {escape(format_tokens(stats["top_workspaces"][0]["tokens"]))} across {escape(format_int(stats["top_workspaces"][0]["sessions"]))} sessions.</span></div>',
        "</div>",
        "</article>",
        "</section>",
        '<section class="grid two-up">',
        '<article class="panel">',
        '<div class="panel-header">',
        '<div>',
        '<h2 class="panel-title">Spend</h2>',
        '<p class="panel-subtitle">Live-priced only. If the official docs were not reachable on this run, dollars stay hidden.</p>',
        "</div>",
        "</div>",
        '<div class="summary-list">',
        "".join(spend_summary_items),
        "</div>",
        "</article>",
        '<article class="panel">',
        '<div class="panel-header">',
        '<div>',
        '<h2 class="panel-title">Model Spend</h2>',
        '<p class="panel-subtitle">Estimated cost by model using the latest verified pricing snapshot.</p>',
        "</div>",
        "</div>",
        (
            render_table(
                [
                    "<thead><tr><th>Model</th><th class=\"number\">Sessions</th><th class=\"number\">Spend</th><th class=\"number\">Share</th><th class=\"number\">Cache Saved</th><th>Shape</th></tr></thead>",
                    f"<tbody>{''.join(spend_model_rows)}</tbody>",
                ]
            )
            if spend
            else '<div class="note">Spend tables are intentionally omitted until pricing can be checked live again.</div>'
        ),
        "</article>",
        "</section>",
        '<section class="grid two-up">',
        '<article class="panel">',
        '<div class="panel-header"><div><h2 class="panel-title">Monthly</h2><p class="panel-subtitle">Month-over-month volume with projection for the current month.</p></div></div>',
        render_table(
            [
                "<thead><tr><th>Month</th><th class=\"number\">Sessions</th><th class=\"number\">Tokens</th><th class=\"number\">Share</th><th>Shape</th><th>Note</th></tr></thead>",
                f"<tbody>{''.join(monthly_rows)}</tbody>",
            ]
        ),
        "</article>",
        '<article class="panel">',
        '<div class="panel-header"><div><h2 class="panel-title">Model Mix</h2><p class="panel-subtitle">Where the token volume is actually landing.</p></div></div>',
        render_table(
            [
                "<thead><tr><th>Model</th><th class=\"number\">Sessions</th><th class=\"number\">Tokens</th><th class=\"number\">Share</th><th>Shape</th></tr></thead>",
                f"<tbody>{''.join(model_rows)}</tbody>",
            ]
        ),
        "</article>",
        "</section>",
        '<section class="grid two-up">',
        '<article class="panel">',
        '<div class="panel-header"><div><h2 class="panel-title">Workspace Mix</h2><p class="panel-subtitle">The few workspaces dominating your spend and attention.</p></div></div>',
        render_table(
            [
                "<thead><tr><th>Workspace</th><th class=\"number\">Sessions</th><th class=\"number\">Tokens</th><th class=\"number\">Share</th><th>Shape</th></tr></thead>",
                f"<tbody>{''.join(workspace_rows)}</tbody>",
            ]
        ),
        "</article>",
        '<article class="panel">',
        '<div class="panel-header"><div><h2 class="panel-title">Timing</h2><p class="panel-subtitle">Top hours and weekdays by total token volume.</p></div></div>',
        '<div class="grid" style="grid-template-columns: 1fr; gap: 16px; margin-top: 0;">',
        render_table(
            [
                "<thead><tr><th>Hour</th><th class=\"number\">Sessions</th><th class=\"number\">Tokens</th><th>Shape</th></tr></thead>",
                f"<tbody>{''.join(hour_rows)}</tbody>",
            ]
        ),
        render_table(
            [
                "<thead><tr><th>Day</th><th class=\"number\">Sessions</th><th class=\"number\">Tokens</th><th>Shape</th></tr></thead>",
                f"<tbody>{''.join(weekday_rows)}</tbody>",
            ]
        ),
        "</div>",
        "</article>",
        "</section>",
        '<section class="grid two-up">',
        '<article class="panel">',
        '<div class="panel-header"><div><h2 class="panel-title">Top Days</h2><p class="panel-subtitle">Single-day spikes worth remembering.</p></div></div>',
        render_table(
            [
                "<thead><tr><th>Day</th><th class=\"number\">Sessions</th><th class=\"number\">Tokens</th></tr></thead>",
                f"<tbody>{''.join(top_day_rows)}</tbody>",
            ]
        ),
        "</article>",
        '<article class="panel">',
        '<div class="panel-header"><div><h2 class="panel-title">Largest Sessions</h2><p class="panel-subtitle">The few sessions doing disproportionate work.</p></div></div>',
        render_table(
            [
                "<thead><tr><th>Start</th><th>Workspace</th><th>Model</th><th class=\"number\">Tokens</th><th class=\"number\">Duration</th></tr></thead>",
                f"<tbody>{''.join(session_rows)}</tbody>",
            ]
        ),
        "</article>",
        "</section>",
        '<section class="panel">',
        '<div class="panel-header"><div><h2 class="panel-title">Notes</h2><p class="panel-subtitle">A few precise caveats so the numbers stay honest.</p></div></div>',
        '<div class="notes">',
        "".join(f'<div class="note">{escape(note)}</div>' for note in notes),
        "</div>",
        "</section>",
    ]

    return "\n".join(parts)


def render_claude_section(stats: dict) -> str:
    recent_max = max((item["tokens"] for item in stats["recent_14_days"]), default=0)
    model_max = max((item["tokens"] for item in stats["top_models"]), default=0)
    workspace_max = max((item["tokens"] for item in stats["top_workspaces"]), default=0)
    recent_chart = "".join(chart_day_column(item, recent_max) for item in stats["recent_14_days"])

    cache_value = "Unavailable"
    cache_detail = "No Claude cache fields were observed in matched transcripts"
    if stats["cache_observed"]:
        cache_value = format_tokens(stats["cache_read_input_tokens"])
        cache_detail = f"{format_tokens(stats['cache_creation_input_tokens'])} cache creation tokens observed"

    hero_cards = [
        metric_card("Recorded", format_tokens(stats["recorded_total"]), f"Input {format_tokens(stats['input_tokens'])} • Output {format_tokens(stats['output_tokens'])}"),
        metric_card("Sessions", format_int(stats["session_count"]), f"{stats['window_start']} to {stats['window_end']}"),
        metric_card("Cache Read", cache_value, cache_detail),
        metric_card("Spend", "Unavailable", "This dashboard does not claim billable Claude dollars in v1"),
    ]

    model_rows = []
    for item in stats["top_models"]:
        model_rows.append(
            "<tr>"
            f"<td><code>{escape(item['label'])}</code></td>"
            f"<td class=\"number\">{format_int(item['sessions'])}</td>"
            f"<td class=\"number\">{format_tokens(item['tokens'])}</td>"
            f"<td class=\"number\">{format_pct(item['share'])}</td>"
            f"<td>{render_progress(item['tokens'] / model_max if model_max else 0)}</td>"
            "</tr>"
        )

    workspace_rows = []
    for item in stats["top_workspaces"]:
        workspace_rows.append(
            "<tr>"
            f"<td><code>{escape(item['label'])}</code></td>"
            f"<td class=\"number\">{format_int(item['sessions'])}</td>"
            f"<td class=\"number\">{format_tokens(item['tokens'])}</td>"
            f"<td class=\"number\">{format_pct(item['share'])}</td>"
            f"<td>{render_progress(item['tokens'] / workspace_max if workspace_max else 0)}</td>"
            "</tr>"
        )

    parts = [
        provider_header(
            stats,
            "Local Claude usage from your machine. Spend is intentionally hidden until billing semantics are trustworthy.",
            "Unavailable",
        ),
        f'<section class="grid metrics">{"".join(hero_cards)}</section>',
        '<section class="grid two-up">',
        '<article class="panel">',
        '<div class="panel-header">',
        '<div>',
        '<h2 class="panel-title">Recent Activity</h2>',
        '<p class="panel-subtitle">Fourteen days of recorded Claude tokens, with short-term movement kept simple.</p>',
        "</div>",
        "</div>",
        f'<div class="day-chart">{recent_chart}</div>',
        '<div class="trend-grid">',
        '<div class="trend-stat"><div class="trend-label">7d tokens</div>'
        f'<div class="trend-value">{escape(format_tokens(stats["last7_tokens"]))}</div>'
        f'<div class="trend-detail">{escape(format_growth(stats["last7_tokens"], stats["prev7_tokens"]))} vs previous 7 days</div></div>',
        '<div class="trend-stat"><div class="trend-label">7d sessions</div>'
        f'<div class="trend-value">{escape(format_int(stats["last7_sessions"]))}</div>'
        f'<div class="trend-detail">{escape(format_growth(stats["last7_sessions"], stats["prev7_sessions"]))} vs previous 7 days</div></div>',
        '<div class="trend-stat"><div class="trend-label">30d footprint</div>'
        f'<div class="trend-value">{escape(format_tokens(stats["last30_tokens"]))}</div>'
        f'<div class="trend-detail">{escape(format_pct(stats["last30_share"]))} of recorded Claude usage</div></div>',
        '<div class="trend-stat"><div class="trend-label">Active streak</div>'
        f'<div class="trend-value">{escape(format_int(stats["streak_current"]))}</div>'
        f'<div class="trend-detail">Longest streak {escape(format_int(stats["streak_longest"]))} days</div></div>',
        "</div>",
        "</article>",
        '<article class="panel">',
        '<div class="panel-header">',
        '<div>',
        '<h2 class="panel-title">Highlights</h2>',
        '<p class="panel-subtitle">Usage first. No invented dollars.</p>',
        "</div>",
        "</div>",
        '<div class="summary-list">',
        f'<div class="summary-item"><strong>Messages</strong><span>{escape(format_int(stats["user_messages"]))} user and {escape(format_int(stats["assistant_messages"]))} assistant messages.</span></div>',
        f'<div class="summary-item"><strong>Per session</strong><span>{escape(format_tokens(stats["avg_session_tokens"]))} average, {escape(format_tokens(stats["median_session_tokens"]))} median, {escape(format_tokens(stats["p90_session_tokens"]))} p90.</span></div>',
        f'<div class="summary-item"><strong>Session duration</strong><span>{escape(format_duration(stats["avg_duration"]))} average, {escape(format_duration(stats["median_duration"]))} median.</span></div>',
        f'<div class="summary-item"><strong>Peak day</strong><span>{escape(stats["top_days"][0]["day"])} at {escape(format_tokens(stats["top_days"][0]["tokens"]))}.</span></div>',
        f'<div class="summary-item"><strong>Top model</strong><span><code>{escape(stats["top_models"][0]["label"])}</code> at {escape(format_tokens(stats["top_models"][0]["tokens"]))}, {escape(format_pct(stats["top_models"][0]["share"]))} of recorded Claude usage.</span></div>',
        f'<div class="summary-item"><strong>Top workspace</strong><span><code>{escape(stats["top_workspaces"][0]["label"])}</code> at {escape(format_tokens(stats["top_workspaces"][0]["tokens"]))} across {escape(format_int(stats["top_workspaces"][0]["sessions"]))} sessions.</span></div>',
        "</div>",
        "</article>",
        "</section>",
        '<section class="grid two-up">',
        '<article class="panel">',
        '<div class="panel-header"><div><h2 class="panel-title">Model Mix</h2><p class="panel-subtitle">Model identity comes from matched Claude transcripts when present.</p></div></div>',
        render_table(
            [
                "<thead><tr><th>Model</th><th class=\"number\">Sessions</th><th class=\"number\">Tokens</th><th class=\"number\">Share</th><th>Shape</th></tr></thead>",
                f"<tbody>{''.join(model_rows)}</tbody>",
            ]
        ),
        "</article>",
        '<article class="panel">',
        '<div class="panel-header"><div><h2 class="panel-title">Workspace Mix</h2><p class="panel-subtitle">The projects where Claude usage actually landed.</p></div></div>',
        render_table(
            [
                "<thead><tr><th>Workspace</th><th class=\"number\">Sessions</th><th class=\"number\">Tokens</th><th class=\"number\">Share</th><th>Shape</th></tr></thead>",
                f"<tbody>{''.join(workspace_rows)}</tbody>",
            ]
        ),
        "</article>",
        "</section>",
        '<section class="panel">',
        '<div class="panel-header"><div><h2 class="panel-title">Notes</h2><p class="panel-subtitle">Blunt caveats so the Claude numbers stay honest.</p></div></div>',
        '<div class="notes">',
        "".join(f'<div class="note">{escape(note)}</div>' for note in stats["notes"]),
        "</div>",
        "</section>",
    ]

    return "\n".join(parts)


def render_page_notes(notes: list[str]) -> str:
    if not notes:
        return ""

    return "\n".join(
        [
            '<section class="panel">',
            '<div class="panel-header"><div><h2 class="panel-title">Page Notes</h2><p class="panel-subtitle">Provider omissions and whole-page caveats.</p></div></div>',
            '<div class="notes">',
            "".join(f'<div class="note">{escape(note)}</div>' for note in notes),
            "</div>",
            "</section>",
        ]
    )


def render_html(dashboard: dict, output_path: Path) -> str:
    provider_names = ", ".join(provider["title"] for provider in dashboard["providers"])
    page_notes = render_page_notes(dashboard["page_notes"])

    parts = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Local AI Usage Dashboard</title>",
        "<style>",
        """
        :root {
          --bg: #f4efe8;
          --panel: #fffdfa;
          --panel-strong: #f8f4ee;
          --text: #1c1a17;
          --muted: #6a6258;
          --border: #ded4c8;
          --accent: #325f64;
          --accent-soft: #dbe8e9;
          --positive: #2c6a50;
          --shadow: 0 8px 24px rgba(36, 31, 25, 0.06);
        }

        * { box-sizing: border-box; }
        body {
          margin: 0;
          background:
            radial-gradient(circle at top left, rgba(50, 95, 100, 0.08), transparent 30%),
            linear-gradient(180deg, #f7f2eb 0%, var(--bg) 100%);
          color: var(--text);
          font-family: "Avenir Next", "Segoe UI", "Helvetica Neue", sans-serif;
        }
        h1, h2, h3 {
          font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", serif;
          font-weight: 600;
          letter-spacing: -0.02em;
          margin: 0;
        }
        p { margin: 0; }
        code {
          font-family: "SFMono-Regular", Menlo, Consolas, monospace;
          font-size: 0.92em;
          background: #f3ede6;
          padding: 0.15rem 0.35rem;
          border-radius: 0.35rem;
        }
        .page {
          max-width: 1180px;
          margin: 0 auto;
          padding: 28px 20px 60px;
        }
        .hero {
          padding: 28px;
          border: 1px solid var(--border);
          border-radius: 24px;
          background: linear-gradient(180deg, rgba(255,255,255,0.72), rgba(255,253,250,0.95));
          box-shadow: var(--shadow);
        }
        .eyebrow {
          color: var(--accent);
          font-size: 0.78rem;
          font-weight: 700;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          margin-bottom: 10px;
        }
        .hero h1 {
          font-size: clamp(2.2rem, 4vw, 3.6rem);
          line-height: 0.98;
          margin-bottom: 12px;
        }
        .hero-copy {
          color: var(--muted);
          max-width: 760px;
          line-height: 1.55;
          font-size: 1rem;
        }
        .hero-meta,
        .provider-pills {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          margin-top: 18px;
        }
        .pill {
          padding: 8px 12px;
          border-radius: 999px;
          background: var(--panel-strong);
          border: 1px solid var(--border);
          color: var(--muted);
          font-size: 0.9rem;
        }
        .grid {
          display: grid;
          gap: 18px;
          margin-top: 22px;
        }
        .metrics {
          grid-template-columns: repeat(4, minmax(0, 1fr));
        }
        .provider-summary {
          grid-template-columns: repeat(2, minmax(0, 1fr));
          margin-top: 0;
        }
        .two-up {
          grid-template-columns: 1.35fr 1fr;
        }
        .metric-card,
        .panel {
          background: var(--panel);
          border: 1px solid var(--border);
          border-radius: 20px;
          box-shadow: var(--shadow);
        }
        .metric-card {
          padding: 18px 18px 16px;
          min-height: 128px;
        }
        .provider-header-panel {
          margin-top: 22px;
        }
        .metric-title {
          color: var(--muted);
          font-size: 0.85rem;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          margin-bottom: 14px;
        }
        .metric-value {
          font-size: 1.75rem;
          line-height: 1;
          margin-bottom: 10px;
        }
        .metric-detail {
          color: var(--muted);
          line-height: 1.45;
          font-size: 0.95rem;
        }
        .panel {
          padding: 22px;
        }
        .panel-header {
          display: flex;
          align-items: flex-end;
          justify-content: space-between;
          gap: 16px;
          margin-bottom: 16px;
        }
        .panel-title {
          font-size: 1.45rem;
        }
        .panel-subtitle {
          color: var(--muted);
          font-size: 0.96rem;
          line-height: 1.5;
        }
        .summary-list {
          display: grid;
          gap: 12px;
        }
        .summary-item {
          padding: 14px 16px;
          border-radius: 16px;
          background: var(--panel-strong);
          border: 1px solid var(--border);
        }
        .summary-item strong {
          display: block;
          margin-bottom: 4px;
          font-size: 1rem;
        }
        .summary-item span {
          color: var(--muted);
          line-height: 1.5;
          font-size: 0.95rem;
        }
        .day-chart {
          height: 220px;
          display: grid;
          grid-template-columns: repeat(14, minmax(0, 1fr));
          gap: 10px;
          align-items: end;
          margin-top: 10px;
        }
        .day-column {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 8px;
          min-width: 0;
        }
        .day-bar {
          width: 100%;
          height: 180px;
          background: #efe7dd;
          border: 1px solid var(--border);
          border-radius: 14px;
          display: flex;
          align-items: flex-end;
          overflow: hidden;
        }
        .day-bar-fill {
          width: 100%;
          background: linear-gradient(180deg, #5a868b 0%, var(--accent) 100%);
          border-radius: 12px;
        }
        .day-label {
          color: var(--muted);
          font-size: 0.78rem;
          font-variant-numeric: tabular-nums;
        }
        .trend-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
          margin-top: 16px;
        }
        .trend-stat {
          padding: 14px 16px;
          border-radius: 16px;
          background: var(--panel-strong);
          border: 1px solid var(--border);
        }
        .trend-label {
          color: var(--muted);
          font-size: 0.84rem;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          margin-bottom: 8px;
        }
        .trend-value {
          font-size: 1.25rem;
          margin-bottom: 4px;
        }
        .trend-detail {
          color: var(--muted);
          font-size: 0.92rem;
        }
        table {
          width: 100%;
          border-collapse: collapse;
        }
        th, td {
          text-align: left;
          padding: 12px 10px;
          border-bottom: 1px solid var(--border);
          vertical-align: middle;
        }
        th {
          color: var(--muted);
          font-size: 0.82rem;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }
        td {
          font-size: 0.95rem;
        }
        tbody tr:last-child td {
          border-bottom: none;
        }
        .number {
          text-align: right;
          font-variant-numeric: tabular-nums;
        }
        .progress {
          position: relative;
          min-width: 140px;
          height: 10px;
          border-radius: 999px;
          background: #ebe2d7;
          overflow: hidden;
        }
        .progress-fill {
          height: 100%;
          background: linear-gradient(90deg, #8db3b6 0%, var(--accent) 100%);
          border-radius: 999px;
        }
        .notes {
          display: grid;
          gap: 10px;
        }
        .note {
          padding: 12px 14px;
          border-radius: 14px;
          background: var(--panel-strong);
          border: 1px solid var(--border);
          color: var(--muted);
        }
        @media (max-width: 1080px) {
          .metrics { grid-template-columns: repeat(3, minmax(0, 1fr)); }
          .provider-summary { grid-template-columns: 1fr; }
          .two-up { grid-template-columns: 1fr; }
        }
        @media (max-width: 720px) {
          .page { padding: 18px 14px 40px; }
          .hero { padding: 20px; border-radius: 20px; }
          .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
          .trend-grid { grid-template-columns: 1fr; }
          th:nth-child(5), td:nth-child(5), th:nth-child(6), td:nth-child(6) { display: none; }
        }
        """,
        "</style>",
        "</head>",
        "<body>",
        '<main class="page">',
        '<section class="hero">',
        '<div class="eyebrow">Local Multi-Provider Usage</div>',
        "<h1>Extremely boring. Actually useful.</h1>",
        "<p class=\"hero-copy\">"
        f"Static HTML. No server. No build step. Each run overwrites <code>{escape(display_path(output_path))}</code> "
        "with a fresh local dashboard for the providers that exposed trustworthy data on this machine."
        "</p>",
        '<div class="hero-meta">',
        f'<div class="pill">Generated {escape(dashboard["generated_at"])}</div>',
        f'<div class="pill">Providers {escape(provider_names)}</div>',
        f'<div class="pill">Codex Mode {"All sessions" if dashboard["include_temp"] else "Non-temp only"}</div>',
        f'<div class="pill">Snapshot {escape(dashboard["snapshot_path"])}</div>',
        "</div>",
        "</section>",
        render_provider_summary(dashboard["providers"]),
    ]

    if dashboard.get("openai") is not None:
        parts.append(render_openai_section(dashboard["openai"]))
    if dashboard.get("claude") is not None:
        parts.append(render_claude_section(dashboard["claude"]))
    if page_notes:
        parts.append(page_notes)

    parts.extend(["</main>", "</body>", "</html>"])
    return "\n".join(parts) + "\n"
