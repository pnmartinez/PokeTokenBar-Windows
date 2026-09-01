from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

from .formatting import (
    DEFAULT_LIMIT_DISPLAY_MODE,
    DEFAULT_LIMIT_TIME_MODE,
    LimitDisplayMode,
    LimitTimeMode,
    compact_tokens,
    format_limit_event_time,
    highest_relevant_limit,
    limit_alert_body,
    limit_percent_text,
    limit_reset_expiry,
    limit_reset_urgency,
    money,
)
from .models import ProviderLimits, UsageSnapshot


PET_MIN_SIZE = 48
PET_MAX_SIZE = 192
PET_SIZE_STEP = 8
PET_DEFAULT_SIZE = 96
PET_ALERT_TTL_MS = 6_000
PET_WARNING_PERCENT = 80.0
PET_CRITICAL_PERCENT = 95.0


def normalize_pet_size(value: Any) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return PET_DEFAULT_SIZE
    if not math.isfinite(number):
        return PET_DEFAULT_SIZE
    clamped = min(PET_MAX_SIZE, max(PET_MIN_SIZE, number))
    steps = round((clamped - PET_MIN_SIZE) / PET_SIZE_STEP)
    return int(PET_MIN_SIZE + steps * PET_SIZE_STEP)


def settings_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return default


@dataclass(slots=True, frozen=True)
class ScreenRect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + max(0, self.width)

    @property
    def bottom(self) -> int:
        return self.y + max(0, self.height)

    def overlap_area(self, x: float, y: float, size: int) -> float:
        width = max(0.0, min(x + size, self.right) - max(x, self.x))
        height = max(0.0, min(y + size, self.bottom) - max(y, self.y))
        return width * height

    def distance_squared(self, x: float, y: float) -> float:
        dx = max(self.x - x, 0.0, x - self.right)
        dy = max(self.y - y, 0.0, y - self.bottom)
        return dx * dx + dy * dy


def _clamp_axis(value: float, start: int, span: int, size: int, margin: int) -> int:
    low = start + margin
    high = start + span - margin - size
    if high < low:
        return round(start + (span - size) / 2)
    return round(min(high, max(low, value)))


def recover_pet_position(
    x: Any,
    y: Any,
    size: Any,
    screens: Sequence[ScreenRect],
    *,
    margin: int = 8,
) -> tuple[int, int]:
    """Clamp a pet fully into the nearest visible work area using logical Qt units."""
    pet_size = normalize_pet_size(size)
    try:
        px, py = float(x), float(y)
    except (TypeError, ValueError):
        px, py = math.nan, math.nan
    if not math.isfinite(px) or not math.isfinite(py):
        if not screens:
            return (120, 120)
        primary = screens[0]
        return (
            _clamp_axis(primary.right - pet_size - 24, primary.x, primary.width, pet_size, margin),
            _clamp_axis(primary.bottom - pet_size - 24, primary.y, primary.height, pet_size, margin),
        )
    usable = [screen for screen in screens if screen.width > 0 and screen.height > 0]
    if not usable:
        return (round(px), round(py))
    overlaps = [(screen.overlap_area(px, py, pet_size), screen) for screen in usable]
    area, target = max(overlaps, key=lambda item: item[0])
    if area <= 0:
        target = min(usable, key=lambda screen: screen.distance_squared(px, py))
    return (
        _clamp_axis(px, target.x, target.width, pet_size, margin),
        _clamp_axis(py, target.y, target.height, pet_size, margin),
    )


@dataclass(slots=True, frozen=True)
class AlertMemory:
    marker: float | None
    tier: int


@dataclass(slots=True, frozen=True)
class PetAlert:
    key: str
    title: str
    body: str
    severity: str
    tier: int
    priority: float


def load_alert_memory(raw: Any) -> dict[str, AlertMemory]:
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    result: dict[str, AlertMemory] = {}
    for key, item in data.items():
        if not isinstance(key, str) or not isinstance(item, dict):
            continue
        try:
            tier = int(item.get("tier", 0))
            marker_raw = item.get("marker")
            marker = float(marker_raw) if marker_raw is not None else None
        except (TypeError, ValueError):
            continue
        if tier not in (1, 2) or (marker is not None and not math.isfinite(marker)):
            continue
        result[key] = AlertMemory(marker, tier)
    return result


def dump_alert_memory(memory: Mapping[str, AlertMemory], limit: int = 200) -> str:
    bounded = list(memory.items())[-max(1, limit):]
    payload = {
        key: {"marker": value.marker, "tier": value.tier}
        for key, value in bounded
        if value.tier in (1, 2)
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _window_change_threshold_seconds(label: str) -> float:
    normalized = label.lower()
    if "week" in normalized or "7-day" in normalized or "seven" in normalized:
        return 3 * 24 * 60 * 60
    if "5-hour" in normalized or "5 hour" in normalized or "5h" in normalized:
        return 3 * 60 * 60
    return 6 * 60 * 60


def _same_window(previous: float | None, current: float | None, label: str) -> bool:
    if previous is None or current is None:
        return previous is current
    return abs(current - previous) < _window_change_threshold_seconds(label)


def _advance_alert(
    memory: dict[str, AlertMemory],
    *,
    key: str,
    marker: float | None,
    label: str,
    tier: int,
    title: str,
    body: str,
    priority: float,
) -> PetAlert | None:
    if tier <= 0:
        memory.pop(key, None)
        return None
    previous = memory.get(key)
    previous_tier = previous.tier if previous and _same_window(previous.marker, marker, label) else 0
    memory[key] = AlertMemory(marker, max(tier, previous_tier))
    if tier <= previous_tier:
        return None
    return PetAlert(
        key=key,
        title=title,
        body=body,
        severity="critical" if tier == 2 else "warning",
        tier=tier,
        priority=priority,
    )


def evaluate_pet_alerts(
    limits_by_provider: Mapping[str, ProviderLimits],
    memory: Mapping[str, AlertMemory] | None = None,
    now: datetime | None = None,
    *,
    warning_percent: float = PET_WARNING_PERCENT,
    critical_percent: float = PET_CRITICAL_PERCENT,
    display_mode: LimitDisplayMode = DEFAULT_LIMIT_DISPLAY_MODE,
    time_mode: LimitTimeMode = DEFAULT_LIMIT_TIME_MODE,
) -> tuple[list[PetAlert], dict[str, AlertMemory]]:
    """Edge-trigger limit and reset alerts while preserving one state per time window."""
    updated = dict(memory or {})
    alerts: list[PetAlert] = []
    for provider, status in limits_by_provider.items():
        provider_label = provider.title()
        for index, window in enumerate(status.windows):
            if "spend" in window.label.lower():
                continue
            used = float(window.used_percent)
            tier = 2 if used >= critical_percent else (1 if used >= warning_percent else 0)
            marker = window.resets_at.timestamp() if window.resets_at is not None else None
            alert = _advance_alert(
                updated,
                key=f"limit|{provider}|{index}|{window.label.lower()}",
                marker=marker,
                label=window.label,
                tier=tier,
                title="Critical limit" if tier == 2 else "Limit warning",
                body=limit_alert_body(provider_label, window.label, used, display_mode),
                priority=used,
            )
            if alert is not None:
                alerts.append(alert)

        expiry = limit_reset_expiry(status)
        urgency = limit_reset_urgency(status, now)
        reset_tier = 2 if urgency == "critical" else (1 if urgency == "warning" else 0)
        reset_marker = expiry.timestamp() if expiry is not None else None
        reset_alert = _advance_alert(
            updated,
            key=f"reset|{provider}",
            marker=reset_marker,
            label="full reset",
            tier=reset_tier,
            title="Full reset expires soon" if reset_tier == 2 else "Full reset reminder",
            body=(
                f"{provider_label} full reset "
                + format_limit_event_time("expires", expiry, time_mode, now)
                + "."
                if expiry is not None else f"{provider_label} full reset expiry is unknown."
            ),
            priority=100.0 if reset_tier == 2 else 80.0,
        )
        if reset_alert is not None:
            alerts.append(reset_alert)
    alerts.sort(key=lambda item: (item.tier, item.key), reverse=True)
    return alerts, updated


def choose_pet_alert(alerts: Sequence[PetAlert]) -> PetAlert | None:
    return max(alerts, key=lambda item: (item.tier, item.priority, item.key), default=None)


def pet_hover_text(
    snapshot: UsageSnapshot,
    limits_by_provider: Mapping[str, ProviderLimits],
    display_mode: LimitDisplayMode = DEFAULT_LIMIT_DISPLAY_MODE,
    *,
    time_mode: LimitTimeMode = DEFAULT_LIMIT_TIME_MODE,
    show_tokens: bool = True,
    show_cost: bool = False,
    show_limit: bool = True,
) -> str:
    lines: list[str] = []
    if show_tokens:
        lines.append(f"{compact_tokens(snapshot.today_tokens)} tokens today")
    if show_cost:
        lines.append(f"{money(snapshot.today_cost)} estimated cost today")
    if show_limit:
        selected = highest_relevant_limit(snapshot, limits_by_provider)
        if selected is not None:
            provider, window = selected
            lines.append(
                f"{provider.title()} {window.label}: "
                f"{limit_percent_text(window.used_percent, display_mode, compact=True)}"
            )

    reset_warnings: list[tuple[float, str]] = []
    if show_limit:
        for provider, status in limits_by_provider.items():
            urgency = limit_reset_urgency(status)
            expiry = limit_reset_expiry(status)
            if urgency != "neutral" and expiry is not None:
                marker = "Critical" if urgency == "critical" else "Warning"
                reset_warnings.append(
                    (
                        expiry.timestamp(),
                        f"{marker}: {provider.title()} full reset "
                        + format_limit_event_time("expires", expiry, time_mode),
                    )
                )
    if reset_warnings:
        lines.append(min(reset_warnings, key=lambda item: item[0])[1])
    return "\n".join(lines)
