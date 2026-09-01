# Upstream tracking

This Windows port is based on `chattymin/PokeTokenBar` and was initially ported from:

- upstream branch: `main`
- upstream commit: `bd0bba9cdf9a46559adc9c5cd099f42caca1aeb6`
- upstream commit date: 2026-08-20
- upstream license: MIT

The implementation reuses the portable Python core developed for the Linux port, while preserving the upstream game-balance constants and local usage-file semantics. Platform integration is Windows-native: Qt/PySide6 notification-area UI, Roaming/Local AppData storage, HKCU Run startup, and Windows provider paths.

## Latest behavior comparison

The Luna Reserve/UI refresh work was compared on 2026-08-30 against upstream `main` at `1ff36e1e8372d85131d67ac5df61248995743ac5` (after tag `v2.5.2`). Relevant parity decisions carried over here are: render every visible Codex time bucket, classify candy rewards by the bucket duration, identify rewards with stable bucket keys rather than reset timestamps, refresh official limits on every automatic poll, and trigger a full refresh after using Rare Candy.

## Limit display and startup review

The Windows limit/startup work was checked again on 2026-08-31 against upstream
main at 37763d3c367068492c18f6e51b45977c2d27f6d5 (after tag v2.5.3):

- Upstream's limitDisplayMode is an explicit segmented Used/Remaining picker and defaults to used. Windows now mirrors that segmented control and migrates the former limits_show_remaining checkbox.
- Upstream changes only the displayed number: its gauges, colors, notifications, warning/critical thresholds, rewards, and alert edge detection keep utilization semantics. Windows intentionally lets the Home gauge fill with the selected Used/Remaining value because the gauge is part of that display preference; risk colors, alert copy, thresholds, rewards, and edge detection still always use utilization. Compact tray/hover text uses "left" in Remaining mode.
- Upstream lets the menu and pet hover observe the same display mode but not the same visibility preferences. Windows intentionally goes further: the tray's token, cost, and limit checkboxes control both compact surfaces so disabling a field never leaves it visible on the pet.
- Upstream's compact Codex calculation takes the maximum primary percentage across every bucket. Windows instead keeps the regular Codex bucket on compact surfaces while it is available and switches to Luna Reserve only after regular usage is exhausted or Codex reports a reached limit, matching [OpenAI's Luna Reserve description](https://help.openai.com/en/articles/20001499-luna-reserve-in-codex-and-chatgpt-work).
- Upstream shows a Claude-only five-hour forecast automatically when official utilization can be paired with active-block token burn. Windows lacks that exact burn-rate model, so its optional forecast extrapolates average utilization for every official timed window with known duration/reset metadata, keeps the same 5% floor, and displays the reason when data is insufficient.
- PokeAPI's sprite repository provides a static sprites/items/poke-ball.png, but no matching Poké Ball opening GIF. Windows fetches that item sprite at runtime and builds the shake/flash/reveal transition in Qt for both the main window and floating pet; no Pokémon asset is bundled.
- Upstream resolves a nil representative synchronously to the active companion when saving the selection. Windows now mirrors that immediate behavior and previews the active companion at once, while its background refresh can subsequently replace the cached static preview with the animated sprite.
- Upstream keeps the popover separate from its bootstrap work. Windows now preserves that outcome by keeping both the first main window and the optional floating pet hidden until the initial usage/limits snapshot and companion sprite lookup (including its offline fallback) are complete.

Recent upstream changes were also reviewed for follow-up work. The most useful independent candidates are per-provider additional scan folders, animation-quality controls, provider account labels/session-key setup, Antigravity official limits, and the newer Pi/omp providers. They are intentionally not mixed into this focused UI/startup branch.

## Syncing future upstream changes

When upstream changes provider formats or game constants, compare these areas first:

- `Sources/PokeTokenBar/Core/CompanionModel.swift` -> `pokemon.py`, `state.py`
- `Sources/PokeTokenBar/Core/LocalUsageReader.swift` -> `usage.py`
- `Sources/PokeTokenBar/Core/LocalAdditionalUsageProvider.swift` -> `usage.py`, `cursor.py`
- `Sources/PokeTokenBar/Core/CursorUsageAPI.swift` -> `cursor.py`
- `Sources/PokeTokenBar/Core/OAuthLimitsProvider.swift` -> `limits.py`
- `Sources/PokeTokenBar/Core/CodexRateLimitsProvider.swift` -> `limits.py`
- `Sources/PokeTokenBar/Core/UsageStore.swift` notification rules -> `notifications.py`, `pet_logic.py`
- `Sources/PokeTokenBar/UI/SettingsView.swift` notification preferences -> `ui.py`
- SwiftUI/AppKit files -> `ui.py`, `app.py`, and `windows.py`

Known intentional gaps are tracked in `README.md` under **Parity / known gaps**.
