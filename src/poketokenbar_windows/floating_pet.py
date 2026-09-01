from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal, QObject
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QMouseEvent,
    QMovie,
    QPainter,
    QPen,
    QPixmap,
    QRegion,
)
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QMenu, QVBoxLayout, QWidget

from .formatting import (
    DEFAULT_LIMIT_DISPLAY_MODE,
    DEFAULT_LIMIT_TIME_MODE,
    LimitDisplayMode,
    LimitTimeMode,
)
from .pet_logic import (
    PET_ALERT_TTL_MS,
    PET_DEFAULT_SIZE,
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
from .windows import APP_NAME, apply_floating_tool_window_style, native_window_styles


PET_ENABLED_KEY = "floating_pet/enabled"
PET_SIZE_KEY = "floating_pet/size"
PET_X_KEY = "floating_pet/position_x"
PET_Y_KEY = "floating_pet/position_y"
PET_ALERTS_KEY = "floating_pet/alerts_enabled"
PET_ALERT_MEMORY_KEY = "floating_pet/alert_memory"
MENU_OPEN_LABEL = "Open PokeTokenBar"
MENU_PET_VISIBILITY_LABEL = "Show desktop pet"
MENU_REFRESH_LABEL = "Refresh"
MENU_QUIT_LABEL = "Quit"


def _egg_pixmap(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = max(4, size // 8)
    rect = (margin + size // 16, margin, size - 2 * margin - size // 8, size - 2 * margin)
    painter.setBrush(QColor("#f7ead0"))
    painter.setPen(QPen(QColor("#c4a574"), max(2, size // 32)))
    painter.drawEllipse(*rect)
    painter.setPen(Qt.PenStyle.NoPen)
    for color, nx, ny, scale in (
        ("#6eb8b0", 0.32, 0.28, 0.18),
        ("#7ec8c0", 0.58, 0.42, 0.14),
        ("#5aa39c", 0.40, 0.55, 0.12),
    ):
        painter.setBrush(QColor(color))
        diameter = max(3, int(rect[2] * scale))
        painter.drawEllipse(
            int(rect[0] + rect[2] * nx - diameter / 2),
            int(rect[1] + rect[3] * ny - diameter / 2),
            diameter,
            diameter,
        )
    painter.end()
    return pixmap


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
    painter.setPen(QPen(QColor("#202124"), max(2, size // 14)))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(margin, margin, diameter, diameter)
    radius = max(3, size // 6)
    painter.setPen(QPen(QColor("#202124"), max(2, size // 16)))
    painter.setBrush(QColor("#fafafa"))
    painter.drawEllipse(size // 2 - radius, size // 2 - radius, radius * 2, radius * 2)
    painter.end()
    return pixmap


def _loading_pokeball_pixmap(size: int, ball: QPixmap, frame: int) -> QPixmap:
    """Render the looping Poké Ball shake used while a new pet is resolved."""
    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    offsets = (0, -5, 5, -4, 4, -2, 2, 0)
    offset = round(offsets[frame % len(offsets)] * size / 96)
    ball_size = max(28, round(size * 0.58))
    rendered = ball.scaled(
        ball_size,
        ball_size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    painter.drawPixmap(
        (size - rendered.width()) // 2 + offset,
        (size - rendered.height()) // 2 + round(size * 0.1),
        rendered,
    )
    painter.end()
    return canvas


class AnimatedSpriteFrameStabilizer:
    """Hide pathological GIF frames whose visible sprite suddenly collapses."""

    def __init__(self, minimum_area_ratio: float = 0.45):
        self.minimum_area_ratio = minimum_area_ratio
        self.largest_visible_area = 0
        self.last_stable_pixmap = QPixmap()

    @staticmethod
    def visible_area(pixmap: QPixmap) -> int:
        if pixmap.isNull():
            return 0
        bounds = QRegion(pixmap.mask()).boundingRect()
        return max(0, bounds.width()) * max(0, bounds.height())

    def reset(self) -> None:
        self.largest_visible_area = 0
        self.last_stable_pixmap = QPixmap()

    def filter(self, pixmap: QPixmap) -> QPixmap:
        area = self.visible_area(pixmap)
        if (
            area > 0
            and self.largest_visible_area > 0
            and area < self.largest_visible_area * self.minimum_area_ratio
            and not self.last_stable_pixmap.isNull()
        ):
            return self.last_stable_pixmap
        if area > 0:
            self.largest_visible_area = max(self.largest_visible_area, area)
            self.last_stable_pixmap = QPixmap(pixmap)
        return pixmap


class FloatingPetWindow(QWidget):
    clicked = Signal()
    hide_requested = Signal()
    refresh_requested = Signal()
    quit_requested = Signal()
    hover_changed = Signal(bool)
    position_committed = Signal(int, int)

    def __init__(self, size: int):
        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setObjectName("FloatingPetWindow")
        self.setWindowTitle(f"{APP_NAME} Pet")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.label.setStyleSheet("background: transparent;")
        self.movie: QMovie | None = None
        self.frame_stabilizer = AnimatedSpriteFrameStabilizer()
        self.sprite_path: Path | None = None
        self.is_egg = False
        self.is_loading = True
        self.loading_frame = 0
        self.loading_ball_pixmap = _pokeball_pixmap(max(32, round(size * 0.56)))
        self.loading_timer = QTimer(self)
        self.loading_timer.setInterval(90)
        self.loading_timer.timeout.connect(self._advance_loading)
        self.loading_timer.start()
        self.reveal_timer = QTimer(self)
        self.reveal_timer.setInterval(70)
        self.reveal_timer.timeout.connect(self._advance_companion_reveal)
        self.reveal_frame = 0
        self.reveal_target_path: Path | None = None
        self.reveal_target_is_egg = False
        self.reveal_ball_pixmap = QPixmap()
        self.reveal_target_pixmap = QPixmap()
        self.pet_size = normalize_pet_size(size)
        self._press_global: QPoint | None = None
        self._start_position: QPoint | None = None
        self._dragging = False
        self.set_pet_size(self.pet_size)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        apply_floating_tool_window_style(int(self.winId()))

    def set_pet_size(self, size: int) -> None:
        self.pet_size = normalize_pet_size(size)
        self.setFixedSize(self.pet_size, self.pet_size)
        self.label.setGeometry(0, 0, self.pet_size, self.pet_size)
        self._render_current_frame()

    def set_sprite(self, path: Path | None, *, is_egg: bool) -> None:
        self.reveal_timer.stop()
        self.frame_stabilizer.reset()
        if self.movie is not None:
            self.movie.stop()
            self.movie.deleteLater()
            self.movie = None
        self.is_loading = False
        self.loading_timer.stop()
        self.sprite_path = path
        self.is_egg = is_egg
        self.label.clear()
        if path is not None and path.exists() and path.suffix.lower() == ".gif":
            movie = QMovie(str(path), parent=self)
            if movie.isValid():
                movie.frameChanged.connect(self._render_current_frame)
                self.movie = movie
                movie.start()
                return
            movie.deleteLater()
        self._render_current_frame()

    def set_loading(self, ball_path: Path | None = None) -> None:
        self.reveal_timer.stop()
        self.frame_stabilizer.reset()
        if self.movie is not None:
            self.movie.stop()
            self.movie.deleteLater()
            self.movie = None
        self.is_loading = True
        self.loading_frame = 0
        ball = (
            QPixmap(str(ball_path))
            if ball_path is not None and ball_path.exists()
            else QPixmap()
        )
        self.loading_ball_pixmap = (
            ball
            if not ball.isNull()
            else _pokeball_pixmap(max(32, round(self.pet_size * 0.56)))
        )
        self.sprite_path = None
        self.is_egg = False
        self.label.clear()
        if self.isVisible():
            self.loading_timer.start()
        self._render_current_frame()

    def start_companion_reveal(
        self,
        target_path: Path | None,
        *,
        is_egg: bool,
        ball_path: Path | None = None,
    ) -> None:
        """Play the same Poké Ball reveal directly on the floating pet."""
        self.reveal_timer.stop()
        self.frame_stabilizer.reset()
        self.loading_timer.stop()
        if self.movie is not None:
            self.movie.stop()
            self.movie.deleteLater()
            self.movie = None
        self.is_loading = False
        ball = (
            QPixmap(str(ball_path))
            if ball_path is not None and ball_path.exists()
            else QPixmap()
        )
        if ball.isNull():
            ball = _pokeball_pixmap(max(32, round(self.pet_size * 0.56)))
        target = (
            QPixmap(str(target_path))
            if target_path is not None and target_path.exists()
            else QPixmap()
        )
        if target.isNull():
            target = _egg_pixmap(self.pet_size) if is_egg else _pokeball_pixmap(self.pet_size)
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
            self.set_sprite(
                self.reveal_target_path,
                is_egg=self.reveal_target_is_egg,
            )
            return

        size = self.pet_size
        center = size // 2
        canvas = QPixmap(size, size)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if frame < 9:
            offset_scale = max(2, round(size / 19))
            offsets = (0, -offset_scale, offset_scale, -offset_scale, offset_scale, -2, 2, 0, 0)
            ball_size = round(size * (0.52 if frame < 7 else 0.58))
            ball = self.reveal_ball_pixmap.scaled(
                ball_size,
                ball_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = center - ball.width() // 2 + offsets[frame]
            y = center - ball.height() // 2 + round(size * 0.12)
            painter.drawPixmap(x, y, ball)
            if frame >= 7:
                flash_alpha = 90 if frame == 7 else 180
                painter.setBrush(QColor(255, 248, 196, flash_alpha))
                painter.setPen(Qt.PenStyle.NoPen)
                radius = round(size * (0.21 + (frame - 7) * 0.16))
                painter.drawEllipse(center - radius, center - radius, radius * 2, radius * 2)
        else:
            progress = min(1.0, (frame - 9) / 9.0)
            eased = 1.0 - (1.0 - progress) ** 3
            painter.setBrush(QColor(255, 248, 196, round(150 * (1.0 - progress))))
            painter.setPen(Qt.PenStyle.NoPen)
            glow_radius = round(size * (0.16 + 0.38 * progress))
            painter.drawEllipse(
                center - glow_radius,
                center - glow_radius,
                glow_radius * 2,
                glow_radius * 2,
            )
            target_size = max(12, round(size * (0.16 + 0.84 * eased)))
            target = self.reveal_target_pixmap.scaled(
                target_size,
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.setOpacity(max(0.15, progress))
            painter.drawPixmap(
                center - target.width() // 2,
                center - target.height() // 2 - round(size * 0.09 * (1.0 - progress)),
                target,
            )
        painter.end()
        self.label.clear()
        self.label.setPixmap(canvas)
        self.reveal_frame += 1

    def _advance_loading(self) -> None:
        if not self.is_loading:
            self.loading_timer.stop()
            return
        self.loading_frame = (self.loading_frame + 1) % 8
        self._render_current_frame()

    def _render_current_frame(self, *_args) -> None:
        if self.is_loading:
            self.label.setText("")
            self.label.setStyleSheet("background: transparent;")
            self.label.setPixmap(
                _loading_pokeball_pixmap(
                    self.pet_size,
                    self.loading_ball_pixmap,
                    self.loading_frame,
                )
            )
            return
        pixmap = QPixmap()
        if self.movie is not None:
            pixmap = self.frame_stabilizer.filter(self.movie.currentPixmap())
        elif self.sprite_path is not None and self.sprite_path.exists():
            pixmap = QPixmap(str(self.sprite_path))
        if pixmap.isNull():
            pixmap = _egg_pixmap(self.pet_size) if self.is_egg else QPixmap()
        if pixmap.isNull():
            self.label.setText("●")
            self.label.setStyleSheet("background: transparent; color: #ef4444; font-size: 42px;")
            return
        self.label.setText("")
        self.label.setStyleSheet("background: transparent;")
        self.label.setPixmap(
            pixmap.scaled(
                self.pet_size,
                self.pet_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        )

    def set_animation_running(self, running: bool) -> None:
        if self.is_loading:
            if running:
                self.loading_timer.start()
            else:
                self.loading_timer.stop()
            self._render_current_frame()
            return
        if self.movie is None:
            return
        if running:
            self.movie.start()
        else:
            self.movie.stop()
            self._render_current_frame()

    def enterEvent(self, event) -> None:  # noqa: N802
        super().enterEvent(event)
        self.hover_changed.emit(True)

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self.hover_changed.emit(False)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._start_position = self.pos()
            self._dragging = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if (
            self._press_global is not None
            and self._start_position is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            delta = event.globalPosition().toPoint() - self._press_global
            if delta.manhattanLength() >= QApplication.startDragDistance():
                self._dragging = True
            if self._dragging:
                self.move(self._start_position + delta)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._press_global is not None:
            was_dragging = self._dragging
            self._press_global = None
            self._start_position = None
            self._dragging = False
            if was_dragging:
                self.position_committed.emit(self.x(), self.y())
            else:
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        self.hover_changed.emit(False)
        menu, actions = self._build_context_menu()
        selected = menu.exec(event.globalPos())
        if selected is actions["open"]:
            self.clicked.emit()
        elif selected is actions["visibility"]:
            self.hide_requested.emit()
        elif selected is actions["refresh"]:
            self.refresh_requested.emit()
        elif selected is actions["quit"]:
            self.quit_requested.emit()

    def _build_context_menu(self) -> tuple[QMenu, dict[str, object]]:
        """Mirror the tray menu exactly while the pet itself is visible."""
        menu = QMenu(self)
        open_action = menu.addAction(MENU_OPEN_LABEL)
        visibility_action = menu.addAction(MENU_PET_VISIBILITY_LABEL)
        visibility_action.setCheckable(True)
        visibility_action.setChecked(True)
        refresh_action = menu.addAction(MENU_REFRESH_LABEL)
        menu.addSeparator()
        quit_action = menu.addAction(MENU_QUIT_LABEL)
        return menu, {
            "open": open_action,
            "visibility": visibility_action,
            "refresh": refresh_action,
            "quit": quit_action,
        }


class _CalloutBase(QFrame):
    def __init__(self):
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet(
            "QFrame { background: #fffdf9; border: 1px solid #d8d2c8; border-radius: 10px; }"
        )

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        apply_floating_tool_window_style(int(self.winId()))


class HoverCallout(_CalloutBase):
    def __init__(self):
        super().__init__()
        self.setObjectName("HoverCallout")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "QFrame#HoverCallout { background: #fffdf9; border: 1px solid #d8d2c8; "
            "border-radius: 4px; } "
            "QLabel#HoverCalloutText { background: transparent; border: none; "
            "color: #26221d; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 3, 5, 3)
        self.label = QLabel()
        self.label.setObjectName("HoverCalloutText")
        self.label.setStyleSheet(
            "background: transparent; border: none; color: #26221d;"
        )
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(280)
        layout.addWidget(self.label)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#fffdf9"))
        painter.setPen(QPen(QColor("#d8d2c8"), 1))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 4, 4)
        painter.end()

    def set_text(self, text: str) -> None:
        self.label.setText(text)
        longest_line = max(text.splitlines() or [""], key=len)
        natural_width = self.label.fontMetrics().horizontalAdvance(longest_line) + 2
        width = max(1, min(280, natural_width))
        self.label.setFixedWidth(width)
        self.resize(self.sizeHint())


class AlertBubble(_CalloutBase):
    def __init__(self):
        super().__init__()
        self.setObjectName("AlertBubble")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(3)
        self.title = QLabel()
        font = self.title.font()
        font.setBold(True)
        self.title.setFont(font)
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setMaximumWidth(240)
        self.title.setStyleSheet("border: none;")
        self.body.setStyleSheet("border: none; color: #4b5563;")
        layout.addWidget(self.title)
        layout.addWidget(self.body)

    def set_alert(self, alert) -> None:
        self.title.setText(alert.title)
        self.body.setText(alert.body)
        color = "#b91c1c" if alert.severity == "critical" else "#b45309"
        self.title.setStyleSheet(f"border: none; color: {color};")
        self.adjustSize()


class FloatingPetController(QObject):
    enabled_changed = Signal(bool)
    size_changed = Signal(int)
    alerts_enabled_changed = Signal(bool)

    def __init__(
        self,
        app: QApplication,
        settings,
        on_open: Callable[[], None],
        *,
        on_refresh: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        warning_percent: float = 80.0,
        critical_percent: float = 95.0,
        display_mode: LimitDisplayMode = DEFAULT_LIMIT_DISPLAY_MODE,
        time_mode: LimitTimeMode = DEFAULT_LIMIT_TIME_MODE,
    ):
        super().__init__()
        self.app = app
        self.settings = settings
        self.on_open = on_open
        self.on_refresh = on_refresh
        self.on_quit = on_quit
        self.enabled = settings_bool(settings.value(PET_ENABLED_KEY, False), False)
        self.alerts_enabled = settings_bool(settings.value(PET_ALERTS_KEY, True), True)
        self.warning_percent = float(warning_percent)
        self.critical_percent = float(critical_percent)
        self.display_mode = display_mode
        self.time_mode = time_mode
        self.show_tokens = settings_bool(settings.value("tray_show_tokens", True), True)
        self.show_cost = settings_bool(settings.value("tray_show_cost", False), False)
        self.show_limit = settings_bool(settings.value("tray_show_limit", True), True)
        self.size = normalize_pet_size(settings.value(PET_SIZE_KEY, PET_DEFAULT_SIZE))
        self.result: Any | None = None
        self.initial_reveal_played = False
        self.reveal_on_next_update = False
        self.alert_memory = load_alert_memory(settings.value(PET_ALERT_MEMORY_KEY, ""))
        self.pet = FloatingPetWindow(self.size)
        self.hover = HoverCallout()
        self.bubble = AlertBubble()
        self.bubble_timer = QTimer(self)
        self.bubble_timer.setSingleShot(True)
        self.bubble_timer.timeout.connect(self.bubble.hide)
        self.pet.clicked.connect(self.on_open)
        if self.on_refresh is not None:
            self.pet.refresh_requested.connect(self.on_refresh)
        if self.on_quit is not None:
            self.pet.quit_requested.connect(self.on_quit)
        self.pet.hide_requested.connect(lambda: self.set_enabled(False))
        self.pet.hover_changed.connect(self._on_hover)
        self.pet.position_committed.connect(self._save_position)
        self.app.screenAdded.connect(self._screen_added)
        self.app.screenRemoved.connect(lambda _screen: self._screens_changed())
        for screen in self.app.screens():
            self._observe_screen(screen)
        self._restore_position()
        self._apply_visibility()

    def _observe_screen(self, screen) -> None:
        screen.geometryChanged.connect(lambda _rect: self._screens_changed())
        screen.availableGeometryChanged.connect(lambda _rect: self._screens_changed())

    def _screen_added(self, screen) -> None:
        self._observe_screen(screen)
        self._screens_changed()

    def _screen_rects(self) -> list[ScreenRect]:
        return [
            ScreenRect(rect.x(), rect.y(), rect.width(), rect.height())
            for rect in (screen.availableGeometry() for screen in self.app.screens())
        ]

    def _restore_position(self) -> None:
        x = self.settings.value(PET_X_KEY, float("nan"))
        y = self.settings.value(PET_Y_KEY, float("nan"))
        target = recover_pet_position(x, y, self.size, self._screen_rects())
        self.pet.move(*target)
        self._save_position(*target)

    def _screens_changed(self) -> None:
        target = recover_pet_position(self.pet.x(), self.pet.y(), self.size, self._screen_rects())
        self.pet.move(*target)
        self._save_position(*target)
        self._position_auxiliary_windows()

    def _save_position(self, x: int, y: int) -> None:
        target = recover_pet_position(x, y, self.size, self._screen_rects())
        if target != (x, y):
            self.pet.move(*target)
        self.settings.setValue(PET_X_KEY, target[0])
        self.settings.setValue(PET_Y_KEY, target[1])
        self.settings.sync()
        self._position_auxiliary_windows()

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self.enabled == enabled:
            return
        self.enabled = enabled
        self.settings.setValue(PET_ENABLED_KEY, enabled)
        self.settings.sync()
        self._apply_visibility()
        self.enabled_changed.emit(enabled)
        if enabled and self.result is not None:
            self._render_result(evaluate_alerts=True)

    def set_size(self, size: int) -> None:
        normalized = normalize_pet_size(size)
        if self.size == normalized:
            return
        self.size = normalized
        self.settings.setValue(PET_SIZE_KEY, normalized)
        self.pet.set_pet_size(normalized)
        self._screens_changed()
        self.settings.sync()
        self.size_changed.emit(normalized)

    def set_alerts_enabled(self, enabled: bool) -> None:
        self.alerts_enabled = bool(enabled)
        self.settings.setValue(PET_ALERTS_KEY, self.alerts_enabled)
        self.settings.sync()
        if not self.alerts_enabled:
            self.bubble_timer.stop()
            self.bubble.hide()
        self.alerts_enabled_changed.emit(self.alerts_enabled)

    def set_alert_thresholds(self, warning_percent: float, critical_percent: float) -> None:
        self.warning_percent = float(warning_percent)
        self.critical_percent = float(critical_percent)

    def set_limit_display_mode(self, display_mode: LimitDisplayMode) -> None:
        self.display_mode = display_mode
        self._refresh_hover_text()

    def set_limit_time_mode(self, time_mode: LimitTimeMode) -> None:
        self.time_mode = time_mode
        self._refresh_hover_text()

    def set_display_preferences(
        self,
        *,
        show_tokens: bool,
        show_cost: bool,
        show_limit: bool,
    ) -> None:
        self.show_tokens = bool(show_tokens)
        self.show_cost = bool(show_cost)
        self.show_limit = bool(show_limit)
        self._refresh_hover_text()

    def _hover_text(self) -> str:
        if self.result is None:
            return ""
        return pet_hover_text(
            self.result.snapshot,
            self.result.limits,
            self.display_mode,
            time_mode=self.time_mode,
            show_tokens=self.show_tokens,
            show_cost=self.show_cost,
            show_limit=self.show_limit,
        )

    def _refresh_hover_text(self) -> None:
        if self.result is not None:
            text = self._hover_text()
            if not text:
                self.hover.hide()
                return
            self.hover.set_text(text)
            if self.hover.isVisible():
                self._position_auxiliary_windows()

    def _apply_visibility(self) -> None:
        if self.enabled and self.result is not None:
            self.pet.show()
            self.pet.raise_()
            self.pet.set_animation_running(True)
            QTimer.singleShot(0, lambda: apply_floating_tool_window_style(int(self.pet.winId())))
        else:
            self.bubble_timer.stop()
            self.hover.hide()
            self.bubble.hide()
            self.pet.set_animation_running(False)
            self.pet.hide()

    def update(self, result: Any) -> None:
        self.result = result
        self._render_result(evaluate_alerts=True)

    def set_loading(self) -> None:
        self.hover.hide()
        self.bubble.hide()
        self.reveal_on_next_update = True
        ball_path = self.result.reveal_ball_path if self.result is not None else None
        self.pet.set_loading(ball_path)

    def _render_result(self, *, evaluate_alerts: bool) -> None:
        if self.result is None:
            return
        animate_reveal = self.enabled and (
            not self.initial_reveal_played or self.reveal_on_next_update
        )
        if animate_reveal:
            self.initial_reveal_played = True
            self.reveal_on_next_update = False
            self.pet.start_companion_reveal(
                self.result.pet_sprite_path,
                is_egg=self.result.pet_is_egg,
                ball_path=self.result.reveal_ball_path,
            )
        else:
            self.pet.set_sprite(self.result.pet_sprite_path, is_egg=self.result.pet_is_egg)
        self.hover.set_text(self._hover_text())
        if not self.enabled:
            self.pet.set_animation_running(False)
            return
        self.pet.set_animation_running(True)
        self.pet.show()
        if evaluate_alerts and self.alerts_enabled:
            alerts, self.alert_memory = evaluate_pet_alerts(
                self.result.limits,
                self.alert_memory,
                warning_percent=self.warning_percent,
                critical_percent=self.critical_percent,
                display_mode=self.display_mode,
                time_mode=self.time_mode,
            )
            self.settings.setValue(PET_ALERT_MEMORY_KEY, dump_alert_memory(self.alert_memory))
            self.settings.sync()
            alert = choose_pet_alert(alerts)
            if alert is not None:
                self.hover.hide()
                self.bubble.set_alert(alert)
                self._position_auxiliary_windows()
                self.bubble.show()
                self.bubble.raise_()
                self.bubble_timer.start(PET_ALERT_TTL_MS)

    def _on_hover(self, hovering: bool) -> None:
        if not hovering or not self.enabled or self.bubble.isVisible() or self.result is None:
            self.hover.hide()
            return
        text = self._hover_text()
        if not text:
            self.hover.hide()
            return
        self.hover.set_text(text)
        self._position_auxiliary_windows()
        self.hover.show()
        self.hover.raise_()

    def _place_above(self, window: QWidget) -> None:
        screen = self.app.screenAt(self.pet.geometry().center()) or self.app.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        size = window.sizeHint().expandedTo(window.size())
        window.resize(size)
        x = self.pet.x() + (self.pet.width() - window.width()) // 2
        x = min(available.right() - window.width(), max(available.left(), x))
        y = self.pet.y() - window.height() - 8
        if y < available.top():
            y = min(available.bottom() - window.height(), self.pet.y() + self.pet.height() + 8)
        window.move(x, y)

    def _position_auxiliary_windows(self) -> None:
        self._place_above(self.hover)
        self._place_above(self.bubble)

    def shutdown(self) -> None:
        self.bubble_timer.stop()
        self.pet.loading_timer.stop()
        self.pet.reveal_timer.stop()
        if self.pet.movie is not None:
            self.pet.movie.stop()
        self.hover.close()
        self.bubble.close()
        self.pet.close()

    def qa_snapshot(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "visible": self.pet.isVisible(),
            "size": self.size,
            "position": [self.pet.x(), self.pet.y()],
            "hwnd": int(self.pet.winId()),
            "native_styles": native_window_styles(int(self.pet.winId())),
            "qt_window_flags": int(self.pet.windowFlags()),
            "translucent_background": self.pet.testAttribute(
                Qt.WidgetAttribute.WA_TranslucentBackground
            ),
            "movie_valid": bool(self.pet.movie is not None and self.pet.movie.isValid()),
            "sprite_path": str(self.pet.sprite_path) if self.pet.sprite_path is not None else None,
            "screens": [
                {
                    "name": screen.name(),
                    "available_geometry": [
                        screen.availableGeometry().x(),
                        screen.availableGeometry().y(),
                        screen.availableGeometry().width(),
                        screen.availableGeometry().height(),
                    ],
                    "device_pixel_ratio": screen.devicePixelRatio(),
                    "logical_dpi": screen.logicalDotsPerInch(),
                }
                for screen in self.app.screens()
            ],
        }
