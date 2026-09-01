from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Mapping

from .models import LimitWindow, ProviderLimits, UsageSnapshot

ResetUrgency = Literal["neutral", "warning", "critical"]
LimitDisplayMode = Literal["used", "remaining"]
LimitTimeMode = Literal["remaining", "datetime"]

LIMIT_DISPLAY_MODE_KEY = "limit_display_mode"
DEFAULT_LIMIT_DISPLAY_MODE: LimitDisplayMode = "used"
LIMIT_TIME_MODE_KEY = "limit_time_display_mode"
DEFAULT_LIMIT_TIME_MODE: LimitTimeMode = "remaining"
FORECAST_ENABLED_KEY = "limits_forecast_enabled"
DEFAULT_FORECAST_ENABLED = True


@dataclass(slots=True, frozen=True)
class LimitDisplayRow:
    text: str
    occurs_at: datetime | None
    urgency: ResetUrgency = "neutral"


@dataclass(slots=True, frozen=True)
class LimitForecast:
    depletion_at: datetime
    before_reset: bool


def compact_tokens(value: int) -> str:
    sign = "-" if value < 0 else ""
    n = abs(float(value))
    if n >= 1_000_000_000:
        return f"{sign}{n / 1_000_000_000:.1f}B".replace(".0B", "B")
    if n >= 1_000_000:
        return f"{sign}{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{sign}{n / 1_000:.1f}K".replace(".0K", "K")
    return f"{sign}{int(n)}"


def money(value: float) -> str:
    if value < 0.005:
        return "$0.00"
    return f"${value:,.2f}"


def companion_level_text(progress_percent: int | float) -> str:
    """Present companion phase progress as a Pokemon-style level."""
    level = max(0, min(100, round(float(progress_percent))))
    return f"Lv. {level}"


def normalize_limit_display_mode(value: Any) -> LimitDisplayMode:
    return "remaining" if str(value).strip().lower() == "remaining" else "used"


def normalize_limit_time_mode(value: Any) -> LimitTimeMode:
    return "datetime" if str(value).strip().lower() == "datetime" else "remaining"


def limit_display_percent(
    used_percent: float,
    mode: LimitDisplayMode = DEFAULT_LIMIT_DISPLAY_MODE,
) -> float:
    used = max(0.0, min(100.0, float(used_percent)))
    return 100.0 - used if normalize_limit_display_mode(mode) == "remaining" else used


def limit_percent_text(
    used_percent: float,
    mode: LimitDisplayMode = DEFAULT_LIMIT_DISPLAY_MODE,
    *,
    compact: bool = False,
) -> str:
    normalized = normalize_limit_display_mode(mode)
    suffix = "left" if compact and normalized == "remaining" else (
        "remaining" if normalized == "remaining" else "used"
    )
    return f"{limit_display_percent(used_percent, normalized):.0f}% {suffix}"


def limit_alert_body(
    provider_label: str,
    window_label: str,
    used_percent: float,
    mode: LimitDisplayMode = DEFAULT_LIMIT_DISPLAY_MODE,
) -> str:
    # Alert semantics stay anchored to utilization regardless of the display
    # preference. This matches upstream and keeps warning thresholds unambiguous.
    return f"{provider_label} {window_label}: {limit_percent_text(used_percent, 'used')}."


def is_reserve_window(window: LimitWindow) -> bool:
    identifier = (window.identifier or "").lower().replace("-", "_")
    label = window.label.lower()
    return identifier.startswith("base_model_inference") or "reserve" in label


def _compact_candidate_windows(status: ProviderLimits) -> list[LimitWindow]:
    windows = [window for window in status.windows if "spend" not in window.label.lower()]
    if status.provider.lower() != "codex":
        return windows

    regular = [window for window in windows if not is_reserve_window(window)]
    reserve = [window for window in windows if is_reserve_window(window)]
    if not reserve:
        return regular
    if not regular:
        return reserve

    # Luna Reserve is a fallback allowance. Surface it on compact views only
    # after regular Codex usage is exhausted (or the server says it is active).
    regular_exhausted = status.reserve_active or any(
        float(window.used_percent) >= 100.0 for window in regular
    )
    return reserve if regular_exhausted else regular


def highest_relevant_limit(
    snapshot: UsageSnapshot,
    limits_by_provider: Mapping[str, ProviderLimits],
) -> tuple[str, LimitWindow] | None:
    """Pick the active, most-used non-spend limit from providers used today."""
    active = {
        provider
        for provider, usage in snapshot.providers.items()
        if usage.today_tokens > 0
    }
    candidates: list[tuple[float, float, str, LimitWindow]] = []
    for provider, status in limits_by_provider.items():
        if provider not in active:
            continue
        for window in _compact_candidate_windows(status):
            reset = window.resets_at.timestamp() if window.resets_at is not None else float("inf")
            candidates.append((float(window.used_percent), -reset, provider, window))
    if not candidates:
        return None
    _, _, provider, window = max(candidates, key=lambda item: (item[0], item[1]))
    return provider, window


def limit_forecast(
    window: LimitWindow,
    now: datetime | None = None,
) -> LimitForecast | None:
    """Extrapolate a timed window from average utilization since its start."""
    reset = window.resets_at
    if reset is None:
        return None
    duration_minutes = window.duration_minutes
    if duration_minutes is None:
        return None

    current = _now_for(reset, now)
    remaining_seconds = (reset - current).total_seconds()
    duration_seconds = duration_minutes * 60
    elapsed_seconds = duration_seconds - remaining_seconds
    used = max(0.0, min(100.0, float(window.used_percent)))
    # Match upstream's 5% stability floor and require a meaningful observed slice.
    if used >= 100:
        return LimitForecast(depletion_at=current, before_reset=True)
    if used < 5 or elapsed_seconds < 60 or remaining_seconds <= 0:
        return None
    seconds_per_percent = elapsed_seconds / used
    seconds_to_full = (100.0 - used) * seconds_per_percent
    depletion_at = current + timedelta(seconds=seconds_to_full)
    return LimitForecast(depletion_at=depletion_at, before_reset=depletion_at < reset)


def limit_forecast_unavailable_reason(
    window: LimitWindow,
    now: datetime | None = None,
) -> str | None:
    """Explain why a requested forecast cannot currently be shown."""
    reset = window.resets_at
    if reset is None:
        return "reset time unavailable"
    if window.duration_minutes is None:
        return "window duration unavailable"
    current = _now_for(reset, now)
    if (reset - current).total_seconds() <= 0:
        return "window already reset"
    used = max(0.0, min(100.0, float(window.used_percent)))
    if used < 5:
        return "not enough data yet"
    elapsed_seconds = window.duration_minutes * 60 - (reset - current).total_seconds()
    if elapsed_seconds < 60:
        return "collecting usage data"
    return None


def format_limit_datetime(value: datetime) -> str:
    return value.strftime("%d %b, %H:%M")


def format_limit_countdown(
    value: datetime,
    now: datetime | None = None,
    *,
    approximate: bool = False,
) -> str:
    seconds = max(0, int((value - _now_for(value, now)).total_seconds()))
    if approximate:
        if seconds >= 3_600:
            hours = max(1, int(seconds / 3_600 + 0.5))
            return f"~{hours}h"
        minutes = max(1, int(seconds / 60 + 0.5))
        return f"~{minutes}m"

    days, remainder = divmod(seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes = remainder // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def format_limit_event_time(
    label: str,
    value: datetime,
    mode: LimitTimeMode = DEFAULT_LIMIT_TIME_MODE,
    now: datetime | None = None,
    *,
    approximate: bool = False,
) -> str:
    normalized = normalize_limit_time_mode(mode)
    if normalized == "datetime":
        return f"{label} {format_limit_datetime(value)}"
    return (
        f"{label} in "
        f"{format_limit_countdown(value, now, approximate=approximate)}"
    )


def _reset_title_and_scope(title: str | None) -> tuple[str, str | None]:
    label = (title or "Rate-limit reset").strip()
    if label.endswith(")") and " (" in label:
        label, raw_scope = label.rsplit(" (", 1)
        scope = raw_scope[:-1].strip()
        return label.strip(), scope or None
    return label, None


def _next_reset_credit(limits: ProviderLimits):
    if limits.reset_credits_available <= 0 or not limits.reset_credits:
        return None
    dated = [credit for credit in limits.reset_credits if credit.expires_at is not None]
    return min(dated, key=lambda credit: credit.expires_at) if dated else limits.reset_credits[0]


def limit_reset_expiry(limits: ProviderLimits) -> datetime | None:
    credit = _next_reset_credit(limits)
    return credit.expires_at if credit else None


def _now_for(reference: datetime, now: datetime | None) -> datetime:
    current = now or datetime.now().astimezone()
    if reference.tzinfo is None and current.tzinfo is not None:
        return current.replace(tzinfo=None)
    if reference.tzinfo is not None and current.tzinfo is None:
        return current.replace(tzinfo=reference.tzinfo)
    if reference.tzinfo is not None:
        return current.astimezone(reference.tzinfo)
    return current


def limit_reset_urgency(limits: ProviderLimits, now: datetime | None = None) -> ResetUrgency:
    expiry = limit_reset_expiry(limits)
    if expiry is None:
        return "neutral"

    remaining = expiry - _now_for(expiry, now)
    if remaining <= timedelta(hours=72):
        return "critical"

    weekly_reset = next(
        (
            window.resets_at
            for window in limits.windows
            if window.label.lower() == "weekly" and window.resets_at is not None
        ),
        None,
    )
    expires_before_weekly = weekly_reset is not None and expiry.timestamp() < weekly_reset.timestamp()
    if expires_before_weekly or remaining < timedelta(days=7):
        return "warning"
    return "neutral"


def limit_reset_summary(
    limits: ProviderLimits,
    now: datetime | None = None,
    *,
    time_mode: LimitTimeMode = DEFAULT_LIMIT_TIME_MODE,
) -> str:
    count = limits.reset_credits_available
    if count <= 0:
        return ""

    next_credit = _next_reset_credit(limits)
    if count == 1:
        label, scope = _reset_title_and_scope(next_credit.title if next_credit else None)
        if not label.lower().endswith("available"):
            label += " available"
        parts = [label]
        if scope:
            parts.append(scope.replace("5 hr", "5h"))
        expiry_label = "expires"
    else:
        parts = [f"{count} resets available"]
        expiry_label = "first expires"

    if next_credit and next_credit.expires_at:
        parts.append(
            format_limit_event_time(
                expiry_label,
                next_credit.expires_at,
                time_mode,
                now,
            )
        )
    else:
        parts.append("expiry unknown")
    return " · ".join(parts)


def limit_reset_tray_warning(
    limits: ProviderLimits,
    now: datetime | None = None,
    *,
    time_mode: LimitTimeMode = DEFAULT_LIMIT_TIME_MODE,
) -> str:
    expiry = limit_reset_expiry(limits)
    urgency = limit_reset_urgency(limits, now)
    if expiry is None or urgency == "neutral":
        return ""
    marker = "🔴" if urgency == "critical" else "🟠"
    expiry_text = format_limit_event_time("expires", expiry, time_mode, now)
    return f"{marker} reset {expiry_text}"


def ordered_limit_windows(limits: ProviderLimits) -> list[LimitWindow]:
    """Keep headline limits first, followed by reserves and ancillary caps."""

    def key(window: LimitWindow) -> tuple[int, float, str]:
        label = window.label.lower()
        if label == "5-hour":
            priority = 0
        elif label == "weekly":
            priority = 1
        elif "luna reserve" in label:
            priority = 2
        elif "spend" in label:
            priority = 4
        else:
            priority = 3
        reset = window.resets_at.timestamp() if window.resets_at is not None else float("inf")
        return priority, reset, label

    return sorted(limits.windows, key=key)


def provider_limit_rows(
    provider_label: str,
    limits: ProviderLimits,
    now: datetime | None = None,
    *,
    display_mode: LimitDisplayMode = DEFAULT_LIMIT_DISPLAY_MODE,
    time_mode: LimitTimeMode = DEFAULT_LIMIT_TIME_MODE,
) -> list[LimitDisplayRow]:
    window_rows: list[LimitDisplayRow] = []
    plan = f" · {limits.plan}" if limits.plan else ""
    for window in ordered_limit_windows(limits):
        reset = (
            format_limit_event_time("resets", window.resets_at, time_mode, now)
            if window.resets_at else "reset unknown"
        )
        window_rows.append(
            LimitDisplayRow(
                text=(
                    f"{provider_label}{plan} · {window.label}: "
                    f"{limit_percent_text(window.used_percent, display_mode)} · {reset}"
                ),
                occurs_at=window.resets_at,
            )
        )

    rows = window_rows

    reset_summary = limit_reset_summary(limits, now, time_mode=time_mode)
    if reset_summary:
        urgency = limit_reset_urgency(limits, now)
        marker = "⚠ " if urgency != "neutral" else ""
        rows.append(
            LimitDisplayRow(
                text=f"[{marker}{provider_label} · {reset_summary}]",
                occurs_at=limit_reset_expiry(limits),
                urgency=urgency,
            )
        )

    return rows
