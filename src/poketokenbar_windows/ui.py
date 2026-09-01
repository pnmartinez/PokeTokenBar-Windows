from __future__ import annotations

import copy
import json
import os
import sys
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QIODevice,
    QObject,
    QPoint,
    QSettings,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QIcon,
    QImage,
    QMovie,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSystemTrayIcon,
    QTabWidget,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from .formatting import (
    DEFAULT_FORECAST_ENABLED,
    DEFAULT_LIMIT_DISPLAY_MODE,
    DEFAULT_LIMIT_TIME_MODE,
    FORECAST_ENABLED_KEY,
    LIMIT_DISPLAY_MODE_KEY,
    LIMIT_TIME_MODE_KEY,
    LimitDisplayMode,
    LimitTimeMode,
    companion_level_text,
    compact_tokens,
    format_limit_event_time,
    highest_relevant_limit,
    is_reserve_window,
    limit_alert_body,
    limit_forecast,
    limit_forecast_unavailable_reason,
    limit_percent_text,
    limit_reset_expiry,
    limit_reset_tray_warning,
    money,
    normalize_limit_display_mode,
    normalize_limit_time_mode,
    ordered_limit_windows,
    provider_limit_rows,
)
from .floating_pet import (
    MENU_OPEN_LABEL,
    MENU_PET_VISIBILITY_LABEL,
    MENU_QUIT_LABEL,
    MENU_REFRESH_LABEL,
    PET_ALERTS_KEY,
    PET_ENABLED_KEY,
    PET_SIZE_KEY,
    AnimatedSpriteFrameStabilizer,
    FloatingPetController,
)
from .limits import fetch_all_limits
from .models import ProviderLimits, UsageSnapshot
from .notifications import (
    COMPANION_NOTIFICATIONS_KEY,
    CRITICAL_MAX,
    CRITICAL_MIN,
    CRITICAL_THRESHOLD_KEY,
    DEFAULT_COMPANION_NOTIFICATIONS,
    DEFAULT_CRITICAL_THRESHOLD,
    DEFAULT_LIMIT_NOTIFICATIONS,
    DEFAULT_WARNING_THRESHOLD,
    LIMIT_NOTIFICATIONS_KEY,
    THRESHOLD_STEP,
    WARNING_MAX,
    WARNING_MIN,
    WARNING_THRESHOLD_KEY,
    companion_notification,
    evaluate_limit_alerts,
    normalize_critical_threshold,
    normalize_warning_threshold,
)
from .pet_logic import PET_DEFAULT_SIZE, PET_MAX_SIZE, PET_MIN_SIZE, PET_SIZE_STEP, normalize_pet_size, settings_bool
from .pokemon import EGG_HATCH_THRESHOLD, PokeAPIClient, egg_price, phase_threshold
from .qml_ui import QmlMainWindow
from .state import (
    GameState,
    StateStore,
    apply_limit_rewards,
    apply_usage,
    buy_egg,
    buy_item,
    companion_progress_percent,
    owned_representative_options,
    representative_subject,
    set_representative,
    usage_delta,
    use_item,
)
from .usage import PROVIDER_LABELS, scan_all
from .windows import APP_NAME, apply_native_window_icon, autostart_enabled, cache_dir, set_autostart, state_dir


@dataclass(slots=True)
class RefreshResult:
    snapshot: UsageSnapshot
    limits: dict[str, ProviderLimits]
    scan_errors: dict[str, str]
    state: GameState
    events: list[str]
    sprite_path: Path | None
    display_name: str
    pet_sprite_path: Path | None = None
    pet_display_name: str = "Pokemon Egg"
    pet_is_egg: bool = True
    reveal_ball_path: Path | None = None


def application_settings() -> QSettings:
    """Use an isolated INI backend for QA while preserving production registry settings."""
    if os.environ.get("PTB_STATE_DIR", "").strip():
        path = state_dir() / "settings.ini"
        path.parent.mkdir(parents=True, exist_ok=True)
        settings = QSettings(str(path), QSettings.Format.IniFormat)
    else:
        settings = QSettings("PokeTokenBar", "PokeTokenBar-Windows")
    _migrate_legacy_settings(settings)
    return settings


def _migrate_legacy_settings(settings: QSettings) -> None:
    """Preserve preferences written by the first desktop-pet UI on master."""
    migrations: tuple[tuple[str, str, Callable[[Any], Any]], ...] = (
        ("pet_visible", PET_ENABLED_KEY, lambda value: settings_bool(value, False)),
        ("pet_size", PET_SIZE_KEY, normalize_pet_size),
        (
            "notify_limits",
            LIMIT_NOTIFICATIONS_KEY,
            lambda value: settings_bool(value, DEFAULT_LIMIT_NOTIFICATIONS),
        ),
        ("limit_warning", WARNING_THRESHOLD_KEY, normalize_warning_threshold),
        ("limit_critical", CRITICAL_THRESHOLD_KEY, normalize_critical_threshold),
        (
            "notify_events",
            COMPANION_NOTIFICATIONS_KEY,
            lambda value: settings_bool(value, DEFAULT_COMPANION_NOTIFICATIONS),
        ),
    )
    changed = False
    for legacy_key, current_key, convert in migrations:
        if settings.contains(current_key) or not settings.contains(legacy_key):
            continue
        settings.setValue(current_key, convert(settings.value(legacy_key)))
        changed = True
    if not settings.contains(LIMIT_DISPLAY_MODE_KEY) and settings.contains("limits_show_remaining"):
        settings.setValue(
            LIMIT_DISPLAY_MODE_KEY,
            "remaining"
            if settings_bool(settings.value("limits_show_remaining"), False)
            else "used",
        )
        changed = True
    if changed:
        settings.sync()


def tray_tooltip(
    result: RefreshResult,
    *,
    show_tokens: bool = True,
    show_cost: bool = False,
    show_limit: bool = True,
    limit_display_mode: LimitDisplayMode = DEFAULT_LIMIT_DISPLAY_MODE,
    limit_time_mode: LimitTimeMode = DEFAULT_LIMIT_TIME_MODE,
) -> str:
    parts: list[str] = []
    if show_tokens:
        parts.append(f"{compact_tokens(result.snapshot.today_tokens)} today")
    if show_cost:
        parts.append(money(result.snapshot.today_cost))
    if result.state.mon:
        parts.append(result.display_name)
    else:
        parts.append("egg")
    parts.append(companion_level_text(companion_progress_percent(result.state)))

    warnings: list[tuple[float, str]] = []
    for limits in result.limits.values():
        warning = limit_reset_tray_warning(
            limits,
            time_mode=limit_time_mode,
        )
        expiry = limit_reset_expiry(limits)
        if warning and expiry is not None:
            warnings.append((expiry.timestamp(), warning))
    if show_limit:
        selected = highest_relevant_limit(result.snapshot, result.limits)
        if selected is not None:
            provider, window = selected
            parts.append(
                f"{provider.title()} {window.label}: "
                f"{limit_percent_text(window.used_percent, limit_display_mode, compact=True)}"
            )
    if show_limit and warnings:
        parts.append(min(warnings, key=lambda item: item[0])[1])
    return f"{APP_NAME} · {' · '.join(parts)}"


def theme_stylesheet(theme: str) -> str:
    common = (
        "QTabBar::tab { padding: 8px 12px; margin: 1px; }"
        "QGroupBox { margin-top: 10px; padding: 10px; border: 1px solid palette(mid); border-radius: 8px; }"
        "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; font-weight: 600; }"
        "QProgressBar { min-height: 8px; border: 0; border-radius: 4px; background: palette(midlight); }"
        "QPushButton:focus, QComboBox:focus, QListWidget:focus { border: 2px solid #2563eb; }"
    )
    if theme == "dark":
        return (
            "QWidget { background: #17191d; color: #f3f4f6; }"
            "QScrollArea, QScrollArea QWidget { background: #17191d; color: #f3f4f6; }"
            "QFrame, QGroupBox, QListWidget, QTabWidget::pane { border-color: #3f4652; }"
            "QPushButton, QComboBox { background: #292e36; border: 1px solid #4b5563; padding: 6px; border-radius: 6px; }"
            "QPushButton:disabled { color: #7c8491; } QToolTip { background: #111827; color: white; }"
            + common
        )
    if theme == "light":
        return (
            "QWidget { background: #faf9f7; color: #202124; }"
            "QPushButton, QComboBox { background: white; border: 1px solid #d7d2ca; padding: 6px; border-radius: 6px; }"
            "QPushButton:disabled { color: #9ca3af; }"
            + common
        )
    return common


class Bridge(QObject):
    refreshed = Signal(object)
    failed = Signal(str)


def _pokeball_pixmap(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = max(1, size // 16)
    diameter = size - margin * 2
    band = max(2, size // 10)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#e53935"))
    painter.drawPie(margin, margin, diameter, diameter, 0, 180 * 16)
    painter.setBrush(QColor("#fafafa"))
    painter.drawPie(margin, margin, diameter, diameter, 180 * 16, 180 * 16)
    painter.setBrush(QColor("#202124"))
    painter.drawRect(margin, size // 2 - band // 2, diameter, band)
    outline = QPen(QColor("#202124"))
    outline.setWidth(max(2, size // 14))
    painter.setPen(outline)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(margin, margin, diameter, diameter)
    radius = max(3, size // 6)
    painter.setPen(QPen(QColor("#202124"), max(2, size // 16)))
    painter.setBrush(QColor("#fafafa"))
    painter.drawEllipse(size // 2 - radius, size // 2 - radius, radius * 2, radius * 2)
    painter.end()
    return pixmap


def _pokeball_ico_bytes() -> bytes:
    images: list[tuple[int, bytes]] = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        ba = QByteArray()
        buffer = QBuffer(ba)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        _pokeball_pixmap(size).save(buffer, "PNG")
        images.append((size, bytes(ba.data())))
    count = len(images)
    offset = 6 + 16 * count
    directory = bytearray(b"\x00\x00\x01\x00") + count.to_bytes(2, "little")
    payload = bytearray()
    for size, png in images:
        stored = 0 if size >= 256 else size
        directory += bytes((stored, stored, 0, 0, 1, 0, 32, 0))
        directory += len(png).to_bytes(4, "little")
        directory += offset.to_bytes(4, "little")
        payload += png
        offset += len(png)
    return bytes(directory) + bytes(payload)


def application_icon() -> QIcon:
    icon_path = cache_dir() / "app.ico"
    try:
        icon_path.parent.mkdir(parents=True, exist_ok=True)
        icon_path.write_bytes(_pokeball_ico_bytes())
        icon = QIcon(str(icon_path))
        if not icon.isNull():
            return icon
    except OSError:
        pass
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_pokeball_pixmap(size))
    return icon


def _egg_pixmap(size: int = 128) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = size // 8
    egg = (margin + size // 16, margin, size - margin * 2 - size // 8, size - margin * 2)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(0, 0, 0, 28))
    painter.drawEllipse(egg[0] + size // 24, egg[1] + size // 8, egg[2], egg[3])
    painter.setBrush(QColor("#f7ead0"))
    painter.setPen(QPen(QColor("#c4a574"), max(2, size // 32)))
    painter.drawEllipse(*egg)
    painter.setPen(Qt.PenStyle.NoPen)
    spots = (
        ("#6eb8b0", 0.32, 0.28, 0.18),
        ("#7ec8c0", 0.58, 0.42, 0.14),
        ("#5aa39c", 0.40, 0.55, 0.12),
        ("#8fd4cc", 0.28, 0.48, 0.10),
        ("#6eb8b0", 0.55, 0.22, 0.10),
    )
    for color, nx, ny, nr in spots:
        painter.setBrush(QColor(color))
        diameter = int(egg[2] * nr)
        painter.drawEllipse(
            int(egg[0] + egg[2] * nx - diameter / 2),
            int(egg[1] + egg[3] * ny - diameter / 2),
            diameter,
            diameter,
        )
    painter.setBrush(QColor(255, 255, 255, 90))
    painter.drawEllipse(
        int(egg[0] + egg[2] * 0.28),
        int(egg[1] + egg[3] * 0.16),
        int(egg[2] * 0.22),
        int(egg[3] * 0.16),
    )
    painter.end()
    return pixmap


def _pokeball_icon(size: int = 64) -> QIcon:
    icon = QIcon()
    icon.addPixmap(_pokeball_pixmap(size))
    icon.addPixmap(_pokeball_pixmap(32))
    icon.addPixmap(_pokeball_pixmap(16))
    return icon


def _sprite_pixmap(path: Path | None, box: int = 96) -> QPixmap:
    pix = QPixmap()
    if path is not None and path.exists():
        if path.suffix.lower() == ".gif":
            movie = QMovie(str(path))
            if movie.isValid():
                movie.jumpToFrame(0)
                pix = movie.currentPixmap()
        else:
            pix = QPixmap(str(path))
    if pix.isNull():
        return QPixmap()
    return pix.scaled(box, box, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)


def _muted_pixmap(pix: QPixmap) -> QPixmap:
    if pix.isNull():
        return pix
    image = pix.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            grey = int(0.3 * color.red() + 0.59 * color.green() + 0.11 * color.blue())
            color.setRgb(grey, grey, grey, int(color.alpha() * 0.4))
            image.setPixelColor(x, y, color)
    return QPixmap.fromImage(image)


def _icon_from_sprite(path: Path | None, *, fallback_egg: bool = False) -> QIcon:
    pix = _sprite_pixmap(path, 128)
    if pix.isNull():
        pix = _egg_pixmap(128) if fallback_egg else _pokeball_pixmap(128)
    return QIcon(pix)


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child = item.layout()
        if widget is not None:
            widget.hide()
            widget.deleteLater()
        elif child is not None:
            _clear_layout(child)


def _data_cache_dir() -> Path:
    path = cache_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _autostart_enabled() -> bool:
    return autostart_enabled()


def _set_autostart(enabled: bool) -> None:
    set_autostart(enabled)


class MetricCard(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        self.title = QLabel(title)
        self.value = QLabel("-")
        font = self.value.font()
        font.setPointSize(font.pointSize() + 4)
        font.setBold(True)
        self.value.setFont(font)
        layout.addWidget(self.title)
        layout.addWidget(self.value)


class DesktopPet(QWidget):
    """Small, draggable companion that stays available outside the main window."""

    open_requested = Signal()
    refresh_requested = Signal()
    visibility_changed = Signal(bool)

    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self.movie: QMovie | None = None
        self._drag_origin: QPoint | None = None
        self._dragged = False
        self._tooltip = APP_NAME
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.sprite = QLabel(self)
        self.sprite.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sprite.setStyleSheet("background: transparent;")
        self.progress_overlay = QLabel(self)
        self.progress_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_overlay.setWordWrap(True)
        self.progress_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.progress_overlay.setStyleSheet(
            "QLabel { background: rgba(17, 24, 39, 210); color: white; border-radius: 8px; "
            "padding: 5px 7px; font-weight: 600; }"
        )
        self.progress_overlay.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.sprite)
        self.set_size(int(settings.value("pet_size", 112)))

        menu = QMenu(self)
        menu.addAction("Open PokeTokenBar", self.open_requested.emit)
        menu.addAction("Refresh", self.refresh_requested.emit)
        menu.addSeparator()
        menu.addAction("Hide desktop pet", lambda: self.visibility_changed.emit(False))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda point: menu.exec(self.mapToGlobal(point)))

    def set_size(self, size: int) -> None:
        size = max(64, min(192, size))
        self.settings.setValue("pet_size", size)
        self.setFixedSize(size, size)
        self.sprite.setFixedSize(size, size)
        if self.movie is not None:
            self.movie.setScaledSize(QSize(size, size))

    def set_sprite(self, path: Path | None, *, egg: bool = False) -> None:
        if self.movie is not None:
            self.movie.stop()
            self.movie = None
        size = self.width()
        if path is not None and path.exists() and path.suffix.lower() == ".gif":
            movie = QMovie(str(path))
            if movie.isValid():
                movie.setScaledSize(QSize(size, size))
                self.sprite.setMovie(movie)
                self.movie = movie
                movie.start()
                return
        pix = _sprite_pixmap(path, size)
        self.sprite.setPixmap(pix if not pix.isNull() else (_egg_pixmap(size) if egg else _pokeball_pixmap(size)))

    def set_status(self, text: str) -> None:
        self._tooltip = text
        self.setToolTip(text)

    def set_progress(self, percent: int, destination: str) -> None:
        self.progress_overlay.setText(
            f"{destination} · {companion_level_text(percent)}"
        )
        self._position_progress_overlay()

    def _position_progress_overlay(self) -> None:
        margin = max(4, self.width() // 24)
        height = max(30, self.progress_overlay.sizeHint().height())
        self.progress_overlay.setGeometry(margin, self.height() - height - margin, self.width() - margin * 2, height)
        self.progress_overlay.raise_()

    def show_bubble(self, text: str) -> None:
        QToolTip.showText(self.mapToGlobal(QPoint(self.width() // 2, 0)), text, self)

    def restore_position(self) -> None:
        x = int(self.settings.value("pet_x", -1))
        y = int(self.settings.value("pet_y", -1))
        screen = QApplication.primaryScreen()
        if x < 0 or y < 0:
            area = screen.availableGeometry() if screen else self.geometry()
            x = area.right() - self.width() - 24
            y = area.bottom() - self.height() - 24
        self.move(x, y)
        self.clamp_to_screen()

    def clamp_to_screen(self) -> None:
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = min(max(self.x(), area.left()), area.right() - self.width() + 1)
        y = min(max(self.y(), area.top()), area.bottom() - self.height() + 1)
        self.move(x, y)
        self.settings.setValue("pet_x", x)
        self.settings.setValue("pet_y", y)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint() - self.pos()
            self._dragged = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            target = event.globalPosition().toPoint() - self._drag_origin
            self._dragged = self._dragged or (target - self.pos()).manhattanLength() > 3
            self.move(target)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self._drag_origin = None
            if self._dragged:
                self.clamp_to_screen()
            else:
                self.open_requested.emit()
        super().mouseReleaseEvent(event)

    def showEvent(self, event) -> None:
        if self.movie is not None:
            self.movie.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        if self.movie is not None:
            self.movie.stop()
        super().hideEvent(event)

    def enterEvent(self, event) -> None:
        self._position_progress_overlay()
        self.progress_overlay.show()
        self.progress_overlay.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.progress_overlay.hide()
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:
        self._position_progress_overlay()
        super().resizeEvent(event)


class MainWindow(QMainWindow):
    refresh_requested = Signal()
    pet_visibility_changed = Signal(bool)
    pet_size_changed = Signal(int)
    preferences_changed = Signal()
    representative_changed = Signal(object)
    language_changed = Signal(str)
    import_requested = Signal()
    export_requested = Signal()

    def __init__(self, state: GameState, settings: QSettings, api: PokeAPIClient):
        super().__init__()
        self.state = state
        self.settings = settings
        self.api = api
        self.movie: QMovie | None = None
        self.frame_stabilizer = AnimatedSpriteFrameStabilizer()
        self.reveal_timer = QTimer(self)
        self.reveal_timer.setInterval(70)
        self.reveal_timer.timeout.connect(self._advance_companion_reveal)
        self.reveal_frame = 0
        self.reveal_target_path: Path | None = None
        self.reveal_target_is_egg = False
        self.reveal_ball_pixmap = QPixmap()
        self.reveal_target_pixmap = QPixmap()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(application_icon())
        self.setMinimumSize(520, 640)
        self.resize(560, 740)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_home(), "Home")
        self.tabs.addTab(self._build_collection(), "Collection")
        self.tabs.addTab(self._build_bag(), "Bag")
        self.tabs.addTab(self._build_shop(), "Shop")
        self.tabs.addTab(self._wrap_scroll(self._build_settings()), "Settings")
        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage("Ready")
        refresh_shortcut = QAction("Refresh", self)
        refresh_shortcut.setShortcut("Ctrl+R")
        refresh_shortcut.triggered.connect(self.refresh_requested.emit)
        self.addAction(refresh_shortcut)
        for index in range(self.tabs.count()):
            tab_shortcut = QAction(self)
            tab_shortcut.setShortcut(f"Alt+{index + 1}")
            tab_shortcut.triggered.connect(lambda checked=False, target=index: self.tabs.setCurrentIndex(target))
            self.addAction(tab_shortcut)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        apply_native_window_icon(int(self.winId()), cache_dir() / "app.ico")
        if self.movie is not None:
            self.movie.start()

    def hideEvent(self, event) -> None:
        if self.movie is not None:
            self.movie.stop()
        super().hideEvent(event)

    def _build_home(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        self.celebration_label = QLabel("")
        self.celebration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.celebration_label.setWordWrap(True)
        self.celebration_label.setStyleSheet(
            "QLabel { background: #fef3c7; color: #92400e; border-radius: 10px; padding: 10px; font-weight: bold; }"
        )
        self.celebration_label.hide()
        layout.addWidget(self.celebration_label)

        hero = QHBoxLayout()
        self.sprite = QLabel()
        self.sprite.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sprite.setFixedSize(128, 128)
        self.sprite.setStyleSheet("QLabel { background: palette(base); border: 1px solid palette(mid); border-radius: 16px; }")
        self.sprite.setPixmap(_egg_pixmap(112))
        hero.addWidget(self.sprite)
        meta = QVBoxLayout()
        self.name_label = QLabel("Pokemon Egg")
        f = self.name_label.font()
        f.setPointSize(f.pointSize() + 6)
        f.setBold(True)
        self.name_label.setFont(f)
        self.name_label.setWordWrap(True)
        self.detail_label = QLabel("Use tokens to hatch it")
        self.detail_label.setWordWrap(True)
        self.evolution_label = QLabel("Hatch the egg to discover its evolution line")
        self.evolution_label.setWordWrap(True)
        self.evolution_label.setStyleSheet("color: #6b7280;")
        self.progress_label = QLabel("")
        self.progress_percent_label = QLabel("Lv. 0")
        percent_font = self.progress_percent_label.font()
        percent_font.setBold(True)
        self.progress_percent_label.setFont(percent_font)
        self.progress_percent_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        progress_stats = QHBoxLayout()
        progress_stats.setContentsMargins(0, 0, 0, 0)
        progress_stats.addWidget(self.progress_label)
        progress_stats.addStretch(1)
        progress_stats.addWidget(self.progress_percent_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(12)
        meta.addWidget(self.name_label)
        meta.addWidget(self.detail_label)
        meta.addWidget(self.evolution_label)
        meta.addLayout(progress_stats)
        meta.addWidget(self.progress)
        meta.addStretch(1)
        hero.addLayout(meta, 1)
        layout.addLayout(hero)

        metrics = QGridLayout()
        self.today_card = MetricCard("Today")
        self.cost_card = MetricCard("Est. cost")
        self.week_card = MetricCard("This week")
        self.wallet_card = MetricCard("Shop wallet")
        metrics.addWidget(self.today_card, 0, 0)
        metrics.addWidget(self.cost_card, 0, 1)
        metrics.addWidget(self.week_card, 1, 0)
        metrics.addWidget(self.wallet_card, 1, 1)
        layout.addLayout(metrics)

        heading = QHBoxLayout()
        label = QLabel("Providers")
        lf = label.font(); lf.setBold(True); label.setFont(lf)
        heading.addWidget(label)
        heading.addStretch(1)
        self.refresh_status = QLabel("Ready")
        self.refresh_status.setStyleSheet("color: #6b7280;")
        heading.addWidget(self.refresh_status)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Scan local usage and official limits now")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        heading.addWidget(self.refresh_button)
        layout.addLayout(heading)

        self.providers_tabs = QTabWidget()
        self.providers_list = QListWidget()
        self.providers_tabs.addTab(self.providers_list, "Summary")
        self.providers_tabs.tabBar().hide()
        self.providers_tabs.setMaximumHeight(130)
        layout.addWidget(self.providers_tabs)

        limits_label = QLabel("Official limits")
        lf = limits_label.font(); lf.setBold(True); limits_label.setFont(lf)
        layout.addWidget(limits_label)
        self.limits_list = QListWidget()
        self.limits_list.setMinimumHeight(190)
        self.limits_list.setWordWrap(True)
        self.limits_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.limits_list, 1)
        return root

    def _build_collection(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        representative_row = QHBoxLayout()
        representative_row.addWidget(QLabel("Desktop representative"))
        self.representative_combo = QComboBox()
        self.representative_combo.setToolTip("Choose a collected species for the tray and desktop pet")
        self.representative_combo.currentIndexChanged.connect(self._choose_representative)
        representative_row.addWidget(self.representative_combo, 1)
        layout.addLayout(representative_row)
        inner = QTabWidget()
        inner.addTab(self._wrap_scroll(self._build_dex_page()), "Pokédex")
        inner.addTab(self._wrap_scroll(self._build_catch_page()), "Catch log")
        layout.addWidget(inner)
        return root

    def _wrap_scroll(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(widget)
        return scroll

    def _build_dex_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        self.dex_page = 0
        dex_header = QHBoxLayout()
        self.dex_counts = QLabel("0 species")
        dex_header.addWidget(self.dex_counts)
        dex_header.addStretch(1)
        self.dex_prev = QPushButton("←")
        self.dex_prev.setToolTip("Previous Pokédex page")
        self.dex_next = QPushButton("→")
        self.dex_next.setToolTip("Next Pokédex page")
        self.dex_page_label = QLabel("Page 1 / 1")
        self.dex_prev.clicked.connect(lambda: self._change_dex_page(-1))
        self.dex_next.clicked.connect(lambda: self._change_dex_page(1))
        dex_header.addWidget(self.dex_prev)
        dex_header.addWidget(self.dex_page_label)
        dex_header.addWidget(self.dex_next)
        layout.addLayout(dex_header)
        self.dex_empty = QLabel("No Pokemon hatched yet")
        self.dex_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.dex_empty)
        self.dex_grid = QGridLayout()
        self.dex_grid.setSpacing(10)
        layout.addLayout(self.dex_grid)
        layout.addStretch(1)
        return page

    def _change_dex_page(self, delta: int) -> None:
        self.dex_page = max(0, self.dex_page + delta)
        self._render_collection()

    def _build_catch_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        self.catch_empty = QLabel("No Pokemon hatched yet")
        self.catch_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.catch_empty)
        self.catch_list = QVBoxLayout()
        self.catch_list.setSpacing(10)
        layout.addLayout(self.catch_list)
        layout.addStretch(1)
        return page

    def _build_bag(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        title = QLabel("Your bag")
        font = title.font(); font.setPointSize(font.pointSize() + 4); font.setBold(True); title.setFont(font)
        layout.addWidget(title)
        self.wallet_bag_label = QLabel()
        self.wallet_bag_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.wallet_bag_label)
        self.bag_label = QLabel()
        self.bag_label.setWordWrap(True)
        layout.addWidget(self.bag_label)
        self.bag_empty = QLabel("Your bag is empty. Earn tokens, then visit the Shop.")
        self.bag_empty.setWordWrap(True)
        self.bag_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bag_empty.setStyleSheet("color: #6b7280; padding: 18px;")
        layout.addWidget(self.bag_empty)
        actions = QGridLayout()
        self.use_candy_btn = QPushButton("Use Rare Candy")
        self.use_mint_btn = QPushButton("Use Mint")
        self.use_candy_btn.setToolTip("Adds progression tokens to the current egg or companion")
        self.use_mint_btn.setToolTip("Changes the current companion's nature")
        actions.addWidget(self.use_candy_btn, 0, 0)
        actions.addWidget(self.use_mint_btn, 0, 1)
        layout.addLayout(actions)
        self.action_feedback = QLabel("")
        self.action_feedback.setWordWrap(True)
        self.action_feedback.setStyleSheet("color: #166534; padding: 8px 0;")
        layout.addWidget(self.action_feedback)
        layout.addStretch(1)
        return root

    def celebrate(self, text: str, *, shiny: bool = False) -> None:
        self.celebration_label.setText(("✨ " if shiny else "🎉 ") + text)
        self.celebration_label.show()
        QTimer.singleShot(4500, self.celebration_label.hide)

    def _choose_representative(self) -> None:
        if self.representative_combo.signalsBlocked():
            return
        self.representative_changed.emit(
            self._representative_selection_data(
                self.representative_combo.currentData()
            )
        )

    @staticmethod
    def _representative_selection_data(value: object) -> tuple[int, bool] | None:
        """Normalize QVariantList data back to the tuple stored by the app."""
        if isinstance(value, (tuple, list)) and len(value) == 2:
            try:
                return int(value[0]), bool(value[1])
            except (TypeError, ValueError):
                return None
        return None

    def _build_shop(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        heading = QHBoxLayout()
        title = QLabel("Shop")
        font = title.font(); font.setPointSize(font.pointSize() + 4); font.setBold(True); title.setFont(font)
        heading.addWidget(title)
        heading.addStretch(1)
        self.wallet_shop_label = QLabel()
        wallet_font = self.wallet_shop_label.font(); wallet_font.setBold(True); self.wallet_shop_label.setFont(wallet_font)
        heading.addWidget(self.wallet_shop_label)
        layout.addLayout(heading)
        hint = QLabel("Spend only tokens observed since PokeTokenBar was installed.")
        hint.setStyleSheet("color: #6b7280;")
        layout.addWidget(hint)
        actions = QGridLayout()
        self.buy_candy_btn = QPushButton("🍬 Rare Candy\nProgress boost · 500M")
        self.buy_mint_btn = QPushButton("🌿 Mint\nChange nature · 100M")
        self.buy_charm_btn = QPushButton("✨ Shiny Charm\nBetter Shiny odds · 3B")
        self.buy_egg_btn = QPushButton("🥚 Normal Egg\nFresh companion · 1B")
        self.buy_uncommon_egg_btn = QPushButton(f"🔵 Uncommon Egg\nUncommon+ · {compact_tokens(egg_price('uncommon'))}")
        self.buy_rare_egg_btn = QPushButton(f"🟣 Rare Egg\nRare+ · {compact_tokens(egg_price('rare'))}")
        for index, button in enumerate([
            self.buy_candy_btn, self.buy_mint_btn, self.buy_charm_btn,
            self.buy_egg_btn, self.buy_uncommon_egg_btn, self.buy_rare_egg_btn,
        ]):
            button.setMinimumHeight(64)
            actions.addWidget(button, index // 2, index % 2)
        layout.addLayout(actions)
        layout.addStretch(1)
        return root

    def _build_settings(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        general = QGroupBox("General")
        general_layout = QVBoxLayout(general)
        row = QHBoxLayout()
        row.addWidget(QLabel("Refresh interval"))
        self.interval_combo = QComboBox()
        for minutes in (1, 2, 5, 10, 15):
            self.interval_combo.addItem(f"{minutes} min", minutes)
        current = int(self.settings.value("refresh_minutes", 5))
        idx = self.interval_combo.findData(current)
        self.interval_combo.setCurrentIndex(max(0, idx))
        self.interval_combo.currentIndexChanged.connect(self._save_interval)
        row.addWidget(self.interval_combo)
        row.addStretch(1)
        general_layout.addLayout(row)

        self.autostart_check = QCheckBox("Start automatically after login")
        self.autostart_check.setChecked(_autostart_enabled())
        self.autostart_check.toggled.connect(self._toggle_autostart)
        general_layout.addWidget(self.autostart_check)
        language_row = QHBoxLayout()
        language_row.addWidget(QLabel("Pokémon names"))
        self.language_combo = QComboBox()
        for label, code in (("English", "en"), ("Español", "es"), ("Français", "fr"), ("日本語", "ja")):
            self.language_combo.addItem(label, code)
        language_index = self.language_combo.findData(self.state.language)
        self.language_combo.setCurrentIndex(max(0, language_index))
        self.language_combo.currentIndexChanged.connect(
            lambda: self.language_changed.emit(str(self.language_combo.currentData()))
        )
        language_row.addWidget(self.language_combo)
        language_row.addStretch(1)
        general_layout.addLayout(language_row)
        layout.addWidget(general)

        desktop = QGroupBox("Desktop pet")
        desktop_layout = QVBoxLayout(desktop)
        self.pet_check = QCheckBox("Show companion on the desktop")
        self.pet_check.setChecked(
            settings_bool(self.settings.value(PET_ENABLED_KEY, False), False)
        )
        self.pet_check.toggled.connect(self._save_pet_visibility)
        desktop_layout.addWidget(self.pet_check)
        pet_size_row = QHBoxLayout()
        pet_size_row.addWidget(QLabel("Size"))
        self.pet_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.pet_size_slider.setRange(PET_MIN_SIZE, PET_MAX_SIZE)
        self.pet_size_slider.setSingleStep(PET_SIZE_STEP)
        self.pet_size_slider.setPageStep(PET_SIZE_STEP)
        self.pet_size_slider.setTickInterval(PET_SIZE_STEP)
        self.pet_size_slider.setValue(
            normalize_pet_size(self.settings.value(PET_SIZE_KEY, PET_DEFAULT_SIZE))
        )
        self.pet_size_slider.valueChanged.connect(self._save_pet_size)
        pet_size_row.addWidget(self.pet_size_slider, 1)
        self.pet_size_label = QLabel(f"{self.pet_size_slider.value()} px")
        pet_size_row.addWidget(self.pet_size_label)
        desktop_layout.addLayout(pet_size_row)
        self.pet_alerts_check = self._setting_check(
            "Show transient usage and full-reset bubbles", PET_ALERTS_KEY, True
        )
        desktop_layout.addWidget(self.pet_alerts_check)
        self._set_pet_controls_enabled(self.pet_check.isChecked())
        layout.addWidget(desktop)

        tray_group = QGroupBox("Tray tooltip")
        tray_layout = QVBoxLayout(tray_group)
        self.tray_tokens_check = self._setting_check("Show today's tokens", "tray_show_tokens", True)
        self.tray_cost_check = self._setting_check("Show estimated cost", "tray_show_cost", False)
        self.tray_limit_check = self._setting_check("Show highest limit percentage", "tray_show_limit", True)
        for check in (self.tray_tokens_check, self.tray_cost_check, self.tray_limit_check):
            tray_layout.addWidget(check)
        layout.addWidget(tray_group)

        limits_group = QGroupBox("Limits")
        limits_layout = QVBoxLayout(limits_group)
        display_row = QHBoxLayout()
        display_row.addWidget(QLabel("Display official limits as"))
        display_mode = normalize_limit_display_mode(
            self.settings.value(
                LIMIT_DISPLAY_MODE_KEY,
                DEFAULT_LIMIT_DISPLAY_MODE,
            )
        )
        self.limit_display_toggle = QFrame()
        self.limit_display_toggle.setObjectName("LimitModeToggle")
        toggle_layout = QHBoxLayout(self.limit_display_toggle)
        toggle_layout.setContentsMargins(0, 0, 0, 0)
        toggle_layout.setSpacing(0)
        self.limit_display_group = QButtonGroup(self.limit_display_toggle)
        self.limit_display_group.setExclusive(True)
        self.limit_used_button = QPushButton("Used")
        self.limit_remaining_button = QPushButton("Remaining")
        for button, mode in (
            (self.limit_used_button, "used"),
            (self.limit_remaining_button, "remaining"),
        ):
            button.setObjectName(
                "LimitModeUsedSegment" if mode == "used" else "LimitModeRemainingSegment"
            )
            button.setProperty("limitModeSegment", True)
            button.setCheckable(True)
            button.setProperty("limitMode", mode)
            button.setFixedWidth(112)
            button.setToolTip(
                "Show quota consumed" if mode == "used" else "Show quota left"
            )
            self.limit_display_group.addButton(button)
            toggle_layout.addWidget(button)
        self.limit_used_button.setChecked(display_mode == "used")
        self.limit_remaining_button.setChecked(display_mode == "remaining")
        self.limit_display_group.buttonClicked.connect(
            lambda button: self._save_preference(
                LIMIT_DISPLAY_MODE_KEY,
                str(button.property("limitMode")),
            )
        )
        self.limit_display_toggle.setStyleSheet(
            "QPushButton[limitModeSegment='true'] {"
            "  border: 1px solid palette(mid); padding: 5px 12px; margin: 0;"
            "  background: palette(button);"
            "}"
            "QPushButton#LimitModeUsedSegment {"
            "  border-top-left-radius: 6px; border-bottom-left-radius: 6px;"
            "  border-right-width: 0;"
            "}"
            "QPushButton#LimitModeRemainingSegment {"
            "  border-top-right-radius: 6px; border-bottom-right-radius: 6px;"
            "}"
            "QPushButton[limitModeSegment='true']:checked {"
            "  background: #2563eb; color: white; border-color: #2563eb;"
            "  font-weight: 600;"
            "}"
        )
        display_row.addWidget(self.limit_display_toggle)
        display_row.addStretch(1)
        limits_layout.addLayout(display_row)
        display_hint = QLabel(
            "This applies to Home, the tray tooltip, the desktop-pet hover and alerts. "
            "Warning and critical thresholds always mean quota used."
        )
        display_hint.setWordWrap(True)
        display_hint.setStyleSheet("color: #6b7280;")
        limits_layout.addWidget(display_hint)
        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Show limit times as"))
        time_mode = normalize_limit_time_mode(
            self.settings.value(
                LIMIT_TIME_MODE_KEY,
                DEFAULT_LIMIT_TIME_MODE,
            )
        )
        self.limit_time_toggle = QFrame()
        self.limit_time_toggle.setObjectName("LimitTimeModeToggle")
        time_toggle_layout = QHBoxLayout(self.limit_time_toggle)
        time_toggle_layout.setContentsMargins(0, 0, 0, 0)
        time_toggle_layout.setSpacing(0)
        self.limit_time_group = QButtonGroup(self.limit_time_toggle)
        self.limit_time_group.setExclusive(True)
        self.limit_time_remaining_button = QPushButton("Time left")
        self.limit_time_datetime_button = QPushButton("Date & time")
        for button, mode in (
            (self.limit_time_remaining_button, "remaining"),
            (self.limit_time_datetime_button, "datetime"),
        ):
            button.setObjectName(
                "LimitTimeRemainingSegment"
                if mode == "remaining"
                else "LimitTimeDatetimeSegment"
            )
            button.setProperty("limitTimeModeSegment", True)
            button.setCheckable(True)
            button.setProperty("limitTimeMode", mode)
            button.setFixedWidth(112)
            button.setToolTip(
                "Show compact countdowns"
                if mode == "remaining"
                else "Show a short date and time"
            )
            self.limit_time_group.addButton(button)
            time_toggle_layout.addWidget(button)
        self.limit_time_remaining_button.setChecked(time_mode == "remaining")
        self.limit_time_datetime_button.setChecked(time_mode == "datetime")
        self.limit_time_group.buttonClicked.connect(
            lambda button: self._save_preference(
                LIMIT_TIME_MODE_KEY,
                str(button.property("limitTimeMode")),
            )
        )
        self.limit_time_toggle.setStyleSheet(
            "QPushButton[limitTimeModeSegment='true'] {"
            "  border: 1px solid palette(mid); padding: 5px 12px; margin: 0;"
            "  background: palette(button);"
            "}"
            "QPushButton#LimitTimeRemainingSegment {"
            "  border-top-left-radius: 6px; border-bottom-left-radius: 6px;"
            "  border-right-width: 0;"
            "}"
            "QPushButton#LimitTimeDatetimeSegment {"
            "  border-top-right-radius: 6px; border-bottom-right-radius: 6px;"
            "}"
            "QPushButton[limitTimeModeSegment='true']:checked {"
            "  background: #2563eb; color: white; border-color: #2563eb;"
            "  font-weight: 600;"
            "}"
        )
        time_row.addWidget(self.limit_time_toggle)
        time_row.addStretch(1)
        limits_layout.addLayout(time_row)
        time_hint = QLabel(
            "Applies to resets, depletion forecasts, reset-credit expiry and related warnings."
        )
        time_hint.setWordWrap(True)
        time_hint.setStyleSheet("color: #6b7280;")
        limits_layout.addWidget(time_hint)
        self.forecast_check = self._setting_check(
            "Show depletion forecast for timed limits",
            FORECAST_ENABLED_KEY,
            DEFAULT_FORECAST_ENABLED,
        )
        self.forecast_check.setToolTip(
            "Uses average quota consumption since each known window began. "
            "When a forecast cannot be calculated, the limit row explains why."
        )
        limits_layout.addWidget(self.forecast_check)
        self.limit_notifications_check = self._setting_check(
            "Limit notifications", LIMIT_NOTIFICATIONS_KEY, DEFAULT_LIMIT_NOTIFICATIONS
        )
        self.event_notifications_check = self._setting_check(
            "Pokémon event notifications",
            COMPANION_NOTIFICATIONS_KEY,
            DEFAULT_COMPANION_NOTIFICATIONS,
        )
        for check in (self.limit_notifications_check, self.event_notifications_check):
            limits_layout.addWidget(check)
        thresholds = QHBoxLayout()
        thresholds.addWidget(QLabel("Warning at"))
        self.warning_spin = QSpinBox()
        self.warning_spin.setRange(WARNING_MIN, WARNING_MAX)
        self.warning_spin.setSingleStep(THRESHOLD_STEP)
        self.warning_spin.setSuffix("% used")
        self.warning_spin.setValue(
            normalize_warning_threshold(
                self.settings.value(WARNING_THRESHOLD_KEY, DEFAULT_WARNING_THRESHOLD)
            )
        )
        self.warning_spin.valueChanged.connect(self._save_warning_threshold)
        thresholds.addWidget(self.warning_spin)
        thresholds.addWidget(QLabel("Critical at"))
        self.critical_spin = QSpinBox()
        self.critical_spin.setRange(CRITICAL_MIN, CRITICAL_MAX)
        self.critical_spin.setSingleStep(THRESHOLD_STEP)
        self.critical_spin.setSuffix("% used")
        self.critical_spin.setValue(
            normalize_critical_threshold(
                self.settings.value(CRITICAL_THRESHOLD_KEY, DEFAULT_CRITICAL_THRESHOLD)
            )
        )
        self.critical_spin.valueChanged.connect(self._save_critical_threshold)
        thresholds.addWidget(self.critical_spin)
        thresholds.addStretch(1)
        limits_layout.addLayout(thresholds)
        layout.addWidget(limits_group)

        appearance = QGroupBox("Appearance")
        appearance_layout = QHBoxLayout(appearance)
        appearance_layout.addWidget(QLabel("Theme"))
        self.theme_combo = QComboBox()
        for label, key in (("Follow Windows", "system"), ("Light", "light"), ("Dark", "dark")):
            self.theme_combo.addItem(label, key)
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(self.settings.value("theme", "system"))))
        self.theme_combo.currentIndexChanged.connect(
            lambda: self._save_preference("theme", str(self.theme_combo.currentData()))
        )
        appearance_layout.addWidget(self.theme_combo)
        appearance_layout.addStretch(1)
        layout.addWidget(appearance)

        advanced = QGroupBox("Advanced")
        advanced.setCheckable(True)
        advanced.setChecked(False)
        advanced_layout = QVBoxLayout(advanced)
        data_hint = QLabel("Export a backup or replace the current save from a JSON backup.")
        data_hint.setWordWrap(True)
        advanced_layout.addWidget(data_hint)
        data_actions = QHBoxLayout()
        export_button = QPushButton("Export save…")
        import_button = QPushButton("Import save…")
        export_button.clicked.connect(self.export_requested.emit)
        import_button.clicked.connect(self.import_requested.emit)
        data_actions.addWidget(export_button)
        data_actions.addWidget(import_button)
        advanced_layout.addLayout(data_actions)
        for advanced_widget in (data_hint, export_button, import_button):
            advanced_widget.setVisible(False)
            advanced.toggled.connect(advanced_widget.setVisible)
        layout.addWidget(advanced)

        note = QLabel(
            "Data is read locally from supported AI coding tools. Pokemon metadata and sprites are fetched "
            "from PokeAPI/PokeAPI sprites. Claude/Codex official limit checks use their existing local credentials/processes."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return root

    def _setting_check(self, text: str, key: str, default: bool) -> QCheckBox:
        check = QCheckBox(text)
        check.setChecked(self.settings.value(key, default, type=bool))
        check.toggled.connect(lambda value, name=key: self._save_preference(name, value))
        return check

    def _save_preference(self, key: str, value: Any) -> None:
        self.settings.setValue(key, value)
        self.settings.sync()
        self.preferences_changed.emit()

    def _save_warning_threshold(self, value: int) -> None:
        normalized = normalize_warning_threshold(value)
        if normalized != value:
            self.warning_spin.blockSignals(True)
            self.warning_spin.setValue(normalized)
            self.warning_spin.blockSignals(False)
        if normalized >= self.critical_spin.value():
            self.critical_spin.setValue(
                normalize_critical_threshold(normalized + THRESHOLD_STEP)
            )
        self._save_preference(WARNING_THRESHOLD_KEY, normalized)

    def _save_critical_threshold(self, value: int) -> None:
        normalized = normalize_critical_threshold(value)
        if normalized != value:
            self.critical_spin.blockSignals(True)
            self.critical_spin.setValue(normalized)
            self.critical_spin.blockSignals(False)
        if normalized <= self.warning_spin.value():
            self.warning_spin.setValue(
                normalize_warning_threshold(normalized - THRESHOLD_STEP)
            )
        self._save_preference(CRITICAL_THRESHOLD_KEY, normalized)

    def _save_pet_visibility(self, visible: bool) -> None:
        self.settings.setValue(PET_ENABLED_KEY, visible)
        self._set_pet_controls_enabled(visible)
        self.pet_visibility_changed.emit(visible)

    def _save_pet_size(self, size: int) -> None:
        normalized = normalize_pet_size(size)
        if normalized != size:
            self.pet_size_slider.blockSignals(True)
            self.pet_size_slider.setValue(normalized)
            self.pet_size_slider.blockSignals(False)
        self.settings.setValue(PET_SIZE_KEY, normalized)
        self.pet_size_label.setText(f"{normalized} px")
        self.pet_size_changed.emit(normalized)

    def _save_interval(self) -> None:
        self.settings.setValue("refresh_minutes", self.interval_combo.currentData())
        self.refresh_requested.emit()

    def _toggle_autostart(self, enabled: bool) -> None:
        try:
            _set_autostart(enabled)
        except OSError:
            self.autostart_check.blockSignals(True)
            self.autostart_check.setChecked(not enabled)
            self.autostart_check.blockSignals(False)
            QMessageBox.warning(self, "Autostart", "Windows could not change the startup setting.")

    def _set_pet_controls_enabled(self, enabled: bool) -> None:
        self.pet_size_slider.setEnabled(enabled)
        self.pet_size_label.setEnabled(enabled)
        self.pet_alerts_check.setEnabled(enabled)

    def sync_floating_pet_settings(self, *, enabled: bool | None = None, size: int | None = None) -> None:
        if enabled is not None and self.pet_check.isChecked() != enabled:
            self.pet_check.blockSignals(True)
            self.pet_check.setChecked(enabled)
            self.pet_check.blockSignals(False)
            self._set_pet_controls_enabled(enabled)
        if size is not None and self.pet_size_slider.value() != size:
            self.pet_size_slider.blockSignals(True)
            self.pet_size_slider.setValue(size)
            self.pet_size_slider.blockSignals(False)
            self.pet_size_label.setText(f"{size} px")

    def set_state(self, state: GameState) -> None:
        self.state = state
        self._render_bag_shop()
        self._render_collection()

    def render(self, result: RefreshResult) -> None:
        self.setUpdatesEnabled(False)
        self.state = result.state
        snapshot = result.snapshot
        self.today_card.value.setText(compact_tokens(snapshot.today_tokens))
        self.cost_card.value.setText(money(snapshot.today_cost))
        self.week_card.value.setText(compact_tokens(snapshot.week_tokens))
        self.wallet_card.value.setText(compact_tokens(result.state.wallet))

        self.providers_list.clear()
        if not snapshot.providers:
            self.providers_list.addItem("No supported local usage logs found yet")
        for key, usage in sorted(snapshot.providers.items(), key=lambda item: item[1].today_tokens, reverse=True):
            label = PROVIDER_LABELS.get(key, key.title())
            self.providers_list.addItem(
                f"{label}: {compact_tokens(usage.today_tokens)} today · "
                f"{compact_tokens(usage.week_tokens)} week · {money(usage.today_cost)}"
            )
        for key in result.scan_errors:
            self.providers_list.addItem(f"{PROVIDER_LABELS.get(key, key)}: local data is temporarily unavailable")
        while self.providers_tabs.count() > 1:
            page = self.providers_tabs.widget(1)
            self.providers_tabs.removeTab(1)
            page.deleteLater()
        if len(snapshot.providers) > 1:
            for key, usage in sorted(snapshot.providers.items()):
                provider_list = QListWidget()
                provider_list.addItem(f"Today · {compact_tokens(usage.today_tokens)}")
                provider_list.addItem(f"This week · {compact_tokens(usage.week_tokens)}")
                provider_list.addItem(f"This month · {compact_tokens(usage.month_tokens)}")
                provider_list.addItem(f"Estimated cost today · {money(usage.today_cost)}")
                self.providers_tabs.addTab(provider_list, PROVIDER_LABELS.get(key, key.title()))
        self.providers_tabs.tabBar().setVisible(len(snapshot.providers) > 1)
        self._fit_provider_panel()

        self.limits_list.clear()
        any_limits = False
        time_mode = normalize_limit_time_mode(
            self.settings.value(
                LIMIT_TIME_MODE_KEY,
                DEFAULT_LIMIT_TIME_MODE,
            )
        )
        for key, limits in result.limits.items():
            label = PROVIDER_LABELS.get(key, key.title())
            ordered_windows = ordered_limit_windows(limits)
            rows = provider_limit_rows(
                label,
                limits,
                display_mode=normalize_limit_display_mode(
                    self.settings.value(
                        LIMIT_DISPLAY_MODE_KEY,
                        DEFAULT_LIMIT_DISPLAY_MODE,
                    )
                ),
                time_mode=time_mode,
            )
            for window in ordered_windows:
                any_limits = True
                item = QListWidgetItem()
                widget = self._limit_widget(label, window)
                item.setSizeHint(widget.sizeHint())
                self.limits_list.addItem(item)
                self.limits_list.setItemWidget(item, widget)
            if key.lower() == "codex" and not any(
                is_reserve_window(window) for window in ordered_windows
            ):
                any_limits = True
                item = QListWidgetItem()
                widget = self._unavailable_limit_widget(
                    label,
                    "Luna Reserve",
                )
                item.setSizeHint(widget.sizeHint())
                self.limits_list.addItem(item)
                self.limits_list.setItemWidget(item, widget)
            for row in rows[len(ordered_windows):]:
                any_limits = True
                item = QListWidgetItem(row.text)
                if row.urgency != "neutral":
                    item.setForeground(QColor("#b91c1c" if row.urgency == "critical" else "#b45309"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.limits_list.addItem(item)
        if not any_limits:
            self.limits_list.addItem("No official limit data available")

        self.name_label.setText(result.display_name)
        if result.state.mon is None:
            self.detail_label.setText("Pokemon Egg" + (f" · {result.state.egg_tier.title()}+" if result.state.egg_tier else ""))
            value = result.state.egg_usage
            target = EGG_HATCH_THRESHOLD
            self._set_sprite(result.sprite_path, egg=True)
            self.evolution_label.setText("Hatch the egg to discover its evolution line")
        else:
            mon = result.state.mon
            shiny = "✨ " if mon.is_shiny else ""
            self.detail_label.setText(f"{shiny}{mon.rarity.title()} · {mon.nature} nature · stage {mon.stage_index + 1}/{len(mon.path_ids)}")
            value = mon.used_at_stage
            target = phase_threshold(mon.rarity, len(mon.path_ids), mon.stage_index)
            self._set_sprite(result.sprite_path)
            current_name = self.api.localized_name(mon.current_id, self.state.language)
            if mon.stage_index + 1 < len(mon.path_ids):
                next_name = self.api.localized_name(mon.path_ids[mon.stage_index + 1], self.state.language)
                self.evolution_label.setText(f"Current: {current_name}  →  Next: {next_name}")
            else:
                self.evolution_label.setText(f"Current: {current_name} · final evolution")
        ratio = min(1.0, value / max(1, target))
        self.progress.setValue(round(ratio * 1000))
        self.progress_label.setText(f"{compact_tokens(value)} / {compact_tokens(target)}")
        self.progress_percent_label.setText(
            companion_level_text(round(ratio * 100))
        )
        self._render_collection()
        self._render_bag_shop()
        self.refresh_button.setEnabled(True)
        stamp = snapshot.scanned_at.astimezone().strftime("%H:%M") if snapshot.scanned_at else "now"
        self.refresh_status.setText(("Updated with warnings · " if result.scan_errors else "Updated · ") + stamp)
        self.setUpdatesEnabled(True)
        self.update()

    def _fit_provider_panel(self) -> None:
        lists: list[QListWidget] = []
        for index in range(self.providers_tabs.count()):
            widget = self.providers_tabs.widget(index)
            if isinstance(widget, QListWidget):
                lists.append(widget)
        rows = max((widget.count() for widget in lists), default=1)
        row_height = max(22, self.providers_list.fontMetrics().height() + 8)
        tabs_height = self.providers_tabs.tabBar().sizeHint().height() if self.providers_tabs.tabBar().isVisible() else 0
        height = min(150, max(42, min(rows, 4) * row_height + tabs_height + 10))
        self.providers_tabs.setMinimumHeight(height)
        self.providers_tabs.setMaximumHeight(height)

    def _limit_widget(self, provider: str, window) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 4, 6, 4)
        used = max(0.0, min(100.0, window.used_percent))
        display_mode = normalize_limit_display_mode(
            self.settings.value(
                LIMIT_DISPLAY_MODE_KEY,
                DEFAULT_LIMIT_DISPLAY_MODE,
            )
        )
        time_mode = normalize_limit_time_mode(
            self.settings.value(
                LIMIT_TIME_MODE_KEY,
                DEFAULT_LIMIT_TIME_MODE,
            )
        )
        detail = ""
        now = datetime.now().astimezone()
        if window.resets_at is not None:
            detail = (
                " · "
                + format_limit_event_time(
                    "resets",
                    window.resets_at,
                    time_mode,
                    now,
                )
            )
        if settings_bool(
            self.settings.value(
                FORECAST_ENABLED_KEY,
                DEFAULT_FORECAST_ENABLED,
            ),
            DEFAULT_FORECAST_ENABLED,
        ):
            forecast = limit_forecast(window, now)
            if forecast is not None:
                if forecast.before_reset:
                    detail += " · forecast: " + format_limit_event_time(
                        "full",
                        forecast.depletion_at,
                        time_mode,
                        now,
                        approximate=True,
                    )
                else:
                    detail += " · forecast: safe until reset"
            else:
                reason = limit_forecast_unavailable_reason(window, now)
                if reason is not None:
                    detail += f" · forecast: {reason}"
        title = QLabel(
            f"{provider} · {window.label} · "
            f"{limit_percent_text(used, display_mode)}{detail}"
        )
        title.setWordWrap(True)
        bar = QProgressBar()
        bar.setRange(0, 100)
        displayed = window.remaining_percent if display_mode == "remaining" else used
        bar.setValue(round(displayed))
        bar.setTextVisible(False)
        bar.setFixedHeight(10)
        bar.setToolTip(
            f"{provider} {window.label}: "
            f"{limit_percent_text(used, display_mode)}"
        )
        warning = normalize_warning_threshold(
            self.settings.value(WARNING_THRESHOLD_KEY, DEFAULT_WARNING_THRESHOLD)
        )
        critical = normalize_critical_threshold(
            self.settings.value(CRITICAL_THRESHOLD_KEY, DEFAULT_CRITICAL_THRESHOLD)
        )
        color = "#16a34a" if used < warning else ("#d97706" if used < critical else "#dc2626")
        bar.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}")
        layout.addWidget(title)
        layout.addWidget(bar)
        return widget

    def _unavailable_limit_widget(self, provider: str, label: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 4, 6, 4)
        title = QLabel(f"{provider} · {label} · unavailable")
        title.setWordWrap(True)
        title.setToolTip(
            f"{provider} did not report {label} in the latest refresh."
        )
        layout.addWidget(title)
        return widget

    def _set_sprite(self, path: Path | None, *, egg: bool = False) -> None:
        if self.reveal_timer.isActive():
            self.reveal_timer.stop()
        self.frame_stabilizer.reset()
        if self.movie is not None:
            self.movie.stop()
            self.movie = None
        if path is not None and path.exists():
            if path.suffix.lower() == ".gif":
                movie = QMovie(str(path), parent=self)
                movie.setScaledSize(QSize(112, 112))
                self.sprite.setMovie(QMovie())
                self.sprite.setPixmap(QPixmap())
                movie.frameChanged.connect(self._render_sprite_movie_frame)
                self.movie = movie
                movie.start()
                return
            pix = QPixmap(str(path))
            if not pix.isNull():
                self.sprite.setMovie(QMovie())
                self.sprite.setPixmap(
                    pix.scaled(112, 112, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
                )
                return
        self.sprite.setMovie(QMovie())
        self.sprite.setPixmap(_egg_pixmap(112) if egg else _pokeball_pixmap(112))

    def _render_sprite_movie_frame(self, *_args) -> None:
        if self.movie is None:
            return
        pixmap = self.frame_stabilizer.filter(self.movie.currentPixmap())
        if not pixmap.isNull():
            self.sprite.setPixmap(pixmap)

    def start_companion_reveal(
        self,
        target_path: Path | None,
        *,
        is_egg: bool,
        ball_path: Path | None = None,
    ) -> None:
        """Animate a runtime-fetched Poké Ball opening into the real companion."""
        self.reveal_timer.stop()
        if self.movie is not None:
            self.movie.stop()
            self.movie = None
        ball = (
            QPixmap(str(ball_path))
            if ball_path is not None and ball_path.exists()
            else QPixmap()
        )
        if ball.isNull():
            ball = _pokeball_pixmap(64)
        target = (
            QPixmap(str(target_path))
            if target_path is not None and target_path.exists()
            else QPixmap()
        )
        if target.isNull():
            target = _egg_pixmap(112) if is_egg else _pokeball_pixmap(112)
        self.reveal_target_path = target_path
        self.reveal_target_is_egg = is_egg
        self.reveal_ball_pixmap = ball
        self.reveal_target_pixmap = target
        self.reveal_frame = 0
        self._advance_companion_reveal()
        self.reveal_timer.start()

    def _advance_companion_reveal(self) -> None:
        frame = self.reveal_frame
        if frame >= 19:
            self.reveal_timer.stop()
            self._set_sprite(
                self.reveal_target_path,
                egg=self.reveal_target_is_egg,
            )
            return

        canvas = QPixmap(112, 112)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if frame < 9:
            offsets = (0, -6, 6, -5, 5, -3, 3, 0, 0)
            ball_size = 54 + (4 if frame >= 7 else 0)
            ball = self.reveal_ball_pixmap.scaled(
                ball_size,
                ball_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (112 - ball.width()) // 2 + offsets[frame]
            y = (112 - ball.height()) // 2 + 14
            painter.drawPixmap(x, y, ball)
            if frame >= 7:
                flash_alpha = 90 if frame == 7 else 180
                painter.setBrush(QColor(255, 248, 196, flash_alpha))
                painter.setPen(Qt.PenStyle.NoPen)
                radius = 24 + (frame - 7) * 18
                painter.drawEllipse(
                    56 - radius,
                    56 - radius,
                    radius * 2,
                    radius * 2,
                )
        else:
            progress = min(1.0, (frame - 9) / 9.0)
            eased = 1.0 - (1.0 - progress) ** 3
            painter.setBrush(QColor(255, 248, 196, round(150 * (1.0 - progress))))
            painter.setPen(Qt.PenStyle.NoPen)
            glow_radius = round(18 + 42 * progress)
            painter.drawEllipse(
                56 - glow_radius,
                56 - glow_radius,
                glow_radius * 2,
                glow_radius * 2,
            )
            target_size = max(18, round(18 + 94 * eased))
            target = self.reveal_target_pixmap.scaled(
                target_size,
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.setOpacity(max(0.15, progress))
            painter.drawPixmap(
                (112 - target.width()) // 2,
                (112 - target.height()) // 2 - round(10 * (1.0 - progress)),
                target,
            )
        painter.end()
        self.sprite.setMovie(QMovie())
        self.sprite.setPixmap(canvas)
        self.reveal_frame += 1

    def _render_collection(self) -> None:
        _clear_layout(self.dex_grid)
        _clear_layout(self.catch_list)
        catches = list(self.state.catches)
        owned = self._owned_species()
        self.representative_combo.blockSignals(True)
        self.representative_combo.clear()
        self.representative_combo.addItem("Follow current companion", None)
        selected = (
            None
            if self.state.representative_species_id is None
            else (
                self.state.representative_species_id,
                bool(self.state.representative_is_shiny),
            )
        )
        for subject in owned_representative_options(self.state):
            assert subject.species_id is not None
            data = (subject.species_id, subject.is_shiny)
            prefix = "✨ " if subject.is_shiny else ""
            self.representative_combo.addItem(
                f"{prefix}#{subject.species_id:03d} "
                f"{self.api.localized_name(subject.species_id, self.state.language)}",
                data,
            )
        selected_index = 0
        if selected is not None:
            for index in range(1, self.representative_combo.count()):
                if (
                    self._representative_selection_data(
                        self.representative_combo.itemData(index)
                    )
                    == selected
                ):
                    selected_index = index
                    break
        self.representative_combo.setCurrentIndex(selected_index)
        self.representative_combo.blockSignals(False)
        self.dex_empty.setVisible(not catches)
        self.catch_empty.setVisible(not catches)
        if not catches:
            self.dex_counts.setText("0 species · hatch your first egg to begin")
            self.dex_prev.setEnabled(False)
            self.dex_next.setEnabled(False)
            return

        current = self._current_catch()
        rarity_counts: dict[str, int] = {}
        for catch in catches:
            rarity_counts[catch.rarity] = rarity_counts.get(catch.rarity, 0) + 1
        rarity_text = " · ".join(f"{key.title()} {value}" for key, value in sorted(rarity_counts.items()))
        self.dex_counts.setText(f"{len(owned)} species · {rarity_text}")
        page_size = 24
        species = sorted(owned)
        page_count = max(1, (len(species) + page_size - 1) // page_size)
        self.dex_page = min(self.dex_page, page_count - 1)
        self.dex_page_label.setText(f"Page {self.dex_page + 1} / {page_count}")
        self.dex_prev.setEnabled(self.dex_page > 0)
        self.dex_next.setEnabled(self.dex_page + 1 < page_count)
        visible_species = species[self.dex_page * page_size:(self.dex_page + 1) * page_size]
        for column, species_id in enumerate(visible_species):
            self.dex_grid.addWidget(
                self._dex_cell(species_id, shiny=owned[species_id]),
                column // 2,
                column % 2,
            )

        for catch in reversed(catches):
            self.catch_list.addWidget(self._catch_card(catch, current is catch))

    def _current_catch(self):
        mon = self.state.mon
        if mon is None:
            return None
        for catch in reversed(self.state.catches):
            if catch.base_id == mon.base_id and catch.nature == mon.nature and catch.is_shiny == mon.is_shiny:
                return catch
        return None

    def _owned_species(self) -> dict[int, bool]:
        owned: dict[int, bool] = {}
        for subject in owned_representative_options(self.state):
            assert subject.species_id is not None
            owned[subject.species_id] = owned.get(subject.species_id, False) or subject.is_shiny
        return owned

    def _dex_cell(self, species_id: int, *, shiny: bool) -> QFrame:
        cell = QFrame()
        cell.setFrameShape(QFrame.Shape.StyledPanel)
        cell.setStyleSheet("QFrame { border: 1px solid palette(mid); border-radius: 12px; }")
        layout = QVBoxLayout(cell)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sprite = QLabel()
        sprite.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sprite.setFixedSize(80, 80)
        path = self.api.sprite_path(species_id, shiny=shiny, animated=False)
        pix = _sprite_pixmap(path, 72)
        sprite.setPixmap(pix if not pix.isNull() else _pokeball_pixmap(72))
        name = QLabel(self.api.localized_name(species_id, self.state.language))
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = name.font()
        font.setBold(True)
        name.setFont(font)
        number = QLabel(f"{'✨ ' if shiny else ''}#{species_id:03d}")
        number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        number.setStyleSheet("color: #6b7280;")
        layout.addWidget(sprite)
        layout.addWidget(number)
        layout.addWidget(name)
        if shiny:
            toggle = QPushButton("Normal / ✨ Shiny")
            toggle.setToolTip("Alternate this owned species between its normal and Shiny sprite")
            showing_shiny = [True]
            def switch_sprite() -> None:
                showing_shiny[0] = not showing_shiny[0]
                selected = self.api.sprite_path(species_id, shiny=showing_shiny[0], animated=False)
                selected_pix = _sprite_pixmap(selected, 72)
                sprite.setPixmap(selected_pix if not selected_pix.isNull() else _pokeball_pixmap(72))
            toggle.clicked.connect(switch_sprite)
            layout.addWidget(toggle)
        return cell

    def _catch_card(self, catch, is_current: bool) -> QFrame:
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet("QFrame { border: 1px solid palette(mid); border-radius: 14px; }")
        layout = QVBoxLayout(card)
        path_ids = catch.path_ids or [catch.species_id]
        owned_index = self.state.mon.stage_index if (is_current and self.state.mon is not None) else len(path_ids) - 1
        owned_index = max(0, min(owned_index, len(path_ids) - 1))
        display_id = path_ids[owned_index]
        owned_name = self.api.localized_name(display_id, self.state.language)

        header = QHBoxLayout()
        title = QLabel(owned_name)
        tf = title.font()
        tf.setPointSize(tf.pointSize() + 3)
        tf.setBold(True)
        title.setFont(tf)
        header.addWidget(title)
        header.addStretch(1)
        owned_badge = QLabel("Owned")
        owned_badge.setStyleSheet("QLabel { background: #dcfce7; color: #166534; border-radius: 8px; padding: 2px 8px; }")
        header.addWidget(owned_badge)
        if is_current:
            badge = QLabel("Current")
            badge.setStyleSheet("QLabel { background: #dbeafe; color: #1d4ed8; border-radius: 8px; padding: 2px 8px; }")
            header.addWidget(badge)
        if catch.is_shiny:
            header.addWidget(QLabel("✨"))
        layout.addLayout(header)

        summary = QLabel(
            f"You have {owned_name} only · stage {owned_index + 1} of {len(path_ids)}"
            if owned_index + 1 < len(path_ids)
            else f"Fully evolved {owned_name}"
        )
        summary.setStyleSheet("color: palette(text);")
        layout.addWidget(summary)

        line = QHBoxLayout()
        line.setAlignment(Qt.AlignmentFlag.AlignLeft)
        for index, species_id in enumerate(path_ids):
            if index:
                arrow = QLabel("→")
                arrow.setStyleSheet("color: #9ca3af; font-size: 16px;")
                line.addWidget(arrow)
            have = index <= owned_index
            current_stage = index == owned_index
            stage = QWidget()
            stage_layout = QVBoxLayout(stage)
            stage_layout.setContentsMargins(0, 0, 0, 0)
            stage_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sprite = QLabel()
            sprite.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sprite.setFixedSize(72, 72)
            path = self.api.sprite_path(species_id, shiny=catch.is_shiny, animated=False) if have else self.api.sprite_path(species_id, animated=False)
            pix = _sprite_pixmap(path, 64)
            if pix.isNull():
                pix = _pokeball_pixmap(64)
            if not have:
                pix = _muted_pixmap(pix)
            sprite.setPixmap(pix)
            if current_stage:
                sprite.setStyleSheet("QLabel { background: #dcfce7; border: 2px solid #16a34a; border-radius: 10px; }")
            elif not have:
                sprite.setStyleSheet("QLabel { background: #f3f4f6; border-radius: 10px; }")
            if have:
                stage_name = QLabel(self.api.localized_name(species_id, self.state.language))
                status = QLabel("You have this" if current_stage else "Previous form")
                status.setStyleSheet("color: #166534;" if current_stage else "color: #6b7280;")
            else:
                stage_name = QLabel("???")
                status = QLabel("Not owned")
                status.setStyleSheet("color: #9ca3af;")
                stage_name.setStyleSheet("color: #9ca3af;")
            stage_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stage_layout.addWidget(sprite)
            stage_layout.addWidget(stage_name)
            stage_layout.addWidget(status)
            line.addWidget(stage)
        line.addStretch(1)
        layout.addLayout(line)

        meta = QLabel(
            f"#{display_id:03d} · {catch.rarity.title()} · {catch.nature} · {catch.caught_at[:10]}"
        )
        meta.setStyleSheet("color: #6b7280;")
        layout.addWidget(meta)
        return card

    def _render_bag_shop(self) -> None:
        self.wallet_shop_label.setText(f"Wallet: {compact_tokens(self.state.wallet)} tokens")
        self.wallet_bag_label.setText(f"Wallet: {compact_tokens(self.state.wallet)} tokens")
        inv = self.state.inventory
        self.bag_empty.setVisible(sum(inv.values()) <= 0)
        self.bag_label.setText(
            f"Bag: 🍬 {inv.get('rare_candy', 0)} Rare Candy · 🌿 {inv.get('mint', 0)} Mint · "
            f"✨ {'active' if self.state.shiny_charm_active else 'no Shiny Charm'}"
        )
        self.use_candy_btn.setEnabled(inv.get("rare_candy", 0) > 0)
        self.use_mint_btn.setEnabled(inv.get("mint", 0) > 0 and self.state.mon is not None)
        self.use_candy_btn.setToolTip("" if self.use_candy_btn.isEnabled() else "No Rare Candy in your bag")
        self.use_mint_btn.setToolTip(
            "" if self.use_mint_btn.isEnabled() else
            ("No Mint in your bag" if inv.get("mint", 0) <= 0 else "Hatch a Pokémon first")
        )
        prices = {
            self.buy_candy_btn: 500_000_000,
            self.buy_mint_btn: 100_000_000,
            self.buy_charm_btn: 3_000_000_000,
            self.buy_egg_btn: egg_price(None),
            self.buy_uncommon_egg_btn: egg_price("uncommon"),
            self.buy_rare_egg_btn: egg_price("rare"),
        }
        effects = {
            self.buy_candy_btn: "Adds progression to the active egg or companion",
            self.buy_mint_btn: "Changes the current companion's nature",
            self.buy_charm_btn: "Improves the chance that a future hatch is Shiny",
            self.buy_egg_btn: "Starts a fresh egg with normal rarity odds",
            self.buy_uncommon_egg_btn: "Starts a fresh egg guaranteed Uncommon or better",
            self.buy_rare_egg_btn: "Starts a fresh egg guaranteed Rare or better",
        }
        for button, price in prices.items():
            available = self.state.wallet >= price
            if button is self.buy_charm_btn and self.state.shiny_charm_active:
                button.setEnabled(False)
                button.setToolTip("Shiny Charm is already active")
            else:
                button.setEnabled(available)
                button.setToolTip(
                    effects[button] if available else
                    f"{effects[button]}. Need {compact_tokens(price - self.state.wallet)} more tokens"
                )


class TrayController(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.settings = application_settings()
        self.store = StateStore()
        self.state = self.store.load()
        self.api = PokeAPIClient(_data_cache_dir())
        self.state_lock = threading.Lock()
        self.bridge = Bridge()
        self.bridge.refreshed.connect(self._on_refreshed)
        self.bridge.failed.connect(self._on_failed)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="poketokenbar-refresh")
        self.refresh_running = False
        self.refresh_pending = False
        self.last_result: RefreshResult | None = None
        self.window_open_pending = False
        self.initial_reveal_played = False
        self.qa_capture_scheduled = False
        self.limit_alert_tiers: dict[str, int] = {}
        self.limit_notifications_enabled = settings_bool(
            self.settings.value(LIMIT_NOTIFICATIONS_KEY, DEFAULT_LIMIT_NOTIFICATIONS),
            DEFAULT_LIMIT_NOTIFICATIONS,
        )
        self.companion_notifications_enabled = settings_bool(
            self.settings.value(
                COMPANION_NOTIFICATIONS_KEY,
                DEFAULT_COMPANION_NOTIFICATIONS,
            ),
            DEFAULT_COMPANION_NOTIFICATIONS,
        )
        self.warning_threshold = normalize_warning_threshold(
            self.settings.value(WARNING_THRESHOLD_KEY, DEFAULT_WARNING_THRESHOLD)
        )
        self.critical_threshold = normalize_critical_threshold(
            self.settings.value(CRITICAL_THRESHOLD_KEY, DEFAULT_CRITICAL_THRESHOLD)
        )
        self.limit_display_mode = normalize_limit_display_mode(
            self.settings.value(
                LIMIT_DISPLAY_MODE_KEY,
                DEFAULT_LIMIT_DISPLAY_MODE,
            )
        )
        self.limit_time_mode = normalize_limit_time_mode(
            self.settings.value(
                LIMIT_TIME_MODE_KEY,
                DEFAULT_LIMIT_TIME_MODE,
            )
        )

        self.window = QmlMainWindow(self.state, self.settings, self.api)
        self.window.refresh_requested.connect(self._refresh_and_reschedule)
        self.window.pet_visibility_changed.connect(self._set_pet_visible)
        self.window.pet_size_changed.connect(self._set_pet_size)
        self.window.preferences_changed.connect(self._preferences_changed)
        self.window.representative_changed.connect(self._set_representative)
        self.window.language_changed.connect(self._set_language)
        self.window.export_requested.connect(self._export_state)
        self.window.import_requested.connect(self._import_state)
        self._wire_shop_buttons()
        self._apply_theme()

        self.tray = QSystemTrayIcon(_pokeball_icon(), self)
        self.tray.setToolTip(f"{APP_NAME} · Loading usage and limits…")
        menu = QMenu()
        open_action = QAction(MENU_OPEN_LABEL, self)
        open_action.triggered.connect(self.show_window)
        self.pet_visibility_action = QAction(MENU_PET_VISIBILITY_LABEL, self)
        self.pet_visibility_action.setCheckable(True)
        self.pet_visibility_action.triggered.connect(self._set_pet_visible)
        refresh_action = QAction(MENU_REFRESH_LABEL, self)
        refresh_action.triggered.connect(self.refresh)
        quit_action = QAction(MENU_QUIT_LABEL, self)
        quit_action.triggered.connect(self.quit)
        menu.addAction(open_action)
        menu.addAction(self.pet_visibility_action)
        menu.addAction(refresh_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

        self.floating_pet = FloatingPetController(
            self.app,
            self.settings,
            self.show_window,
            on_refresh=self.refresh,
            on_quit=self.quit,
            warning_percent=self.warning_threshold,
            critical_percent=self.critical_threshold,
            display_mode=self.limit_display_mode,
            time_mode=self.limit_time_mode,
        )
        self.floating_pet.enabled_changed.connect(self._sync_pet_visibility)
        self.floating_pet.size_changed.connect(
            lambda size: self.window.sync_floating_pet_settings(size=size)
        )
        self._sync_pet_visibility(self.floating_pet.enabled)
        self.window.sync_floating_pet_settings(size=self.floating_pet.size)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self._reschedule()
        self.stale_timer = QTimer(self)
        self.stale_timer.timeout.connect(self._check_staleness)
        self.stale_timer.start(60_000)
        QTimer.singleShot(0, self.refresh)

    def _wire_shop_buttons(self) -> None:
        if isinstance(self.window, QmlMainWindow):
            self.window.use_item_requested.connect(self._use_item)
            self.window.buy_item_requested.connect(self._buy_item)
            self.window.buy_egg_requested.connect(self._buy_egg)
            return
        self.window.use_candy_btn.clicked.connect(lambda: self._use_item("rare_candy"))
        self.window.use_mint_btn.clicked.connect(lambda: self._use_item("mint"))
        self.window.buy_candy_btn.clicked.connect(lambda: self._buy_item("rare_candy"))
        self.window.buy_mint_btn.clicked.connect(lambda: self._buy_item("mint"))
        self.window.buy_charm_btn.clicked.connect(lambda: self._buy_item("shiny_charm"))
        self.window.buy_egg_btn.clicked.connect(lambda: self._buy_egg(None))
        self.window.buy_uncommon_egg_btn.clicked.connect(lambda: self._buy_egg("uncommon"))
        self.window.buy_rare_egg_btn.clicked.connect(lambda: self._buy_egg("rare"))

    def _refresh_and_reschedule(self) -> None:
        self._reschedule()
        self.refresh()

    def _reschedule(self) -> None:
        minutes = int(self.settings.value("refresh_minutes", 5))
        self.timer.start(max(1, minutes) * 60_000)

    def _check_staleness(self) -> None:
        if self.last_result is None or self.last_result.snapshot.scanned_at is None or self.refresh_running:
            return
        scanned = self.last_result.snapshot.scanned_at
        now = datetime.now().astimezone()
        if scanned.tzinfo is None:
            now = now.replace(tzinfo=None)
        else:
            now = now.astimezone(scanned.tzinfo)
        stale_after = max(2, int(self.settings.value("refresh_minutes", 5)) * 2) * 60
        if (now - scanned).total_seconds() > stale_after:
            self.window.refresh_status.setText("Data is stale · refreshing…")
            self.window.statusBar().showMessage("Existing data is stale; refreshing in the background")
            self.refresh()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_window()

    def _sync_pet_visibility(self, enabled: bool) -> None:
        self.window.sync_floating_pet_settings(enabled=bool(enabled))
        self.pet_visibility_action.blockSignals(True)
        self.pet_visibility_action.setChecked(bool(enabled))
        self.pet_visibility_action.blockSignals(False)

    def _set_pet_visible(self, visible: bool) -> None:
        self.floating_pet.set_enabled(visible)
        self._sync_pet_visibility(self.floating_pet.enabled)

    def _set_pet_size(self, size: int) -> None:
        self.floating_pet.set_size(size)
        self.window.sync_floating_pet_settings(size=self.floating_pet.size)

    def _set_representative(self, selection: object) -> None:
        species_id: int | None = None
        is_shiny: bool | None = None
        if isinstance(selection, tuple) and len(selection) == 2:
            species_id = int(selection[0])
            is_shiny = bool(selection[1])
        try:
            with self.state_lock:
                candidate = copy.deepcopy(self.state)
                if not set_representative(candidate, species_id, is_shiny):
                    QMessageBox.information(
                        self.window,
                        "PokeTokenBar",
                        "That Pokémon is not currently owned.",
                    )
                    self.window.set_state(self.state)
                    return
                self.store.save(candidate)
                self.state = candidate
        except Exception:  # noqa: BLE001
            QMessageBox.warning(
                self.window,
                "PokeTokenBar",
                "The representative could not be changed. Your save was not changed.",
            )
            return
        self.window.set_state(self.state)
        self.floating_pet.set_loading()
        preview = self._representative_preview()
        if preview is not None:
            self.last_result = preview
            self._update_companion_surfaces(preview)
        self.refresh()

    def _representative_preview(self) -> RefreshResult | None:
        """Resolve a representative immediately; the background refresh may add GIF."""
        if self.last_result is None:
            return None
        subject = representative_subject(self.state)
        if self.state.representative_species_id is None:
            pet_sprite = self.last_result.sprite_path
            pet_name = self.last_result.display_name
        elif subject.species_id is not None:
            pet_sprite = self.api.sprite_path(
                subject.species_id,
                shiny=subject.is_shiny,
                animated=False,
            )
            pet_name = self.api.localized_name(
                subject.species_id,
                self.state.language,
            )
        else:
            pet_sprite = self.api.egg_sprite_path()
            pet_name = "Pokemon Egg"
        return replace(
            self.last_result,
            state=self.state,
            pet_sprite_path=pet_sprite,
            pet_display_name=pet_name,
            pet_is_egg=subject.is_egg,
        )

    def _update_companion_surfaces(self, result: RefreshResult) -> None:
        self.floating_pet.update(result)
        self.tray.setIcon(
            _icon_from_sprite(result.pet_sprite_path, fallback_egg=result.pet_is_egg)
        )
        self._update_tray_presentation()

    def _update_tray_presentation(self) -> None:
        if self.last_result is None:
            return
        result = self.last_result
        tooltip = tray_tooltip(
            result,
            show_tokens=self.settings.value("tray_show_tokens", True, type=bool),
            show_cost=self.settings.value("tray_show_cost", False, type=bool),
            show_limit=self.settings.value("tray_show_limit", True, type=bool),
            limit_display_mode=self.limit_display_mode,
            limit_time_mode=self.limit_time_mode,
        )
        self.tray.setToolTip(tooltip)

    def _preferences_changed(self) -> None:
        self.limit_notifications_enabled = settings_bool(
            self.settings.value(LIMIT_NOTIFICATIONS_KEY, DEFAULT_LIMIT_NOTIFICATIONS),
            DEFAULT_LIMIT_NOTIFICATIONS,
        )
        self.companion_notifications_enabled = settings_bool(
            self.settings.value(
                COMPANION_NOTIFICATIONS_KEY,
                DEFAULT_COMPANION_NOTIFICATIONS,
            ),
            DEFAULT_COMPANION_NOTIFICATIONS,
        )
        self.warning_threshold = normalize_warning_threshold(
            self.settings.value(WARNING_THRESHOLD_KEY, DEFAULT_WARNING_THRESHOLD)
        )
        self.critical_threshold = normalize_critical_threshold(
            self.settings.value(CRITICAL_THRESHOLD_KEY, DEFAULT_CRITICAL_THRESHOLD)
        )
        self.limit_display_mode = normalize_limit_display_mode(
            self.settings.value(
                LIMIT_DISPLAY_MODE_KEY,
                DEFAULT_LIMIT_DISPLAY_MODE,
            )
        )
        self.limit_time_mode = normalize_limit_time_mode(
            self.settings.value(
                LIMIT_TIME_MODE_KEY,
                DEFAULT_LIMIT_TIME_MODE,
            )
        )
        self.floating_pet.set_alerts_enabled(
            settings_bool(self.settings.value(PET_ALERTS_KEY, True), True)
        )
        self.floating_pet.set_alert_thresholds(
            self.warning_threshold,
            self.critical_threshold,
        )
        self.floating_pet.set_limit_display_mode(self.limit_display_mode)
        self.floating_pet.set_limit_time_mode(self.limit_time_mode)
        self.floating_pet.set_display_preferences(
            show_tokens=settings_bool(
                self.settings.value("tray_show_tokens", True),
                True,
            ),
            show_cost=settings_bool(
                self.settings.value("tray_show_cost", False),
                False,
            ),
            show_limit=settings_bool(
                self.settings.value("tray_show_limit", True),
                True,
            ),
        )
        self.settings.sync()
        self._apply_theme()
        if self.last_result is not None:
            self.window.render(self.last_result)
        self._update_tray_presentation()

    def _apply_theme(self) -> None:
        theme = str(self.settings.value("theme", "system"))
        self.app.setStyleSheet(theme_stylesheet(theme))

    def _set_language(self, language: str) -> None:
        with self.state_lock:
            candidate = copy.deepcopy(self.state)
            candidate.language = language
            self.store.save(candidate)
            self.state = candidate
        self.window.set_state(candidate)
        self.refresh()

    def _export_state(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self.window, "Export PokeTokenBar save", "poketokenbar-save.json", "JSON files (*.json)"
        )
        if not filename:
            return
        try:
            self.store.save(self.state)
            Path(filename).write_text(self.store.path.read_text(encoding="utf-8"), encoding="utf-8")
            self.window.statusBar().showMessage("Save exported", 5000)
        except OSError:
            QMessageBox.warning(self.window, "Export save", "The selected file could not be written.")

    def _import_state(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self.window, "Import PokeTokenBar save", "", "JSON files (*.json)"
        )
        if not filename:
            return
        try:
            raw = json.loads(Path(filename).read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or not any(key in raw for key in ("catches", "mon", "egg_usage")):
                raise ValueError
            if not isinstance(raw.get("catches", []), list):
                raise TypeError
            if raw.get("mon") is not None and not isinstance(raw.get("mon"), dict):
                raise TypeError
            if not isinstance(raw.get("inventory", {}), dict):
                raise TypeError
            backup = self.store.path.with_name(
                f"state-before-import-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.json"
            )
            if self.store.path.exists():
                backup.write_text(self.store.path.read_text(encoding="utf-8"), encoding="utf-8")
            imported_path = self.store.path.with_suffix(".import.tmp")
            imported_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
            imported_path.replace(self.store.path)
            imported = self.store.load()
            self.state = imported
            self.window.set_state(imported)
            self.refresh()
            self.window.statusBar().showMessage("Save imported; previous save backed up", 7000)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            QMessageBox.warning(self.window, "Import save", "This is not a valid PokeTokenBar save file.")

    def show_window(self) -> None:
        if self.last_result is None:
            self.window_open_pending = True
            self.tray.setToolTip(f"{APP_NAME} · Loading usage and limits…")
            return
        self._present_window(animate_reveal=not self.initial_reveal_played)

    def _present_window(self, *, animate_reveal: bool) -> None:
        self.window.show()
        apply_native_window_icon(int(self.window.winId()), cache_dir() / "app.ico")
        self.window.raise_()
        self.window.activateWindow()
        if animate_reveal and self.last_result is not None:
            self.initial_reveal_played = True
            self.window.start_companion_reveal(
                self.last_result.sprite_path,
                is_egg=self.last_result.state.mon is None,
                ball_path=self.last_result.reveal_ball_path,
            )

    def refresh(self) -> None:
        if self.refresh_running:
            self.refresh_pending = True
            return
        self.refresh_running = True
        self.window.refresh_button.setEnabled(False)
        self.window.refresh_status.setText("Updating…")
        self.window.statusBar().showMessage("Updating local usage and limits…")
        self.executor.submit(self._refresh_worker)

    def _refresh_worker(self) -> None:
        try:
            snapshot, errors = scan_all()
            limits = fetch_all_limits()
            reveal_ball = self.api.item_sprite_path("poke-ball")
            with self.state_lock:
                candidate = copy.deepcopy(self.state)
                delta = usage_delta(
                    candidate,
                    {provider: usage.today_tokens for provider, usage in snapshot.providers.items()},
                )
                events = apply_usage(candidate, delta, self.api) if delta else []
                events.extend(apply_limit_rewards(candidate, limits))
                mon = candidate.mon
                sprite = self.api.sprite_path(mon.current_id, shiny=mon.is_shiny) if mon else self.api.egg_sprite_path()
                pet_subject = representative_subject(candidate)
                pet_sprite = (
                    self.api.sprite_path(pet_subject.species_id, shiny=pet_subject.is_shiny)
                    if pet_subject.species_id is not None else self.api.egg_sprite_path()
                )
                self._prefetch_collection(candidate)
                display_name = self.api.localized_name(mon.current_id, candidate.language) if mon else "Pokemon Egg"
                pet_display_name = (
                    self.api.localized_name(pet_subject.species_id, candidate.language)
                    if pet_subject.species_id is not None else "Pokemon Egg"
                )
                self.store.save(candidate)
                self.state = candidate
                state = candidate
            self.bridge.refreshed.emit(RefreshResult(
                snapshot=snapshot,
                limits=limits,
                scan_errors=errors,
                state=state,
                events=events,
                sprite_path=sprite,
                display_name=display_name,
                pet_sprite_path=pet_sprite,
                pet_display_name=pet_display_name,
                pet_is_egg=pet_subject.is_egg,
                reveal_ball_path=reveal_ball,
            ))
        except Exception as exc:  # noqa: BLE001
            self.bridge.failed.emit(f"{type(exc).__name__}: {exc}")

    def _prefetch_collection(self, state: GameState) -> None:
        for catch in state.catches:
            for species_id in catch.path_ids or [catch.species_id]:
                try:
                    self.api.localized_name(species_id, state.language)
                    self.api.sprite_path(species_id, shiny=catch.is_shiny, animated=False)
                except Exception:  # noqa: BLE001, S112
                    continue

    def _on_refreshed(self, result: RefreshResult) -> None:
        self.refresh_running = False
        self.last_result = result
        self.window.render(result)
        self._update_companion_surfaces(result)
        if self.window_open_pending:
            self.window_open_pending = False
            self._present_window(animate_reveal=not self.initial_reveal_played)
        for event in result.events:
            if event.startswith("hatched:"):
                shiny = bool(result.state.mon and result.state.mon.is_shiny)
                self.window.celebrate(f"{result.display_name} hatched!", shiny=shiny)
            elif event.startswith("evolved:"):
                self.window.celebrate(
                    f"Your companion evolved into {result.display_name}!"
                )
            elif event.startswith("graduated:"):
                self.window.celebrate("Your companion graduated! A new egg is ready.")
        limit_alerts, self.limit_alert_tiers = evaluate_limit_alerts(
            result.limits,
            self.limit_alert_tiers,
            warning_percent=self.warning_threshold,
            critical_percent=self.critical_threshold,
        )
        if self.limit_notifications_enabled:
            for alert in limit_alerts:
                provider = PROVIDER_LABELS.get(alert.provider, alert.provider.title())
                title = "Critical limit" if alert.severity == "critical" else "Limit warning"
                icon = (
                    QSystemTrayIcon.MessageIcon.Critical
                    if alert.severity == "critical"
                    else QSystemTrayIcon.MessageIcon.Warning
                )
                self.tray.showMessage(
                    title,
                    limit_alert_body(
                        provider,
                        alert.window_label,
                        alert.used_percent,
                        self.limit_display_mode,
                    ),
                    icon,
                    6_000,
                )
        self._schedule_qa_capture()
        if self.companion_notifications_enabled:
            for event in result.events:
                notification = companion_notification(event, result.display_name)
                if notification is None:
                    continue
                if notification.use_sprite_icon:
                    icon = _icon_from_sprite(result.sprite_path)
                else:
                    icon = QSystemTrayIcon.MessageIcon.Information
                self.tray.showMessage(notification.title, notification.body, icon, 5_000)
        if self.refresh_pending:
            self.refresh_pending = False
            QTimer.singleShot(0, self.refresh)

    def _schedule_qa_capture(self) -> None:
        target = os.environ.get("PTB_QA_ARTIFACT_DIR", "").strip()
        if not target or self.qa_capture_scheduled:
            return
        self.qa_capture_scheduled = True
        QTimer.singleShot(1_000, lambda: self._write_qa_artifacts(Path(target)))

    def _write_qa_artifacts(self, target: Path) -> None:
        try:
            target.mkdir(parents=True, exist_ok=True)
            main_path = target / "main-window.png"
            settings_path = target / "settings-tab.png"
            pet_path = target / "floating-pet.png"
            hover_path = target / "hover-callout.png"
            self.window.grab().save(str(main_path), "PNG")
            tabs = self.window.centralWidget()
            if isinstance(tabs, QTabWidget):
                current_tab = tabs.currentIndex()
                tabs.setCurrentIndex(tabs.count() - 1)
                QApplication.processEvents()
                self.window.grab().save(str(settings_path), "PNG")
                tabs.setCurrentIndex(current_tab)
            self.floating_pet.pet.grab().save(str(pet_path), "PNG")
            self.floating_pet.hover.grab().save(str(hover_path), "PNG")
            report = {
                "pid": os.getpid(),
                "executable": sys.executable,
                "frozen": bool(getattr(sys, "frozen", False)),
                "settings_file": self.settings.fileName(),
                "state_file": str(self.store.path),
                "main_visible": self.window.isVisible(),
                "main_size": [self.window.width(), self.window.height()],
                "tray_visible": self.tray.isVisible(),
                "tray_tooltip": self.tray.toolTip(),
                "notifications": {
                    "limit_alerts": self.limit_notifications_enabled,
                    "warning_threshold": self.warning_threshold,
                    "critical_threshold": self.critical_threshold,
                    "companion_events": self.companion_notifications_enabled,
                    "deduplicated_limit_windows": len(self.limit_alert_tiers),
                },
                "pet": self.floating_pet.qa_snapshot(),
            }
            tmp = target / "qa-report.tmp"
            tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
            tmp.replace(target / "qa-report.json")
        except Exception:
            self.qa_capture_scheduled = False

    def _on_failed(self, message: str) -> None:
        self.refresh_running = False
        self.window.refresh_button.setEnabled(True)
        self.window.refresh_status.setText("Update failed · retry scheduled")
        self.window.statusBar().showMessage("Update failed; existing data is still shown", 7000)
        if self.last_result is None:
            self.tray.setToolTip(f"{APP_NAME} · Initial load failed · retrying…")
        self.tray.showMessage(
            "PokeTokenBar could not refresh",
            "Some local usage data could not be read. PokeTokenBar will try again automatically.",
            QSystemTrayIcon.MessageIcon.Warning,
            5000,
        )
        if self.refresh_pending:
            self.refresh_pending = False
            QTimer.singleShot(0, self.refresh)

    def _mutate_state(
        self,
        operation: Callable[[GameState], tuple[bool, str] | tuple[bool, str, list[str]]],
        *,
        refresh: bool = False,
    ) -> bool:
        try:
            with self.state_lock:
                candidate = copy.deepcopy(self.state)
                outcome = operation(candidate)
                ok = bool(outcome[0])
                message = str(outcome[1])
                events = outcome[2] if len(outcome) > 2 else []
                if ok:
                    self.store.save(candidate)
                    self.state = candidate
        except Exception:  # noqa: BLE001
            QMessageBox.warning(self.window, "PokeTokenBar", "The action could not be completed. Your save was not changed.")
            return False
        if not ok:
            QMessageBox.information(self.window, "PokeTokenBar", message)
            return False
        self.window.set_state(self.state)
        self.window.action_feedback.setText(f"✓ {message}")
        QTimer.singleShot(5000, lambda: self.window.action_feedback.setText(""))
        if events or refresh:
            self.refresh()
        return True

    def _buy_item(self, item: str) -> None:
        labels = {"rare_candy": "Rare Candy", "mint": "Mint", "shiny_charm": "Shiny Charm"}
        if QMessageBox.question(
            self.window,
            "Confirm purchase",
            f"Buy {labels.get(item, item)}?",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._mutate_state(lambda state: buy_item(state, item))

    def _use_item(self, item: str) -> None:
        labels = {"rare_candy": "Rare Candy", "mint": "Mint"}
        if QMessageBox.question(
            self.window,
            "Use item",
            f"Use one {labels.get(item, item)} on your current companion?",
        ) != QMessageBox.StandardButton.Yes:
            return
        old_nature = self.state.mon.nature if self.state.mon else None
        self._mutate_state(
            lambda state: use_item(state, item, self.api),
            refresh=item == "rare_candy",
        )
        if item == "mint" and self.state.mon and self.state.mon.nature != old_nature:
            self.window.action_feedback.setText(f"✓ New nature: {self.state.mon.nature}")

    def _buy_egg(self, tier: str | None) -> None:
        tier_label = (tier or "normal").title()
        warning = f"Buy a {tier_label} Egg?"
        if self.state.mon is not None:
            warning += "\n\nThis replaces your active companion and its unfinished catch."
            if self.state.mon.is_shiny:
                warning += "\n\n⚠ Your active companion is Shiny. This cannot be undone."
        if QMessageBox.warning(
            self.window,
            "Confirm fresh egg",
            warning,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        ) != QMessageBox.StandardButton.Yes:
            return
        if self._mutate_state(lambda state: buy_egg(state, tier)):
            self.refresh()

    def quit(self) -> None:
        self.store.save(self.state)
        self.floating_pet.shutdown()
        self.tray.hide()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.app.quit()
