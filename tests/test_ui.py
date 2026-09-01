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
        self.assertIn("resets in", title)
        self.assertIn("forecast: full in ~1h", title)
        self.assertEqual(widget.findChild(QProgressBar).value(), 25)

        tooltip = tray_tooltip(result, limit_display_mode="remaining")
        self.assertIn("Codex 5-hour: 25% left", tooltip)
        self.assertIn("Lv. 0", tooltip)
        self.assertNotIn("% progress", tooltip)

        self.settings.setValue("limits_forecast_enabled", False)
        window.render(result)
        widget = window.limits_list.itemWidget(window.limits_list.item(0))
        title = next(label.text() for label in widget.findChildren(QLabel) if "Codex" in label.text())
        self.assertNotIn("forecast:", title)

    def test_limit_display_uses_upstream_style_segmented_toggle(self):
        window = self._window()
        self.assertTrue(window.limit_used_button.isChecked())
        self.assertFalse(window.limit_remaining_button.isChecked())

        window.limit_remaining_button.click()

        self.assertTrue(window.limit_remaining_button.isChecked())
        self.assertEqual(self.settings.value("limit_display_mode"), "remaining")

    def test_limit_time_display_uses_a_shared_segmented_toggle(self):
        window = self._window()
        self.assertTrue(window.limit_time_remaining_button.isChecked())
        self.assertFalse(window.limit_time_datetime_button.isChecked())

        window.limit_time_datetime_button.click()

        self.assertTrue(window.limit_time_datetime_button.isChecked())
        self.assertEqual(
            self.settings.value("limit_time_display_mode"),
            "datetime",
        )

    def test_datetime_mode_uses_short_dates_for_reset_and_forecast(self):
        self.settings.setValue("limit_time_display_mode", "datetime")
        now = datetime.now(timezone.utc)
        reset = now + timedelta(hours=2)
        limits = {
            "codex": ProviderLimits(
                "codex",
                windows=[LimitWindow("5-hour", 75, reset, duration_minutes=300)],
            )
        }
        window = self._window()
        window.render(
            RefreshResult(
                UsageSnapshot(scanned_at=now),
                limits,
                {},
                GameState(),
                [],
                None,
                "Pokemon Egg",
            )
        )

        widget = window.limits_list.itemWidget(window.limits_list.item(0))
        title = next(
            label.text()
            for label in widget.findChildren(QLabel)
            if "Codex" in label.text()
        )
        self.assertIn(f"resets {reset:%d %b, %H:%M}", title)
        self.assertIn("forecast: full ", title)
        self.assertNotIn("resets in", title)
        self.assertNotIn("full in", title)

    def test_forecast_explains_when_there_is_not_enough_data(self):
        self.settings.setValue("limits_forecast_enabled", True)
        now = datetime.now(timezone.utc)
        limits = {
            "codex": ProviderLimits(
                "codex",
                windows=[
                    LimitWindow(
                        "Weekly",
                        4,
                        now + timedelta(days=3),
                        duration_minutes=10_080,
                    )
                ],
            )
        }
        window = self._window()
        window.render(
            RefreshResult(
                UsageSnapshot(scanned_at=now),
                limits,
                {},
                GameState(),
                [],
                None,
                "Pokemon Egg",
            )
        )
        widget = window.limits_list.itemWidget(window.limits_list.item(0))
        title = next(label.text() for label in widget.findChildren(QLabel) if "Codex" in label.text())
        self.assertIn("forecast: not enough data yet", title)
        self.assertNotIn("(<5% used)", title)

    def test_forecast_uses_short_safe_until_reset_copy(self):
        self.settings.setValue("limits_forecast_enabled", True)
        now = datetime.now(timezone.utc)
        limits = {
            "codex": ProviderLimits(
                "codex",
                windows=[
                    LimitWindow(
                        "5-hour",
                        30,
                        now + timedelta(hours=2),
                        duration_minutes=300,
                    )
                ],
            )
        }
        window = self._window()
        window.render(
            RefreshResult(
                UsageSnapshot(scanned_at=now),
                limits,
                {},
                GameState(),
                [],
                None,
                "Pokemon Egg",
            )
        )
        widget = window.limits_list.itemWidget(window.limits_list.item(0))
        title = next(label.text() for label in widget.findChildren(QLabel) if "Codex" in label.text())
        self.assertIn("forecast: safe until reset", title)
        self.assertNotIn("not expected before reset", title)

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

    def test_floating_pet_plays_the_same_companion_reveal(self):
        pet = FloatingPetWindow(96)
        pet.start_companion_reveal(None, is_egg=True)
        self.assertTrue(pet.reveal_timer.isActive())
        pet.reveal_frame = 19
        pet._advance_companion_reveal()
        self.assertFalse(pet.reveal_timer.isActive())
        self.assertFalse(pet.label.pixmap().isNull())
        pet.close()

    def test_floating_pet_loading_uses_a_pokeball_instead_of_dots(self):
        pet = FloatingPetWindow(96)
        pet.set_loading()
        image = pet.label.pixmap().toImage()
        has_pokeball_red = any(
            image.pixelColor(x, y).red() > 180
            and image.pixelColor(x, y).green() < 100
            and image.pixelColor(x, y).alpha() > 0
            for x in range(image.width())
            for y in range(image.height())
        )
        self.assertTrue(has_pokeball_red)
        self.assertEqual(pet.loading_timer.interval(), 90)
        pet.close()

    def test_floating_pet_menu_matches_tray_order_and_labels(self):
        pet = FloatingPetWindow(96)
        menu, actions = pet._build_context_menu()
        self.assertEqual(
            [action.text() if not action.isSeparator() else None for action in menu.actions()],
            ["Open PokeTokenBar", "Show desktop pet", "Refresh", None, "Quit"],
        )
        self.assertTrue(actions["visibility"].isCheckable())
        self.assertTrue(actions["visibility"].isChecked())
        menu.close()
        pet.close()

    def test_limit_only_hover_keeps_a_readable_horizontal_shape(self):
        hover = HoverCallout()
        text = "Codex 5-hour: 46% left"
        expected_width = min(
            280,
            hover.label.fontMetrics().horizontalAdvance(text) + 2,
        )
        hover.set_text(text)
        self.assertEqual(hover.label.width(), expected_width)
        hover.show()
        self.app.processEvents()
        self.assertGreaterEqual(hover.label.geometry().x(), 5)
        self.assertLessEqual(hover.width(), hover.label.width() + 12)
        self.assertLess(hover.height(), 60)
        image = hover.grab().toImage()
        self.assertGreater(image.pixelColor(2, image.height() // 2).alpha(), 0)
        hover.close()

    def test_severely_shrunken_animation_frame_keeps_last_normal_frame(self):
        stabilizer = AnimatedSpriteFrameStabilizer()

        normal = QPixmap(96, 96)
        normal.fill(Qt.GlobalColor.transparent)
        painter = QPainter(normal)
        painter.fillRect(8, 8, 80, 80, QColor("red"))
        painter.end()

        shrunken = QPixmap(96, 96)
        shrunken.fill(Qt.GlobalColor.transparent)
        painter = QPainter(shrunken)
        painter.fillRect(35, 28, 26, 40, QColor("red"))
        painter.end()

        stabilizer.filter(normal)
        filtered = stabilizer.filter(shrunken)

        self.assertEqual(stabilizer.visible_area(filtered), 80 * 80)

    def test_follow_current_companion_previews_the_active_pet_immediately(self):
        state = GameState(
            mon=MonState(1, [1, 2, 3], 1, 10, "common", False, "Hardy"),
            catches=[
                CatchRecord(2, 1, [1, 2, 3], "common", False, "Hardy", "2026-08-30T10:00:00")
            ],
            representative_species_id=1,
            representative_is_shiny=False,
        )
        controller = TrayController.__new__(TrayController)
        controller.state_lock = threading.Lock()
        controller.state = state
        controller.store = Mock()
        controller.window = Mock()
        controller.floating_pet = Mock()
        controller.tray = Mock()
        controller.settings = self.settings
        controller.limit_display_mode = "used"
        controller.limit_time_mode = "remaining"
        controller.api = FakeUIAPI()
        controller.refresh = Mock()
        controller.last_result = RefreshResult(
            UsageSnapshot(scanned_at=datetime.now(timezone.utc)),
            {},
            {},
            state,
            [],
            None,
            "Ivysaur",
            pet_display_name="Bulbasaur",
            pet_is_egg=False,
        )

        controller._set_representative(None)

        self.assertIsNone(controller.state.representative_species_id)
        self.assertEqual(controller.last_result.pet_display_name, "Ivysaur")
        self.assertFalse(controller.last_result.pet_is_egg)
        controller.floating_pet.set_loading.assert_called_once_with()
        controller.floating_pet.update.assert_called_once_with(controller.last_result)
        controller.refresh.assert_called_once_with()

    def test_home_keeps_luna_reserve_visible_when_compact_surfaces_do_not(self):
        now = datetime.now(timezone.utc)
        limits = {
            "codex": ProviderLimits(
                "codex",
                windows=[
                    LimitWindow("5-hour", 46, now + timedelta(hours=2)),
                    LimitWindow(
                        "Luna Reserve",
                        5,
                        now + timedelta(days=5),
                        identifier="base_model_inference.primary",
                    ),
                ],
            )
        }
        window = self._window()
        window.render(
            RefreshResult(
                UsageSnapshot(
                    providers={"codex": ProviderUsage("codex", today_tokens=1_000)},
                    scanned_at=now,
                ),
                limits,
                {},
                GameState(),
                [],
                None,
                "Pokemon Egg",
            )
        )
        titles = [
            label.text()
            for index in range(window.limits_list.count())
            if (widget := window.limits_list.itemWidget(window.limits_list.item(index)))
            for label in widget.findChildren(QLabel)
        ]
        self.assertTrue(any("Luna Reserve" in title for title in titles))
        self.assertNotIn(
            "Luna Reserve",
            tray_tooltip(
                RefreshResult(
                    UsageSnapshot(
                        providers={"codex": ProviderUsage("codex", today_tokens=1_000)}
                    ),
                    limits,
                    {},
                    GameState(),
                    [],
                    None,
                    "Pokemon Egg",
                )
            ),
        )

    def test_home_shows_luna_reserve_when_codex_omits_its_bucket(self):
        now = datetime.now(timezone.utc)
        window = self._window()
        window.render(
            RefreshResult(
                UsageSnapshot(scanned_at=now),
                {
                    "codex": ProviderLimits(
                        "codex",
                        windows=[
                            LimitWindow("Weekly", 17, now + timedelta(days=6))
                        ],
                    )
                },
                {},
                GameState(),
                [],
                None,
                "Pokemon Egg",
            )
        )

        reserve_widget = window.limits_list.itemWidget(window.limits_list.item(1))
        reserve_title = reserve_widget.findChild(QLabel).text()
        self.assertEqual(reserve_title, "Codex · Luna Reserve · unavailable")
        self.assertIsNone(reserve_widget.findChild(QProgressBar))

    def test_offline_refresh_still_emits_a_renderable_result(self):
        controller = TrayController.__new__(TrayController)
        controller.state_lock = threading.Lock()
        controller.state = GameState()
        controller.store = Mock()
        controller.api = Mock()
        controller.api.item_sprite_path.return_value = None
        controller.api.egg_sprite_path.return_value = None
        controller.bridge = Mock()
        controller._prefetch_collection = Mock()
        now = datetime.now(timezone.utc)
        offline_limits = {
            "claude": ProviderLimits("claude", error="offline"),
            "codex": ProviderLimits("codex", error="offline"),
        }

        with (
            patch(
                "poketokenbar_windows.ui.scan_all",
                return_value=(UsageSnapshot(scanned_at=now), {}),
            ),
            patch(
                "poketokenbar_windows.ui.fetch_all_limits",
                return_value=offline_limits,
            ),
        ):
            controller._refresh_worker()

        controller.bridge.failed.emit.assert_not_called()
        controller.bridge.refreshed.emit.assert_called_once()
        result = controller.bridge.refreshed.emit.call_args.args[0]
        self.assertEqual(result.limits, offline_limits)
        self.assertIsNone(result.sprite_path)
        self.assertIsNone(result.reveal_ball_path)

    def test_collection_has_counts_paging_and_representative_choice(self):
        catches = [CatchRecord(3, 1, [1, 2, 3], "rare", True, "Bold", "2026-08-30T10:00:00")]
        window = self._window(GameState(catches=catches))
        window._render_collection()
        self.assertIn("Rare 1", window.dex_counts.text())
        self.assertEqual(window.representative_combo.count(), 4)
        self.assertEqual(window.dex_page_label.text(), "Page 1 / 1")

    def test_follow_current_dropdown_emits_the_automatic_selection(self):
        state = GameState(
            mon=MonState(1, [1, 2, 3], 1, 10, "common", False, "Hardy"),
            catches=[
                CatchRecord(2, 1, [1, 2, 3], "common", False, "Hardy", "2026-08-30T10:00:00")
            ],
            representative_species_id=1,
            representative_is_shiny=False,
        )
        window = self._window(state)
        window._render_collection()
        selections = []
        window.representative_changed.connect(selections.append)
        self.assertGreater(window.representative_combo.currentIndex(), 0)

        window.representative_combo.setCurrentIndex(0)

        self.assertEqual(selections, [None])
        species_index = next(
            index
            for index in range(1, window.representative_combo.count())
            if window._representative_selection_data(
                window.representative_combo.itemData(index)
            )
            == (2, False)
        )
        window.representative_combo.setCurrentIndex(species_index)
        self.assertEqual(selections, [None, (2, False)])

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
