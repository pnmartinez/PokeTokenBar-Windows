from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from .models import ProviderLimits


LIMIT_NOTIFICATIONS_KEY = "limitNotifications"
LIMIT_RESET_NOTIFICATIONS_KEY = "limitResetNotifications"
BANKED_RESET_NOTIFICATIONS_KEY = "bankedResetNotifications"
WARNING_THRESHOLD_KEY = "warnThreshold"
CRITICAL_THRESHOLD_KEY = "critThreshold"
COMPANION_NOTIFICATIONS_KEY = "companionNotifications"

DEFAULT_LIMIT_NOTIFICATIONS = True
DEFAULT_LIMIT_RESET_NOTIFICATIONS = True
DEFAULT_BANKED_RESET_NOTIFICATIONS = True
DEFAULT_WARNING_THRESHOLD = 80
DEFAULT_CRITICAL_THRESHOLD = 95
DEFAULT_COMPANION_NOTIFICATIONS = True

WARNING_MIN = 50
WARNING_MAX = 95
CRITICAL_MIN = 80
CRITICAL_MAX = 100
THRESHOLD_STEP = 5


def _normalize_threshold(value: Any, *, minimum: int, maximum: int, default: int) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    clamped = min(maximum, max(minimum, number))
    steps = round((clamped - minimum) / THRESHOLD_STEP)
    return int(minimum + steps * THRESHOLD_STEP)


def normalize_warning_threshold(value: Any) -> int:
    return _normalize_threshold(
        value,
        minimum=WARNING_MIN,
        maximum=WARNING_MAX,
        default=DEFAULT_WARNING_THRESHOLD,
    )


def normalize_critical_threshold(value: Any) -> int:
    return _normalize_threshold(
        value,
        minimum=CRITICAL_MIN,
        maximum=CRITICAL_MAX,
        default=DEFAULT_CRITICAL_THRESHOLD,
    )


@dataclass(slots=True, frozen=True)
class LimitAlert:
    key: str
    provider: str
    window_label: str
    used_percent: float
    severity: str
    tier: int


def evaluate_limit_alerts(
    limits_by_provider: Mapping[str, ProviderLimits],
    tiers: Mapping[str, int] | None = None,
    *,
    warning_percent: float = DEFAULT_WARNING_THRESHOLD,
    critical_percent: float = DEFAULT_CRITICAL_THRESHOLD,
) -> tuple[list[LimitAlert], dict[str, int]]:
    """Return edge-triggered alerts, independently keyed per provider/window."""
    updated = dict(tiers or {})
    alerts: list[LimitAlert] = []
    for provider, status in limits_by_provider.items():
        for index, window in enumerate(status.windows):
            used = float(window.used_percent)
            tier = 2 if used >= critical_percent else (1 if used >= warning_percent else 0)
            key = f"limit|{provider}|{index}|{window.label.lower()}"
            if tier <= 0:
                updated.pop(key, None)
                continue
            previous_tier = int(updated.get(key, 0))
            updated[key] = max(tier, previous_tier)
            if tier <= previous_tier:
                continue
            alerts.append(
                LimitAlert(
                    key=key,
                    provider=provider,
                    window_label=window.label,
                    used_percent=used,
                    severity="critical" if tier == 2 else "warning",
                    tier=tier,
                )
            )
    alerts.sort(key=lambda alert: (alert.tier, alert.used_percent, alert.key), reverse=True)
    return alerts, updated


@dataclass(slots=True, frozen=True)
class LimitChange:
    kind: str
    provider: str
    window_label: str = ""
    previous_count: int = 0
    count: int = 0


def evaluate_limit_changes(
    limits_by_provider: Mapping[str, ProviderLimits],
    observations: Mapping[str, float | int] | None = None,
) -> tuple[list[LimitChange], dict[str, float | int]]:
    """Detect fully depleted limit resets and newly granted reset credits.

    The first valid observation is a baseline, so startup never claims that a
    reset or grant just happened. Missing or failed provider data is ignored.
    """
    updated = dict(observations or {})
    changes: list[LimitChange] = []
    for provider, status in limits_by_provider.items():
        if status.error:
            continue
        for index, window in enumerate(status.windows):
            used = float(window.used_percent)
            if not math.isfinite(used):
                continue
            identity = window.identifier or f"{index}|{window.label.lower()}"
            key = f"used|{provider}|{identity}"
            previous = updated.get(key)
            if previous is not None and float(previous) < 99.5 and used >= 99.5:
                changes.append(LimitChange("depleted", provider, window.label))
            if previous is not None and float(previous) >= 99.5 and used <= 0.5:
                changes.append(LimitChange("recovered", provider, window.label))
            updated[key] = used

        if status.reset_credits_known:
            key = f"credits|{provider}"
            count = max(0, int(status.reset_credits_available))
            previous = updated.get(key)
            if previous is not None and count > int(previous):
                changes.append(
                    LimitChange(
                        "banked", provider,
                        previous_count=int(previous), count=count,
                    )
                )
            updated[key] = count
    return changes, updated


@dataclass(slots=True, frozen=True)
class CompanionNotification:
    title: str
    body: str
    use_sprite_icon: bool = False


def companion_notification(event: str, display_name: str) -> CompanionNotification | None:
    if event.startswith("hatched:"):
        return CompanionNotification("Pokemon hatched!", display_name, use_sprite_icon=True)
    if event.startswith("evolved:"):
        return CompanionNotification("Evolution!", display_name)
    if event.startswith("graduated:"):
        return CompanionNotification("Pokemon graduated!", "A new egg is ready.")
    if event.startswith("candy:"):
        parts = event.split(":", 3)
        count = parts[1] if len(parts) > 1 else "1"
        return CompanionNotification("Rare Candy earned!", f"You earned {count} Rare Candy.")
    return None
