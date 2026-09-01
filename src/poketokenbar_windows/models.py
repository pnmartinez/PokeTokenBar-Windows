from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True, frozen=True)
class UsageEntry:
    id: str
    date: datetime
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    explicit_cost: float | None = None

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_write_tokens
            + self.cache_read_tokens
        )


@dataclass(slots=True)
class ProviderUsage:
    provider: str
    today_tokens: int = 0
    week_tokens: int = 0
    month_tokens: int = 0
    block_tokens: int = 0
    today_cost: float = 0.0
    entry_count: int = 0


@dataclass(slots=True)
class UsageSnapshot:
    providers: dict[str, ProviderUsage] = field(default_factory=dict)
    scanned_at: datetime | None = None

    @property
    def today_tokens(self) -> int:
        return sum(v.today_tokens for v in self.providers.values())

    @property
    def week_tokens(self) -> int:
        return sum(v.week_tokens for v in self.providers.values())

    @property
    def month_tokens(self) -> int:
        return sum(v.month_tokens for v in self.providers.values())

    @property
    def block_tokens(self) -> int:
        return sum(v.block_tokens for v in self.providers.values())

    @property
    def today_cost(self) -> float:
        return sum(v.today_cost for v in self.providers.values())


@dataclass(slots=True)
class LimitWindow:
    label: str
    used_percent: float
    resets_at: datetime | None = None
    duration_minutes: int | None = None
    identifier: str | None = None

    @property
    def remaining_percent(self) -> float:
        return max(0.0, min(100.0, 100.0 - self.used_percent))


@dataclass(slots=True)
class RateLimitResetCredit:
    title: str | None = None
    description: str | None = None
    status: str | None = None
    expires_at: datetime | None = None


@dataclass(slots=True)
class ProviderLimits:
    provider: str
    plan: str | None = None
    windows: list[LimitWindow] = field(default_factory=list)
    reserve_active: bool = False
    reset_credits_available: int = 0
    reset_credits: list[RateLimitResetCredit] = field(default_factory=list)
    error: str | None = None
