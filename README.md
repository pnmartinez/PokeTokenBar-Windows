# PokeTokenBar Windows

A native Windows port of [chattymin/PokeTokenBar](https://github.com/chattymin/PokeTokenBar): your local AI coding-token usage raises a Pokemon companion from the Windows notification area.

> **Status: alpha.** The token tracker, game loop, tray UI, local state, shop/bag, runtime Pokemon fetching, Windows startup integration, and Claude/Codex official-limit checks are implemented. See **Parity / known gaps** before replacing the macOS app in a workflow you depend on.

## What works

- Windows 10/11 notification-area tray icon + Qt/PySide6 window, with current companion and stage progress in the tray tooltip and a right-click toggle for the floating pet
- Opt-in interactive floating desktop pet: animated egg/Pokemon, 48–192 px sizing, drag-and-drop position persistence, hover fields shared with the tray, click-to-open, a context menu matching the tray, and transient limit/full-reset bubbles
- Optional owned representative Pokemon for the desktop pet, independent of the actively progressing companion and preserving shiny variants; returning to Follow current companion switches immediately to the active egg/Pokemon
- Configurable Windows balloon/toast-style notifications: deduplicated official-limit warnings (80% warning and 95% critical by default) plus an independent toggle for hatch/evolution/graduation/Rare Candy events
- Animated Gen-V Pokemon sprites with static fallback, fetched and cached at runtime
- Egg -> hatch -> real evolution path -> graduation progression
- Upstream balance values: 5M hatch threshold; 750M / 1.875B / 3B / 6B graduation totals by rarity
- 25 natures, PokeAPI capture-rate rarity, shiny hatches, and Shiny Charm
- Bag and token shop: Rare Candy, Mint, Shiny Charm, normal/Uncommon/Rare eggs
- Separate Home, Collection, Bag, Shop, and Settings areas; paged Pokédex, Shiny sprite toggle, catch history, evolution line, and short in-app celebrations
- Configurable light/dark/system theme, refresh interval, limit thresholds, used/remaining percentages, tray fields, notifications, Pokémon-name language, and save import/export
- One upstream-style segmented Used/Remaining selector shared by Home, tray, and desktop-pet hover; compact surfaces use "left", Home gauges follow the selected mode, while warning/critical copy, thresholds, rewards, and risk colors always mean quota used
- A shared Time left/Date & time selector keeps resets, depletion forecasts, reset-credit expiry and related warnings in one consistent temporal format; countdown forecasts retain the compact "full in ~2h" style, while absolute values use a short date and time
- Optional timed-limit depletion forecasts with explicit insufficient-data states; Codex Luna Reserve stays visible in Home (as unavailable when Codex omits that bucket) but only replaces the regular allowance on tray/hover after regular usage is exhausted
- Pokémon-style companion progress shown consistently as `Lv. 0`–`Lv. 100`
- Deferred first window: real usage and limit data is rendered before the UI appears, followed by a Poké Ball reveal in both the main window and floating pet using a runtime-fetched PokeAPI item sprite with a drawn fallback; later representative changes use the same Poké Ball transition instead of a generic loader
- Edge-triggered Rare Candy rewards when an official time window reaches 100%, with upstream-compatible first-snapshot seeding and stable identities that ignore one-second reset-time drift
- Install-time usage baseline: pre-install usage is never retroactively converted into growth or shop currency
- Collection/catch history and persistent state under `%APPDATA%\PokeTokenBar-Windows`
- Sprite/API cache under `%LOCALAPPDATA%\PokeTokenBar-Windows\Cache`
- Start with Windows via `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
- Local token/cost aggregation for Claude Code, Codex, Gemini CLI, OpenCode, Hermes Agent, Cursor, Grok CLI, GitHub Copilot CLI, and Kiro CLI
- Claude official limits via `~\.claude\.credentials.json`
- Codex official remaining limits and available reset-credit expiry via `codex app-server --stdio`; headline limits stay first, Luna Reserve follows them, and each reset credit stays last in its provider block, turns amber when it expires before Weekly or within one week, red within 72 hours, and adds a matching 🟠/🔴 warning to the tray tooltip

## Game loop and items

Only one egg or companion is raised at a time; previously reached species remain in the Pokédex. A normal egg hatches after 5M newly observed tokens. Completing the final stage graduates the companion automatically and starts a fresh egg, so buying an egg is only a paid reroll that discards the unfinished active companion. Normal, Uncommon+, and Rare+ shop eggs cost 1B, 2.5B, and 4B wallet tokens.

- **Rare Candy** adds 100M progression without altering real usage totals. Filling a session-class limit grants one; filling a weekly-class limit (including Luna Reserve) grants five. Using one schedules an immediate full refresh.
- **Mint** costs 100M and rerolls the active companion's cosmetic nature.
- **Shiny Charm** costs 3B, is permanent, and improves future hatch odds from 1/64 to 1/48; it is not retroactive.

The default automatic refresh is every five minutes. Each refresh scans local usage **and** fetches official limits before applying growth, alerts, and Rare Candy rewards. On startup the main window and optional desktop pet stay hidden until this first real snapshot is ready.

## Install

### Standalone EXE

GitHub Actions builds a Windows artifact containing `PokeTokenBar-Windows.exe`. Extract the artifact and run the EXE; it is a GUI executable and does not need a console window.

### From source

Requirements: Windows 10/11 and Python 3.10+.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install.ps1
pythonw -m poketokenbar_windows
```

For development:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
pythonw -m poketokenbar_windows
```

Build the standalone Windows directory with PyInstaller:

```powershell
.\scripts\build-exe.ps1
```

The result is `dist\PokeTokenBar-Windows\PokeTokenBar-Windows.exe`.

## Local data sources

The Windows port reads the same underlying local formats as upstream and uses native Windows locations where needed.

| Tool | Windows locations / behavior |
|---|---|
| Claude Code | `$env:CLAUDE_CONFIG_DIR\projects`, `%USERPROFILE%\.config\claude\projects`, `%USERPROFILE%\.claude\projects`; classic and Microsoft Store Claude Desktop session stores under AppData are also probed |
| Codex | `$env:CODEX_HOME\sessions` or `%USERPROFILE%\.codex\sessions`, plus `archived_sessions` |
| Gemini CLI | `%USERPROFILE%\.gemini\tmp\**\chats\*.json(l)` |
| OpenCode | `$env:OPENCODE_DATA_DIR` or `%USERPROFILE%\.local\share\opencode` (the Windows location documented by OpenCode) |
| Hermes Agent | `$env:HERMES_HOME\state.db` or `%USERPROFILE%\.hermes\state.db` |
| Cursor | `%APPDATA%\Cursor\User\globalStorage\state.vscdb` for login token; usage from `cursor.com` dashboard API (local bubbles are fallback; they are often 0 on current Cursor) |
| Grok CLI | `$env:GROK_HOME\sessions\**\updates.jsonl` or `%USERPROFILE%\.grok\sessions` |
| Copilot CLI | `$env:COPILOT_HOME\session-store.db` or `%USERPROFILE%\.copilot\session-store.db` |
| Kiro CLI | `$env:KIRO_CLI_HOME\data.sqlite3`, plus Local/Roaming AppData and `%USERPROFILE%\.kiro` candidates |

No model turn is started to collect usage. Claude limits make an authenticated GET to Anthropic's OAuth usage endpoint using Claude Code's existing local OAuth token. When current Microsoft Store builds keep authentication inside their app container, the fresh local `plan-usage-history.json` is used as a fallback. Codex limits query the local Codex app-server account snapshot.

### Overrides

The existing provider environment variables above are honored. The port also supports:

- `PTB_STATE_DIR` — alternate state directory, useful for QA/demo isolation
- `PTB_CACHE_DIR` — alternate Pokemon metadata/sprite cache directory
- `PTB_SHOW_MAIN` — show the main window on launch, useful for isolated GUI QA and restricted shells
- `PTB_QA_ARTIFACT_DIR` — write one opt-in real-widget QA capture and native-window report after refresh
- `CODEX_BIN` — explicit Codex executable path; otherwise the current Codex Desktop binary is
  discovered under `%LOCALAPPDATA%\OpenAI\Codex\bin\*\codex.exe` on Windows

## Privacy

Token logs are parsed locally. Outbound requests are limited to functionality that needs them:

- `pokeapi.co` for species/evolution metadata
- `raw.githubusercontent.com/PokeAPI/sprites` for Pokémon, egg, and Poké Ball item sprites
- `api.anthropic.com` for Claude official limits
- `cursor.com` for Cursor usage when local bubble token counts are zero (uses the existing Cursor IDE login; disable with `CURSOR_USAGE_API=0`)

Codex official limits use a local child process. The app does not upload your local usage logs.

## Parity / known gaps

This is a serious first Windows port, not a bit-for-bit rewrite of the SwiftUI app. Current gaps:

- Antigravity's protobuf-in-SQLite reader is not ported yet.
- Kiro's Windows database location is probed across likely AppData layouts because its local layout has changed between releases; `KIRO_CLI_HOME` is the authoritative override.
- Codex fork/replay dedup is simplified versus upstream's deep parent-rollout reconciliation. Normal `token_count` snapshots are deduplicated, but pathological fork histories may differ slightly.
- Provider incident banners and in-app self-updater are not included yet.
- Full UI translation is not yet ported; the configured language currently applies to Pokémon names.
- Virtual-desktop behavior is intentionally scoped to the current Windows virtual desktop; all of its monitors are supported, including negative coordinates and mixed-DPI layouts.

## Tests

```powershell
python -m unittest discover -s tests -v
python -m compileall -q src tests
```

CI runs those checks on `windows-latest` for Python 3.10 and 3.12 and builds a PyInstaller artifact on Windows.

## Collaboration

All contributors and coding agents must follow [AGENTS.md](AGENTS.md). In particular, fetch GitHub before starting, inspect active branches and pull requests for overlap, publish every new branch, and push every commit so parallel work remains visible.

## Publish to GitHub

The repository is prepared for `pnmartinez/PokeTokenBar-Windows`. With GitHub CLI authenticated:

```powershell
.\scripts\publish-github.ps1
```

Override the target with `GITHUB_OWNER`, `GITHUB_REPO`, or `GITHUB_VISIBILITY` if desired.

See `UPSTREAM.md` for the pinned upstream commit and the files to compare when syncing future upstream changes.

## Upstream credit

This project ports the behavior and balance of [PokeTokenBar](https://github.com/chattymin/PokeTokenBar), originally written in Swift/SwiftUI by chattymin and contributors. The upstream MIT license is preserved in `LICENSE`. See `NOTICE.md` for the Pokemon/PokeAPI disclaimer.
