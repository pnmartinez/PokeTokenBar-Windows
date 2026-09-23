from __future__ import annotations

import os
from calendar import monthrange
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate, QEvent, Property, QObject, QRect, QSettings, Qt, QTimer, QUrl, Signal, Slot, QLocale
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QMainWindow

from .floating_pet import PET_ALERTS_KEY, PET_ENABLED_KEY, PET_SIZE_KEY
from .formatting import (
    DEFAULT_FORECAST_ENABLED,
    DEFAULT_LIMIT_DISPLAY_MODE,
    FORECAST_ENABLED_KEY,
    LIMIT_DISPLAY_MODE_KEY,
    LIMIT_TIME_MODE_KEY,
    DEFAULT_LIMIT_TIME_MODE,
    compact_tokens,
    format_limit_countdown,
    format_limit_datetime,
    limit_display_percent,
    limit_forecast,
    limit_forecast_unavailable_reason,
    limit_reset_expiry,
    limit_reset_urgency,
    normalize_limit_display_mode,
    normalize_limit_time_mode,
    ordered_limit_windows,
)
from .notifications import (
    BANKED_RESET_NOTIFICATIONS_KEY,
    DEFAULT_BANKED_RESET_NOTIFICATIONS,
    DEFAULT_LIMIT_RESET_NOTIFICATIONS,
    LIMIT_RESET_NOTIFICATIONS_KEY,
    COMPANION_NOTIFICATIONS_KEY,
    CRITICAL_THRESHOLD_KEY,
    DEFAULT_COMPANION_NOTIFICATIONS,
    DEFAULT_CRITICAL_THRESHOLD,
    DEFAULT_LIMIT_NOTIFICATIONS,
    DEFAULT_WARNING_THRESHOLD,
    LIMIT_NOTIFICATIONS_KEY,
    WARNING_THRESHOLD_KEY,
    normalize_critical_threshold,
    normalize_warning_threshold,
)
from .localization import (
    LANGUAGE_OPTIONS,
    normalize_language,
    text as translated_text,
    ui_strings,
)
from .pet_logic import PET_DEFAULT_SIZE, normalize_pet_size, settings_bool
from .pokemon import (
    EGG_HATCH_THRESHOLD,
    MINT_PRICE,
    RARE_CANDY_XP,
    RARE_CANDY_PRICE,
    SHINY_CHARM_PRICE,
    PokeAPIClient,
    egg_price,
)
from .state import GameState, companion_progress_percent, owned_representative_options
from .usage import PROVIDER_LABELS, scan_month_history
from .windows import APP_NAME, autostart_enabled, set_autostart


_WINDOWS_SNAP_STYLE = 0x00040000 | 0x00010000  # WS_THICKFRAME | WS_MAXIMIZEBOX


def _enable_windows_snap(hwnd: int) -> bool:
    """Restore the native sizing style required by Windows edge snapping."""
    if os.name != "nt":
        return True

    import ctypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    get_style = user32.GetWindowLongPtrW
    get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
    get_style.restype = ctypes.c_ssize_t
    set_style = user32.SetWindowLongPtrW
    set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    set_style.restype = ctypes.c_ssize_t
    set_position = user32.SetWindowPos
    set_position.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    set_position.restype = ctypes.c_bool

    handle = ctypes.c_void_p(hwnd)
    current = int(get_style(handle, -16))
    desired = current | _WINDOWS_SNAP_STYLE
    if desired != current:
        ctypes.set_last_error(0)
        previous = int(set_style(handle, -16, desired))
        if previous == 0 and ctypes.get_last_error() != 0:
            return False
        # Recalculate the non-client area without moving or activating the window.
        set_position(handle, None, 0, 0, 0, 0, 0x0037)
    return (int(get_style(handle, -16)) & _WINDOWS_SNAP_STYLE) == _WINDOWS_SNAP_STYLE


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
    windowMinimizeRequested = Signal()
    windowToggleMaximizeRequested = Signal()
    windowCloseRequested = Signal()
    windowMoveRequested = Signal()
    windowResizeRequested = Signal(int)
    monthHistoryRequested = Signal()

    def __init__(self, state: GameState, settings: QSettings, api: PokeAPIClient):
        super().__init__()
        self.state = state
        self.settings = settings
        self.api = api
        self._dex_page = 0
        self._current_month = ""
        self._selected_month = ""
        self._month_history: dict[str, tuple[list[int], list[float]]] | None = None
        self._pending_previous = False
        self._snapshot = None
        self._dex_filter = "all"
        self._dex_shiny_by_species: dict[int, bool] = {}
        language = normalize_language(state.language)
        self._values: dict[str, Any] = {
            "loading": True,
            "refreshEnabled": False,
            "statusText": translated_text(language, "loading"),
            "feedbackText": "",
            "toastText": "",
            "toastShiny": False,
            "revealActive": False,
            "companionName": "Pokémon Egg",
            "companionSubtitle": "Preparing your companion",
            "companionProgress": 0,
            "companionProgressText": f"0 / {compact_tokens(EGG_HATCH_THRESHOLD)}",
            "companionLevelText": "Lv. 0",
            "companionEvolutionText": translated_text(language, "hatch_hint"),
            "spriteUrl": "",
            "todayTokens": "—",
            "todayCost": "—",
            "weekTokens": "—",
            "weekCost": "—",
            "wallet": compact_tokens(state.wallet),
            "providers": [],
            "monthTrend": [],
            "trendMonthLabel": "",
            "trendMonthTokens": "—",
            "trendMonthCost": "—",
            "trendCaption": "",
            "trendPeak": "",
            "trendCanPrevious": False,
            "trendCanNext": False,
            "trendLoading": False,
            "growthBoost": False,
            "limits": [],
            "collection": [],
            "dexEntries": [],
            "dexBrowseEntries": [],
            "dexFilters": [],
            "dexSummary": "0 especies",
            "dexPage": 1,
            "dexPageCount": 1,
            "dexFilter": "all",
            "catches": [],
            "shopItems": [],
            "rareCandyCount": 0,
            "rareCandyXp": compact_tokens(RARE_CANDY_XP),
            "mintCount": 0,
            "shinyCharmActive": False,
            "hasActiveCompanion": state.mon is not None,
            "representativeFollowsCurrent": state.representative_species_id is None,
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
            "limitTimeMode": normalize_limit_time_mode(
                settings.value(LIMIT_TIME_MODE_KEY, DEFAULT_LIMIT_TIME_MODE)
            ),
            "forecastEnabled": settings_bool(
                settings.value(FORECAST_ENABLED_KEY, DEFAULT_FORECAST_ENABLED),
                DEFAULT_FORECAST_ENABLED,
            ),
            "limitNotifications": settings_bool(
                settings.value(LIMIT_NOTIFICATIONS_KEY, DEFAULT_LIMIT_NOTIFICATIONS),
                DEFAULT_LIMIT_NOTIFICATIONS,
            ),
            "limitResetNotifications": settings_bool(
                settings.value(
                    LIMIT_RESET_NOTIFICATIONS_KEY, DEFAULT_LIMIT_RESET_NOTIFICATIONS
                ),
                DEFAULT_LIMIT_RESET_NOTIFICATIONS,
            ),
            "bankedResetNotifications": settings_bool(
                settings.value(
                    BANKED_RESET_NOTIFICATIONS_KEY, DEFAULT_BANKED_RESET_NOTIFICATIONS
                ),
                DEFAULT_BANKED_RESET_NOTIFICATIONS,
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
            "windowMaximized": False,
            "language": language,
            "strings": ui_strings(language),
            "languageOptions": list(LANGUAGE_OPTIONS),
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
    companionLevelText = Property(
        str, lambda self: self._values["companionLevelText"], notify=dataChanged
    )
    companionEvolutionText = Property(
        str, lambda self: self._values["companionEvolutionText"], notify=dataChanged
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
    weekCost = Property(str, lambda self: self._values["weekCost"], notify=dataChanged)
    wallet = Property(str, lambda self: self._values["wallet"], notify=dataChanged)
    providers = Property(
        "QVariantList", lambda self: self._values["providers"], notify=dataChanged
    )
    limits = Property(
        "QVariantList", lambda self: self._values["limits"], notify=dataChanged
    )
    monthTrend = Property(
        "QVariantList", lambda self: self._values["monthTrend"], notify=dataChanged
    )
    trendMonthLabel = Property(str, lambda self: self._values["trendMonthLabel"], notify=dataChanged)
    trendMonthTokens = Property(str, lambda self: self._values["trendMonthTokens"], notify=dataChanged)
    trendMonthCost = Property(str, lambda self: self._values["trendMonthCost"], notify=dataChanged)
    trendCaption = Property(str, lambda self: self._values["trendCaption"], notify=dataChanged)
    trendPeak = Property(str, lambda self: self._values["trendPeak"], notify=dataChanged)
    trendCanPrevious = Property(bool, lambda self: self._values["trendCanPrevious"], notify=dataChanged)
    trendCanNext = Property(bool, lambda self: self._values["trendCanNext"], notify=dataChanged)
    trendLoading = Property(bool, lambda self: self._values["trendLoading"], notify=dataChanged)

    growthBoost = Property(
        bool, lambda self: self._values["growthBoost"], notify=dataChanged
    )
    collection = Property(
        "QVariantList", lambda self: self._values["collection"], notify=dataChanged
    )
    dexEntries = Property(
        "QVariantList", lambda self: self._values["dexEntries"], notify=dataChanged
    )
    dexBrowseEntries = Property(
        "QVariantList", lambda self: self._values["dexBrowseEntries"], notify=dataChanged
    )
    dexFilters = Property(
        "QVariantList", lambda self: self._values["dexFilters"], notify=dataChanged
    )
    dexSummary = Property(
        str, lambda self: self._values["dexSummary"], notify=dataChanged
    )
    dexPage = Property(int, lambda self: self._values["dexPage"], notify=dataChanged)
    dexPageCount = Property(
        int, lambda self: self._values["dexPageCount"], notify=dataChanged
    )
    dexFilter = Property(
        str, lambda self: self._values["dexFilter"], notify=dataChanged
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
    rareCandyXp = Property(
        str, lambda self: self._values["rareCandyXp"], notify=dataChanged
    )
    mintCount = Property(
        int, lambda self: self._values["mintCount"], notify=dataChanged
    )
    shinyCharmActive = Property(
        bool, lambda self: self._values["shinyCharmActive"], notify=dataChanged
    )
    hasActiveCompanion = Property(
        bool, lambda self: self._values["hasActiveCompanion"], notify=dataChanged
    )
    representativeFollowsCurrent = Property(
        bool, lambda self: self._values["representativeFollowsCurrent"], notify=dataChanged
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
    limitTimeMode = Property(
        str, lambda self: self._values["limitTimeMode"], notify=dataChanged
    )
    forecastEnabled = Property(
        bool, lambda self: self._values["forecastEnabled"], notify=dataChanged
    )
    limitNotifications = Property(
        bool, lambda self: self._values["limitNotifications"], notify=dataChanged
    )
    limitResetNotifications = Property(
        bool, lambda self: self._values["limitResetNotifications"], notify=dataChanged
    )
    bankedResetNotifications = Property(
        bool, lambda self: self._values["bankedResetNotifications"], notify=dataChanged
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
    windowMaximized = Property(
        bool, lambda self: self._values["windowMaximized"], notify=dataChanged
    )
    language = Property(str, lambda self: self._values["language"], notify=dataChanged)
    strings = Property(
        "QVariantMap", lambda self: self._values["strings"], notify=dataChanged
    )
    languageOptions = Property(
        "QVariantList", lambda self: self._values["languageOptions"], notify=dataChanged
    )
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

    def _language(self) -> str:
        return normalize_language(self._values.get("language", self.state.language))

    def _tr(self, key: str, **values: Any) -> str:
        return translated_text(self._language(), key, **values)

    def _event_text(
        self,
        label: str,
        value: Any,
        time_mode: str,
        now: Any = None,
        *,
        approximate: bool = False,
    ) -> str:
        if normalize_limit_time_mode(time_mode) == "datetime":
            return f"{label} {format_limit_datetime(value)}"
        connector = "in" if self._language() == "en" else "en"
        countdown = format_limit_countdown(value, now, approximate=approximate)
        return f"{label} {connector} {countdown}"

    def _render_state(self) -> None:
        state = self.state
        language = normalize_language(state.language)
        self._values["language"] = language
        self._values["strings"] = ui_strings(language)
        progress = companion_progress_percent(state)
        level_prefix = "Lv." if language == "en" else "Nv."
        if state.mon is None:
            name = self._tr("pokemon_egg")
            tier = f" · {state.egg_tier.title()}+" if state.egg_tier else ""
            subtitle = self._tr("waiting_to_hatch", tier=tier)
            evolution_text = self._tr("hatch_hint")
            value = state.egg_usage
            target = EGG_HATCH_THRESHOLD
            sprite_path = self.api.egg_sprite_path()
        else:
            mon = state.mon
            name = self.api.localized_name(mon.current_id, language)
            shiny = "✨ " if mon.is_shiny else ""
            rarity = self._tr(mon.rarity)
            subtitle = (
                f"{shiny}{rarity} · {mon.nature} {self._tr('nature')} · "
                f"{self._tr('stage')} {mon.stage_index + 1}/{len(mon.path_ids)}"
            )
            value = mon.used_at_stage
            target = mon.stage_threshold
            if mon.stage_index + 1 < len(mon.path_ids):
                next_name = self.api.localized_name(
                    mon.path_ids[mon.stage_index + 1], language
                )
                evolution_text = self._tr("current_next", current=name, next=next_name)
            else:
                evolution_text = self._tr("current_final", current=name)
            sprite_path = self.api.sprite_path(mon.current_id, shiny=mon.is_shiny)

        self._values.update(
            companionName=name,
            growthBoost=bool(state.mon and state.mon.has_growth_boost),
            companionSubtitle=subtitle,
            companionProgress=progress,
            companionProgressText=f"{compact_tokens(value)} / {compact_tokens(target)}",
            companionLevelText=f"{level_prefix} {progress}",
            companionEvolutionText=evolution_text,
            spriteUrl=_file_url(sprite_path),
            wallet=compact_tokens(state.wallet),
            rareCandyCount=int(state.inventory.get("rare_candy", 0)),
            mintCount=int(state.inventory.get("mint", 0)),
            shinyCharmActive=state.shiny_charm_active,
            hasActiveCompanion=state.mon is not None,
            representativeFollowsCurrent=state.representative_species_id is None,
            language=language,
            strings=ui_strings(language),
        )
        self._values["collection"] = self._collection_rows()
        self._refresh_dex_rows()
        self._values["catches"] = self._catch_rows()
        self._values["shopItems"] = self._shop_rows()

    def _collection_rows(self) -> list[dict[str, Any]]:
        selected_id = self.state.representative_species_id
        selected_shiny = self.state.representative_is_shiny
        rows: list[dict[str, Any]] = [
            {
                "speciesId": 0,
                "name": self._tr("follow_companion"),
                "display": self._tr("follow_companion"),
                "number": "AUTO",
                "shiny": False,
                "sprite": self._values.get("spriteUrl", ""),
                "selected": selected_id is None,
            }
        ]
        for subject in owned_representative_options(self.state):
            species_id = int(subject.species_id or 0)
            name = self.api.localized_name(species_id, self._language())
            number = f"#{species_id:03d}"
            shiny = bool(subject.is_shiny)
            rows.append(
                {
                    "speciesId": species_id,
                    "name": name,
                    "display": f"{'✨ ' if shiny else ''}{number} {name}",
                    "number": number,
                    "shiny": shiny,
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

    def _is_current_catch(self, catch: Any) -> bool:
        mon = self.state.mon
        return bool(
            mon
            and catch.base_id == mon.base_id
            and catch.path_ids == mon.path_ids
            and catch.nature == mon.nature
            and catch.is_shiny == mon.is_shiny
        )

    def _all_dex_rows(self) -> list[dict[str, Any]]:
        species: dict[int, dict[str, Any]] = {}
        for catch in self.state.catches:
            path_ids = catch.path_ids or [catch.species_id]
            obtained_count = len(path_ids)
            if self._is_current_catch(catch) and self.state.mon is not None:
                obtained_count = min(len(path_ids), self.state.mon.stage_index + 1)
            for species_id in path_ids[:obtained_count]:
                row = species.setdefault(
                    int(species_id),
                    {
                        "speciesId": int(species_id),
                        "rarity": catch.rarity,
                        "hasShiny": False,
                    },
                )
                row["hasShiny"] = bool(row["hasShiny"] or catch.is_shiny)

        selected_id = self.state.representative_species_id
        selected_shiny = bool(self.state.representative_is_shiny)
        follows_current = selected_id is None
        current_id = self.state.mon.current_id if self.state.mon is not None else None
        current_shiny = bool(self.state.mon.is_shiny) if self.state.mon is not None else False

        rows: list[dict[str, Any]] = []
        for species_id, row in sorted(species.items()):
            has_shiny = bool(row["hasShiny"])
            default_shiny = has_shiny
            if selected_id == species_id:
                default_shiny = selected_shiny
            elif follows_current and current_id == species_id:
                default_shiny = current_shiny
            show_shiny = self._dex_shiny_by_species.get(species_id, default_shiny)
            if not has_shiny:
                show_shiny = False
            is_representative = (
                selected_id == species_id and selected_shiny == show_shiny
            ) or (
                follows_current
                and current_id == species_id
                and current_shiny == show_shiny
            )
            rows.append(
                {
                    **row,
                    "name": self.api.localized_name(species_id, self._language()),
                    "number": f"#{species_id:03d}",
                    "showShiny": show_shiny,
                    "representative": is_representative,
                    "followingCurrent": is_representative and follows_current,
                    "sprite": _file_url(
                        self.api.sprite_path(
                            species_id, shiny=show_shiny, animated=False
                        )
                    ),
                    "animatedSprite": _file_url(
                        self.api.sprite_path(
                            species_id, shiny=show_shiny, animated=True
                        )
                    ),
                }
            )
        return rows

    def _refresh_dex_rows(self) -> None:
        all_rows = self._all_dex_rows()
        rarity_order = ("common", "uncommon", "rare", "legendary")
        counts = {
            rarity: sum(row["rarity"] == rarity for row in all_rows)
            for rarity in rarity_order
        }
        filters = [{"key": "all", "label": self._tr("all"), "count": len(all_rows)}]
        filters.extend(
            {"key": rarity, "label": self._tr(rarity), "count": counts[rarity]}
            for rarity in rarity_order
            if counts[rarity]
        )
        valid_filters = {item["key"] for item in filters}
        if self._dex_filter not in valid_filters:
            self._dex_filter = "all"
        filtered = (
            all_rows
            if self._dex_filter == "all"
            else [row for row in all_rows if row["rarity"] == self._dex_filter]
        )
        page_size = 24
        page_count = max(1, (len(filtered) + page_size - 1) // page_size)
        self._dex_page = max(0, min(self._dex_page, page_count - 1))
        start = self._dex_page * page_size
        rarity_summary = " · ".join(
            f"{self._tr(rarity)} {counts[rarity]}"
            for rarity in rarity_order
            if counts[rarity]
        )
        summary = self._tr("species_count", count=len(all_rows))
        if rarity_summary:
            summary += f" · {rarity_summary}"
        self._values.update(
            dexEntries=filtered[start : start + page_size],
            dexBrowseEntries=filtered,
            dexFilters=filters,
            dexSummary=summary,
            dexPage=self._dex_page + 1,
            dexPageCount=page_count,
            dexFilter=self._dex_filter,
        )

    def _catch_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for catch in reversed(self.state.catches):
            path_ids = catch.path_ids or [catch.species_id]
            is_current = self._is_current_catch(catch)
            owned_index = len(path_ids) - 1
            if is_current and self.state.mon is not None:
                owned_index = min(len(path_ids) - 1, self.state.mon.stage_index)
            display_id = path_ids[owned_index]
            stages = []
            for index, species_id in enumerate(path_ids):
                owned = index <= owned_index
                current = index == owned_index
                stages.append(
                    {
                        "name": (
                            self.api.localized_name(species_id, self._language())
                            if owned
                            else "???"
                        ),
                        "status": (
                            self._tr("catch_owned")
                            if index == owned_index
                            else self._tr("catch_previous" if owned else "catch_future")
                        ),
                        "owned": owned,
                        "current": current,
                        "sprite": _file_url(
                            self.api.sprite_path(
                                species_id,
                                shiny=bool(catch.is_shiny and owned),
                                animated=False,
                            )
                        ),
                    }
                )
            rows.append(
                {
                    "name": self.api.localized_name(display_id, self._language()),
                    "number": f"#{display_id:03d}",
                    "meta": f"{self._tr(catch.rarity)} · {catch.nature} · {catch.caught_at[:10]}",
                    "shiny": bool(catch.is_shiny),
                    "current": is_current,
                    "description": (
                        self._tr("fully_evolved")
                        if owned_index == len(path_ids) - 1
                        else self._tr(
                            "have_only_stage",
                            stage=owned_index + 1,
                            total=len(path_ids),
                        )
                    ),
                    "stages": stages,
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
            ("item", "rare_candy", "rare_candy", "rare_candy_description", "🍬", RARE_CANDY_PRICE),
            ("item", "mint", "mint", "mint_description", "🌿", MINT_PRICE),
            ("item", "shiny_charm", "shiny_charm", "shiny_charm_description", "✨", SHINY_CHARM_PRICE),
            ("egg", "normal", "normal_egg", "normal_egg_description", "🥚", egg_price(None)),
            ("egg", "uncommon", "uncommon_egg", "uncommon_egg_description", "🔵", egg_price("uncommon")),
            ("egg", "rare", "rare_egg", "rare_egg_description", "🟣", egg_price("rare")),
        )
        rows = []
        for kind, key, title_key, subtitle_key, icon, price in definitions:
            owned = key == "shiny_charm" and inventory.get("shiny_charm", 0) > 0
            rows.append(
                {
                    "kind": kind,
                    "key": key,
                    "title": self._tr(title_key),
                    "subtitle": self._tr(subtitle_key),
                    "icon": icon,
                    "eggTier": key if kind == "egg" else "",
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

    @staticmethod
    def _adjacent_month(key: str, step: int) -> str:
        year, month = map(int, key.split("-"))
        index = year * 12 + month - 1 + step
        return f"{index // 12:04d}-{index % 12 + 1:02d}"

    def _rebuild_month_trend(self) -> None:
        if self._snapshot is None or not self._selected_month:
            return
        language = self._values["language"]
        year, month = map(int, self._selected_month.split("-"))
        is_current = self._selected_month == self._current_month
        if is_current:
            tokens = self._snapshot.month_daily
            costs = self._snapshot.month_daily_cost
            today_day = self._snapshot.scanned_at.astimezone().day if self._snapshot.scanned_at else len(tokens)
        else:
            tokens, costs = (self._month_history or {}).get(
                self._selected_month, ([0] * monthrange(year, month)[1], [])
            )
            today_day = -1
        days = len(tokens)
        peak = max(tokens, default=0)
        rows = []
        for index, value in enumerate(tokens):
            day = index + 1
            date_label = QLocale({"en": "en_US", "es": "es_ES", "gl": "gl_ES"}.get(language, "en_US")).toString(
                QDate(year, month, day), "ddd d MMM"
            )
            caption = self._tr("trend_day", day=date_label, tokens=compact_tokens(value))
            if index < len(costs) and costs[index] > 0:
                caption += f" · ${costs[index]:,.2f}"
            rows.append({
                "day": day, "tokens": value,
                "barHeight": max(1.5, round(value * 34 / peak)) if peak else 1.5,
                "label": str(day) if day == 1 or day == today_day or (
                    not is_current and day == days
                ) or (
                    day % 7 == 0 and abs(day - (today_day if is_current else days)) > 3
                ) else "",
                "weekend": datetime(year, month, day).weekday() >= 5,
                "today": day == today_day,
                "empty": value == 0,
                "caption": caption,
            })
        locale = QLocale({"en": "en_US", "es": "es_ES", "gl": "gl_ES"}.get(language, "en_US"))
        month_label = locale.monthName(month, QLocale.FormatType.LongFormat)
        self._values["monthTrend"] = rows
        self._values["trendMonthLabel"] = f"{month_label.capitalize()} {year}"
        self._values["trendMonthTokens"] = compact_tokens(sum(tokens))
        self._values["trendMonthCost"] = f"${sum(costs):,.2f}"
        self._values["trendCaption"] = rows[-1]["caption"] if rows else self._tr("trend_no_data")
        self._values["trendPeak"] = self._tr("trend_peak", tokens=compact_tokens(peak))
        earliest = min(self._month_history) if self._month_history else self._current_month
        self._values["trendCanPrevious"] = (
            not self._values["trendLoading"] and (
                self._month_history is None or self._selected_month > earliest
            )
        )
        self._values["trendCanNext"] = self._selected_month < self._current_month

    @Slot(int)
    def moveMonth(self, step: int) -> None:
        if step not in (-1, 1) or not self._selected_month:
            return
        target = self._adjacent_month(self._selected_month, step)
        if target > self._current_month:
            return
        if step < 0 and self._month_history is None:
            self._pending_previous = True
            self._values["trendLoading"] = True
            self._rebuild_month_trend()
            self.dataChanged.emit()
            self.monthHistoryRequested.emit()
            return
        if step < 0 and (not self._month_history or target < min(self._month_history)):
            return
        self._selected_month = target
        self._rebuild_month_trend()
        self.dataChanged.emit()

    def set_month_history(self, history: dict[str, tuple[list[int], list[float]]]) -> None:
        self._month_history = history
        self._values["trendLoading"] = False
        if self._pending_previous and history:
            target = self._adjacent_month(self._selected_month, -1)
            if target >= min(history):
                self._selected_month = target
        self._pending_previous = False
        self._rebuild_month_trend()
        self.dataChanged.emit()

    def render(self, result: Any) -> None:
        self.state = result.state
        language = normalize_language(result.state.language)
        self._values["language"] = language
        self._values["strings"] = ui_strings(language)
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
                    "error": key in result.scan_errors,
                }
            )
        self._snapshot = snapshot
        local_now = (snapshot.scanned_at or datetime.now().astimezone()).astimezone()
        current_month = f"{local_now.year:04d}-{local_now.month:02d}"
        if current_month != self._current_month:
            self._current_month = current_month
            self._selected_month = current_month
            self._month_history = None
        self._rebuild_month_trend()

        display_mode = normalize_limit_display_mode(
            self.settings.value(LIMIT_DISPLAY_MODE_KEY, DEFAULT_LIMIT_DISPLAY_MODE)
        )
        time_mode = normalize_limit_time_mode(
            self.settings.value(LIMIT_TIME_MODE_KEY, DEFAULT_LIMIT_TIME_MODE)
        )
        forecast_enabled = settings_bool(
            self.settings.value(FORECAST_ENABLED_KEY, DEFAULT_FORECAST_ENABLED),
            DEFAULT_FORECAST_ENABLED,
        )
        warning = normalize_warning_threshold(
            self.settings.value(WARNING_THRESHOLD_KEY, DEFAULT_WARNING_THRESHOLD)
        )
        critical = normalize_critical_threshold(
            self.settings.value(CRITICAL_THRESHOLD_KEY, DEFAULT_CRITICAL_THRESHOLD)
        )
        now = snapshot.scanned_at
        limits = []
        reason_keys = {
            "reset time unavailable": "forecast_reset_unknown",
            "window duration unavailable": "forecast_duration_unknown",
            "window already reset": "forecast_already_reset",
            "not enough data yet": "forecast_not_enough",
            "collecting usage data": "forecast_collecting",
        }
        for key, provider_limits in result.limits.items():
            provider_name = PROVIDER_LABELS.get(key, key.title())
            ordered_windows = ordered_limit_windows(provider_limits)
            for window in ordered_windows:
                reset = (
                    self._event_text(self._tr("resets"), window.resets_at, time_mode, now)
                    if window.resets_at
                    else self._tr("reset_unknown")
                )
                used = max(0.0, min(100.0, float(window.used_percent)))
                urgency = (
                    "critical"
                    if used >= critical
                    else ("warning" if used >= warning else "neutral")
                )
                forecast_text = ""
                if forecast_enabled:
                    forecast = limit_forecast(window, now)
                    if forecast is not None:
                        if forecast.before_reset:
                            when = (
                                format_limit_datetime(forecast.depletion_at)
                                if time_mode == "datetime"
                                else format_limit_countdown(
                                    forecast.depletion_at, now, approximate=True
                                )
                            )
                            forecast_text = self._tr("forecast_full", when=when)
                        else:
                            forecast_text = self._tr("forecast_safe")
                    else:
                        reason = limit_forecast_unavailable_reason(window, now)
                        if reason:
                            forecast_text = self._tr(reason_keys.get(reason, reason))
                limits.append(
                    {
                        "kind": "window",
                        "provider": provider_name,
                        "plan": provider_limits.plan or "",
                        "label": (
                            self._tr("limit_5_hour")
                            if window.label.lower() == "5-hour"
                            else (
                                self._tr("limit_weekly")
                                if window.label.lower() == "weekly"
                                else window.label
                            )
                        ),
                        "percent": round(limit_display_percent(used, display_mode)),
                        "percentText": (
                            f"{round(limit_display_percent(used, display_mode))}% "
                            f"{self._tr('remaining' if display_mode == 'remaining' else 'used').lower()}"
                        ),
                        "reset": reset,
                        "forecast": forecast_text,
                        "urgency": urgency,
                    }
                )

            count = int(provider_limits.reset_credits_available)
            if count > 0:
                expiry = limit_reset_expiry(provider_limits)
                summary = self._tr(
                    "reset_available" if count == 1 else "resets_available",
                    count=count,
                )
                if expiry is not None:
                    expiry_label = self._tr("expires" if count == 1 else "first_expires")
                    summary += " · " + self._event_text(
                        expiry_label, expiry, time_mode, now
                    )
                else:
                    summary += " · " + self._tr("expiry_unknown")
                limits.append(
                    {
                        "kind": "credit",
                        "provider": provider_name,
                        "plan": provider_limits.plan or "",
                        "label": summary,
                        "percent": 0,
                        "percentText": "",
                        "reset": "",
                        "forecast": "",
                        "urgency": limit_reset_urgency(provider_limits, now),
                    }
                )

        status_key = "updated_warnings" if result.scan_errors else "updated"
        stamp = (
            snapshot.scanned_at.astimezone().strftime("%H:%M")
            if snapshot.scanned_at
            else ""
        )
        self._values.update(
            loading=False,
            refreshEnabled=True,
            statusText=self._tr(status_key) + (f" · {stamp}" if stamp else ""),
            todayTokens=compact_tokens(snapshot.today_tokens),
            todayCost=f"${snapshot.today_cost:,.2f}",
            weekTokens=compact_tokens(snapshot.week_tokens),
            weekCost=f"${snapshot.week_cost:,.2f}",
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
        known = {
            "Data is stale · refreshing…": "status_stale",
            "Updating…": "status_updating",
            "Update failed · retry scheduled": "status_failed",
        }
        self._set("statusText", self._tr(known[text]) if text in known else text)

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

    @Slot()
    def minimizeWindow(self) -> None:
        self.windowMinimizeRequested.emit()

    @Slot()
    def toggleMaximizeWindow(self) -> None:
        self.windowToggleMaximizeRequested.emit()

    @Slot()
    def closeWindow(self) -> None:
        self.windowCloseRequested.emit()

    @Slot()
    def startWindowMove(self) -> None:
        self.windowMoveRequested.emit()

    @Slot(int)
    def startWindowResize(self, edges: int) -> None:
        self.windowResizeRequested.emit(int(edges))

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
            "limitTimeMode": LIMIT_TIME_MODE_KEY,
            "forecastEnabled": FORECAST_ENABLED_KEY,
            "limitNotifications": LIMIT_NOTIFICATIONS_KEY,
            "limitResetNotifications": LIMIT_RESET_NOTIFICATIONS_KEY,
            "bankedResetNotifications": BANKED_RESET_NOTIFICATIONS_KEY,
            "companionNotifications": COMPANION_NOTIFICATIONS_KEY,
            "warningThreshold": WARNING_THRESHOLD_KEY,
            "criticalThreshold": CRITICAL_THRESHOLD_KEY,
            "theme": "theme",
        }
        setting_key = known.get(key)
        if setting_key is None:
            return
        if key == "warningThreshold":
            value = normalize_warning_threshold(value)
            critical = normalize_critical_threshold(
                self._values["criticalThreshold"]
            )
            if value >= critical:
                critical = normalize_critical_threshold(value + 5)
                self.settings.setValue(CRITICAL_THRESHOLD_KEY, critical)
                self._values["criticalThreshold"] = critical
        elif key == "criticalThreshold":
            value = normalize_critical_threshold(value)
            warning = normalize_warning_threshold(self._values["warningThreshold"])
            if value <= warning:
                warning = normalize_warning_threshold(value - 5)
                self.settings.setValue(WARNING_THRESHOLD_KEY, warning)
                self._values["warningThreshold"] = warning
        elif key == "limitDisplayMode":
            value = normalize_limit_display_mode(value)
        elif key == "limitTimeMode":
            value = normalize_limit_time_mode(value)
        self.settings.setValue(setting_key, value)
        self.settings.sync()
        self._values[key] = value
        if key == "theme":
            self._refresh_dark_mode()
        self.dataChanged.emit()
        self.preferencesChanged.emit()

    @Slot(str)
    def setDexFilter(self, value: str) -> None:
        self._dex_filter = str(value)
        self._dex_page = 0
        self._refresh_dex_rows()
        self.dataChanged.emit()

    @Slot(int)
    def moveDexPage(self, delta: int) -> None:
        self._dex_page += int(delta)
        self._refresh_dex_rows()
        self.dataChanged.emit()

    @Slot(int)
    def toggleDexVariant(self, species_id: int) -> None:
        species_id = int(species_id)
        self._dex_shiny_by_species[species_id] = not self._dex_shiny_by_species.get(
            species_id, True
        )
        self._refresh_dex_rows()
        self.dataChanged.emit()

    @Slot(int)
    def setRefreshMinutes(self, minutes: int) -> None:
        minutes = max(1, int(minutes))
        self.settings.setValue("refresh_minutes", minutes)
        self.settings.sync()
        self._set("refreshMinutes", minutes)
        self.refreshRequested.emit()

    @Slot(str)
    def setLanguage(self, language: str) -> None:
        normalized = normalize_language(language)
        if normalized != language:
            return
        self._values["language"] = normalized
        self._values["strings"] = ui_strings(normalized)
        self.dataChanged.emit()
        self.languageChanged.emit(normalized)

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

    @Slot(int, bool)
    def chooseDexRepresentative(self, species_id: int, shiny: bool) -> None:
        self.representativeChanged.emit((int(species_id), bool(shiny)))

    @Slot()
    def followCurrentRepresentative(self) -> None:
        self.representativeChanged.emit(None)

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
            self.show_feedback(self._tr("startup_error"))
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
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(520, 640)
        self.resize(560, 740)
        self.settings = settings
        self._geometry_ready = False
        self._last_normal_rect = QRect(self.geometry())
        self._geometry_timer = QTimer(self)
        self._geometry_timer.setSingleShot(True)
        self._geometry_timer.setInterval(250)
        self._geometry_timer.timeout.connect(self.save_window_geometry)

        self._month_history_executor: ThreadPoolExecutor | None = None
        self._month_history_future: Future | None = None
        self._month_history_timer = QTimer(self)
        self._month_history_timer.setInterval(100)
        self._month_history_timer.timeout.connect(self._poll_month_history)
        self.view_model = QmlViewModel(state, settings, api)
        self.view_model.refreshRequested.connect(self.refresh_requested)
        self.view_model.monthHistoryRequested.connect(self._load_month_history)
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
        self.view_model.windowMinimizeRequested.connect(self.showMinimized)
        self.view_model.windowToggleMaximizeRequested.connect(self._toggle_maximized)
        self.view_model.windowCloseRequested.connect(self.close)
        self.view_model.windowMoveRequested.connect(self._start_system_move)
        self.view_model.windowResizeRequested.connect(self._start_system_resize)

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
        self.windows_snap_enabled = _enable_windows_snap(int(self.winId()))
        self._restore_window_geometry()
        self._geometry_ready = True

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

    def _load_month_history(self) -> None:
        if self._month_history_future is not None:
            return
        self._month_history_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="poketokenbar-history")
        self._month_history_future = self._month_history_executor.submit(scan_month_history)
        self._month_history_timer.start()

    def _poll_month_history(self) -> None:
        future = self._month_history_future
        if future is None or not future.done():
            return
        self._month_history_timer.stop()
        try:
            history = future.result()
        except Exception:  # noqa: BLE001  # restore navigation if a log is unreadable
            history = {}
        self._month_history_future = None
        self.view_model.set_month_history(history)
        if self._month_history_executor is not None:
            self._month_history_executor.shutdown(wait=False)
            self._month_history_executor = None

    def _restore_window_geometry(self) -> None:
        rect = self.settings.value("main_window_rect")
        if isinstance(rect, QRect) and rect.isValid():
            self._last_normal_rect = QRect(rect)
            self.setGeometry(rect)
            maximized = self.settings.value("main_window_maximized", False)
            if settings_bool(maximized, False):
                self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)
        else:
            saved = self.settings.value("main_window_geometry")
            if saved and self.restoreGeometry(saved):
                self._last_normal_rect = QRect(self.normalGeometry())
        visible = any(
            screen.availableGeometry().intersects(self.normalGeometry())
            for screen in QGuiApplication.screens()
        )
        if not visible:
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                area = screen.availableGeometry()
                normal = self.normalGeometry()
                self.setGeometry(
                    area.x() + max(0, (area.width() - normal.width()) // 2),
                    area.y() + max(0, (area.height() - normal.height()) // 2),
                    normal.width(),
                    normal.height(),
                )
                self._last_normal_rect = QRect(self.geometry())

    def save_window_geometry(self) -> None:
        if not self._geometry_ready:
            return
        normal = self._last_normal_rect if self.isMaximized() else self.geometry()
        if normal.isValid():
            self.settings.setValue("main_window_rect", normal)
        self.settings.setValue("main_window_maximized", self.isMaximized())
        self.settings.setValue("main_window_geometry", self.saveGeometry())
        self.settings.sync()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if self._geometry_ready and self.isVisible():
            if not self.isMaximized() and not self.isMinimized():
                self._last_normal_rect = QRect(self.geometry())
            self._geometry_timer.start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._geometry_ready and self.isVisible():
            if not self.isMaximized() and not self.isMinimized():
                self._last_normal_rect = QRect(self.geometry())
            self._geometry_timer.start()

    def _sync_window_state(self) -> None:
        self.view_model._set("windowMaximized", self.isMaximized())

    def _toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self._last_normal_rect = QRect(self.geometry())
            self.showMaximized()
        QTimer.singleShot(0, self._sync_window_state)

    def _start_system_move(self) -> None:
        handle = self.windowHandle()
        if handle is not None:
            handle.startSystemMove()

    def _start_system_resize(self, edges: int) -> None:
        handle = self.windowHandle()
        if handle is not None and not self.isMaximized():
            handle.startSystemResize(Qt.Edge(edges))

    def changeEvent(self, event) -> None:
        was_maximized = (
            event.type() == QEvent.Type.WindowStateChange
            and bool(event.oldState() & Qt.WindowState.WindowMaximized)
        )
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            if was_maximized and not self.isMaximized() and not self.isMinimized():
                normal = QRect(self._last_normal_rect)
                QTimer.singleShot(0, lambda: self.setGeometry(normal))
            QTimer.singleShot(0, self._sync_window_state)

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
        self._geometry_timer.stop()
        self.save_window_geometry()
        event.ignore()
        self.hide()
