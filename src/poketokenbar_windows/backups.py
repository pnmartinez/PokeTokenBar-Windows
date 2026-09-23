"""Local, timestamped save snapshots and conservative automatic retention."""

from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

AUTO_NAME = re.compile(
    r"^state-backup-(daily|limit)-(\d{8}-\d{6}-\d{6}[+-]\d{4})-[0-9a-f]{8}\.json$"
)
STAMP_FORMAT = "%Y%m%d-%H%M%S-%f%z"
AUTOMATIC_KINDS = frozenset({"daily", "limit"})
ALL_KINDS = AUTOMATIC_KINDS | {"manual", "before-import", "imported"}


def local_now() -> datetime:
    return datetime.now().astimezone()


def backup_filename(kind: str, when: datetime | None = None) -> str:
    if kind not in ALL_KINDS:
        raise ValueError(f"Unknown backup kind: {kind}")
    moment = when or local_now()
    if moment.tzinfo is None:
        raise ValueError("Backup timestamps must include a timezone")
    return f"state-backup-{kind}-{moment.strftime(STAMP_FORMAT)}-{uuid4().hex[:8]}.json"


def backup_path(state_path: Path, kind: str, when: datetime | None = None) -> Path:
    return state_path.with_name(backup_filename(kind, when))


@contextmanager
def save_lock(path: Path):
    """Serialize cooperating application versions across threads and processes."""
    lock_path = path.with_name(f".{path.name}.lock")
    with lock_path.open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            for attempt in range(400):
                try:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if attempt == 399:
                        raise
                    time.sleep(0.025)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def atomic_write(path: Path, contents: str) -> None:
    """Replace a file only after the complete sibling temp file has been written."""
    tmp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def _valid_snapshot(path: Path) -> bool:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(raw, dict)
        and isinstance(raw.get("catches"), list)
        and all(isinstance(item, dict) for item in raw["catches"])
        and (raw.get("mon") is None or isinstance(raw.get("mon"), dict))
        and isinstance(raw.get("inventory", {}), dict)
        and "egg_usage" in raw
    )


def _automatic_files(folder: Path) -> list[tuple[Path, str, datetime]]:
    results = []
    for path in folder.iterdir():
        match = AUTO_NAME.fullmatch(path.name)
        if match is None or not path.is_file() or not _valid_snapshot(path):
            continue
        try:
            moment = datetime.strptime(match.group(2), STAMP_FORMAT)
        except ValueError:
            continue
        results.append((path, match.group(1), moment))
    return results


def has_automatic_backup_today(state_path: Path, when: datetime | None = None) -> bool:
    moment = when or local_now()
    return any(
        saved_at.date() == moment.date()
        for _, _, saved_at in _automatic_files(state_path.parent)
    )


def prune_automatic_backups(state_path: Path, when: datetime | None = None) -> list[Path]:
    """Keep dense recent history, then daily, weekly, and monthly checkpoints.

    Only known automatic filenames containing valid saves are eligible for deletion.
    Manual, pre-import, legacy, and unrecognized files are never touched.
    """
    moment = when or local_now()
    files = sorted(_automatic_files(state_path.parent), key=lambda item: (item[2], item[0].name), reverse=True)
    chosen: set[tuple[object, ...]] = set()
    removed: list[Path] = []
    for path, _, saved_at in files:
        age = moment - saved_at
        if age < timedelta(0):
            continue
        if age <= timedelta(hours=48):
            continue
        if age <= timedelta(days=7):
            bucket: tuple[object, ...] = ("day", saved_at.date())
        elif age <= timedelta(days=35):
            iso = saved_at.isocalendar()
            bucket = ("week", iso.year, iso.week)
        else:
            months_ago = (moment.year - saved_at.year) * 12 + moment.month - saved_at.month
            bucket = ("month", saved_at.year, saved_at.month) if 0 <= months_ago <= 12 else ()
        if bucket and bucket not in chosen:
            chosen.add(bucket)
            continue
        path.unlink()
        removed.append(path)
    return removed


def write_backup(
    state_path: Path,
    kind: str,
    contents: str,
    when: datetime | None = None,
) -> Path:
    target = backup_path(state_path, kind, when)
    atomic_write(target, contents)
    if not _valid_snapshot(target):
        raise ValueError(f"Backup failed validation: {target}")
    if kind in AUTOMATIC_KINDS:
        prune_automatic_backups(state_path, when)
    return target


def ensure_daily_backup(
    state_path: Path,
    contents: str,
    when: datetime | None = None,
) -> Path | None:
    moment = when or local_now()
    if has_automatic_backup_today(state_path, moment):
        return None
    return write_backup(state_path, "daily", contents, moment)
