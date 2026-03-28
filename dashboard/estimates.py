from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, tzinfo
from pathlib import Path

from usage_report_common import (
    ANTHROPIC_PRICING_URL,
    OPENAI_MODEL_PRICING_URLS,
    OPENAI_PRICING_URL,
    ModelPricing,
    collapse_html_text,
    fetch_live_page,
    load_pricing_snapshot,
    write_provider_snapshots,
)
from usage_report_providers import parse_gpt54_long_context_rates, parse_standard_model_rates

from .providers import NormalizedSession


EXTRA_OPENAI_MODEL_PRICING_URLS = {
    "gpt-5.2": "https://developers.openai.com/api/docs/models/gpt-5.2",
}

OPENAI_MODEL_URLS = {
    **OPENAI_MODEL_PRICING_URLS,
    **EXTRA_OPENAI_MODEL_PRICING_URLS,
}

CLAUDE_MODEL_LABELS = {
    "claude-opus-4-6": "Claude Opus 4.6",
    "claude-opus-4-5": "Claude Opus 4.5",
    "claude-opus-4-1": "Claude Opus 4.1",
    "claude-opus-4": "Claude Opus 4",
    "claude-sonnet-4-6": "Claude Sonnet 4.6",
    "claude-sonnet-4-5": "Claude Sonnet 4.5",
    "claude-sonnet-4": "Claude Sonnet 4",
    "claude-sonnet-3-7": "Claude Sonnet 3.7",
    "claude-haiku-4-5": "Claude Haiku 4.5",
    "claude-haiku-3-5": "Claude Haiku 3.5",
    "claude-haiku-3": "Claude Haiku 3",
}


@dataclass(frozen=True)
class PricingSnapshotRow:
    snapshot_id: str
    provider: str
    model: str
    checked_at: datetime
    freshness_label: str
    source_url: str
    currency: str
    input_per_million: float | None
    cached_input_per_million: float | None
    output_per_million: float | None
    cache_write_5m_per_million: float | None
    cache_write_1h_per_million: float | None
    cache_read_per_million: float | None
    snapshot_path: str | None
    notes_json: str


@dataclass(frozen=True)
class SessionEstimateRow:
    provider: str
    session_id: str
    snapshot_id: str | None
    estimation_method: str
    estimate_label: str
    pricing_freshness: str
    estimated_cost_usd: float | None
    estimated_cache_savings_usd: float | None
    excluded: bool
    exclusion_reason: str | None
    assumption_flags_json: str


@dataclass(frozen=True)
class ClaudeModelPricing:
    model: str
    input_per_million: float
    cache_write_5m_per_million: float
    cache_write_1h_per_million: float
    cache_read_per_million: float
    output_per_million: float
    source_url: str

    def to_dict(self) -> dict[str, float | str]:
        return {
            "input_per_million": self.input_per_million,
            "cache_write_5m_per_million": self.cache_write_5m_per_million,
            "cache_write_1h_per_million": self.cache_write_1h_per_million,
            "cache_read_per_million": self.cache_read_per_million,
            "output_per_million": self.output_per_million,
            "source_url": self.source_url,
        }


def estimate_openai_sessions(
    sessions: list[NormalizedSession],
    snapshot_path: Path,
    report_tz: tzinfo,
    pricing_mode: str,
    snapshot_id: str,
) -> tuple[list[PricingSnapshotRow], list[SessionEstimateRow]]:
    pricing_by_model, freshness_by_model, pricing_rows = _resolve_openai_pricing(
        sessions=sessions,
        snapshot_path=snapshot_path,
        report_tz=report_tz,
        pricing_mode=pricing_mode,
        snapshot_id=snapshot_id,
    )

    estimates: list[SessionEstimateRow] = []
    for session in sessions:
        pricing = pricing_by_model.get(session.model)
        freshness = freshness_by_model.get(session.model, "Unavailable")
        if pricing is None:
            estimates.append(
                SessionEstimateRow(
                    provider=session.provider,
                    session_id=session.session_id,
                    snapshot_id=None,
                    estimation_method="token-based",
                    estimate_label="Partial",
                    pricing_freshness="Unavailable",
                    estimated_cost_usd=None,
                    estimated_cache_savings_usd=None,
                    excluded=True,
                    exclusion_reason="unsupported_model",
                    assumption_flags_json="[]",
                )
            )
            continue

        estimated_cost = _estimate_openai_cost(session, pricing)
        estimated_no_cache_cost = _estimate_openai_no_cache_cost(session, pricing)
        estimates.append(
            SessionEstimateRow(
                provider=session.provider,
                session_id=session.session_id,
                snapshot_id=snapshot_id,
                estimation_method="token-based",
                estimate_label="Direct",
                pricing_freshness=freshness,
                estimated_cost_usd=estimated_cost,
                estimated_cache_savings_usd=estimated_no_cache_cost - estimated_cost,
                excluded=False,
                exclusion_reason=None,
                assumption_flags_json="[]",
            )
        )

    return pricing_rows, estimates


def estimate_claude_sessions(
    sessions: list[NormalizedSession],
    snapshot_path: Path,
    report_tz: tzinfo,
    pricing_mode: str,
    snapshot_id: str,
) -> tuple[list[PricingSnapshotRow], list[SessionEstimateRow]]:
    pricing_by_model, freshness_by_model, pricing_rows = _resolve_claude_pricing(
        sessions=sessions,
        snapshot_path=snapshot_path,
        report_tz=report_tz,
        pricing_mode=pricing_mode,
        snapshot_id=snapshot_id,
    )

    estimates: list[SessionEstimateRow] = []
    for session in sessions:
        pricing_key = claude_pricing_key(session.model)
        freshness = freshness_by_model.get(pricing_key or "", "Unavailable")
        pricing = pricing_by_model.get(pricing_key or "")
        if pricing is None:
            estimates.append(
                SessionEstimateRow(
                    provider=session.provider,
                    session_id=session.session_id,
                    snapshot_id=None,
                    estimation_method="token-and-cache-based",
                    estimate_label="Partial",
                    pricing_freshness="Unavailable",
                    estimated_cost_usd=None,
                    estimated_cache_savings_usd=None,
                    excluded=True,
                    exclusion_reason="unsupported_model",
                    assumption_flags_json="[]",
                )
            )
            continue

        estimated_cost, estimated_no_cache_cost, estimate_label, assumption_flags = _estimate_claude_cost(
            session,
            pricing,
        )
        estimates.append(
            SessionEstimateRow(
                provider=session.provider,
                session_id=session.session_id,
                snapshot_id=snapshot_id,
                estimation_method="token-and-cache-based",
                estimate_label=estimate_label,
                pricing_freshness=freshness,
                estimated_cost_usd=estimated_cost,
                estimated_cache_savings_usd=estimated_no_cache_cost - estimated_cost,
                excluded=False,
                exclusion_reason=None,
                assumption_flags_json=json.dumps(assumption_flags),
            )
        )

    return pricing_rows, estimates


def claude_pricing_key(model: str) -> str | None:
    normalized = (model or "").strip().lower()
    if not normalized or normalized.startswith("<"):
        return None

    for key in CLAUDE_MODEL_LABELS:
        if normalized == key or normalized.startswith(f"{key}-"):
            return key

    return None


def _resolve_openai_pricing(
    sessions: list[NormalizedSession],
    snapshot_path: Path,
    report_tz: tzinfo,
    pricing_mode: str,
    snapshot_id: str,
) -> tuple[dict[str, ModelPricing], dict[str, str], list[PricingSnapshotRow]]:
    previous_snapshot = load_pricing_snapshot(snapshot_path)
    provider_snapshot = previous_snapshot.get("providers", {}).get("openai") or {}
    previous_models = provider_snapshot.get("models") or {}

    checked_at = datetime.now(report_tz)
    pricing_by_model: dict[str, ModelPricing] = {}
    freshness_by_model: dict[str, str] = {}
    pricing_rows: list[PricingSnapshotRow] = []
    live_models: dict[str, dict] = {}

    needs_main_page = pricing_mode != "snapshot" and any(session.model == "gpt-5.4" for session in sessions)
    main_page_text = None
    if needs_main_page:
        raw_page, error = fetch_live_page(OPENAI_PRICING_URL)
        if error is None and raw_page is not None:
            main_page_text = collapse_html_text(raw_page)

    for model in sorted({session.model for session in sessions if session.model}):
        url = OPENAI_MODEL_URLS.get(model)
        if url is None:
            continue

        pricing = None
        freshness = "Unavailable"

        if pricing_mode != "snapshot":
            pricing = _fetch_openai_pricing(model, url, main_page_text)
            if pricing is not None:
                freshness = "Fresh"
                live_models[model] = pricing.to_dict()

        if pricing is None and pricing_mode in ("snapshot", "auto"):
            snapshot_model = previous_models.get(model)
            if isinstance(snapshot_model, dict):
                pricing = _openai_pricing_from_snapshot(model, snapshot_model, url)
                freshness = "Snapshot"

        if pricing is None:
            continue

        pricing_by_model[model] = pricing
        freshness_by_model[model] = freshness
        pricing_rows.append(
            PricingSnapshotRow(
                snapshot_id=snapshot_id,
                provider="openai",
                model=model,
                checked_at=checked_at,
                freshness_label=freshness,
                source_url=url,
                currency="USD",
                input_per_million=pricing.input_per_million,
                cached_input_per_million=pricing.cached_input_per_million,
                output_per_million=pricing.output_per_million,
                cache_write_5m_per_million=None,
                cache_write_1h_per_million=None,
                cache_read_per_million=None,
                snapshot_path=str(snapshot_path),
                notes_json="[]",
            )
        )

    if live_models:
        provider_payload = {
            "fetched_at": checked_at.isoformat(),
            "source_url": OPENAI_PRICING_URL,
            "models": {**previous_models, **live_models},
        }
        _write_provider_snapshot(previous_snapshot, snapshot_path, "openai", provider_payload)

    return pricing_by_model, freshness_by_model, pricing_rows


def _resolve_claude_pricing(
    sessions: list[NormalizedSession],
    snapshot_path: Path,
    report_tz: tzinfo,
    pricing_mode: str,
    snapshot_id: str,
) -> tuple[dict[str, ClaudeModelPricing], dict[str, str], list[PricingSnapshotRow]]:
    previous_snapshot = load_pricing_snapshot(snapshot_path)
    provider_snapshot = previous_snapshot.get("providers", {}).get("anthropic") or {}
    previous_models = provider_snapshot.get("models") or {}

    checked_at = datetime.now(report_tz)
    pricing_by_model: dict[str, ClaudeModelPricing] = {}
    freshness_by_model: dict[str, str] = {}
    pricing_rows: list[PricingSnapshotRow] = []
    live_models: dict[str, dict] = {}

    live_pricing: dict[str, ClaudeModelPricing] = {}
    if pricing_mode != "snapshot":
        raw_page, error = fetch_live_page(ANTHROPIC_PRICING_URL)
        if error is None and raw_page is not None:
            live_pricing = _parse_claude_pricing_page(collapse_html_text(raw_page))

    pricing_keys = {claude_pricing_key(session.model) for session in sessions}
    for key in sorted(key for key in pricing_keys if key is not None):

        pricing = None
        freshness = "Unavailable"

        if key in live_pricing:
            pricing = live_pricing[key]
            freshness = "Fresh"
            live_models[key] = pricing.to_dict()
        elif pricing_mode in ("snapshot", "auto"):
            snapshot_model = previous_models.get(key)
            if isinstance(snapshot_model, dict):
                pricing = _claude_pricing_from_snapshot(key, snapshot_model)
                freshness = "Snapshot"

        if pricing is None:
            continue

        pricing_by_model[key] = pricing
        freshness_by_model[key] = freshness
        pricing_rows.append(
            PricingSnapshotRow(
                snapshot_id=snapshot_id,
                provider="claude",
                model=key,
                checked_at=checked_at,
                freshness_label=freshness,
                source_url=ANTHROPIC_PRICING_URL,
                currency="USD",
                input_per_million=pricing.input_per_million,
                cached_input_per_million=None,
                output_per_million=pricing.output_per_million,
                cache_write_5m_per_million=pricing.cache_write_5m_per_million,
                cache_write_1h_per_million=pricing.cache_write_1h_per_million,
                cache_read_per_million=pricing.cache_read_per_million,
                snapshot_path=str(snapshot_path),
                notes_json="[]",
            )
        )

    if live_models:
        provider_payload = {
            "fetched_at": checked_at.isoformat(),
            "source_url": ANTHROPIC_PRICING_URL,
            "models": {**previous_models, **live_models},
        }
        _write_provider_snapshot(previous_snapshot, snapshot_path, "anthropic", provider_payload)

    return pricing_by_model, freshness_by_model, pricing_rows


def _fetch_openai_pricing(model: str, url: str, main_page_text: str | None) -> ModelPricing | None:
    raw_page, error = fetch_live_page(url)
    if error is not None or raw_page is None:
        return None

    page_text = collapse_html_text(raw_page)
    rates = parse_standard_model_rates(page_text)
    if rates is None:
        return None

    input_rate, cached_input_rate, output_rate = rates
    pricing = ModelPricing(
        model=model,
        input_per_million=input_rate,
        cached_input_per_million=cached_input_rate,
        output_per_million=output_rate,
        source_url=url,
    )

    if model != "gpt-5.4" or main_page_text is None:
        return pricing

    long_rates = parse_gpt54_long_context_rates(main_page_text)
    if long_rates is None:
        return pricing

    long_input_rate, long_cached_rate, long_output_rate = long_rates
    return ModelPricing(
        model=model,
        input_per_million=input_rate,
        cached_input_per_million=cached_input_rate,
        output_per_million=output_rate,
        source_url=url,
        long_input_per_million=long_input_rate,
        long_cached_input_per_million=long_cached_rate,
        long_output_per_million=long_output_rate,
    )


def _openai_pricing_from_snapshot(model: str, payload: dict, source_url: str) -> ModelPricing:
    return ModelPricing(
        model=model,
        input_per_million=float(payload.get("input_per_million") or 0),
        cached_input_per_million=float(payload.get("cached_input_per_million") or 0),
        output_per_million=float(payload.get("output_per_million") or 0),
        source_url=str(payload.get("source_url") or source_url),
        long_input_per_million=_float_or_none(payload.get("long_input_per_million")),
        long_cached_input_per_million=_float_or_none(payload.get("long_cached_input_per_million")),
        long_output_per_million=_float_or_none(payload.get("long_output_per_million")),
    )


def _parse_claude_pricing_page(page_text: str) -> dict[str, ClaudeModelPricing]:
    pricing_by_model: dict[str, ClaudeModelPricing] = {}

    for key, label in CLAUDE_MODEL_LABELS.items():
        start = page_text.find(label)
        if start == -1:
            continue

        snippet = page_text[start : start + 300]
        amounts = re.findall(r"\$(\d+(?:\.\d+)?)", snippet)
        if len(amounts) < 5:
            continue

        input_rate, cache_write_5m_rate, cache_write_1h_rate, cache_read_rate, output_rate = (
            float(value) for value in amounts[:5]
        )
        pricing_by_model[key] = ClaudeModelPricing(
            model=key,
            input_per_million=input_rate,
            cache_write_5m_per_million=cache_write_5m_rate,
            cache_write_1h_per_million=cache_write_1h_rate,
            cache_read_per_million=cache_read_rate,
            output_per_million=output_rate,
            source_url=ANTHROPIC_PRICING_URL,
        )

    return pricing_by_model


def _claude_pricing_from_snapshot(model: str, payload: dict) -> ClaudeModelPricing:
    return ClaudeModelPricing(
        model=model,
        input_per_million=float(payload.get("input_per_million") or 0),
        cache_write_5m_per_million=float(payload.get("cache_write_5m_per_million") or 0),
        cache_write_1h_per_million=float(payload.get("cache_write_1h_per_million") or 0),
        cache_read_per_million=float(payload.get("cache_read_per_million") or 0),
        output_per_million=float(payload.get("output_per_million") or 0),
        source_url=str(payload.get("source_url") or ANTHROPIC_PRICING_URL),
    )


def _estimate_openai_cost(session: NormalizedSession, pricing: ModelPricing) -> float:
    uncached_input_tokens = max(session.input_tokens - session.cached_input_tokens, 0)
    total = (
        uncached_input_tokens * pricing.input_per_million
        + session.cached_input_tokens * pricing.cached_input_per_million
        + session.output_tokens * pricing.output_per_million
    )
    return total / 1_000_000


def _estimate_openai_no_cache_cost(session: NormalizedSession, pricing: ModelPricing) -> float:
    total = session.input_tokens * pricing.input_per_million + session.output_tokens * pricing.output_per_million
    return total / 1_000_000


def _estimate_claude_cost(
    session: NormalizedSession,
    pricing: ClaudeModelPricing,
) -> tuple[float, float, str, list[str]]:
    estimate_label = "Direct"
    assumption_flags: list[str] = []

    base_input_tokens = session.input_tokens
    if session.token_coverage == "enriched":
        base_input_tokens = max(session.input_tokens - session.cache_creation_input_tokens - session.cache_read_tokens, 0)

    cache_write_5m_tokens = session.cache_creation_5m_tokens
    cache_write_1h_tokens = session.cache_creation_1h_tokens
    cache_write_total = session.cache_creation_input_tokens
    cache_write_known = cache_write_5m_tokens + cache_write_1h_tokens

    if cache_write_total > cache_write_known:
        cache_write_5m_tokens += cache_write_total - cache_write_known
        estimate_label = "Approx"
        assumption_flags.append("assumed_missing_cache_write_split_is_5m")

    if cache_write_total and cache_write_known > cache_write_total:
        overflow = cache_write_known - cache_write_total
        if cache_write_1h_tokens >= overflow:
            cache_write_1h_tokens -= overflow
        else:
            overflow -= cache_write_1h_tokens
            cache_write_1h_tokens = 0
            cache_write_5m_tokens = max(cache_write_5m_tokens - overflow, 0)
        estimate_label = "Approx"
        assumption_flags.append("clamped_cache_write_split_to_total")

    estimated_cost = (
        base_input_tokens * pricing.input_per_million
        + cache_write_5m_tokens * pricing.cache_write_5m_per_million
        + cache_write_1h_tokens * pricing.cache_write_1h_per_million
        + session.cache_read_tokens * pricing.cache_read_per_million
        + session.output_tokens * pricing.output_per_million
    ) / 1_000_000

    if session.token_coverage == "enriched":
        no_cache_input_tokens = base_input_tokens + session.cache_creation_input_tokens + session.cache_read_tokens
    else:
        no_cache_input_tokens = session.input_tokens + session.cache_creation_input_tokens + session.cache_read_tokens

    estimated_no_cache_cost = (
        no_cache_input_tokens * pricing.input_per_million
        + session.output_tokens * pricing.output_per_million
    ) / 1_000_000

    return estimated_cost, estimated_no_cache_cost, estimate_label, assumption_flags


def _write_provider_snapshot(previous_snapshot: dict, snapshot_path: Path, provider: str, payload: dict) -> None:
    providers = dict(previous_snapshot.get("providers", {}))
    providers[provider] = payload
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    write_provider_snapshots(snapshot_path, providers)


def _float_or_none(value) -> float | None:
    if value is None:
        return None
    return float(value)
