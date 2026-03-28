from __future__ import annotations

import html
import json
import math
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_OUTPUT = Path(__file__).resolve().parent / "index.html"
PRICING_SNAPSHOT = Path(__file__).resolve().parent / ".pricing_snapshot.json"

OPENAI_PRICING_URL = "https://developers.openai.com/api/docs/pricing"
OPENAI_MODEL_PRICING_URLS = {
    "gpt-5.4": "https://developers.openai.com/api/docs/models/gpt-5.4",
    "gpt-5.3-codex": "https://developers.openai.com/api/docs/models/gpt-5.3-codex",
    "gpt-5.2-codex": "https://developers.openai.com/api/docs/models/gpt-5.2-codex",
    "gpt-5.1-codex-mini": "https://developers.openai.com/api/docs/models/gpt-5.1-codex-mini",
    "gpt-5.1-codex-max": "https://developers.openai.com/api/docs/models/gpt-5.1-codex-max",
}
ANTHROPIC_PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing"
ANTHROPIC_BILLING_URL = "https://support.claude.com/en/articles/8977456-how-do-i-pay-for-my-claude-api-usage"
COPILOT_BILLING_URL = "https://docs.github.com/en/copilot/concepts/billing/copilot-requests"

UNKNOWN_LABEL = "(unknown)"


@dataclass
class SessionRecord:
    path: Path
    timestamp_utc: datetime
    timestamp_local: datetime
    cwd: str
    model: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    total_tokens: int
    user_messages: int
    assistant_messages: int
    reasoning_messages: int
    duration_s: float | None
    is_temp: bool

    @property
    def local_day(self):
        return self.timestamp_local.date()

    @property
    def local_hour(self) -> int:
        return self.timestamp_local.hour

    @property
    def local_weekday(self) -> str:
        return self.timestamp_local.strftime("%a")

    @property
    def workspace(self) -> str:
        return workspace_label(self.cwd)


@dataclass
class ClaudeSessionRecord:
    session_id: str
    path: Path
    timestamp_utc: datetime
    timestamp_local: datetime
    cwd: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    user_messages: int
    assistant_messages: int
    duration_s: float | None
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    cache_creation_ephemeral_5m_input_tokens: int
    cache_creation_ephemeral_1h_input_tokens: int
    has_enriched_tokens: bool
    is_partial_parse: bool = False

    @property
    def local_day(self):
        return self.timestamp_local.date()

    @property
    def local_hour(self) -> int:
        return self.timestamp_local.hour

    @property
    def local_weekday(self) -> str:
        return self.timestamp_local.strftime("%a")

    @property
    def workspace(self) -> str:
        return workspace_label(self.cwd)


@dataclass(frozen=True)
class ModelPricing:
    model: str
    input_per_million: float
    cached_input_per_million: float
    output_per_million: float
    source_url: str
    long_input_per_million: float | None = None
    long_cached_input_per_million: float | None = None
    long_output_per_million: float | None = None

    def to_dict(self) -> dict:
        return {
            "input_per_million": self.input_per_million,
            "cached_input_per_million": self.cached_input_per_million,
            "output_per_million": self.output_per_million,
            "source_url": self.source_url,
            "long_input_per_million": self.long_input_per_million,
            "long_cached_input_per_million": self.long_cached_input_per_million,
            "long_output_per_million": self.long_output_per_million,
        }


def resolve_timezone(name: str) -> tzinfo:
    if name != "local":
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError as exc:
            raise SystemExit(f"Unknown timezone: {name}") from exc

    local_tz = datetime.now().astimezone().tzinfo
    if local_tz is None:
        return timezone.utc

    tz_key = getattr(local_tz, "key", None)
    if tz_key:
        return ZoneInfo(tz_key)

    return local_tz


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def is_temp_workspace(cwd: str) -> bool:
    if not cwd:
        return False
    if cwd.startswith("/private/var/folders/"):
        return True
    if cwd.startswith("/var/folders/"):
        return True
    if cwd.startswith("/tmp/"):
        return True
    if cwd.startswith("/private/tmp/"):
        return True
    if "/pytest-" in cwd:
        return True
    return False


def workspace_label(cwd: str) -> str:
    if not cwd:
        return UNKNOWN_LABEL

    parts = [part for part in cwd.split("/") if part]
    if len(parts) >= 5 and parts[0] == "Users":
        return "/" + "/".join(parts[:5])

    return cwd


def build_day_map(sessions: Iterable) -> dict:
    by_day = defaultdict(Counter)

    for session in sessions:
        entry = by_day[session.local_day]
        entry["sessions"] += 1
        entry["total_tokens"] += session.total_tokens

    return dict(by_day)


def sum_days(by_day: dict, start, end) -> Counter:
    totals = Counter()
    current = start

    while current <= end:
        totals.update(by_day.get(current, {}))
        current += timedelta(days=1)

    return totals


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]

    sorted_values = sorted(values)
    index = (len(sorted_values) - 1) * p
    lower = math.floor(index)
    upper = math.ceil(index)

    if lower == upper:
        return sorted_values[lower]

    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def current_and_longest_streak(days: Iterable, latest_day) -> tuple[int, int]:
    ordered_days = sorted(days)
    if not ordered_days:
        return 0, 0

    longest = 0
    current = 0
    previous = None

    for day in ordered_days:
        if previous is not None and day == previous + timedelta(days=1):
            current += 1
        else:
            current = 1
        longest = max(longest, current)
        previous = day

    active_days = set(ordered_days)
    current = 0
    day = latest_day
    while day in active_days:
        current += 1
        day -= timedelta(days=1)

    return current, longest


def format_int(value) -> str:
    if value is None:
        return "n/a"
    return f"{int(round(value)):,}"


def format_tokens(value) -> str:
    if value is None:
        return "n/a"

    absolute = abs(float(value))
    if absolute >= 1_000_000_000:
        return f"{value / 1_000_000_000:.3f}B"
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if absolute >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(int(round(value)))


def format_pct(value) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def format_growth(current: float, previous: float) -> str:
    if previous == 0:
        return "n/a"
    return f"{((current - previous) / previous) * 100:+.1f}%"


def format_duration(seconds) -> str:
    if seconds is None:
        return "n/a"

    total_seconds = int(round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def format_currency(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.2f}"


def collapse_html_text(source: str) -> str:
    text = html.unescape(source)
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_live_page(url: str, timeout_seconds: int = 20) -> tuple[str | None, str | None]:
    curl = shutil.which("curl")
    if curl is None:
        return None, "curl not found"

    try:
        result = subprocess.run(
            [curl, "--location", "--fail", "--silent", url],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "timed out"

    if result.returncode != 0:
        message = result.stderr.strip() or f"curl exited with {result.returncode}"
        return None, message

    return result.stdout, None


def load_pricing_snapshot(snapshot_path: Path) -> dict:
    if not snapshot_path.is_file():
        return {"providers": {}}

    try:
        data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"providers": {}}

    if not isinstance(data, dict):
        return {"providers": {}}

    providers = data.get("providers")
    if isinstance(providers, dict):
        return {"providers": providers}

    if any(key in data for key in ("fetched_at", "models", "source_url")):
        return {"providers": {"openai": data}}

    return {"providers": {}}


def write_provider_snapshots(snapshot_path: Path, providers: dict[str, dict]) -> None:
    payload = {"providers": providers}
    snapshot_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def monthly_projection_value(month: str, month_total: float, latest_day) -> tuple[float | None, float | None]:
    year_text, month_text = month.split("-")
    year = int(year_text)
    month_number = int(month_text)

    if latest_day.year != year or latest_day.month != month_number:
        return None, None

    elapsed_days = latest_day.day
    if elapsed_days <= 0:
        return None, None

    if month_number == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month_number + 1, 1)

    current_month = datetime(year, month_number, 1)
    days_in_month = (next_month - current_month).days
    projection = (month_total / elapsed_days) * days_in_month
    daily_rate = month_total / elapsed_days
    return projection, daily_rate


def monthly_projection(month: str, month_total: int, latest_day) -> tuple[int | None, float | None]:
    projection, daily_rate = monthly_projection_value(month, float(month_total), latest_day)
    if projection is None:
        return None, None
    return int(round(projection)), daily_rate


def escape(value) -> str:
    return html.escape(str(value), quote=True)


def display_path(p) -> str:
    path = Path(p)
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)
