from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QSettings, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QMainWindow

from .floating_pet import PET_ALERTS_KEY, PET_ENABLED_KEY, PET_SIZE_KEY
from .formatting import (
    DEFAULT_FORECAST_ENABLED,
    DEFAULT_LIMIT_DISPLAY_MODE,
    FORECAST_ENABLED_KEY,
    LIMIT_DISPLAY_MODE_KEY,
    compact_tokens,
    format_limit_datetime,
    limit_display_percent,
    limit_percent_text,
    normalize_limit_display_mode,
    ordered_limit_windows,
)
from .notifications import (
    COMPANION_NOTIFICATIONS_KEY,
    CRITICAL_THRESHOLD_KEY,
    DEFAULT_COMPANION_NOTIFICATIONS,
    DEFAULT_CRITICAL_THRESHOLD,
    DEFAULT_LIMIT_NOTIFICATIONS,
    DEFAULT_WARNING_THRESHOLD,
    LIMIT_NOTIFICATIONS_KEY,
    WARNING_THRESHOLD_KEY,
)
from .pet_logic import PET_DEFAULT_SIZE, normalize_pet_size, settings_bool
from .pokemon import (
    MINT_PRICE,
    RARE_CANDY_PRICE,
    SHINY_CHARM_PRICE,
    PokeAPIClient,
    egg_price,
)
from .state import GameState, companion_progress_percent, owned_representative_options
from .usage import PROVIDER_LABELS
from .windows import APP_NAME, autostart_enabled, set_autostart


def _file_url(path: Path | None) -> str:
    if path is None:
        return ""
    return QUrl.fromLocalFile(str(path.resolve())).toString()


class _TextProxy(QObject):
    def __init__(self, setter, parent: QObject | None = None):
        super().__init__(parent)
        self._setter = setter

    def setText(self, value: str) -> None:
        self._setter(str(value))


class _ButtonProxy(QObject):
    clicked = Signal()

    def __init__(self, enabled_setter=None, parent: QObject | None = None):
        super().__init__(parent)
        self._enabled_setter = enabled_setter

    def setEnabled(self, value: bool) -> None:
        if self._enabled_setter is not None:
            self._enabled_setter(bool(value))


class QmlViewModel(QObject):
    dataChanged = Signal()
    revealChanged = Signal()

    refreshRequested = Signal()
    petVisibilityChanged = Signal(bool)
    petSizeChanged = Signal(int)
    preferencesChanged = Signal()
    representativeChanged = Signal(object)
    languageChanged = Signal(str)
    exportRequested = Signal()
    importRequested = Signal()
    useItemRequested = Signal(str)
    buyItemRequested = Signal(str)
    buyEggRequested = Signal(object)

    def __init__(self, state: GameState, settings: QSettings, api: PokeAPIClient):
        super().__init__()
        self.state = state
        self.settings = settings
        self.api = api
        self._values: dict[str, Any] = {
            "loading": True,
            "refreshEnabled": False,
            "statusText": "Loading usage and limits…",
            "feedbackText": "",
            "toastText": "",
            "toastShiny": False,
            "revealActive": False,
            "companionName": "Pokémon Egg",
            "companionSubtitle": "Preparing your companion",
            "companionProgress": 0,
            "companionProgressText": "0% until hatching",
            "spriteUrl": "",
            "todayTokens": "—",
            "todayCost": "—",
            "weekTokens": "—",
            "wallet": compact_tokens(state.wallet),
            "providers": [],
            "limits": [],
            "collection": [],
            "catches": [],
            "shopItems": [],
            "rareCandyCount": 0,
            "mintCount": 0,
            "shinyCharmActive": False,
            "refreshMinutes": int(settings.value("refresh_minutes", 5)),
            "petEnabled": settings_bool(settings.value(PET_ENABLED_KEY, False), False),
            "petSize": normalize_pet_size(
                settings.value(PET_SIZE_KEY, PET_DEFAULT_SIZE)
            ),
            "petAlerts": settings_bool(settings.value(PET_ALERTS_KEY, True), True),
            "trayShowTokens": settings.value("tray_show_tokens", True, type=bool),
            "trayShowCost": settings.value("tray_show_cost", False, type=bool),
            "trayShowLimit": settings.value("tray_show_limit", True, type=bool),
            "limitDisplayMode": normalize_limit_display_mode(
                settings.value(LIMIT_DISPLAY_MODE_KEY, DEFAULT_LIMIT_DISPLAY_MODE)
            ),
            "forecastEnabled": settings_bool(
                settings.value(FORECAST_ENABLED_KEY, DEFAULT_FORECAST_ENABLED),
                DEFAULT_FORECAST_ENABLED,
            ),
            "limitNotifications": settings_bool(
                settings.value(LIMIT_NOTIFICATIONS_KEY, DEFAULT_LIMIT_NOTIFICATIONS),
                DEFAULT_LIMIT_NOTIFICATIONS,
            ),
            "companionNotifications": settings_bool(
                settings.value(
                    COMPANION_NOTIFICATIONS_KEY, DEFAULT_COMPANION_NOTIFICATIONS
                ),
                DEFAULT_COMPANION_NOTIFICATIONS,
            ),
            "warningThreshold": int(
                settings.value(WARNING_THRESHOLD_KEY, DEFAULT_WARNING_THRESHOLD)
            ),
            "criticalThreshold": int(
                settings.value(CRITICAL_THRESHOLD_KEY, DEFAULT_CRITICAL_THRESHOLD)
            ),
            "theme": str(settings.value("theme", "system")),
            "darkMode": False,
            "language": state.language,
            "autostart": autostart_enabled(),
        }
        self._refresh_dark_mode()
        self._render_state()

    loading = Property(bool, lambda self: self._values["loading"], notify=dataChanged)
    refreshEnabled = Property(
        bool, lambda self: self._values["refreshEnabled"], notify=dataChanged
    )
    statusText = Property(
        str, lambda self: self._values["statusText"], notify=dataChanged
    )
    feedbackText = Property(
        str, lambda self: self._values["feedbackText"], notify=dataChanged
    )
    toastText = Property(
        str, lambda self: self._values["toastText"], notify=dataChanged
    )
    toastShiny = Property(
        bool, lambda self: self._values["toastShiny"], notify=dataChanged
    )
    revealActive = Property(
        bool, lambda self: self._values["revealActive"], notify=revealChanged
    )
    companionName = Property(
        str, lambda self: self._values["companionName"], notify=dataChanged
    )
    companionSubtitle = Property(
        str, lambda self: self._values["companionSubtitle"], notify=dataChanged
    )
    companionProgress = Property(
        int, lambda self: self._values["companionProgress"], notify=dataChanged
    )
    companionProgressText = Property(
        str, lambda self: self._values["companionProgressText"], notify=dataChanged
    )
    spriteUrl = Property(
        str, lambda self: self._values["spriteUrl"], notify=dataChanged
    )
    todayTokens = Property(
        str, lambda self: self._values["todayTokens"], notify=dataChanged
    )
    todayCost = Property(
        str, lambda self: self._values["todayCost"], notify=dataChanged
    )
    weekTokens = Property(
        str, lambda self: self._values["weekTokens"], notify=dataChanged
    )
    wallet = Property(str, lambda self: self._values["wallet"], notify=dataChanged)
    providers = Property(
        "QVariantList", lambda self: self._values["providers"], notify=dataChanged
    )
    limits = Property(
        "QVariantList", lambda self: self._values["limits"], notify=dataChanged
    )
    collection = Property(
        "QVariantList", lambda self: self._values["collection"], notify=dataChanged
    )
    catches = Property(
        "QVariantList", lambda self: self._values["catches"], notify=dataChanged
    )
    shopItems = Property(
        "QVariantList", lambda self: self._values["shopItems"], notify=dataChanged
    )
    rareCandyCount = Property(
        int, lambda self: self._values["rareCandyCount"], notify=dataChanged
    )
    mintCount = Property(
        int, lambda self: self._values["mintCount"], notify=dataChanged
    )
    shinyCharmActive = Property(
        bool, lambda self: self._values["shinyCharmActive"], notify=dataChanged
    )
    refreshMinutes = Property(
        int, lambda self: self._values["refreshMinutes"], notify=dataChanged
    )
    petEnabled = Property(
        bool, lambda self: self._values["petEnabled"], notify=dataChanged
    )
    petSize = Property(int, lambda self: self._values["petSize"], notify=dataChanged)
    petAlerts = Property(
        bool, lambda self: self._values["petAlerts"], notify=dataChanged
    )
    trayShowTokens = Property(
        bool, lambda self: self._values["trayShowTokens"], notify=dataChanged
    )
    trayShowCost = Property(
        bool, lambda self: self._values["trayShowCost"], notify=dataChanged
    )
    trayShowLimit = Property(
        bool, lambda self: self._values["trayShowLimit"], notify=dataChanged
    )
    limitDisplayMode = Property(
        str, lambda self: self._values["limitDisplayMode"], notify=dataChanged
    )
    forecastEnabled = Property(
        bool, lambda self: self._values["forecastEnabled"], notify=dataChanged
    )
    limitNotifications = Property(
        bool, lambda self: self._values["limitNotifications"], notify=dataChanged
    )
    companionNotifications = Property(
        bool, lambda self: self._values["companionNotifications"], notify=dataChanged
    )
    warningThreshold = Property(
        int, lambda self: self._values["warningThreshold"], notify=dataChanged
    )
    criticalThreshold = Property(
        int, lambda self: self._values["criticalThreshold"], notify=dataChanged
    )
    theme = Property(str, lambda self: self._values["theme"], notify=dataChanged)
    darkMode = Property(bool, lambda self: self._values["darkMode"], notify=dataChanged)
    language = Property(str, lambda self: self._values["language"], notify=dataChanged)
    autostart = Property(
        bool, lambda self: self._values["autostart"], notify=dataChanged
    )

    def _refresh_dark_mode(self) -> None:
        theme = str(self._values["theme"])
        system_dark = False
        try:
            system_dark = QGuiApplication.styleHints().colorScheme().name == "Dark"
        except (AttributeError, RuntimeError):
            pass
        self._values["darkMode"] = theme == "dark" or (
            theme == "system" and system_dark
        )

    def _set(self, key: str, value: Any) -> None:
        if self._values.get(key) == value:
            return
        self._values[key] = value
        self.dataChanged.emit()

    def _render_state(self) -> None:
        state = self.state
        progress = companion_progress_percent(state)
        if state.mon is None:
            name = "Pokémon Egg"
            tier = f" · {state.egg_tier.title()}+" if state.egg_tier else ""
            subtitle = f"Waiting to hatch{tier}"
            progress_text = f"{progress}% until hatching"
            sprite_path = self.api.egg_sprite_path()
        else:
            mon = state.mon
            name = self.api.localized_name(mon.current_id, state.language)
            shiny = "✨ " if mon.is_shiny else ""
            subtitle = f"{shiny}{mon.rarity.title()} · {mon.nature} · stage {mon.stage_index + 1}/{len(mon.path_ids)}"
            progress_text = (
                "Fully evolved"
                if mon.stage_index + 1 >= len(mon.path_ids)
                else f"{progress}% until the next evolution"
            )
            sprite_path = self.api.sprite_path(mon.current_id, shiny=mon.is_shiny)

        self._values.update(
            companionName=name,
            companionSubtitle=subtitle,
            companionProgress=progress,
            companionProgressText=progress_text,
            spriteUrl=_file_url(sprite_path),
            wallet=compact_tokens(state.wallet),
            rareCandyCount=int(state.inventory.get("rare_candy", 0)),
            mintCount=int(state.inventory.get("mint", 0)),
            shinyCharmActive=state.shiny_charm_active,
            language=state.language,
        )
        self._values["collection"] = self._collection_rows()
        self._values["catches"] = self._catch_rows()
        self._values["shopItems"] = self._shop_rows()

    def _collection_rows(self) -> list[dict[str, Any]]:
        selected_id = self.state.representative_species_id
        selected_shiny = self.state.representative_is_shiny
        rows: list[dict[str, Any]] = [
            {
                "speciesId": 0,
                "name": "Follow active companion",
                "number": "AUTO",
                "shiny": False,
                "sprite": self._values.get("spriteUrl", ""),
                "selected": selected_id is None,
            }
        ]
        for subject in owned_representative_options(self.state):
            species_id = int(subject.species_id or 0)
            rows.append(
                {
                    "speciesId": species_id,
                    "name": self.api.localized_name(species_id, self.state.language),
                    "number": f"#{species_id:03d}",
                    "shiny": bool(subject.is_shiny),
                    "sprite": _file_url(
                        self.api.sprite_path(
                            species_id, shiny=subject.is_shiny, animated=False
                        )
                    ),
                    "selected": species_id == selected_id
                    and bool(subject.is_shiny) == bool(selected_shiny),
                }
            )
        return rows

    def _catch_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for catch in reversed(self.state.catches):
            path_ids = catch.path_ids or [catch.species_id]
            display_id = path_ids[-1]
            if (
                self.state.mon
                and catch.base_id == self.state.mon.base_id
                and catch.nature == self.state.mon.nature
            ):
                display_id = self.state.mon.current_id
            rows.append(
                {
                    "name": self.api.localized_name(display_id, self.state.language),
                    "number": f"#{display_id:03d}",
                    "meta": f"{catch.rarity.title()} · {catch.nature} · {catch.caught_at[:10]}",
                    "shiny": bool(catch.is_shiny),
                    "sprite": _file_url(
                        self.api.sprite_path(
                            display_id, shiny=catch.is_shiny, animated=False
                        )
                    ),
                }
            )
        return rows

    def _shop_rows(self) -> list[dict[str, Any]]:
        wallet = self.state.wallet
        inventory = self.state.inventory
        definitions = (
            (
                "item",
                "rare_candy",
                "Rare Candy",
                "Progress boost",
                "🍬",
                RARE_CANDY_PRICE,
            ),
            ("item", "mint", "Mint", "Change nature", "🌿", MINT_PRICE),
            (
                "item",
                "shiny_charm",
                "Shiny Charm",
                "Better shiny odds",
                "✨",
                SHINY_CHARM_PRICE,
            ),
            ("egg", "normal", "Normal Egg", "A fresh companion", "🥚", egg_price(None)),
            (
                "egg",
                "uncommon",
                "Uncommon Egg",
                "Uncommon or better",
                "🔵",
                egg_price("uncommon"),
            ),
            ("egg", "rare", "Rare Egg", "Rare or better", "🟣", egg_price("rare")),
        )
        rows = []
        for kind, key, title, subtitle, icon, price in definitions:
            owned = key == "shiny_charm" and inventory.get("shiny_charm", 0) > 0
            rows.append(
                {
                    "kind": kind,
                    "key": key,
                    "title": title,
                    "subtitle": subtitle,
                    "icon": icon,
                    "price": compact_tokens(price),
                    "enabled": wallet >= price and not owned,
                    "owned": owned,
                }
            )
        return rows

    def set_state(self, state: GameState) -> None:
        self.state = state
        self._render_state()
        self.dataChanged.emit()

    def render(self, result: Any) -> None:
        self.state = result.state
        snapshot = result.snapshot
        providers = []
        for key, usage in sorted(
            snapshot.providers.items(),
            key=lambda item: item[1].today_tokens,
            reverse=True,
        ):
            providers.append(
                {
                    "key": key,
                    "name": PROVIDER_LABELS.get(key, key.title()),
                    "today": compact_tokens(usage.today_tokens),
                    "week": compact_tokens(usage.week_tokens),
                    "month": compact_tokens(usage.month_tokens),
                    "cost": f"${usage.today_cost:,.2f}",
                    "error": False,
                }
            )
        for key in result.scan_errors:
            providers.append(
                {
                    "key": key,
                    "name": PROVIDER_LABELS.get(key, key.title()),
                    "today": "Unavailable",
                    "week": "—",
                    "month": "—",
                    "cost": "—",
                    "error": True,
                }
            )

        display_mode = normalize_limit_display_mode(
            self.settings.value(LIMIT_DISPLAY_MODE_KEY, DEFAULT_LIMIT_DISPLAY_MODE)
        )
        limits = []
        for key, provider_limits in result.limits.items():
            provider_name = PROVIDER_LABELS.get(key, key.title())
            for window in ordered_limit_windows(provider_limits):
                reset = (
                    format_limit_datetime(window.resets_at)
                    if window.resets_at
                    else "Reset unknown"
                )
                used = max(0.0, min(100.0, float(window.used_percent)))
                urgency = (
                    "critical"
                    if used >= 95
                    else ("warning" if used >= 80 else "neutral")
                )
                limits.append(
                    {
                        "provider": provider_name,
                        "plan": provider_limits.plan or "",
                        "label": window.label,
                        "percent": round(limit_display_percent(used, display_mode)),
                        "percentText": limit_percent_text(used, display_mode),
                        "reset": reset,
                        "urgency": urgency,
                    }
                )
        self._values.update(
            loading=False,
            refreshEnabled=True,
            statusText=(
                f"Updated {snapshot.scanned_at.astimezone().strftime('%H:%M')}"
                if snapshot.scanned_at
                else "Updated"
            ),
            todayTokens=compact_tokens(snapshot.today_tokens),
            todayCost=f"${snapshot.today_cost:,.2f}",
            weekTokens=compact_tokens(snapshot.week_tokens),
            providers=providers,
            limits=limits,
        )
        self._render_state()
        self.dataChanged.emit()

    def set_refresh_enabled(self, enabled: bool) -> None:
        self._values["refreshEnabled"] = bool(enabled)
        self._values["loading"] = not enabled and not self._values["providers"]
        self.dataChanged.emit()

    def set_status(self, text: str) -> None:
        self._set("statusText", text)

    def show_feedback(self, text: str) -> None:
        self._set("feedbackText", text)

    def celebrate(self, text: str, shiny: bool = False) -> None:
        self._values["toastText"] = text
        self._values["toastShiny"] = shiny
        self.dataChanged.emit()

    def set_reveal(self, active: bool) -> None:
        active = bool(active)
        if self._values["revealActive"] == active:
            return
        self._values["revealActive"] = active
        self.revealChanged.emit()

    @Slot()
    def requestRefresh(self) -> None:
        self.refreshRequested.emit()

    @Slot(bool)
    def setPetEnabled(self, enabled: bool) -> None:
        self.settings.setValue(PET_ENABLED_KEY, enabled)
        self._set("petEnabled", bool(enabled))
        self.petVisibilityChanged.emit(bool(enabled))

    @Slot(int)
    def setPetSize(self, size: int) -> None:
        normalized = normalize_pet_size(size)
        self.settings.setValue(PET_SIZE_KEY, normalized)
        self._set("petSize", normalized)
        self.petSizeChanged.emit(normalized)

    @Slot(str, "QVariant")
    def setPreference(self, key: str, value: Any) -> None:
        known = {
            "petAlerts": PET_ALERTS_KEY,
            "trayShowTokens": "tray_show_tokens",
            "trayShowCost": "tray_show_cost",
            "trayShowLimit": "tray_show_limit",
            "limitDisplayMode": LIMIT_DISPLAY_MODE_KEY,
            "forecastEnabled": FORECAST_ENABLED_KEY,
            "limitNotifications": LIMIT_NOTIFICATIONS_KEY,
            "companionNotifications": COMPANION_NOTIFICATIONS_KEY,
            "warningThreshold": WARNING_THRESHOLD_KEY,
            "criticalThreshold": CRITICAL_THRESHOLD_KEY,
            "theme": "theme",
        }
        setting_key = known.get(key)
        if setting_key is None:
            return
        if key in {"warningThreshold", "criticalThreshold"}:
            value = int(value)
        elif key == "limitDisplayMode":
            value = normalize_limit_display_mode(value)
        self.settings.setValue(setting_key, value)
        self.settings.sync()
        self._values[key] = value
        if key == "theme":
            self._refresh_dark_mode()
        self.dataChanged.emit()
        self.preferencesChanged.emit()

    @Slot(int)
    def setRefreshMinutes(self, minutes: int) -> None:
        minutes = max(1, int(minutes))
        self.settings.setValue("refresh_minutes", minutes)
        self.settings.sync()
        self._set("refreshMinutes", minutes)
        self.refreshRequested.emit()

    @Slot(str)
    def setLanguage(self, language: str) -> None:
        if language not in {"en", "es", "fr", "ja"}:
            return
        self._set("language", language)
        self.languageChanged.emit(language)

    @Slot(int)
    def chooseRepresentative(self, index: int) -> None:
        rows = self._values["collection"]
        if not 0 <= index < len(rows):
            return
        row = rows[index]
        selection = (
            None
            if row["speciesId"] == 0
            else (int(row["speciesId"]), bool(row["shiny"]))
        )
        self.representativeChanged.emit(selection)

    @Slot(str)
    def useItem(self, key: str) -> None:
        self.useItemRequested.emit(key)

    @Slot(str, str)
    def buy(self, kind: str, key: str) -> None:
        if kind == "egg":
            self.buyEggRequested.emit(None if key == "normal" else key)
        else:
            self.buyItemRequested.emit(key)

    @Slot()
    def requestExport(self) -> None:
        self.exportRequested.emit()

    @Slot()
    def requestImport(self) -> None:
        self.importRequested.emit()

    @Slot(bool)
    def setAutostart(self, enabled: bool) -> None:
        try:
            set_autostart(enabled)
        except OSError:
            enabled = autostart_enabled()
            self.show_feedback("Windows could not change the startup setting.")
        self._set("autostart", bool(enabled))


class QmlMainWindow(QMainWindow):
    refresh_requested = Signal()
    pet_visibility_changed = Signal(bool)
    pet_size_changed = Signal(int)
    preferences_changed = Signal()
    representative_changed = Signal(object)
    language_changed = Signal(str)
    export_requested = Signal()
    import_requested = Signal()
    use_item_requested = Signal(str)
    buy_item_requested = Signal(str)
    buy_egg_requested = Signal(object)

    def __init__(self, state: GameState, settings: QSettings, api: PokeAPIClient):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(820, 580)
        self.resize(1080, 720)

        self.view_model = QmlViewModel(state, settings, api)
        self.view_model.refreshRequested.connect(self.refresh_requested)
        self.view_model.petVisibilityChanged.connect(self.pet_visibility_changed)
        self.view_model.petSizeChanged.connect(self.pet_size_changed)
        self.view_model.preferencesChanged.connect(self.preferences_changed)
        self.view_model.representativeChanged.connect(self.representative_changed)
        self.view_model.languageChanged.connect(self.language_changed)
        self.view_model.exportRequested.connect(self.export_requested)
        self.view_model.importRequested.connect(self.import_requested)
        self.view_model.useItemRequested.connect(self.use_item_requested)
        self.view_model.buyItemRequested.connect(self.buy_item_requested)
        self.view_model.buyEggRequested.connect(self.buy_egg_requested)

        self.quick = QQuickWidget(self)
        self.quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.quick.rootContext().setContextProperty("appModel", self.view_model)
        qml_path = Path(__file__).resolve().parent / "qml" / "Main.qml"
        self.quick.setSource(QUrl.fromLocalFile(str(qml_path)))
        if self.quick.status() == QQuickWidget.Status.Error:
            details = "\n".join(error.toString() for error in self.quick.errors())
            raise RuntimeError(f"Could not load the QML interface:\n{details}")
        self.setCentralWidget(self.quick)
        self.statusBar().hide()

        self.refresh_button = _ButtonProxy(self.view_model.set_refresh_enabled, self)
        self.refresh_status = _TextProxy(self.view_model.set_status, self)
        self.action_feedback = _TextProxy(self.view_model.show_feedback, self)
        self.use_candy_btn = _ButtonProxy(parent=self)
        self.use_mint_btn = _ButtonProxy(parent=self)
        self.buy_candy_btn = _ButtonProxy(parent=self)
        self.buy_mint_btn = _ButtonProxy(parent=self)
        self.buy_charm_btn = _ButtonProxy(parent=self)
        self.buy_egg_btn = _ButtonProxy(parent=self)
        self.buy_uncommon_egg_btn = _ButtonProxy(parent=self)
        self.buy_rare_egg_btn = _ButtonProxy(parent=self)

    def set_state(self, state: GameState) -> None:
        self.view_model.set_state(state)

    def render(self, result: Any) -> None:
        self.view_model.render(result)

    def sync_floating_pet_settings(
        self, *, enabled: bool | None = None, size: int | None = None
    ) -> None:
        if enabled is not None:
            self.view_model._set("petEnabled", bool(enabled))
        if size is not None:
            self.view_model._set("petSize", normalize_pet_size(size))

    def celebrate(self, text: str, *, shiny: bool = False) -> None:
        self.view_model.celebrate(text, shiny)
        QTimer.singleShot(5000, lambda: self.view_model.celebrate("", False))

    def start_companion_reveal(
        self,
        sprite_path: Path | None,
        *,
        is_egg: bool = False,
        ball_path: Path | None = None,
    ) -> None:
        del sprite_path, is_egg, ball_path
        self.view_model.set_reveal(False)
        QTimer.singleShot(0, lambda: self.view_model.set_reveal(True))
        QTimer.singleShot(1200, lambda: self.view_model.set_reveal(False))

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.hide()
