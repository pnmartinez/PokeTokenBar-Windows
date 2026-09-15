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

- Pokédex cards use most of their image area. Selecting a card opens that companion as a large animated sprite; Previous and Next browse the full filtered collection across page boundaries, and Back restores the matching grid page.
- Catch history shows one large sprite per evolution stage, arrows between stages, a sentence stating whether the line is complete, clear ownership labels, and the active Raising badge aligned to the right. The header does not duplicate the current stage sprite.
- The desktop representative setting belongs to the Desktop pet group and explains that it controls the tray icon and floating desktop pet.
- Representative choices include the Pokédex number and name. The Pokédex marks the current desktop representative and lets a collected variant become the representative from its animated detail view. Following the active companion remains an explicit option there and in Settings.
- Capture summaries describe completion or stage without repeating the Pokémon name already shown in the card.
- Bag icons and text share the same left edge at narrow widths. All egg tiers use one egg silhouette with escalating colors and rarity cues rather than unrelated circle symbols.
- A Windows login launch stays in the tray; the floating pet follows its saved preference and the main window opens only on a manual action. An existing login command is upgraded only when it points to the same executable.
- Available reset credits show no warning icon while neutral. A vector warning triangle appears only when expiry is warning (amber) or critical (red), using the same urgency rules as the row color in both themes.
- The single language setting controls the interface, Pokémon names, tray tooltip and context menu, desktop pet tooltip and context menu, and limit notifications.
- Settings provide a short tooltip and accessible description for every non-obvious control. Reset format calls the countdown option Time remaining rather than Time.
- Dark mode controls and secondary text retain readable contrast; combo boxes and numeric selectors use the same panel palette as the rest of the interface.
- The main window uses one integrated, theme-aware header with the app identity, status, native-equivalent minimize/maximize/close actions, drag, double-click maximize, edge resizing, and Windows snapping when dragged to a screen edge. The maximize icon must repaint as a restore icon while maximized, and title-bar dragging must delegate to Windows even from the maximized state so restoring and moving remain available. It must not expose a separate light system title bar in dark mode.
- Page descriptions live in the navigation tooltips and accessible descriptions instead of consuming a row inside every page.
- Home keeps Refresh inside the companion card. The animated companion sits in a large square frame with equal inner margins, and all progress content stays inside the card.
- Collection presents Pokédex and Captures as primary tabs without an enclosing panel. Pokédex filters and page position share a secondary row because pagination applies to that filtered view.
- Bag and Shop share the same slim wallet strip in the same position so the balance feels persistent while switching between them.
- Body copy must remain readable at the minimum window size. Ordinary labels are at least 12 px where the layout permits it; captions and metadata are at least 10 px.

## Regression coverage

Tests must cover the minimum window size, top navigation, all-language level prefixes, absolute companion progress, forecasts for both short and weekly timed limits, reset-credit summaries, numbered representative choices, evolution arrows, provider overflow geometry, animated companion rendering, zero-local-usage limit visibility, selected notification display mode, translated native menus, Pokédex detail navigation, capture status copy, settings grouping, tooltip help, and dark-mode control contrast.

