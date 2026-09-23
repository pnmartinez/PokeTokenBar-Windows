from __future__ import annotations

import glob
import json
import math
import os
import sqlite3
from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import ProviderUsage, UsageEntry, UsageSnapshot
from .pricing import cost_for
from .windows import (
    claude_desktop_roots,
)
from .windows import (
    cursor_database_candidates as native_cursor_database_candidates,
)
from .windows import (
    kiro_database_candidates as native_kiro_database_candidates,
)

PROVIDER_LABELS = {
    "claude": "Claude Code",
    "codex": "Codex",
    "gemini": "Gemini CLI",
    "opencode": "OpenCode",
    "hermes": "Hermes Agent",
    "cursor": "Cursor",
    "grok": "Grok CLI",
    "copilot": "Copilot CLI",
    "kiro": "Kiro CLI",
}


def _now_local() -> datetime:
    return datetime.now().astimezone()


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw <= 0:
            return None
        if raw >= 100_000_000_000:
            raw /= 1000.0
        try:
            return datetime.fromtimestamp(raw, tz=timezone.utc).astimezone()
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        # SQLite datetime('now') default shape.
        try:
            dt = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()


def _int(value: Any) -> int:
    try:
        if value is None or isinstance(value, bool):
            return 0
        return max(0, int(float(value)))
    except (TypeError, ValueError, OverflowError):
        return 0


def _float(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        out = float(value)
        return None if math.isnan(out) else out
    except (TypeError, ValueError, OverflowError):
        return None


def _entry(
    *,
    id: str,
    date: datetime,
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
    total_tokens: int = 0,
    explicit_cost: float | None = None,
) -> UsageEntry | None:
    input_tokens = max(0, input_tokens)
    output_tokens = max(0, output_tokens)
    cache_write_tokens = max(0, cache_write_tokens)
    cache_read_tokens = max(0, cache_read_tokens)
    parts = input_tokens + output_tokens + cache_write_tokens + cache_read_tokens
    if total_tokens > parts:
        output_tokens += total_tokens - parts
    if input_tokens + output_tokens + cache_write_tokens + cache_read_tokens <= 0:
        return None
    return UsageEntry(
        id=id,
        date=date,
        provider=provider,
        model=model or "unknown",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_write_tokens=cache_write_tokens,
        cache_read_tokens=cache_read_tokens,
        explicit_cost=explicit_cost,
    )


def _dedup_keep_max(entries: Iterable[UsageEntry]) -> list[UsageEntry]:
    by_id: dict[str, UsageEntry] = {}
    for entry in entries:
        old = by_id.get(entry.id)
        if old is None or entry.total_tokens > old.total_tokens:
            by_id[entry.id] = entry
    return list(by_id.values())


def _iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    yield obj
    except OSError:
        return


def _paths_from_env(name: str) -> list[Path] | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    return [Path(part.strip()).expanduser() for part in raw.split(",") if part.strip()]


def _files_newer(root: Path, patterns: tuple[str, ...], since: datetime) -> Iterator[Path]:
    if not root.exists():
        return
    seen: set[Path] = set()
    for pattern in patterns:
        for raw in glob.iglob(str(root / pattern), recursive=True):
            path = Path(raw)
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone()
            except OSError:
                continue
            if mtime >= since:
                yield path


# ---- Claude Code ---------------------------------------------------------

def claude_roots() -> list[Path]:
    home = Path.home()
    roots: list[Path] = []
    for config in _paths_from_env("CLAUDE_CONFIG_DIR") or []:
        roots.append(config / "projects")
    roots.extend([home / ".config/claude/projects", home / ".claude/projects"])
    # Native Windows Claude Desktop session stores; recursively scanned below.
    roots.extend(claude_desktop_roots())
    out: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve(strict=False))
        if key not in seen:
            seen.add(key)
            out.append(root)
    return out


def parse_claude_object(obj: dict[str, Any]) -> UsageEntry | None:
    if obj.get("type") != "assistant":
        return None
    msg = obj.get("message")
    if not isinstance(msg, dict):
        return None
    usage = msg.get("usage")
    if not isinstance(usage, dict):
        return None
    date = _parse_datetime(obj.get("timestamp"))
    if date is None:
        return None
    entry_id = f"{msg.get('id', '')}|{obj.get('requestId', '')}"
    return _entry(
        id=f"claude|{entry_id}",
        date=date,
        provider="claude",
        model=str(msg.get("model") or "unknown"),
        input_tokens=_int(usage.get("input_tokens")),
        output_tokens=_int(usage.get("output_tokens")),
        cache_write_tokens=_int(usage.get("cache_creation_input_tokens")),
        cache_read_tokens=_int(usage.get("cache_read_input_tokens")),
    )


def scan_claude(since: datetime) -> list[UsageEntry]:
    entries: list[UsageEntry] = []
    for root in claude_roots():
        # The normal roots contain logs directly; desktop session roots can hide
        # .claude/projects several levels below, so recursive JSONL scanning covers both.
        for path in _files_newer(root, ("**/*.jsonl",), since):
            for obj in _iter_jsonl(path):
                entry = parse_claude_object(obj)
                if entry is not None and entry.date >= since:
                    entries.append(entry)
    return _dedup_keep_max(entries)


# ---- Codex ---------------------------------------------------------------

def _codex_model(obj: dict[str, Any]) -> str | None:
    payload = obj.get("payload")
    if isinstance(payload, dict):
        model = payload.get("model")
        if isinstance(model, str) and model:
            return model
    model = obj.get("model")
    return model if isinstance(model, str) and model else None


def parse_codex_object(obj: dict[str, Any], *, file_id: str, turn: int, model: str) -> UsageEntry | None:
    payload = obj.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "token_count":
        return None
    info = payload.get("info")
    if not isinstance(info, dict):
        return None
    last = info.get("last_token_usage")
    if not isinstance(last, dict):
        return None
    date = _parse_datetime(obj.get("timestamp"))
    if date is None:
        return None
    full_input = _int(last.get("input_tokens"))
    cached = _int(last.get("cached_input_tokens"))
    return _entry(
        id=f"codex|{file_id}|{turn}",
        date=date,
        provider="codex",
        model=model,
        input_tokens=max(0, full_input - cached),
        output_tokens=_int(last.get("output_tokens")),
        cache_read_tokens=cached,
    )


def scan_codex(since: datetime) -> list[UsageEntry]:
    home = Path.home()
    roots = _paths_from_env("CODEX_HOME") or [home / ".codex"]
    entries: list[UsageEntry] = []
    for root in roots:
        files = list(_files_newer(root / "sessions", ("**/*.jsonl",), since))
        files += list(_files_newer(root / "archived_sessions", ("**/*.jsonl",), since))
        for path in files:
            model = "codex"
            turn = 0
            previous_fingerprint: str | None = None
            for obj in _iter_jsonl(path):
                found_model = _codex_model(obj)
                if found_model:
                    model = found_model
                payload = obj.get("payload")
                if not isinstance(payload, dict) or payload.get("type") != "token_count":
                    continue
                info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
                last = info.get("last_token_usage") if isinstance(info, dict) else None
                total = info.get("total_token_usage") if isinstance(info, dict) else None
                fingerprint = json.dumps([total, last], sort_keys=True, separators=(",", ":"), default=str)
                if fingerprint == previous_fingerprint:
                    continue
                previous_fingerprint = fingerprint
                entry = parse_codex_object(obj, file_id=str(path), turn=turn, model=model)
                turn += 1
                if entry is not None and entry.date >= since:
                    entries.append(entry)
    # Upstream performs a more sophisticated fork/replay reconciliation. Stable
    # fingerprints plus id/date dedupe remove the common duplicate snapshots.
    by_signature: dict[tuple[str, datetime, int, int, int], UsageEntry] = {}
    for entry in entries:
        key = (entry.model, entry.date, entry.input_tokens, entry.output_tokens, entry.cache_read_tokens)
        by_signature.setdefault(key, entry)
    return list(by_signature.values())


# ---- Gemini CLI ----------------------------------------------------------

def _gemini_entry(obj: dict[str, Any], file_id: str, fallback_date: datetime | None) -> UsageEntry | None:
    tokens = obj.get("tokens")
    if not isinstance(tokens, dict):
        return None
    date = _parse_datetime(obj.get("timestamp")) or fallback_date
    if date is None:
        return None
    input_total = _int(tokens.get("input"))
    cached = _int(tokens.get("cached"))
    return _entry(
        id=f"gemini|{file_id}|{obj.get('id') or repr(obj.get('timestamp'))}",
        date=date,
        provider="gemini",
        model=str(obj.get("model") or "gemini"),
        input_tokens=max(0, input_total - cached) + _int(tokens.get("tool")),
        output_tokens=_int(tokens.get("output")) + _int(tokens.get("thoughts")),
        cache_read_tokens=cached,
    )


def scan_gemini(since: datetime) -> list[UsageEntry]:
    root = (_paths_from_env("GEMINI_HOME") or [Path.home() / ".gemini"])[0] / "tmp"
    entries: list[UsageEntry] = []
    for path in _files_newer(root, ("**/chats/*.jsonl", "**/chats/*.json"), since):
        if path.suffix == ".jsonl":
            by_id: dict[str, UsageEntry] = {}
            last_date: datetime | None = None
            for obj in _iter_jsonl(path):
                last_date = _parse_datetime(obj.get("timestamp")) or last_date
                entry = _gemini_entry(obj, str(path), last_date)
                if entry is not None:
                    key = str(obj.get("id") or entry.id)
                    by_id[key] = entry
            entries.extend(v for v in by_id.values() if v.date >= since)
        else:
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(obj, dict):
                continue
            fallback = _parse_datetime(obj.get("startTime"))
            for message in obj.get("messages", []):
                if isinstance(message, dict):
                    entry = _gemini_entry(message, str(path), fallback)
                    if entry is not None and entry.date >= since:
                        entries.append(entry)
    return _dedup_keep_max(entries)


# ---- Grok CLI ------------------------------------------------------------

def parse_grok_object(envelope: dict[str, Any]) -> UsageEntry | None:
    notification = envelope.get("params") if isinstance(envelope.get("params"), dict) else envelope
    update = notification.get("update") if isinstance(notification, dict) else None
    if not isinstance(update, dict) or update.get("sessionUpdate") != "turn_completed":
        return None
    usage = update.get("usage")
    if not isinstance(usage, dict):
        return None
    meta = notification.get("_meta") if isinstance(notification.get("_meta"), dict) else {}
    if meta.get("isReplay") is True:
        return None
    turn_id = update.get("prompt_id")
    if not isinstance(turn_id, str) or not turn_id:
        return None
    date = _parse_datetime(envelope.get("timestamp")) or _parse_datetime(meta.get("timestamp"))
    if date is None:
        return None
    cached = _int(usage.get("cachedReadTokens") or usage.get("cached_read_tokens"))
    if usage.get("inputTokens") is not None:
        input_tokens = max(0, _int(usage.get("inputTokens")) - cached)
    else:
        input_tokens = _int(usage.get("input_tokens"))
    output_tokens = _int(usage.get("outputTokens") or usage.get("output_tokens"))
    total = _int(usage.get("totalTokens") or usage.get("total_tokens"))
    cost = _float(usage.get("costUsd"))
    if cost is None:
        ticks = _float(usage.get("costUsdTicks") or usage.get("cost_usd_ticks"))
        if ticks is not None:
            # xAI CLI uses micro-dollar ticks in current session records.
            cost = ticks / 1_000_000.0
    return _entry(
        id=f"grok|{turn_id}",
        date=date,
        provider="grok",
        model=str(usage.get("model") or update.get("model") or "grok"),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cached,
        total_tokens=total,
        explicit_cost=cost,
    )


def scan_grok(since: datetime) -> list[UsageEntry]:
    root = Path(os.environ.get("GROK_HOME", str(Path.home() / ".grok"))).expanduser() / "sessions"
    entries: list[UsageEntry] = []
    for path in _files_newer(root, ("**/updates.jsonl",), since):
        summary = path.parent / "summary.json"
        try:
            if summary.exists():
                data = json.loads(summary.read_text(encoding="utf-8"))
                if isinstance(data, dict) and str(data.get("session_kind", "")).startswith("subagent"):
                    continue
        except (OSError, json.JSONDecodeError):
            pass
        for obj in _iter_jsonl(path):
            entry = parse_grok_object(obj)
            if entry is not None and entry.date >= since:
                entries.append(entry)
    return _dedup_keep_max(entries)


# ---- SQLite helpers ------------------------------------------------------

def _open_sqlite_ro(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    uri = path.resolve().as_uri()
    for suffix in ("?mode=ro", "?mode=ro&immutable=1"):
        try:
            return sqlite3.connect(uri + suffix, uri=True, timeout=5.0)
        except sqlite3.Error:
            continue
    try:
        return sqlite3.connect(str(path), timeout=5.0)
    except sqlite3.Error:
        return None


def _json_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(value, str):
        return None
    try:
        obj = json.loads(value)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


# ---- OpenCode ------------------------------------------------------------

def _parse_opencode_message(obj: dict[str, Any], fallback_id: str) -> UsageEntry | None:
    tokens = obj.get("tokens")
    time = obj.get("time")
    if not isinstance(tokens, dict) or not isinstance(time, dict):
        return None
    date = _parse_datetime(time.get("created"))
    if date is None:
        return None
    cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
    return _entry(
        id=f"opencode|{obj.get('id') or fallback_id}",
        date=date,
        provider="opencode",
        model=str(obj.get("modelID") or "unknown"),
        input_tokens=_int(tokens.get("input")),
        output_tokens=_int(tokens.get("output")),
        cache_write_tokens=_int(cache.get("write")),
        cache_read_tokens=_int(cache.get("read")),
        total_tokens=_int(tokens.get("total")),
        explicit_cost=_float(obj.get("cost")),
    )


def scan_opencode(since: datetime) -> list[UsageEntry]:
    roots = _paths_from_env("OPENCODE_DATA_DIR") or [Path.home() / ".local/share/opencode"]
    entries: list[UsageEntry] = []
    for root in roots:
        db_candidates = [root] if root.suffix == ".db" else [root / "opencode.db"] + sorted(root.glob("opencode-*.db"))
        for db in db_candidates:
            conn = _open_sqlite_ro(db)
            if conn is None:
                continue
            try:
                try:
                    rows = conn.execute("SELECT id, session_id, data FROM message WHERE time_created >= ?", (int(since.timestamp() * 1000),))
                except sqlite3.Error:
                    rows = conn.execute("SELECT id, session_id, data FROM message")
                for row in rows:
                    obj = _json_dict(row[2])
                    if obj is None:
                        continue
                    entry = _parse_opencode_message(obj, str(row[0]))
                    if entry is not None and entry.date >= since:
                        entries.append(entry)
            except sqlite3.Error:
                pass
            finally:
                conn.close()
            if db.exists():
                break
        legacy = root / "storage/message"
        for path in _files_newer(legacy, ("**/*.json",), since):
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(obj, dict):
                entry = _parse_opencode_message(obj, path.stem)
                if entry is not None and entry.date >= since:
                    entries.append(entry)
    return _dedup_keep_max(entries)


# ---- Hermes --------------------------------------------------------------

def scan_hermes(since: datetime) -> list[UsageEntry]:
    roots = _paths_from_env("HERMES_HOME") or [Path.home() / ".hermes"]
    entries: list[UsageEntry] = []
    sql = """
        SELECT id, model, billing_provider, started_at, message_count,
               input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
               reasoning_tokens, estimated_cost_usd, actual_cost_usd
        FROM sessions
        WHERE model IS NOT NULL AND TRIM(model) != '' AND started_at >= ?
    """
    for root in roots:
        db = root if root.suffix == ".db" else root / "state.db"
        conn = _open_sqlite_ro(db)
        if conn is None:
            continue
        try:
            for row in conn.execute(sql, (int(since.timestamp()),)):
                date = _parse_datetime(row[3])
                if date is None:
                    continue
                actual = _float(row[11]) or 0.0
                estimated = _float(row[10]) or 0.0
                entry = _entry(
                    id=f"hermes|{row[0]}", date=date, provider="hermes", model=str(row[1]),
                    input_tokens=_int(row[5]), output_tokens=_int(row[6]) + _int(row[9]),
                    cache_read_tokens=_int(row[7]), cache_write_tokens=_int(row[8]),
                    explicit_cost=actual if actual > 0 else estimated,
                )
                if entry is not None and entry.date >= since:
                    entries.append(entry)
        except sqlite3.Error:
            pass
        finally:
            conn.close()
    return _dedup_keep_max(entries)


# ---- Cursor --------------------------------------------------------------

def cursor_database_candidates() -> list[Path]:
    roots = _paths_from_env("CURSOR_DATA_DIR")
    if roots:
        return [root if root.suffix == ".vscdb" else root / "state.vscdb" for root in roots]
    return native_cursor_database_candidates()


def scan_cursor(since: datetime) -> list[UsageEntry]:
    from .cursor import scan_cursor as scan_cursor_impl

    return scan_cursor_impl(since)


# ---- Copilot CLI ---------------------------------------------------------

def scan_copilot(since: datetime) -> list[UsageEntry]:
    roots = _paths_from_env("COPILOT_HOME") or [Path.home() / ".copilot"]
    entries: list[UsageEntry] = []
    sql = """
        SELECT id, model, input_tokens, output_tokens, cache_read_tokens,
               cache_write_tokens, created_at
        FROM assistant_usage_events
    """
    for root in roots:
        db = root if root.suffix == ".db" else root / "session-store.db"
        conn = _open_sqlite_ro(db)
        if conn is None:
            continue
        try:
            for row in conn.execute(sql):
                date = _parse_datetime(row[6])
                if date is None or date < since:
                    continue
                cache_read = _int(row[4])
                cache_write = _int(row[5])
                entry = _entry(
                    id=f"copilot|{db}|{row[0]}", date=date, provider="copilot",
                    model=str(row[1] or "unknown"),
                    input_tokens=max(0, _int(row[2]) - cache_read - cache_write),
                    output_tokens=_int(row[3]), cache_read_tokens=cache_read,
                    cache_write_tokens=cache_write,
                )
                if entry is not None:
                    entries.append(entry)
        except sqlite3.Error:
            pass
        finally:
            conn.close()
    return _dedup_keep_max(entries)


# ---- Kiro CLI ------------------------------------------------------------

def _kiro_value_bytes(value: Any) -> int:
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return len(str(value).encode("utf-8"))
    if isinstance(value, list):
        return sum(_kiro_value_bytes(item) for item in value)
    if isinstance(value, dict):
        return sum(_kiro_value_bytes(item) for item in value.values())
    return 0


def _kiro_field_bytes(value: Any) -> int:
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if not isinstance(value, dict):
        return 0
    return sum(_kiro_value_bytes(item) for key, item in value.items() if key != "images")


def _kiro_turn_entries(conversation_id: str, obj: dict[str, Any], since: datetime) -> list[UsageEntry]:
    history = obj.get("history")
    if not isinstance(history, list):
        return []
    cumulative = _kiro_value_bytes(obj.get("latest_summary", 0))
    out: list[UsageEntry] = []
    for turn in history:
        if not isinstance(turn, dict):
            continue
        user_bytes = _kiro_field_bytes(turn.get("user"))
        assistant_bytes = _kiro_field_bytes(turn.get("assistant"))
        meta = turn.get("request_metadata") if isinstance(turn.get("request_metadata"), dict) else None
        if meta:
            date = _parse_datetime(meta.get("request_start_timestamp_ms"))
            raw_ts = _float(meta.get("request_start_timestamp_ms"))
            if date is not None and raw_ts and date >= since:
                entry = _entry(
                    id=f"kiro|{conversation_id}|{int(raw_ts)}", date=date,
                    provider="kiro", model=str(meta.get("model_id") or "unknown"),
                    input_tokens=(cumulative + user_bytes) // 4,
                    output_tokens=_int(meta.get("response_size")) // 4,
                )
                if entry is not None:
                    out.append(entry)
        cumulative += user_bytes + assistant_bytes
    return out


def kiro_database_candidates() -> list[Path]:
    roots = _paths_from_env("KIRO_CLI_HOME")
    if roots:
        return [root if root.suffix == ".sqlite3" else root / "data.sqlite3" for root in roots]
    return native_kiro_database_candidates()


def scan_kiro(since: datetime) -> list[UsageEntry]:
    entries: list[UsageEntry] = []
    for db in kiro_database_candidates():
        conn = _open_sqlite_ro(db)
        if conn is None:
            continue
        any_query = False
        try:
            try:
                rows = list(conn.execute("SELECT conversation_id, value FROM conversations_v2"))
                any_query = True
                for conv_id, value in rows:
                    obj = _json_dict(value)
                    if obj is not None:
                        entries.extend(_kiro_turn_entries(str(conv_id or obj.get("conversation_id") or db), obj, since))
            except sqlite3.Error:
                pass
            try:
                rows = list(conn.execute("SELECT value FROM conversations"))
                any_query = True
                for (value,) in rows:
                    obj = _json_dict(value)
                    if obj is not None and obj.get("conversation_id"):
                        entries.extend(_kiro_turn_entries(str(obj["conversation_id"]), obj, since))
            except sqlite3.Error:
                pass
        finally:
            conn.close()
        if any_query:
            continue
    return _dedup_keep_max(entries)


SCANNERS = {
    "claude": scan_claude,
    "codex": scan_codex,
    "gemini": scan_gemini,
    "opencode": scan_opencode,
    "hermes": scan_hermes,
    "cursor": scan_cursor,
    "grok": scan_grok,
    "copilot": scan_copilot,
    "kiro": scan_kiro,
}


def _period_starts(now: datetime) -> tuple[datetime, datetime, datetime, datetime]:
    local_day = now.astimezone().date()
    # Resolve each midnight separately so a DST change inside the month does not
    # shift the scan boundary by an hour.
    today = datetime.combine(local_day, datetime.min.time()).astimezone()
    week = datetime.combine(
        local_day - timedelta(days=local_day.weekday()), datetime.min.time()
    ).astimezone()
    month = datetime.combine(
        local_day.replace(day=1), datetime.min.time()
    ).astimezone()
    block = now.astimezone() - timedelta(hours=5)
    return today, week, month, block


def month_daily_series(entries: list[UsageEntry], now: datetime) -> list[int]:
    """Return one total per local calendar day, from the first through today."""
    today = now.astimezone().date()
    first = today.replace(day=1)
    totals = [0] * today.day
    for entry in entries:
        day = entry.date.astimezone().date()
        if first <= day <= today:
            totals[day.day - 1] += entry.total_tokens
    return totals


def _entry_cost(entry: UsageEntry) -> float:
    if entry.provider == "cursor":
        return 0.0
    if entry.explicit_cost is not None and entry.explicit_cost > 0:
        return entry.explicit_cost
    return cost_for(
        entry.model, entry.input_tokens, entry.output_tokens,
        entry.cache_write_tokens, entry.cache_read_tokens,
    )


def month_daily_cost_series(entries: list[UsageEntry], now: datetime) -> list[float]:
    today = now.astimezone().date()
    first = today.replace(day=1)
    totals = [0.0] * today.day
    for entry in entries:
        day = entry.date.astimezone().date()
        if first <= day <= today:
            totals[day.day - 1] += _entry_cost(entry)
    return totals


def scan_month_history(now: datetime | None = None) -> dict[str, tuple[list[int], list[float]]]:
    """Scan local logs once on demand, then group historical usage by local month."""
    from calendar import monthrange
    from collections import defaultdict

    now = now or _now_local()
    since = datetime(2000, 1, 1).astimezone()
    entries_by_month: dict[str, list[UsageEntry]] = defaultdict(list)
    for provider, scanner in SCANNERS.items():
        try:
            if provider == "cursor":
                from .cursor import scan_cursor_local
                entries = scan_cursor_local(since)
            else:
                entries = scanner(since)
        except Exception:  # noqa: BLE001  # one inaccessible provider must not hide other history
            continue
        for entry in entries:
            day = entry.date.astimezone().date()
            if entry.total_tokens > 0 and day <= now.astimezone().date() and day.year >= 2000:
                entries_by_month[f"{day.year:04d}-{day.month:02d}"].append(entry)
    history = {}
    for key, entries in entries_by_month.items():
        year, month = map(int, key.split("-"))
        tokens = [0] * monthrange(year, month)[1]
        costs = [0.0] * len(tokens)
        for entry in entries:
            offset = entry.date.astimezone().day - 1
            tokens[offset] += entry.total_tokens
            costs[offset] += _entry_cost(entry)
        history[key] = (tokens, costs)
    return history


def scan_all(now: datetime | None = None) -> tuple[UsageSnapshot, dict[str, str]]:
    now = now or _now_local()
    today, week, month, block = _period_starts(now)
    errors: dict[str, str] = {}
    providers: dict[str, ProviderUsage] = {}
    for provider, scanner in SCANNERS.items():
        try:
            entries = scanner(month)
        except Exception as exc:  # noqa: BLE001  # a broken local DB should not take down the tray
            errors[provider] = f"{type(exc).__name__}: {exc}"
            entries = []
        if provider == "cursor" and not entries:
            from .cursor import last_scan_warning

            if last_scan_warning:
                errors["cursor"] = last_scan_warning
        if not entries:
            continue
        usage = ProviderUsage(
            provider=provider, entry_count=len(entries),
            month_daily=month_daily_series(entries, now),
            month_daily_cost=month_daily_cost_series(entries, now),
        )
        for entry in entries:
            local_day = entry.date.astimezone().date()
            if local_day > today.date():
                continue
            if local_day >= month.date():
                usage.month_tokens += entry.total_tokens
            if local_day >= week.date():
                usage.week_tokens += entry.total_tokens
            if entry.date >= block:
                usage.block_tokens += entry.total_tokens
            if local_day >= today.date():
                usage.today_tokens += entry.total_tokens
                usage.today_cost += _entry_cost(entry)
        providers[provider] = usage
    return UsageSnapshot(providers=providers, scanned_at=now), errors
