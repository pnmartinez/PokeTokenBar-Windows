from __future__ import annotations

import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QSettings, Qt
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QScrollArea

from poketokenbar_windows.models import (
    LimitWindow,
    ProviderLimits,
    ProviderUsage,
    UsageSnapshot,
)
from poketokenbar_windows.pokemon import EGG_HATCH_THRESHOLD, RARE_CANDY_XP
from poketokenbar_windows.qml_ui import QmlMainWindow, QmlViewModel
from poketokenbar_windows.state import CatchRecord, GameState, MonState
from poketokenbar_windows.ui import (
    DesktopPet,
    MainWindow,
    RefreshResult,
    TrayController,
    _migrate_legacy_settings,
    theme_stylesheet,
    tray_tooltip,
)


class FakeUIAPI:
    def localized_name(self, species_id: int, language: str = "en") -> str:
        return {1: "Bulbasaur", 2: "Ivysaur", 3: "Venusaur"}.get(species_id, f"Species {species_id}")

    def sprite_path(self, species_id: int, shiny: bool = False, animated: bool = True):
        return None

    def egg_sprite_path(self):
        return None


class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.Format.IniFormat)

    def tearDown(self):
        self.settings.clear()
        self.tmp.cleanup()

    def _window(self, state: GameState | None = None) -> MainWindow:
        return MainWindow(state or GameState(), self.settings, FakeUIAPI())

    def test_primary_navigation_and_scrollable_settings(self):
        window = self._window()
        self.assertEqual(
            [window.tabs.tabText(index) for index in range(window.tabs.count())],
            ["Home", "Collection", "Bag", "Shop", "Settings"],
        )
        self.assertIsInstance(window.tabs.widget(4), QScrollArea)

    def test_qml_window_loads_and_exposes_the_modern_shell(self):
        window = QmlMainWindow(GameState(), self.settings, FakeUIAPI())
        self.app.processEvents()

        self.assertEqual(window.quick.status(), QQuickWidget.Status.Ready)
        self.assertIsNotNone(window.quick.rootObject())
        self.assertGreaterEqual(window.minimumWidth(), 820)

    def test_qml_view_model_renders_usage_limits_and_companion_progress(self):
        state = GameState(egg_usage=EGG_HATCH_THRESHOLD // 2)
        model = QmlViewModel(state, self.settings, FakeUIAPI())
        reset = datetime.now(timezone.utc) + timedelta(hours=2)
        result = RefreshResult(
            UsageSnapshot(
                providers={"codex": ProviderUsage("codex", today_tokens=1_500_000)},
                scanned_at=datetime.now(timezone.utc),
            ),
            {"codex": ProviderLimits("codex", windows=[LimitWindow("5-hour", 75, reset)])},
            {},
            state,
            [],
            None,
            "Pokemon Egg",
        )

        model.render(result)

        self.assertEqual(model.todayTokens, "1.5M")
        self.assertEqual(model.companionProgress, 50)
        self.assertEqual(model.providers[0]["name"], "Codex")
        self.assertEqual(model.limits[0]["percentText"], "75% used")

    def test_legacy_desktop_pet_preferences_migrate_without_overwriting_current_values(self):
        self.settings.setValue("pet_visible", True)
        self.settings.setValue("pet_size", 113)
        self.settings.setValue("notify_limits", False)
        self.settings.setValue("limit_warning", 82)
        self.settings.setValue("limit_critical", 97)
        self.settings.setValue("notify_events", False)
        self.settings.setValue("warnThreshold", 90)
        self.settings.setValue("limits_show_remaining", True)

        _migrate_legacy_settings(self.settings)

        self.assertTrue(self.settings.value("floating_pet/enabled", type=bool))
        self.assertEqual(self.settings.value("floating_pet/size", type=int), 112)
        self.assertFalse(self.settings.value("limitNotifications", type=bool))
        self.assertEqual(self.settings.value("warnThreshold", type=int), 90)
        self.assertEqual(self.settings.value("critThreshold", type=int), 95)
        self.assertFalse(self.settings.value("companionNotifications", type=bool))
        self.assertEqual(self.settings.value("limit_display_mode"), "remaining")

    def test_provider_tabs_only_appear_for_multiple_providers(self):
        window = self._window()
        state = GameState()
        one = UsageSnapshot(providers={"codex": ProviderUsage("codex", today_tokens=10)})
        window.render(RefreshResult(one, {}, {}, state, [], None, "Pokemon Egg"))
        self.assertEqual(window.providers_tabs.count(), 1)
        self.assertFalse(window.providers_tabs.tabBar().isVisible())
        self.assertLess(window.providers_tabs.maximumHeight(), window.limits_list.minimumHeight())

        two = UsageSnapshot(providers={
            "codex": ProviderUsage("codex", today_tokens=10),
            "claude": ProviderUsage("claude", today_tokens=20),
        })
        window.render(RefreshResult(two, {}, {}, state, [], None, "Pokemon Egg"))
        self.assertEqual(window.providers_tabs.count(), 3)

    def test_companion_level_is_readable_above_the_thin_bar(self):
        window = self._window()
        state = GameState(egg_usage=EGG_HATCH_THRESHOLD // 2)
        snapshot = UsageSnapshot(scanned_at=datetime.now(timezone.utc))
        window.render(RefreshResult(snapshot, {}, {}, state, [], None, "Pokemon Egg"))
        self.assertEqual(window.progress_percent_label.text(), "Lv. 50")
        self.assertFalse(window.progress.isTextVisible())
        self.assertEqual(window.progress.height(), 12)

    def test_using_rare_candy_requests_a_full_refresh_without_an_evolution(self):
        controller = TrayController.__new__(TrayController)
        controller.state_lock = threading.Lock()
        controller.state = GameState(
            mon=MonState(1, [1, 2, 3], 0, 0, "common", False, "Hardy"),
            inventory={"rare_candy": 1, "mint": 0, "shiny_charm": 0},
        )
        controller.store = Mock()
        controller.window = Mock()
        controller.api = FakeUIAPI()
        controller.refresh = Mock()

        with patch.object(
            QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            controller._use_item("rare_candy")

        self.assertEqual(controller.state.inventory["rare_candy"], 0)
        self.assertEqual(controller.state.mon.used_at_stage, RARE_CANDY_XP)
        controller.refresh.assert_called_once_with()

    def test_limit_progress_widget_does_not_duplicate_text(self):
        window = self._window()
        reset = datetime.now(timezone.utc) + timedelta(hours=2)
        limits = {"codex": ProviderLimits("codex", windows=[LimitWindow("5-hour", 75, reset)])}
        snapshot = UsageSnapshot(scanned_at=datetime.now(timezone.utc))
        window.render(RefreshResult(snapshot, limits, {}, GameState(), [], None, "Pokemon Egg"))
        item = window.limits_list.item(0)
        self.assertEqual(item.text(), "")
        self.assertIsNotNone(window.limits_list.itemWidget(item))
        self.assertEqual(
            window.limits_list.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )

    def test_limit_widget_and_tray_share_remaining_mode_and_forecast_setting(self):
        self.settings.setValue("limit_display_mode", "remaining")
        reset = datetime.now(timezone.utc) + timedelta(hours=2)
        limits = {
            "codex": ProviderLimits(
                "codex",
                windows=[LimitWindow("5-hour", 75, reset, duration_minutes=300)],
            )
        }
        snapshot = UsageSnapshot(
            providers={"codex": ProviderUsage("codex", today_tokens=1_500_000)},
            scanned_at=datetime.now(timezone.utc),
        )
        result = RefreshResult(
            snapshot,
            limits,
            {},
            GameState(),
            [],
            None,
            "Pokemon Egg",
        )
        window = self._window()
        window.render(result)
        widget = window.limits_list.itemWidget(window.limits_list.item(0))
        title = next(label.text() for label in widget.findChildren(QLabel) if "Codex" in label.text())
        self.assertIn("25% remaining", title)
        self.assertIn("forecast: full around", title)

        tooltip = tray_tooltip(result, limit_display_mode="remaining")
        self.assertIn("Codex 5-hour: 25% remaining", tooltip)
        self.assertIn("Lv. 0", tooltip)
        self.assertNotIn("% progress", tooltip)

        self.settings.setValue("limits_forecast_enabled", False)
        window.render(result)
        widget = window.limits_list.itemWidget(window.limits_list.item(0))
        title = next(label.text() for label in widget.findChildren(QLabel) if "Codex" in label.text())
        self.assertNotIn("forecast:", title)

    def test_initial_window_waits_for_real_refresh_data(self):
        controller = TrayController.__new__(TrayController)
        controller.last_result = None
        controller.window_open_pending = False
        controller.window = Mock()
        controller.tray = Mock()

        controller.show_window()

        self.assertTrue(controller.window_open_pending)
        controller.window.show.assert_not_called()
        self.assertIn("Loading", controller.tray.setToolTip.call_args.args[0])

    def test_companion_reveal_finishes_on_the_real_sprite(self):
        window = self._window()
        window.start_companion_reveal(None, is_egg=True)
        self.assertTrue(window.reveal_timer.isActive())
        window.reveal_frame = 19
        window._advance_companion_reveal()
        self.assertFalse(window.reveal_timer.isActive())
        self.assertFalse(window.sprite.pixmap().isNull())

    def test_collection_has_counts_paging_and_representative_choice(self):
        catches = [CatchRecord(3, 1, [1, 2, 3], "rare", True, "Bold", "2026-08-30T10:00:00")]
        window = self._window(GameState(catches=catches))
        window._render_collection()
        self.assertIn("Rare 1", window.dex_counts.text())
        self.assertEqual(window.representative_combo.count(), 4)
        self.assertEqual(window.dex_page_label.text(), "Page 1 / 1")

    def test_tray_tooltip_respects_visibility_preferences(self):
        snapshot = UsageSnapshot(
            providers={"codex": ProviderUsage("codex", today_tokens=1_500_000, today_cost=2.5)}
        )
        result = RefreshResult(snapshot, {}, {}, GameState(), [], None, "Pokemon Egg")
        text = tray_tooltip(result, show_tokens=False, show_cost=True, show_limit=False)
        self.assertNotIn("1.5M", text)
        self.assertIn("$2.50", text)

    def test_light_dark_and_system_themes_share_accessibility_rules(self):
        for theme in ("system", "light", "dark"):
            stylesheet = theme_stylesheet(theme)
            self.assertIn("QPushButton:focus", stylesheet)
            self.assertIn("QProgressBar", stylesheet)
        self.assertIn("#17191d", theme_stylesheet("dark"))
        self.assertIn("#faf9f7", theme_stylesheet("light"))

    def test_desktop_pet_shows_progress_overlay_on_hover(self):
        pet = DesktopPet(self.settings)
        pet.set_progress(47, "Next evolution")
        pet.show()
        self.app.processEvents()
        QApplication.sendEvent(pet, QEvent(QEvent.Type.Enter))
        self.assertTrue(pet.progress_overlay.isVisible())
        self.assertEqual(pet.progress_overlay.text(), "Next evolution · Lv. 47")
        QApplication.sendEvent(pet, QEvent(QEvent.Type.Leave))
        self.assertFalse(pet.progress_overlay.isVisible())
        pet.close()


if __name__ == "__main__":
    unittest.main()
