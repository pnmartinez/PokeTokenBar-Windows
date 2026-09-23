from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from poketokenbar_windows.backups import (
    atomic_write,
    backup_path,
    ensure_daily_backup,
    has_automatic_backup_today,
    prune_automatic_backups,
    write_backup,
)
from poketokenbar_windows.state import CatchRecord, GameState, StateStore


TZ = timezone(timedelta(hours=2))
NOW = datetime(2026, 9, 23, 12, 0, tzinfo=TZ)
EMPTY_SAVE = json.dumps({"version": 2, "egg_usage": 0, "mon": None, "catches": []})


class BackupTests(unittest.TestCase):
    def test_daily_backup_is_created_once_per_used_day_and_limit_adds_an_event(self):
        with tempfile.TemporaryDirectory() as folder:
            state_path = Path(folder) / "state.json"
            first = ensure_daily_backup(state_path, EMPTY_SAVE, NOW)
            self.assertIsNotNone(first)
            self.assertIsNone(ensure_daily_backup(state_path, EMPTY_SAVE, NOW + timedelta(hours=1)))
            event = write_backup(state_path, "limit", EMPTY_SAVE, NOW + timedelta(hours=2))
            self.assertTrue(event.exists())
            self.assertTrue(has_automatic_backup_today(state_path, NOW))
            tomorrow = NOW + timedelta(days=1)
            self.assertIsNotNone(ensure_daily_backup(state_path, EMPTY_SAVE, tomorrow))
            self.assertEqual(len(list(Path(folder).glob("state-backup-*.json"))), 3)

    def test_corrupt_backup_cannot_suppress_daily_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            state_path = Path(folder) / "state.json"
            corrupt = backup_path(state_path, "daily", NOW)
            corrupt.write_text("{bad json", encoding="utf-8")
            self.assertFalse(has_automatic_backup_today(state_path, NOW))
            self.assertIsNotNone(ensure_daily_backup(state_path, EMPTY_SAVE, NOW))
            self.assertTrue(corrupt.exists())

    def test_retention_keeps_recent_daily_weekly_monthly_and_never_prunes_manual(self):
        with tempfile.TemporaryDirectory() as folder:
            state_path = Path(folder) / "state.json"

            def seed(kind: str, when: datetime, contents: str = EMPTY_SAVE) -> Path:
                path = backup_path(state_path, kind, when)
                atomic_write(path, contents)
                return path

            last_six_hours = [seed("daily", NOW - timedelta(hours=i)) for i in (1, 6)]
            last_thirty_hours = [seed("limit", NOW - timedelta(hours=i)) for i in (25, 30)]
            old_day = seed("daily", NOW - timedelta(days=3, hours=1))
            latest_day = seed("limit", NOW - timedelta(days=3))
            week_day = seed("daily", NOW - timedelta(days=6))
            old_week = seed("daily", NOW - timedelta(days=10, hours=1))
            latest_week = seed("limit", NOW - timedelta(days=10))
            another_week = seed("daily", NOW - timedelta(days=20))
            old_month = seed("daily", NOW - timedelta(days=50))
            latest_month = seed("limit", NOW - timedelta(days=45))
            last_year = seed("daily", datetime(2025, 10, 1, 12, tzinfo=TZ))
            expired = seed("daily", NOW - timedelta(days=400))
            manual = seed("manual", NOW - timedelta(days=400))
            before_import = seed("before-import", NOW - timedelta(days=400))
            imported = seed("imported", NOW - timedelta(days=400))
            corrupt = seed("daily", NOW - timedelta(days=401), "{broken")
            legacy = Path(folder) / "state-backup.json"
            legacy.write_text(EMPTY_SAVE, encoding="utf-8")
            restore = Path(folder) / "state-ManualRestore.json"
            restore.write_text(EMPTY_SAVE, encoding="utf-8")

            removed = prune_automatic_backups(state_path, NOW)
            self.assertEqual(set(removed), {old_day, old_week, old_month, expired})
            for path in (
                *last_six_hours, *last_thirty_hours, latest_day, week_day,
                latest_week, another_week, latest_month, last_year,
                manual, before_import, imported, corrupt, legacy, restore,
            ):
                self.assertTrue(path.exists(), path)

    def test_open_creates_daily_snapshot_before_any_refresh(self):
        with tempfile.TemporaryDirectory() as folder:
            state_path = Path(folder) / "state.json"
            state_path.write_text(EMPTY_SAVE, encoding="utf-8")
            store = StateStore(state_path)
            store.load()
            with patch("poketokenbar_windows.backups.local_now", return_value=NOW):
                store.ensure_daily_on_open()
                store.ensure_daily_on_open()
            self.assertEqual(len(list(Path(folder).glob("state-backup-daily-*.json"))), 1)

    def test_unreadable_save_is_never_overwritten_by_a_default_egg(self):
        with tempfile.TemporaryDirectory() as folder:
            state_path = Path(folder) / "state.json"
            state_path.write_text("{broken json", encoding="utf-8")
            store = StateStore(state_path)
            self.assertIsNone(store.load().mon)
            self.assertIsNotNone(store.load_error)
            with self.assertRaises(ValueError):
                store.save(GameState(egg_usage=123))
            self.assertEqual(state_path.read_text(encoding="utf-8"), "{broken json")
            recovered = json.loads(StateStore.serialize_state(GameState(egg_usage=99)))
            store.import_payload(recovered)
            self.assertIsNone(store.load_error)
            self.assertEqual(store.load().egg_usage, 99)

    def test_json_object_without_save_fields_is_not_loaded_as_an_egg(self):
        with tempfile.TemporaryDirectory() as folder:
            state_path = Path(folder) / "state.json"
            state_path.write_text("{}", encoding="utf-8")
            store = StateStore(state_path)
            self.assertIsNone(store.load().mon)
            self.assertIsNotNone(store.load_error)
            with self.assertRaises(ValueError):
                store.save(GameState())
            self.assertEqual(state_path.read_text(encoding="utf-8"), "{}")

    def test_state_save_creates_one_daily_backup_and_import_preserves_both_states(self):
        with tempfile.TemporaryDirectory() as folder:
            state_path = Path(folder) / "state.json"
            store = StateStore(state_path)
            before = GameState(
                catches=[CatchRecord(300, 300, [300, 301], "common", False, "Bashful", "2026-08-25")],
                used_since_install=100,
            )
            after = GameState(egg_usage=20, used_since_install=200)
            with patch("poketokenbar_windows.backups.local_now", return_value=NOW):
                store.save(before)
                store.save(before)
            self.assertEqual(len(list(Path(folder).glob("state-backup-daily-*.json"))), 1)
            imported = store.import_payload(json.loads(StateStore.serialize_state(after)))
            self.assertEqual(imported.egg_usage, 20)
            previous_files = list(Path(folder).glob("state-backup-before-import-*.json"))
            imported_files = list(Path(folder).glob("state-backup-imported-*.json"))
            self.assertEqual(len(previous_files), 1)
            self.assertEqual(len(imported_files), 1)
            self.assertEqual(len(json.loads(previous_files[0].read_text(encoding="utf-8"))["catches"]), 1)
            self.assertEqual(json.loads(imported_files[0].read_text(encoding="utf-8"))["egg_usage"], 20)
            self.assertEqual(store.load().egg_usage, 20)
            with self.assertRaises(ValueError):
                store.import_payload({"egg_usage": 0, "mon": {"broken": True}, "catches": []})
            self.assertEqual(store.load().egg_usage, 20)


if __name__ == "__main__":
    unittest.main()
