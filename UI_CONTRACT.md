# PokeTokenBar UI behavior contract

This document records user-visible behavior that must survive visual redesigns and UI framework migrations. The tag `bruno/ultima-fea-pero-estable-2026-09-01` is the reference implementation when a detail is unclear.

## Compatibility rules

- A UI rewrite must preserve every value already supplied by the application model. Moving a screen to another toolkit is not permission to drop working behavior.
- The main window must remain usable at 520 by 640 pixels. Home must not use page-level scrolling; only lists that can genuinely overflow may scroll.
- Navigation stays horizontal at the top so every destination keeps an intuitive icon and a visible text label at the minimum width. Page bodies do not repeat the active tab name as a large heading.
- English is the default interface language. English, Spanish, and Galician are supported. The selected interface language also controls Pokémon names; when the API has no name in that language, the official English name is used.

## Home

- The application header is PokeTokenBar; Home does not repeat it as a page heading.
- Companion progress shows absolute token progress (`current / target`) and a separate level label. The level prefix is `Lv.` in English and `Nv.` in Spanish and Galician.
- Provider usage appears above official limits. Its height follows the visible provider count up to a maximum; it must not scroll while all rows fit, and it must stop at the final row when scrolling is necessary. Official limits receive the remaining space.
- Every timed official limit can show a depletion forecast. A missing forecast must have an explanation when the calculation lacks enough data.
- Codex reset credits show the available count and the earliest expiry. A UI change must not hide this data.
- Luna Reserve appears only when the Codex limits response reports that window.
- Compact tray and pet surfaces show the most relevant official limit even when local usage for that provider is zero today.
- Warning thresholds are based on used percentage, while notification text follows the selected Used or Remaining display mode.

## Collection and settings

- Catch history shows one large sprite per evolution stage, arrows between stages, clear ownership labels, and the active Raising badge aligned to the right. The header does not duplicate the current stage sprite.
- The desktop representative setting explains that it controls the tray icon and floating desktop pet.
- Representative choices include the Pokédex number and name. Following the active companion remains an explicit option.
- The single language setting controls the interface, Pokémon names, tray tooltip and context menu, desktop pet tooltip and context menu, and limit notifications.

## Regression coverage

Tests must cover the minimum window size, top navigation, all-language level prefixes, absolute companion progress, forecasts for both short and weekly timed limits, reset-credit summaries, numbered representative choices, evolution arrows, provider overflow geometry, animated companion rendering, zero-local-usage limit visibility, selected notification display mode, and translated native menus.

