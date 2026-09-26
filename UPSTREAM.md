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

## UI/UX inventory review

The visible feature inventory was reviewed again on 2026-09-04 against upstream
`main` at `5f1ef524a104dceee681a21c13a92a7404c6f176`. The resulting status matrix and
prioritized work are recorded in `ROADMAP.md`. This audit treats the active
`QmlMainWindow` as the product surface: behavior that remains only in the legacy
Qt Widgets window or in the Python backend is marked partial rather than complete.

Upstream is four commits ahead of the previous comparison point. The only new
portable UI behavior is that all three egg cards remain visible during the egg
stage and explain why buying is disabled. The bundled Codex locator change is
specific to `ChatGPT.app` on macOS; the status-bar sprite optimization and comment
cleanup do not add Windows-visible features.

## Release audit ledger

**Latest upstream release fully reviewed: [v2.5.4](https://github.com/chattymin/PokeTokenBar/releases/tag/v2.5.4), commit `09fd6003dde877a2a546d261d08a43562fcc572b`, dated 2026-09-12.** Reviewed on 2026-09-26 against the previous documented checkpoint `5f1ef524a104dceee681a21c13a92a7404c6f176` (2026-09-03). The full first-parent range `5f1ef52..09fd600` contains the 25 changes below. “Reviewed” means assessed for this Windows port, not that the two applications have feature parity.

| Upstream commit | Change | Windows disposition |
| --- | --- | --- |
| `cd3125a` #267 | Floating pet maximum size 384 px | Deferred: Windows slider currently caps at 192 px; revisit only if requested. |
| `f2fe5ac` #263 | Absolute quota reset beside countdown | Adapted: Windows supports date/time reset format in `formatting.py`, exposed in Settings. |
| `b34673a` #252 | Refresh on network reconnection | Deferred: Windows already polls; no network-change listener, low value for two users. |
| `184c5f4` #282 | Lazy large catch log and sprite cache | Platform-specific AppKit remedy; Windows collection is paged in QML. Reassess if a measured stall appears. |
| `5bd8d43` #283 | Aside usage provider | Deferred: no known Windows user need. |
| `c9c016d` #280 | Prefer user account over MCP placeholder in macOS Keychain | macOS credential handling; no direct Windows equivalent. |
| `b0c6074` #244 | Difficulty multipliers and pet toggle | Deferred: changes game balance and the existing Windows controls; separate product decision. |
| `dec297a` #254 | Repeat hatch gets 2× growth | **Integrated** in `c25b1c9`, refined in `9d67372`: `state.py` persists `has_growth_boost`, QML shows the badge, `test_core.py` covers repeats and save compatibility. |
| `b6bf676` #264 | Individual Pokémon values and Pokédex detail | Deferred: substantial save model and UI expansion; not needed for current experience. |
| `0912c68` #270 | Current-month day-by-day usage | **Integrated/adapted** in `c25b1c9` and later UI refinements: `usage.py:month_daily_series`, Home chart in `qml/Main.qml`, `test_core.py` month series invariants. |
| `7898065` #275 | Claude macOS Keychain/session-key help | macOS-specific credentials; current Windows Claude fallback is documented separately. |
| `232108c` #279 | Count Codex total-only turns; Fable 5.1 cache pricing | **Priority candidate for a separate PR.** Windows `usage.py:parse_codex_object` may undercount total-only turns; inspect real fixtures and pricing before porting. |
| `d4d34e7` #284 | Remove redundant floating-pet toggle | UI-specific; Windows controls are in Settings, not the upstream popover footer. |
| `087fd0f` #285 | Preserve Dex sprite animation in detail page | Upstream detail-page behavior; Windows has no matching detail page. |
| `fd008e5` #286 | Graph fill follows Remaining mode | Already adapted for Windows Home gauge; `UPSTREAM.md` limit-display notes record the deliberate behavior. |
| `5963293` #287 | Save difficulty without advancing progress | Depends on #244 difficulty; deferred with it. |
| `69ff39b` #289 | Distinguish estimated and unavailable cost | Worth a later correctness review in `pricing.py` and `usage.py`; larger provider-wide change, lower priority than #279. |
| `2fab082` #290 | Complete localization across upstream app | Platform UI strings differ. Windows has English, Spanish and Galician strings; review individual gaps when observed. |
| `bb92bd2` #292 | Trailing alignment for quota percentages | Upstream visual polish; no direct parity requirement. |
| `a8b3ba8` #293 | Plain dollar cost display | Windows currently displays currency amounts in its own UI; no functional port required. |
| `1a8a725` #295 | Avoid English flash when loading localized Pokémon detail names | Depends on upstream detail page; defer until that surface exists here. |
| `aaef5db` #274 | Antigravity OAuth file parsing and refresh | Candidate only if Windows Antigravity limits become a user requirement; credentials differ by platform. |
| `5e08e6f` #296 | Release notes and contributor attribution gate | Upstream release process. Windows release checklist will require notes and verified artifact, without copying its infrastructure. |
| `065b2e1` #297 | Release tour/screenshots | Documentation-only upstream. |
| `09fd600` | Bump version to 2.5.4 | Upstream version marker; Windows uses independent `1.x` QML versioning. |

For each new upstream Release, compare the commits after the **last reviewed tag** through its tag, update this ledger with the exact SHA/date and decisions, and only then move the latest-reviewed marker. A release number alone is not proof of code parity. The Windows version number is independent of upstream's version number.

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
