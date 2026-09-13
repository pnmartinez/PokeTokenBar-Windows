from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QSettings, Qt
from PySide6.QtGui import QAccessible, QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from poketokenbar_windows.models import LimitWindow, ProviderLimits, UsageSnapshot
from poketokenbar_windows.qml_ui import QmlMainWindow
from poketokenbar_windows.state import CatchRecord, GameState, MonState
from poketokenbar_windows.ui import RefreshResult


class LocalSprites:
    def localized_name(self, species_id, language="en"):
        return f"Pokemon {species_id}"

    def sprite_path(self, species_id, shiny=False, animated=True):
        return None

    def egg_sprite_path(self):
        return None


class QmlKeyboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        # The Windows offscreen plugin does not discover the system fonts.
        # Load the actual UI font so geometry matches an interactive Windows run.
        font = Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts" / "segoeui.ttf"
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))
            cls.app.setFont(QFont("Segoe UI", 9))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.IniFormat)
        self.settings.setValue("floating_pet/enabled", True)
        self.state = GameState(
            mon=MonState(1, [1, 2, 3], 1, 10, "common", False, "Hardy"),
            used_since_install=10_000_000_000,
            inventory={"rare_candy": 1, "mint": 1, "shiny_charm": 0},
            catches=[
                CatchRecord(
                    i,
                    i,
                    [1, 2, 3] if i == 1 else [i],
                    "common",
                    i == 1,
                    "Hardy",
                    "2026-09-01",
                )
                for i in range(1, 27)
            ],
        )
        self.window = QmlMainWindow(self.state, self.settings, LocalSprites())
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.window.hide)
        self.root = self.window.quick.rootObject()
        reset = datetime.now(timezone.utc) + timedelta(hours=2)
        self.window.render(RefreshResult(
            UsageSnapshot(scanned_at=datetime.now(timezone.utc)),
            {"codex": ProviderLimits("codex", plan="Plus", windows=[LimitWindow(f"Window {i}", i * 15, reset) for i in range(5)])},
            {}, self.state, [], None, "Pokemon 2",
        ))
        self.window.show()
        self.window.quick.setFocus()
        QTest.qWait(20)

    def key(self, key, modifiers=Qt.NoModifier):
        QTest.keyClick(self.window.quick, key, modifiers)
        self.app.processEvents()

    def name(self, item):
        accessible = QAccessible.queryAccessibleInterface(item)
        return accessible.text(QAccessible.Text.Name) if accessible else ""

    def controls(self, item=None):
        for child in (item or self.root).childItems():
            if child.isVisible() and child.isEnabled() and child.activeFocusOnTab():
                yield child
            yield from self.controls(child)

    def control(self, accessible_name):
        return next(item for item in self.controls() if self.name(item) == accessible_name)

    def activate(self, accessible_name):
        self.control(accessible_name).forceActiveFocus(Qt.TabFocusReason)
        self.key(Qt.Key_Space)

    def test_tab_and_backtab_keep_every_page_control_named_and_on_screen(self):
        for width in (520, 820):
            for theme in ("light", "dark"):
                self.window.resize(width, 580)
                self.window.view_model.setPreference("theme", theme)
                for page in range(5):
                    with self.subTest(width=width, theme=theme, page=page):
                        self.root.setProperty("currentPage", page)
                        self.root.forceActiveFocus()
                        QTest.qWait(10)
                        expected = list(self.controls())
                        visited = []
                        for _ in range(len(expected)):
                            self.key(Qt.Key_Tab)
                            item = self.window.quick.quickWindow().activeFocusItem()
                            self.assertIsNotNone(item)
                            self.assertNotIn(item, visited, "Tab cycled before reaching every control")
                            visited.append(item)
                            self.assertTrue(self.name(item), item.metaObject().className())
                            point = item.mapToItem(self.root, 0, 0)
                            self.assertGreaterEqual(point.x(), -1)
                            self.assertGreaterEqual(point.y(), -1)
                            self.assertLessEqual(point.x() + item.width(), self.root.width() + 1)
                            self.assertLessEqual(point.y() + item.height(), self.root.height() + 1)
                        self.assertCountEqual(visited, expected)
                        for _ in range(len(expected)):
                            self.key(Qt.Key_Tab, Qt.ShiftModifier)
                            item = self.window.quick.quickWindow().activeFocusItem()
                            point = item.mapToItem(self.root, 0, 0)
                            self.assertGreaterEqual(point.y(), -1)
                            self.assertLessEqual(point.y() + item.height(), self.root.height() + 1)

    def test_restored_settings_respond_to_keyboard_and_persist(self):
        self.root.setProperty("currentPage", 4)
        self.app.processEvents()
        self.activate("Quota percentage: Remaining")
        self.assertEqual(self.settings.value("limit_display_mode"), "remaining")
        self.activate("Reset format: Date")
        self.assertEqual(self.settings.value("limit_time_display_mode"), "datetime")
        warning = self.root.findChild(QObject, "warningThresholdSpin")
        warning.forceActiveFocus(Qt.TabFocusReason)
        self.key(Qt.Key_Up)
        self.assertEqual(self.settings.value("warnThreshold", type=int), 85)
        critical = self.root.findChild(QObject, "criticalThresholdSpin")
        critical.forceActiveFocus(Qt.TabFocusReason)
        self.key(Qt.Key_Down)
        self.assertEqual(self.settings.value("critThreshold", type=int), 90)
        self.activate("Primary limit in tray")
        self.assertFalse(self.settings.value("tray_show_limit", type=bool))
        slider = self.root.findChild(QObject, "petSizeSlider")
        slider.forceActiveFocus(Qt.TabFocusReason)
        previous_size = self.window.view_model.petSize
        self.key(Qt.Key_Right)
        self.assertEqual(self.window.view_model.petSize, previous_size + 8)
        combo = self.root.findChild(QObject, "themeCombo")
        combo.forceActiveFocus(Qt.TabFocusReason)
        self.key(Qt.Key_Down)
        self.assertEqual(self.window.view_model.theme, "light")
        self.assertFalse(self.root.property("darkMode"))

    def test_limits_panel_contains_all_rows_including_more_than_three(self):
        panel = self.root.findChild(QObject, "limitsPanel")
        content = self.root.findChild(QObject, "limitsContent")
        self.assertEqual(len(self.window.view_model.limits), 6)
        self.assertGreaterEqual(panel.height(), 90)
        self.assertEqual(content.property("count"), 6)
        self.assertGreater(content.property("contentHeight"), content.height())

    def test_catch_log_declares_evolution_arrows(self):
        qml = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "poketokenbar_windows"
            / "qml"
            / "Main.qml"
        ).read_text(encoding="utf-8")
        self.assertIn('objectName: "evolutionArrow"', qml)
        self.assertIn('visible: index > 0; text: "→"', qml)
        self.assertEqual(len(self.window.view_model.catches[-1]["stages"]), 3)

    def test_collection_can_be_paged_and_switched_using_keyboard(self):
        self.root.setProperty("currentPage", 1)
        self.app.processEvents()
        self.activate("Show normal Pokemon 1")
        self.assertFalse(self.window.view_model.dexEntries[0]["showShiny"])
        self.activate("Next →")
        self.assertEqual(self.window.view_model.dexPage, 2)
        self.activate("← Previous")
        self.assertEqual(self.window.view_model.dexPage, 1)
        self.activate("Collection view: Catch log")
        self.assertEqual(self.root.property("collectionMode"), "catches")
        self.activate("Collection view: Pokédex")
        self.assertEqual(self.root.property("collectionMode"), "dex")


if __name__ == "__main__":
    unittest.main()
