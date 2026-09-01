from __future__ import annotations

import json
import math
import os
import queue
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import LimitWindow, ProviderLimits, RateLimitResetCredit
from .windows import (
    APP_NAME,
    claude_plan_usage_paths,
    hidden_subprocess_kwargs,
    local_appdata,
    resolve_gui_binary,
)

CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_LOCAL_USAGE_MAX_AGE = timedelta(hours=1)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw >= 100_000_000_000:
            raw /= 1000.0
        try:
            return datetime.fromtimestamp(raw, tz=timezone.utc).astimezone()
        except (OSError, ValueError, OverflowError):
            return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()


def _plan_display(subscription_type: str | None, tier: str | None) -> str | None:
    if not subscription_type:
        return None
    base = subscription_type[:1].upper() + subscription_type[1:]
    if tier:
        for part in tier.split("_"):
            if part.endswith("x") and part[:-1].isdigit():
                return f"{base} {part}"
    return base


def _claude_credential_paths() -> list[Path]:
    home = Path.home()
    paths: list[Path] = []
    raw = os.environ.get("CLAUDE_CONFIG_DIR")
    if raw:
        for part in raw.split(","):
            part = part.strip()
            if part:
                paths.append(Path(part).expanduser() / ".credentials.json")
    paths.extend([home / ".config/claude/.credentials.json", home / ".claude/.credentials.json"])
    return paths


def _read_claude_oauth() -> tuple[str, str | None, str | None] | None:
    for path in _claude_credential_paths():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or not isinstance(data.get("claudeAiOauth"), dict):
            continue
        oauth = data["claudeAiOauth"]
        token = oauth.get("accessToken")
        if not isinstance(token, str) or not token:
            continue
        expires = _parse_datetime(oauth.get("expiresAt"))
        if expires is not None and expires.timestamp() <= datetime.now().astimezone().timestamp() + 60:
            continue
        return token, oauth.get("subscriptionType"), oauth.get("rateLimitTier")
    return None


def _read_claude_local_limits(now: datetime | None = None) -> ProviderLimits | None:
    """Read the newest fresh usage sample written by Claude Desktop.

    Microsoft Store builds keep current authentication inside their app
    container, so the traditional Claude Code OAuth file can be unavailable or
    expired even while Desktop is signed in. Its local plan history provides a
    privacy-preserving fallback for the two standard utilization windows.
    """
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc).astimezone()

    newest: tuple[datetime, dict[str, Any]] | None = None
    for path in claude_plan_usage_paths():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("version") != 2:
            continue
        samples = data.get("samples")
        if not isinstance(samples, list):
            continue
        for sample in samples:
            if not isinstance(sample, dict) or not isinstance(sample.get("u"), dict):
                continue
            sampled_at = _parse_datetime(sample.get("t"))
            if sampled_at is None:
                continue
            if newest is None or sampled_at > newest[0]:
                newest = sampled_at, sample["u"]

    if newest is None:
        return None
    sampled_at, usage = newest
    age = current - sampled_at.astimezone(current.tzinfo)
    if age < -timedelta(minutes=5) or age > CLAUDE_LOCAL_USAGE_MAX_AGE:
        return None

    windows: list[LimitWindow] = []
    for key, label in (("fh", "5-hour"), ("sd", "Weekly")):
        try:
            used = float(usage[key])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(used):
            windows.append(LimitWindow(label=label, used_percent=used))
    if not windows:
        return None
    return ProviderLimits(provider="claude", windows=windows)


def _claude_fallback(error: str) -> ProviderLimits:
    return _read_claude_local_limits() or ProviderLimits(provider="claude", error=error)


def fetch_claude_limits(timeout: float = 12.0) -> ProviderLimits:
    credential = _read_claude_oauth()
    if credential is None:
        return _claude_fallback("Claude OAuth credentials not found")
    token, subscription_type, rate_limit_tier = credential
    request = urllib.request.Request(
        CLAUDE_USAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "Accept": "application/json",
            "User-Agent": "PokeTokenBar-Windows/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        return _claude_fallback(f"Claude limits HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return _claude_fallback(f"Claude limits: {exc}")
    if not isinstance(data, dict):
        return _claude_fallback("Claude limits returned an unexpected payload")

    windows: list[LimitWindow] = []
    for key, label, duration in (
        ("five_hour", "5-hour", 300),
        ("seven_day", "Weekly", 10_080),
    ):
        raw = data.get(key)
        if isinstance(raw, dict) and raw.get("utilization") is not None:
            try:
                used = float(raw["utilization"])
            except (TypeError, ValueError):
                continue
            windows.append(LimitWindow(
                label=label,
                used_percent=used,
                resets_at=_parse_datetime(raw.get("resets_at")),
                duration_minutes=duration,
            ))

    # Newer Claude usage responses can include a generalized limits[] list.
    for item in data.get("limits", []) if isinstance(data.get("limits"), list) else []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        if windows and kind in {"session", "weekly_all"}:
            continue
        percent = item.get("percent")
        if percent is None:
            continue
        try:
            used = float(percent)
        except (TypeError, ValueError):
            continue
        scope = item.get("scope") if isinstance(item.get("scope"), dict) else {}
        model = scope.get("model") if isinstance(scope.get("model"), dict) else {}
        display = model.get("display_name") if isinstance(model, dict) else None
        label = str(display or item.get("group") or kind or "Limit").replace("_", " ").title()
        duration = 300 if kind == "session" else (10_080 if kind.startswith("weekly") else None)
        windows.append(LimitWindow(
            label=label,
            used_percent=used,
            resets_at=_parse_datetime(item.get("resets_at")),
            duration_minutes=duration,
        ))

    result = ProviderLimits(
        provider="claude",
        plan=_plan_display(subscription_type, rate_limit_tier),
        windows=windows,
    )
    return result if result.windows else (_read_claude_local_limits() or result)


def _find_codex() -> str | None:
    override = os.environ.get("CODEX_BIN")
    if override:
        override_path = Path(override).expanduser()
        if override_path.is_file():
            return str(override_path)

    desktop_bin = local_appdata() / "OpenAI/Codex/bin"
    desktop_candidates = [desktop_bin / "codex.exe", *desktop_bin.glob("*/codex.exe")]

    def modified_time(path: Path) -> float:
        try:
            return path.stat().st_mtime if path.is_file() else -1.0
        except OSError:
            return -1.0

    desktop_candidates.sort(key=modified_time, reverse=True)
    candidates = desktop_candidates + [
        Path.home() / ".codex/bin/codex",
        Path.home() / ".codex/bin/codex.exe",
        Path.home() / ".local/bin/codex",
        Path("/usr/local/bin/codex"),
        Path("/usr/bin/codex"),
    ]
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which("codex")


def _codex_request_lines() -> str:
    messages = [
        {
            "method": "initialize",
            "id": 0,
            "params": {
                "clientInfo": {"name": "poketokenbar_windows", "title": APP_NAME, "version": "0.1.0"},
                "capabilities": {"experimentalApi": True},
            },
        },
        {"method": "initialized", "params": {}},
        {"method": "account/rateLimits/read", "id": 1, "params": {}},
    ]
    return "".join(json.dumps(message, separators=(",", ":")) + "\n" for message in messages)


def _read_codex_stream(
    source: str,
    stream: Any,
    messages: queue.Queue[tuple[str, str | None]],
) -> None:
    try:
        for line in iter(stream.readline, ""):
            messages.put((source, line.rstrip()))
    finally:
        messages.put((source, None))


def _stop_codex_process(proc: subprocess.Popen[str]) -> None:
    if proc.stdin is not None:
        try:
            proc.stdin.close()
        except OSError:
            pass
    if proc.poll() is None:
        try:
            proc.terminate()
        except OSError:
            pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
    for stream in (proc.stdout, proc.stderr):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass


def _codex_rpc_result(binary: str, timeout: float) -> dict[str, Any]:
    proc = subprocess.Popen(
        [binary, "app-server", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        **hidden_subprocess_kwargs(),
    )
    if proc.stdin is None or proc.stdout is None or proc.stderr is None:
        _stop_codex_process(proc)
        raise RuntimeError("Codex app-server pipes are unavailable")

    messages: queue.Queue[tuple[str, str | None]] = queue.Queue()
    readers = [
        threading.Thread(target=_read_codex_stream, args=("stdout", proc.stdout, messages), daemon=True),
        threading.Thread(target=_read_codex_stream, args=("stderr", proc.stderr, messages), daemon=True),
    ]
    for reader in readers:
        reader.start()

    last_stderr = ""
    deadline = time.monotonic() + timeout
    try:
        proc.stdin.write(_codex_request_lines())
        proc.stdin.flush()
        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                source, line = messages.get(timeout=min(0.25, remaining))
            except queue.Empty:
                if proc.poll() is not None:
                    break
                continue
            if line is None:
                if source == "stdout" and proc.poll() is not None:
                    break
                continue
            if source == "stderr":
                last_stderr = line[-300:]
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict) or obj.get("id") != 1:
                continue
            error = obj.get("error")
            if isinstance(error, dict):
                raise RuntimeError(str(error.get("message") or error))  # noqa: TRY004
            result = obj.get("result")
            if not isinstance(result, dict):
                raise RuntimeError("Codex app-server returned an unexpected rate-limit response")  # noqa: TRY004
            return result

        if proc.poll() is None:
            raise TimeoutError("timed out waiting for the Codex rate-limit response")
        detail = last_stderr or f"app-server exited with code {proc.returncode} without a rate-limit response"
        raise RuntimeError(detail)
    finally:
        _stop_codex_process(proc)


def _codex_window(raw: Any, label: str, *, identifier: str | None = None) -> LimitWindow | None:
    if not isinstance(raw, dict):
        return None
    used = raw.get("usedPercent")
    if used is None:
        used = raw.get("used_percent")
    try:
        percent = float(used)
    except (TypeError, ValueError):
        return None
    duration_raw = raw.get("windowDurationMins") or raw.get("window_duration_mins")
    try:
        duration = int(duration_raw) if duration_raw is not None else None
    except (TypeError, ValueError):
        duration = None
    if duration == 300:
        label = "5-hour"
    elif duration == 10080:
        label = "Weekly"
    resets = raw.get("resetsAt") if raw.get("resetsAt") is not None else raw.get("resets_at")
    return LimitWindow(
        label=label,
        used_percent=percent,
        resets_at=_parse_datetime(resets),
        duration_minutes=duration,
        identifier=identifier,
    )


def _codex_reset_credits(payload: dict[str, Any]) -> tuple[int, list[RateLimitResetCredit]]:
    raw = payload.get("rateLimitResetCredits")
    if raw is None:
        raw = payload.get("rate_limit_reset_credits")
    if not isinstance(raw, dict):
        return 0, []

    credits: list[RateLimitResetCredit] = []
    details = raw.get("credits")
    if isinstance(details, list):
        for item in details:
            if not isinstance(item, dict):
                continue
            status = item.get("status")
            if status is not None and str(status).lower() != "available":
                continue
            expires_at = item.get("expiresAt")
            if expires_at is None:
                expires_at = item.get("expires_at")
            credits.append(
                RateLimitResetCredit(
                    title=str(item["title"]) if item.get("title") else None,
                    description=str(item["description"]) if item.get("description") else None,
                    status=str(status) if status is not None else None,
                    expires_at=_parse_datetime(expires_at),
                )
            )

    count = raw.get("availableCount")
    if count is None:
        count = raw.get("available_count")
    try:
        available_count = max(0, int(count))
    except (TypeError, ValueError):
        available_count = len(credits)
    return available_count, credits


def _codex_rate_limit_snapshots(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return visible Codex buckets with the headline bucket first.

    Codex now exposes the Luna Reserve allowance as the
    ``base_model_inference``/``gpt-reserve`` bucket.  The upstream app shows all
    buckets that contain an actual time or spend window, so keep the same rule
    instead of discarding every non-``codex`` entry.
    """
    by_id = payload.get("rateLimitsByLimitId")
    if by_id is None:
        by_id = payload.get("rate_limits_by_limit_id")
    if isinstance(by_id, dict):
        headline = by_id.get("codex")
        if not isinstance(headline, dict):
            headline = None
        if headline is None:
            for item in by_id.values():
                if not isinstance(item, dict):
                    continue
                limit_id = item.get("limitId")
                if limit_id is None:
                    limit_id = item.get("limit_id")
                if limit_id == "codex":
                    headline = item
                    break

        snapshots = [headline] if headline is not None else []
        headline_id = None
        if headline is not None:
            headline_id = headline.get("limitId") or headline.get("limit_id") or "codex"
        for key, item in sorted(by_id.items(), key=lambda pair: str(pair[0])):
            if not isinstance(item, dict):
                continue
            limit_id = item.get("limitId")
            if limit_id is None:
                limit_id = item.get("limit_id")
            resolved_id = limit_id or str(key)
            if item is headline or resolved_id == headline_id:
                continue
            if any(
                isinstance(item.get(field), dict)
                for field in ("primary", "secondary", "individualLimit", "individual_limit")
            ):
                snapshots.append(item)
        if snapshots:
            return snapshots

    legacy = payload.get("rateLimits")
    if legacy is None:
        legacy = payload.get("rate_limits")
    if isinstance(legacy, dict):
        return [legacy]
    if any(key in payload for key in ("primary", "secondary", "individualLimit", "individual_limit")):
        return [payload]
    return []


def _codex_bucket_display_name(snapshot: dict[str, Any]) -> str:
    limit_id = str(snapshot.get("limitId") or snapshot.get("limit_id") or "").strip()
    limit_name = str(snapshot.get("limitName") or snapshot.get("limit_name") or "").strip()
    normalized_id = limit_id.lower().replace("-", "_")
    normalized_name = limit_name.lower().replace("_", "-")
    if normalized_id == "base_model_inference" or normalized_name in {
        "gpt-reserve",
        "luna-reserve",
        "luna reserve",
    }:
        return "Luna Reserve"
    raw = limit_name or limit_id or "Codex limit"
    return raw.replace("_", " ").replace("-", " ").strip().title()


def fetch_codex_limits(timeout: float = 20.0) -> ProviderLimits:
    binary = _find_codex()
    if binary is None:
        return ProviderLimits(provider="codex", error="codex executable not found")
    binary = resolve_gui_binary(binary)
    try:
        payload = _codex_rpc_result(binary, timeout)
    except (OSError, RuntimeError, TimeoutError, subprocess.SubprocessError) as exc:
        return ProviderLimits(provider="codex", error=f"Codex limits: {exc}")

    snapshots = _codex_rate_limit_snapshots(payload)

    windows: list[LimitWindow] = []
    plan: str | None = None
    reserve_active = False
    for index, snapshot in enumerate(snapshots):
        limit_id = str(
            snapshot.get("limitId")
            or snapshot.get("limit_id")
            or ("codex" if index == 0 else f"codex-{index}")
        )
        name = _codex_bucket_display_name(snapshot)
        if index == 0:
            reached_type = str(
                snapshot.get("rateLimitReachedType")
                or snapshot.get("rate_limit_reached_type")
                or ""
            )
            reserve_active = reached_type.strip().lower() == "rate_limit_reached"
        plan = plan or snapshot.get("planType")
        parsed_windows = [
            window
            for window in (
                _codex_window(
                    snapshot.get("primary"),
                    f"{name} primary",
                    identifier=f"{limit_id}.primary",
                ),
                _codex_window(
                    snapshot.get("secondary"),
                    f"{name} secondary",
                    identifier=f"{limit_id}.secondary",
                ),
            )
            if window is not None
        ]
        if limit_id != "codex":
            for window in parsed_windows:
                duration_label = window.label
                window.label = name if len(parsed_windows) == 1 else f"{name} · {duration_label}"
        windows.extend(parsed_windows)
        individual = snapshot.get("individualLimit") or snapshot.get("individual_limit")
        if isinstance(individual, dict):
            remaining = individual.get("remainingPercent")
            if remaining is None:
                remaining = individual.get("remaining_percent")
            try:
                used = max(0.0, min(100.0, 100.0 - float(remaining)))
            except (TypeError, ValueError):
                used = None
            if used is not None:
                windows.append(LimitWindow(
                    label=f"{name} spend",
                    used_percent=used,
                    resets_at=_parse_datetime(individual.get("resetsAt") or individual.get("resets_at")),
                    identifier=f"{limit_id}.individual",
                ))

    reset_credits_available, reset_credits = _codex_reset_credits(payload)
    return ProviderLimits(
        provider="codex",
        plan=str(plan).title() if plan else None,
        windows=windows,
        reserve_active=reserve_active,
        reset_credits_available=reset_credits_available,
        reset_credits=reset_credits,
    )


def fetch_all_limits() -> dict[str, ProviderLimits]:
    # Called from a worker thread by the UI, so sequential network/process access is fine.
    return {"claude": fetch_claude_limits(), "codex": fetch_codex_limits()}
