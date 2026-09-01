from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from poketokenbar_windows.models import (
    LimitWindow,
    ProviderLimits,
    ProviderUsage,
    RateLimitResetCredit,
    UsageSnapshot,
)
from poketokenbar_windows.pet_logic import (
    PET_DEFAULT_SIZE,
    AlertMemory,
    PetAlert,
    ScreenRect,
    choose_pet_alert,
    dump_alert_memory,
    evaluate_pet_alerts,
    load_alert_memory,
    normalize_pet_size,
    pet_hover_text,
    recover_pet_position,
    settings_bool,
)
from poketokenbar_windows.state import (
    STATE_VERSION,
    CatchRecord,
    GameState,
    MonState,
    StateStore,
    owned_representative_options,
    representative_subject,
    buy_egg,
    set_representative,
)


class PetPreferenceTests(unittest.TestCase):
    def test_size_defaults_clamps_and_uses_eight_pixel_steps(self):
        self.assertEqual(normalize_pet_size(None), PET_DEFAULT_SIZE)
        self.assertEqual(normalize_pet_size("bad"), PET_DEFAULT_SIZE)
        self.assertEqual(normalize_pet_size(20), 48)
        self.assertEqual(normalize_pet_size(500), 192)
        self.assertEqual(normalize_pet_size(101), 104)

    def test_qsettings_style_booleans_are_not_truthy_strings(self):
        self.assertFalse(settings_bool("false", True))
        self.assertTrue(settings_bool("true", False))
        self.assertFalse(settings_bool(0, True))
        self.assertTrue(settings_bool(1, False))

    def test_alert_memory_round_trip_ignores_corrupt_items(self):
        memory = {"weekly": AlertMemory(1234.0, 2)}
        self.assertEqual(load_alert_memory(dump_alert_memory(memory)), memory)
        self.assertEqual(load_alert_memory("not json"), {})
        self.assertEqual(load_alert_memory(json.dumps({"x": {"tier": 9}})), {})


class PetPositionTests(unittest.TestCase):
    def test_position_inside_primary_is_unchanged(self):
        screens = [ScreenRect(0, 0, 1920, 1040)]
        self.assertEqual(recover_pet_position(100, 200, 96, screens), (100, 200))

    def test_negative_coordinate_monitor_is_supported(self):
        screens = [ScreenRect(0, 0, 1920, 1040), ScreenRect(-1600, 0, 1600, 860)]
        self.assertEqual(recover_pet_position(-1400, 100, 96, screens), (-1400, 100))

    def test_offscreen_position_recovers_to_nearest_visible_monitor(self):
        screens = [ScreenRect(0, 0, 1920, 1040), ScreenRect(-1600, 0, 1600, 860)]
        x, y = recover_pet_position(-2500, 900, 192, screens)
        self.assertGreaterEqual(x, -1592)
        self.assertLessEqual(x + 192, -8)
        self.assertGreaterEqual(y, 8)
        self.assertLessEqual(y + 192, 852)

    def test_invalid_coordinates_use_visible_primary_fallback(self):
        x, y = recover_pet_position("nan", None, 96, [ScreenRect(100, -200, 1200, 900)])
        self.assertGreaterEqual(x, 108)
        self.assertLessEqual(x + 96, 1292)
        self.assertGreaterEqual(y, -192)
        self.assertLessEqual(y + 96, 692)


class PetAlertTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)

    def _limits(self, used: float, reset: datetime | None = None) -> dict[str, ProviderLimits]:
        return {
            "codex": ProviderLimits(
                provider="codex",
                windows=[LimitWindow("5-hour", used, reset or self.now + timedelta(hours=4))],
            )
        }

    def test_warning_and_critical_are_edge_triggered(self):
        alerts, memory = evaluate_pet_alerts(self._limits(79.9), now=self.now)
        self.assertEqual(alerts, [])
        alerts, memory = evaluate_pet_alerts(self._limits(80), memory, self.now)
        self.assertEqual([alert.severity for alert in alerts], ["warning"])
        alerts, memory = evaluate_pet_alerts(self._limits(94.9), memory, self.now)
        self.assertEqual(alerts, [])
        alerts, memory = evaluate_pet_alerts(self._limits(95), memory, self.now)
        self.assertEqual([alert.severity for alert in alerts], ["critical"])
        alerts, _ = evaluate_pet_alerts(self._limits(99), memory, self.now)
        self.assertEqual(alerts, [])

    def test_configurable_limit_thresholds_are_shared_with_pet_bubbles(self):
        limits = self._limits(used=90.0)
        alerts, _ = evaluate_pet_alerts(
            limits,
            warning_percent=90,
            critical_percent=100,
        )
        self.assertEqual([alert.severity for alert in alerts], ["warning"])

        remaining_alerts, _ = evaluate_pet_alerts(
            limits,
            warning_percent=90,
            critical_percent=100,
            display_mode="remaining",
        )
        self.assertEqual(
            remaining_alerts[0].body,
            "Codex 5-hour: 90% used.",
        )

    def test_new_time_window_rearms_but_small_reset_drift_does_not(self):
        first_reset = self.now + timedelta(hours=4)
        alerts, memory = evaluate_pet_alerts(self._limits(85, first_reset), now=self.now)
        self.assertEqual(len(alerts), 1)
        alerts, memory = evaluate_pet_alerts(
            self._limits(86, first_reset + timedelta(minutes=5)), memory, self.now
        )
        self.assertEqual(alerts, [])
        alerts, _ = evaluate_pet_alerts(
            self._limits(85, first_reset + timedelta(hours=5)), memory, self.now
        )
        self.assertEqual(len(alerts), 1)

    def test_drop_below_warning_rearms_same_window(self):
        alerts, memory = evaluate_pet_alerts(self._limits(85), now=self.now)
        self.assertEqual(len(alerts), 1)
        _, memory = evaluate_pet_alerts(self._limits(40), memory, self.now)
        alerts, _ = evaluate_pet_alerts(self._limits(85), memory, self.now)
        self.assertEqual(len(alerts), 1)

    def test_full_reset_warning_and_exact_72_hour_critical(self):
        weekly = LimitWindow("Weekly", 40, self.now + timedelta(days=10))
        warning_expiry = self.now + timedelta(days=8)
        status = ProviderLimits(
            provider="codex",
            windows=[weekly],
            reset_credits_available=1,
            reset_credits=[RateLimitResetCredit(expires_at=warning_expiry)],
        )
        alerts, memory = evaluate_pet_alerts({"codex": status}, now=self.now)
        self.assertIn("warning", [alert.severity for alert in alerts])
        reset_alert = next(alert for alert in alerts if alert.key.startswith("reset|"))
        self.assertIn("expires in 8d 0h", reset_alert.body)
        status.reset_credits[0].expires_at = self.now + timedelta(hours=72)
        alerts, _ = evaluate_pet_alerts(
            {"codex": status},
            memory,
            self.now,
            time_mode="datetime",
        )
        self.assertIn("critical", [alert.severity for alert in alerts])
        reset_alert = next(alert for alert in alerts if alert.key.startswith("reset|"))
        self.assertIn(
            (self.now + timedelta(hours=72)).strftime("expires %d %b, %H:%M"),
            reset_alert.body,
        )

    def test_hover_and_alerts_ignore_codex_spend_bucket(self):
        status = ProviderLimits(
            provider="codex",
            windows=[
                LimitWindow("5-hour", 30, self.now + timedelta(hours=4)),
                LimitWindow("Codex spend", 99, self.now + timedelta(days=1)),
            ],
        )
        snapshot = UsageSnapshot(providers={"codex": ProviderUsage("codex", today_tokens=1234)})
        self.assertIn("5-hour: 30% used", pet_hover_text(snapshot, {"codex": status}))
        self.assertIn(
            "5-hour: 70% left",
            pet_hover_text(snapshot, {"codex": status}, "remaining"),
        )
        alerts, _ = evaluate_pet_alerts({"codex": status}, now=self.now)
        self.assertEqual(alerts, [])

    def test_hover_preferences_match_tray_visibility_fields(self):
        status = ProviderLimits(
            provider="codex",
            windows=[LimitWindow("5-hour", 30, self.now + timedelta(hours=4))],
        )
        snapshot = UsageSnapshot(
            providers={
                "codex": ProviderUsage(
                    "codex",
                    today_tokens=1234,
                    today_cost=2.5,
                )
            }
        )
        text = pet_hover_text(
            snapshot,
            {"codex": status},
            show_tokens=False,
            show_cost=True,
            show_limit=False,
        )
        self.assertNotIn("tokens", text)
        self.assertIn("$2.50", text)
        self.assertNotIn("5-hour", text)

    def test_hover_uses_regular_codex_limit_until_reserve_is_active(self):
        regular = LimitWindow(
            "Weekly",
            40,
            self.now + timedelta(days=4),
            duration_minutes=10_080,
            identifier="codex.secondary",
        )
        reserve = LimitWindow(
            "Luna Reserve",
            95,
            self.now + timedelta(days=5),
            duration_minutes=10_080,
            identifier="base_model_inference.primary",
        )
        snapshot = UsageSnapshot(
            providers={"codex": ProviderUsage("codex", today_tokens=1234)}
        )
        status = ProviderLimits(provider="codex", windows=[regular, reserve])
        self.assertIn("Weekly: 40% used", pet_hover_text(snapshot, {"codex": status}))
        self.assertNotIn("Reserve", pet_hover_text(snapshot, {"codex": status}))

        status.reserve_active = True
        self.assertIn("Luna Reserve: 95% used", pet_hover_text(snapshot, {"codex": status}))

    def test_hover_does_not_surface_limits_for_unused_provider(self):
        snapshot = UsageSnapshot(providers={"claude": ProviderUsage("claude", today_tokens=500)})
        codex = ProviderLimits(
            provider="codex",
            windows=[LimitWindow("Weekly", 90, self.now + timedelta(days=2))],
        )
        self.assertEqual(pet_hover_text(snapshot, {"codex": codex}), "500 tokens today")

    def test_duplicate_display_labels_keep_independent_alert_state(self):
        status = ProviderLimits(
            provider="codex",
            windows=[
                LimitWindow("Weekly", 82, self.now + timedelta(days=6)),
                LimitWindow("Weekly", 85, self.now + timedelta(days=7)),
            ],
        )
        alerts, memory = evaluate_pet_alerts({"codex": status}, now=self.now)
        self.assertEqual(len(alerts), 2)
        alerts, _ = evaluate_pet_alerts({"codex": status}, memory, self.now)
        self.assertEqual(alerts, [])

    def test_bubble_picker_prefers_higher_utilization_within_tier(self):
        lower = PetAlert("a", "Critical", "95", "critical", 2, 95)
        higher = PetAlert("b", "Critical", "99", "critical", 2, 99)
        self.assertEqual(choose_pet_alert([lower, higher]), higher)


class RepresentativePokemonTests(unittest.TestCase):
    def _state(self) -> GameState:
        normal = CatchRecord(3, 1, [1, 2, 3], "common", False, "Hardy", "2026-01-01")
        shiny = CatchRecord(25, 25, [25, 26], "rare", True, "Jolly", "2026-02-01")
        return GameState(
            egg_usage=321,
            mon=MonState(25, [25, 26], 0, 456, "rare", True, "Jolly"),
            catches=[normal, shiny],
        )

    def test_only_reached_current_stages_are_selectable(self):
        options = {(item.species_id, item.is_shiny) for item in owned_representative_options(self._state())}
        self.assertIn((1, False), options)
        self.assertIn((3, False), options)
        self.assertIn((25, True), options)
        self.assertNotIn((26, True), options)

    def test_representative_is_independent_and_preserves_shiny(self):
        state = self._state()
        before = (state.mon.current_id, state.mon.stage_index, state.mon.used_at_stage, state.egg_usage)
        self.assertTrue(set_representative(state, 25, True))
        self.assertEqual(representative_subject(state).species_id, 25)
        self.assertTrue(representative_subject(state).is_shiny)
        self.assertEqual(
            (state.mon.current_id, state.mon.stage_index, state.mon.used_at_stage, state.egg_usage),
            before,
        )
        self.assertTrue(set_representative(state, None))
        self.assertIsNone(state.representative_species_id)

    def test_non_owned_representative_is_rejected_and_falls_back_to_current(self):
        state = self._state()
        self.assertFalse(set_representative(state, 999, False))
        state.representative_species_id = 999
        self.assertEqual(representative_subject(state).species_id, state.mon.current_id)

    def test_fresh_egg_clears_representative_if_its_only_catch_is_discarded(self):
        state = self._state()
        state.used_since_install = 2_000_000_000
        self.assertTrue(set_representative(state, 25, True))
        ok, _ = buy_egg(state, None)
        self.assertTrue(ok)
        self.assertIsNone(state.representative_species_id)
        self.assertTrue(representative_subject(state).is_egg)

    def test_old_state_migrates_without_losing_game_fields(self):
        old = {
            "version": 1,
            "egg_usage": 123,
            "egg_tier": "rare",
            "mon": None,
            "catches": [],
            "inventory": {"rare_candy": 7, "mint": 2, "shiny_charm": 1},
            "install_baseline_set": True,
            "used_since_install": 999,
            "spent_tokens": 111,
            "last_day": "2026-08-27",
            "last_today_tokens": 222,
            "language": "en",
            "claimed_limit_windows": ["codex|Weekly|old"],
            "candy_feature_seeded": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(json.dumps(old), encoding="utf-8")
            state = StateStore(path).load()
        self.assertEqual(state.version, STATE_VERSION)
        self.assertEqual(state.egg_usage, 123)
        self.assertEqual(state.inventory["rare_candy"], 7)
        self.assertEqual(state.used_since_install, 999)
        self.assertEqual(state.claimed_limit_windows, ["codex|Weekly|old"])
        self.assertIsNone(state.representative_species_id)
        self.assertIsNone(state.representative_is_shiny)


if __name__ == "__main__":
    unittest.main()
