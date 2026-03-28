from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .db import connect
from .queries import (
    DashboardFilters,
    get_methodology_context,
    get_overview_context,
    get_workspaces_context,
)


router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def root(request: Request):
    if request.query_params:
        return RedirectResponse(url=f"/overview?{request.query_params}", status_code=307)
    return RedirectResponse(url="/overview", status_code=307)


@router.get("/overview", response_class=HTMLResponse)
def overview(request: Request):
    filters = _parse_filters(request)
    with connect(request.app.state.db_path, read_only=True) as db:
        context = get_overview_context(db, filters)

    return _render_page(
        request=request,
        template_name="overview.html",
        page_title="Overview",
        page_description="High-signal usage and cost view.",
        page_path="/overview",
        filters=filters,
        context=context,
    )


@router.get("/workspaces", response_class=HTMLResponse)
def workspaces(request: Request):
    filters = _parse_filters(request)
    with connect(request.app.state.db_path, read_only=True) as db:
        context = get_workspaces_context(db, filters)

    return _render_page(
        request=request,
        template_name="workspaces.html",
        page_title="Workspaces",
        page_description="Ranked workspace concentration and selected workspace detail.",
        page_path="/workspaces",
        filters=filters,
        context=context,
    )


@router.get("/methodology", response_class=HTMLResponse)
def methodology(request: Request):
    filters = _parse_filters(request)
    with connect(request.app.state.db_path, read_only=True) as db:
        context = get_methodology_context(db, filters)

    return _render_page(
        request=request,
        template_name="methodology.html",
        page_title="Methodology",
        page_description="How the estimates are built and what remains excluded.",
        page_path="/methodology",
        filters=filters,
        context=context,
    )


def _parse_filters(request: Request) -> DashboardFilters:
    params = request.query_params
    return DashboardFilters(
        provider=params.get("provider", "all"),
        workspace=params.get("workspace") or None,
        include_temp=_parse_bool(params.get("include_temp")),
        metric=params.get("metric", "cost"),
        date_from=_parse_date(params.get("date_from")),
        date_to=_parse_date(params.get("date_to")),
        anonymize=_parse_bool(params.get("anonymize")),
    )


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "on"}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _render_page(
    *,
    request: Request,
    template_name: str,
    page_title: str,
    page_description: str,
    page_path: str,
    filters: DashboardFilters,
    context: dict,
):
    template_context = {
        "title": page_title,
        "page": page_path.lstrip("/"),
        "page_title": page_title,
        "page_description": page_description,
        "page_path": page_path,
        "filters": _template_filters(request, filters),
        "filter_options": _template_filter_options(
            context.get("filter_options", context.get("filters", {}))
        ),
        "trust_banner": context.get("trust_banner", {}),
        "headline_metrics": context.get("headline_metrics", []),
        "cost_trend_series": context.get("cost_trend_series", []),
        "provider_mix_rows": context.get("provider_mix_rows", []),
        "model_mix_rows": context.get("model_mix_rows", []),
        "work_shape_rows": context.get("work_shape_rows", []),
        "workspace_rows": context.get("workspace_rows", []),
        "selected_workspace": context.get("selected_workspace"),
        "selected_workspace_metrics": context.get("selected_workspace_metrics", []),
        "selected_workspace_trend": context.get("selected_workspace_trend", []),
        "selected_workspace_model_mix": context.get("selected_workspace_model_mix", []),
        "selected_workspace_provider_mix": context.get("selected_workspace_provider_mix", []),
        "selected_workspace_work_shape": context.get("selected_workspace_work_shape", []),
        "pricing_summary": context.get("pricing_summary", []),
        "estimate_rules": context.get("estimate_rules", []),
        "coverage_summary": context.get("coverage_summary", []),
        "exclusions_summary": context.get("exclusions_summary", []),
        "doctor_summary": context.get("doctor_summary", []),
        "source_paths": context.get("source_paths", {}),
        "unsupported_models": context.get("unsupported_models", []),
        "nav_links": _nav_links(page_path, request, filters),
        "metric_links": _metric_links(page_path, request, filters),
        "context": context,
}
    return request.app.state.templates.TemplateResponse(
        request=request,
        name=template_name,
        context=template_context,
    )


def _template_filter_options(raw: dict[str, Any]) -> dict[str, Any]:
    provider_options = raw.get("providers") or []
    workspace_options = raw.get("workspaces") or []
    metric_options = raw.get("metric_options") or [
        {"value": "cost", "label": "Cost"},
        {"value": "tokens", "label": "Tokens"},
        {"value": "sessions", "label": "Sessions"},
    ]

    return {
        "provider": raw.get("provider", "all"),
        "workspace": raw.get("workspace"),
        "include_temp": raw.get("include_temp", False),
        "metric": raw.get("metric", "cost"),
        "date_from": raw.get("date_from", ""),
        "date_to": raw.get("date_to", ""),
        "anonymize": raw.get("anonymize", False),
        "min_day": raw.get("min_day", ""),
        "max_day": raw.get("max_day", ""),
        "provider_options": [
            {"value": item["value"], "label": item["label"], "sessions": item.get("sessions")}
            for item in provider_options
        ],
        "workspace_options": [
            {"value": item["value"], "label": item["label"], "sessions": item.get("sessions")}
            for item in workspace_options
        ],
        "model_options": raw.get("model_options")
        or [{"value": "", "label": "All models", "sessions": None}],
        "metric_options": [
            {"value": item["value"], "label": item["label"]}
            for item in metric_options
        ],
    }


def _template_filters(request: Request, filters: DashboardFilters) -> dict[str, object]:
    params = request.query_params
    return {
        "from": params.get("date_from") or (filters.date_from.isoformat() if filters.date_from else ""),
        "to": params.get("date_to") or (filters.date_to.isoformat() if filters.date_to else ""),
        "provider": filters.provider,
        "workspace": filters.workspace or "",
        "model": params.get("model", "all"),
        "include_temp": filters.include_temp,
        "anonymize": filters.anonymize,
        "sort": params.get("sort", "cost"),
        "dir": params.get("dir", "desc"),
        "metric": filters.metric,
    }


def _nav_links(page_path: str, request: Request, filters: DashboardFilters) -> dict[str, str]:
    query = request.query_params
    suffix = f"?{query}" if query else ""
    if page_path == "/overview":
        return {
            "overview": f"/overview{suffix}",
            "workspaces": f"/workspaces{suffix}",
            "methodology": f"/methodology{suffix}",
        }
    return {
        "overview": f"/overview{suffix}",
        "workspaces": f"/workspaces{suffix}",
        "methodology": f"/methodology{suffix}",
    }


def _metric_links(page_path: str, request: Request, filters: DashboardFilters) -> dict[str, str]:
    query = dict(request.query_params)
    links = {}
    for metric in ("cost", "tokens", "sessions"):
        query["metric"] = metric
        suffix = "?" + urlencode(query)
        links[metric] = f"{page_path}{suffix}"
    return links
