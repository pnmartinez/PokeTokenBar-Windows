# PokeTokenBar UI behavior contract

This document records user-visible behavior that must survive visual redesigns and UI framework migrations. The tag `bruno/ultima-fea-pero-estable-2026-09-01` is the reference implementation when a detail is unclear.

## Compatibility rules

- A UI rewrite must preserve every value already supplied by the application model. Moving a screen to another toolkit is not permission to drop working behavior.
- The main window must remain usable at 520 by 640 pixels. Home must not use page-level scrolling; only lists that can genuinely overflow may scroll.
- Navigation stays horizontal at the top so every destination keeps a visible text label at the minimum width.
- English is the default interface language. English, Spanish, and Galician are supported. The selected interface language also controls Pokémon names; when the API has no name in that language, the official English name is used.

## Home

- The page title is `PokeTokenBar`.
- Companion progress shows absolute token progress (`current / target`) and a separate level label. The level prefix is `Lv.` in English and `Nv.` in Spanish and Galician.
- Provider usage appears above official limits. Its height follows the visible provider count up to a maximum; official limits receive the remaining space.
- Every timed official limit can show a depletion forecast. A missing forecast must have an explanation when the calculation lacks enough data.
- Codex reset credits show the available count and the earliest expiry. A UI change must not hide this data.

## Collection and settings

- Catch history shows arrows between evolution stages.
- The desktop representative setting explains that it controls the tray icon and floating desktop pet.
- Representative choices include the Pokédex number and name. Following the active companion remains an explicit option.
- The single language setting controls both the interface and Pokémon names.

## Regression coverage

Tests must cover the minimum window size, top navigation, all-language level prefixes, absolute companion progress, forecasts for both short and weekly timed limits, reset-credit summaries, numbered representative choices, and evolution arrows.

