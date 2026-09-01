from __future__ import annotations

import base64
import io
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath
from unittest.mock import patch

import poketokenbar_windows.limits as limits_module
from poketokenbar_windows.cursor import (
    cache_account_identifier,
    has_next_page,
    parse_cursor_bubble,
    parse_usage_event,
    workos_session_cookie,
)
from poketokenbar_windows.formatting import (
    companion_level_text,
    compact_tokens,
    format_limit_countdown,
    format_limit_datetime,
    format_limit_event_time,
    limit_alert_body,
    limit_forecast,
    limit_forecast_unavailable_reason,
    limit_percent_text,
    limit_reset_summary,
    limit_reset_tray_warning,
    limit_reset_urgency,
    normalize_limit_display_mode,
    normalize_limit_time_mode,
    provider_limit_rows,
)
from poketokenbar_windows.models import (
    LimitWindow,
    ProviderLimits,
    RateLimitResetCredit,
)
from poketokenbar_windows.pokemon import (
    EGG_HATCH_THRESHOLD,
    GRADUATION_TOTALS,
    HatchResult,
    PokeAPIClient,
    egg_price,
    phase_threshold,
    rarity_from,
)
from poketokenbar_windows.state import (
    GameState,
    StateStore,
    apply_limit_rewards,
    apply_usage,
    buy_egg,
    companion_progress_percent,
    usage_delta,
)
from poketokenbar_windows.usage import parse_claude_object, parse_codex_object
from poketokenbar_windows.windows import (
    APP_NAME,
    REGISTRY_VALUE_NAME,
    cache_dir,
    claude_desktop_roots,
    claude_plan_usage_paths,
    cursor_database_candidates,
    kiro_database_candidates,
    state_dir,
)


class FakeAPI:
    def hatch(self, minimum_rarity=None, shiny_charm=False):
        return HatchResult(
            base_id=1,
            path_ids=[1, 2, 3],
            rarity="common",
            nature="Hardy",
            is_shiny=False,
            capture_rate=45,
        )


class RecordingStdin(io.StringIO):
    def __init__(self):
        super().__init__()
        self.was_closed = False

    def close(self):
        self.was_closed = True


class OpenStdinResponse(io.StringIO):
    def __init__(self, stdin: RecordingStdin, content: str):
        super().__init__(content)
        self.stdin = stdin
        self.read_while_open = False

    def readline(self, *args, **kwargs):
        if self.stdin.was_closed:
            return ""
        self.read_while_open = True
        return super().readline(*args, **kwargs)


class FakeCodexProcess:
    def __init__(self, response: dict):
        self.stdin = RecordingStdin()
        self.stdout = OpenStdinResponse(self.stdin, json.dumps(response) + "\n")
        self.stderr = io.StringIO()
        self.returncode = None
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.returncode = -1

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


class BalanceTests(unittest.TestCase):
    def test_phase_thresholds_sum_to_graduation_total(self):
        for rarity, total in GRADUATION_TOTALS.items():
            for forms in (1, 2, 3):
                self.assertAlmostEqual(
                    sum(phase_threshold(rarity, forms, index) for index in range(forms)),
                    total,
                    delta=forms,
                )

    def test_rarity_boundaries(self):
        self.assertEqual(rarity_from(255, False, False), "common")
        self.assertEqual(rarity_from(120, False, False), "uncommon")
        self.assertEqual(rarity_from(45, False, False), "rare")
        self.assertEqual(rarity_from(3, True, False), "legendary")

    def test_egg_prices(self):
        self.assertEqual(egg_price(None), 1_000_000_000)
        self.assertEqual(egg_price("uncommon"), 2_500_000_000)
        self.assertEqual(egg_price("rare"), 4_000_000_000)


class UsageParserTests(unittest.TestCase):
    def test_claude(self):
        entry = parse_claude_object({
            "type": "assistant",
            "timestamp": "2026-08-21T10:00:00Z",
            "requestId": "r1",
            "message": {
                "id": "m1",
                "model": "claude-sonnet-4-6",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_creation_input_tokens": 20,
                    "cache_read_input_tokens": 30,
                },
            },
        })
        self.assertIsNotNone(entry)
        self.assertEqual(entry.total_tokens, 200)
        self.assertEqual(entry.id, "claude|m1|r1")

    def test_codex_last_usage(self):
        entry = parse_codex_object({
            "timestamp": "2026-08-21T10:00:00Z",
            "payload": {
                "type": "token_count",
                "info": {"last_token_usage": {"input_tokens": 1000, "cached_input_tokens": 400, "output_tokens": 200}},
            },
        }, file_id="rollout.jsonl", turn=0, model="gpt-5.5")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.input_tokens, 600)
        self.assertEqual(entry.cache_read_tokens, 400)
        self.assertEqual(entry.total_tokens, 1200)


class CursorUsageTests(unittest.TestCase):
    def test_zero_bubble_tokens_are_ignored(self):
        since = datetime(2026, 1, 1, tzinfo=timezone.utc)
        entry = parse_cursor_bubble(
            {
                "tokenCount": {"inputTokens": 0, "outputTokens": 0},
                "createdAt": "2026-08-18T13:00:00.000Z",
                "modelType": "gpt-4o",
            },
            key="bubbleId:tab:zero",
            since=since,
        )
        self.assertIsNone(entry)

    def test_dashboard_event_includes_cache_tokens(self):
        since = datetime(2025, 1, 1, tzinfo=timezone.utc)
        entry = parse_usage_event(
            {
                "timestamp": "1750979225854",
                "model": "claude-opus-5-thinking-high",
                "tokenUsage": {
                    "inputTokens": 126,
                    "outputTokens": 450,
                    "cacheWriteTokens": 6112,
                    "cacheReadTokens": 11964,
                },
            },
            row_index=0,
            since=since,
        )
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.input_tokens, 126)
        self.assertEqual(entry.output_tokens, 450)
        self.assertEqual(entry.cache_write_tokens, 6112)
        self.assertEqual(entry.cache_read_tokens, 11964)
        self.assertTrue(entry.id.startswith("cursor|api|"))

    def test_workos_cookie_and_account_id(self):
        payload = base64.urlsafe_b64encode(b'{"sub":"user_01TEST"}').decode("ascii").rstrip("=")
        jwt = f"hdr.{payload}.sig"
        self.assertEqual(workos_session_cookie(jwt), f"user_01TEST::{jwt}")
        self.assertEqual(cache_account_identifier(jwt), "subject:user_01TEST")
        self.assertEqual(cache_account_identifier(f"user_01TEST::{jwt}"), "subject:user_01TEST")

    def test_has_next_page_uses_total_count(self):
        self.assertTrue(has_next_page(None, total_count=239, page=1, event_count=100))
        self.assertFalse(has_next_page(None, total_count=239, page=3, event_count=39))


class StateTests(unittest.TestCase):
    def test_companion_progress_percent_for_egg_and_pokemon(self):
        state = GameState(egg_usage=EGG_HATCH_THRESHOLD // 2)
        self.assertEqual(companion_progress_percent(state), 50)

        apply_usage(state, EGG_HATCH_THRESHOLD // 2, FakeAPI())
        assert state.mon is not None
        target = phase_threshold(state.mon.rarity, len(state.mon.path_ids), state.mon.stage_index)
        state.mon.used_at_stage = target // 2
        self.assertEqual(companion_progress_percent(state), 50)

    def test_companion_progress_percent_is_clamped(self):
        self.assertEqual(companion_progress_percent(GameState(egg_usage=-1)), 0)
        self.assertEqual(companion_progress_percent(GameState(egg_usage=EGG_HATCH_THRESHOLD + 1)), 100)

    def test_usage_delta_seeds_install_baseline_and_resets_daily(self):
        state = GameState()
        self.assertEqual(usage_delta(state, 10, date(2026, 8, 21)), 0)
        self.assertTrue(state.install_baseline_set)
        self.assertEqual(usage_delta(state, 15, date(2026, 8, 21)), 5)
        self.assertEqual(usage_delta(state, 3, date(2026, 8, 22)), 3)
        self.assertEqual(state.used_since_install, 8)

    def test_new_provider_is_seeded_without_retroactive_credit(self):
        state = GameState()
        self.assertEqual(usage_delta(state, {"claude": 100}, date(2026, 8, 21)), 0)
        self.assertEqual(usage_delta(state, {"claude": 110, "codex": 500}, date(2026, 8, 21)), 10)
        self.assertEqual(usage_delta(state, {"claude": 120, "codex": 520}, date(2026, 8, 21)), 30)

    def test_hatch_and_evolve(self):
        state = GameState()
        events = apply_usage(state, EGG_HATCH_THRESHOLD, FakeAPI())
        self.assertEqual(events, ["hatched:1"])
        self.assertIsNotNone(state.mon)
        first = phase_threshold("common", 3, 0)
        events = apply_usage(state, first, FakeAPI())
        self.assertEqual(events, ["evolved:2"])
        self.assertEqual(state.mon.current_id, 2)

    def test_limit_candy_is_once_per_window_after_initial_seed(self):
        state = GameState()
        first = {"claude": ProviderLimits(provider="claude", windows=[
            LimitWindow("Weekly", 100.0, datetime(2026, 8, 24, tzinfo=timezone.utc))
        ])}
        self.assertEqual(apply_limit_rewards(state, first), [])
        self.assertEqual(state.inventory["rare_candy"], 0)

        one_second_drift = {"claude": ProviderLimits(provider="claude", windows=[
            LimitWindow("Weekly", 100.0, datetime(2026, 8, 24, 0, 0, 1, tzinfo=timezone.utc))
        ])}
        self.assertEqual(apply_limit_rewards(state, one_second_drift), [])
        self.assertEqual(state.inventory["rare_candy"], 0)

        rearmed = {"claude": ProviderLimits(provider="claude", windows=[
            LimitWindow("Weekly", 99.0, datetime(2026, 8, 31, tzinfo=timezone.utc))
        ])}
        self.assertEqual(apply_limit_rewards(state, rearmed), [])

        next_cap = {"claude": ProviderLimits(provider="claude", windows=[
            LimitWindow("Weekly", 100.0, datetime(2026, 8, 31, tzinfo=timezone.utc))
        ])}
        self.assertEqual(len(apply_limit_rewards(state, next_cap)), 1)
        self.assertEqual(state.inventory["rare_candy"], 5)
        self.assertEqual(apply_limit_rewards(state, next_cap), [])
        self.assertEqual(state.inventory["rare_candy"], 5)

    def test_luna_reserve_uses_its_weekly_duration_for_candy(self):
        state = GameState(candy_feature_seeded=True)
        reserve = LimitWindow(
            "Luna Reserve",
            100.0,
            datetime(2026, 9, 7, tzinfo=timezone.utc),
            duration_minutes=10_080,
            identifier="base_model_inference.primary",
        )
        grants = apply_limit_rewards(
            state,
            {"codex": ProviderLimits(provider="codex", windows=[reserve])},
        )
        self.assertEqual(grants, ["candy:5:codex:Luna Reserve"])
        self.assertEqual(state.inventory["rare_candy"], 5)

    def test_fresh_egg_discards_active_ungraduated_catch(self):
        state = GameState(install_baseline_set=True, used_since_install=2_000_000_000)
        apply_usage(state, EGG_HATCH_THRESHOLD, FakeAPI())
        self.assertEqual(len(state.catches), 1)
        ok, _ = buy_egg(state, None)
        self.assertTrue(ok)
        self.assertIsNone(state.mon)
        self.assertEqual(state.catches, [])

    def test_state_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(Path(tmp) / "state.json")
            state = GameState(egg_usage=123, used_since_install=456)
            store.save(state)
            loaded = store.load()
            self.assertEqual(loaded.egg_usage, 123)
            self.assertEqual(loaded.used_since_install, 456)


class WindowsIntegrationTests(unittest.TestCase):
    def test_short_display_name_preserves_stable_windows_identity(self):
        self.assertEqual(APP_NAME, "PokeTokenBar")
        self.assertEqual(REGISTRY_VALUE_NAME, "PokeTokenBar Windows")

    def test_native_appdata_paths(self):
        env = {
            "USERPROFILE": r"C:\Users\ash",
            "APPDATA": r"C:\Users\ash\AppData\Roaming",
            "LOCALAPPDATA": r"C:\Users\ash\AppData\Local",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(
                PureWindowsPath(str(state_dir())),
                PureWindowsPath(r"C:\Users\ash\AppData\Roaming\PokeTokenBar-Windows"),
            )
            self.assertEqual(
                PureWindowsPath(str(cache_dir())),
                PureWindowsPath(r"C:\Users\ash\AppData\Local\PokeTokenBar-Windows\Cache"),
            )
            self.assertIn(
                PureWindowsPath(r"C:\Users\ash\AppData\Roaming\Cursor\User\globalStorage\state.vscdb"),
                [PureWindowsPath(str(path)) for path in cursor_database_candidates()],
            )
            self.assertIn(
                PureWindowsPath(r"C:\Users\ash\AppData\Local\kiro-cli\data.sqlite3"),
                [PureWindowsPath(str(path)) for path in kiro_database_candidates()],
            )

    def test_hidden_subprocess_flags(self):
        from poketokenbar_windows.windows import (
            hidden_subprocess_kwargs,
            resolve_gui_binary,
        )

        kwargs = hidden_subprocess_kwargs()
        self.assertIn("creationflags", kwargs)
        self.assertEqual(resolve_gui_binary(r"C:\missing-codex.cmd"), r"C:\missing-codex.cmd")

    def test_microsoft_store_claude_paths_are_discovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            local_root = Path(tmp) / "Local"
            roaming_root = Path(tmp) / "Roaming"
            store_data = local_root / "Packages/Claude_test/LocalCache/Roaming/Claude"
            store_data.mkdir(parents=True)
            with (
                patch("poketokenbar_windows.windows.local_appdata", return_value=local_root),
                patch("poketokenbar_windows.windows.roaming_appdata", return_value=roaming_root),
            ):
                self.assertIn(store_data / "local-agent-mode-sessions", claude_desktop_roots())
                self.assertIn(store_data / "claude-code-sessions", claude_desktop_roots())
                self.assertIn(store_data / "plan-usage-history.json", claude_plan_usage_paths())


class ClaudeLimitsTests(unittest.TestCase):
    def test_falls_back_to_fresh_microsoft_store_plan_history(self):
        now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "plan-usage-history.json"
            history.write_text(json.dumps({
                "version": 2,
                "samples": [
                    {"t": int((now - timedelta(minutes=15)).timestamp() * 1000), "u": {"fh": 21, "sd": 59}},
                ],
            }), encoding="utf-8")
            with patch.object(limits_module, "claude_plan_usage_paths", return_value=[history]):
                result = limits_module._read_claude_local_limits(now)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIsNone(result.error)
        self.assertEqual([(item.label, item.used_percent) for item in result.windows], [
            ("5-hour", 21.0),
            ("Weekly", 59.0),
        ])

    def test_stale_plan_history_is_not_reported(self):
        now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "plan-usage-history.json"
            history.write_text(json.dumps({
                "version": 2,
                "samples": [
                    {"t": int((now - timedelta(hours=2)).timestamp() * 1000), "u": {"fh": 21, "sd": 59}},
                ],
            }), encoding="utf-8")
            with patch.object(limits_module, "claude_plan_usage_paths", return_value=[history]):
                self.assertIsNone(limits_module._read_claude_local_limits(now))

    def test_fetch_uses_local_history_when_oauth_is_unavailable(self):
        local = ProviderLimits(provider="claude", windows=[LimitWindow("Weekly", 59.0)])
        with (
            patch.object(limits_module, "_read_claude_oauth", return_value=None),
            patch.object(limits_module, "_read_claude_local_limits", return_value=local),
        ):
            self.assertIs(limits_module.fetch_claude_limits(), local)


class CodexLimitsTests(unittest.TestCase):
    def test_absent_reset_credits_stay_hidden(self):
        available_count, credits = limits_module._codex_reset_credits({})
        self.assertEqual(available_count, 0)
        self.assertEqual(credits, [])

    def test_discovers_newest_codex_desktop_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            local_root = Path(tmp)
            old_binary = local_root / "OpenAI/Codex/bin/old/codex.exe"
            new_binary = local_root / "OpenAI/Codex/bin/new/codex.exe"
            old_binary.parent.mkdir(parents=True)
            new_binary.parent.mkdir(parents=True)
            old_binary.write_bytes(b"old")
            new_binary.write_bytes(b"new")
            os.utime(old_binary, (1, 1))
            os.utime(new_binary, (2, 2))
            with (
                patch.dict(os.environ, {"CODEX_BIN": ""}, clear=False),
                patch.object(limits_module, "local_appdata", return_value=local_root),
                patch.object(Path, "home", return_value=local_root / "home"),
                patch.object(limits_module.shutil, "which", return_value=None),
            ):
                self.assertEqual(limits_module._find_codex(), str(new_binary))

    def test_codex_rpc_keeps_stdin_open_until_rate_limit_response(self):
        response = {
            "id": 1,
            "result": {
                "rateLimits": {
                    "limitId": "codex",
                    "planType": "plus",
                    "primary": {
                        "usedPercent": 25,
                        "windowDurationMins": 300,
                        "resetsAt": 1_788_000_000,
                    },
                    "secondary": {
                        "usedPercent": 40,
                        "windowDurationMins": 10_080,
                        "resetsAt": 1_788_100_000,
                    },
                },
                "rateLimitsByLimitId": {
                    "codex": {
                        "limitId": "codex",
                        "planType": "plus",
                        "primary": {
                            "usedPercent": 25,
                            "windowDurationMins": 300,
                            "resetsAt": 1_788_000_000,
                        },
                        "secondary": {
                            "usedPercent": 40,
                            "windowDurationMins": 10_080,
                            "resetsAt": 1_788_100_000,
                        },
                    },
                    "base_model_inference": {
                        "limitId": "base_model_inference",
                        "limitName": "gpt-reserve",
                        "planType": "plus",
                        "primary": {
                            "usedPercent": 0,
                            "windowDurationMins": 10_080,
                            "resetsAt": 1_788_200_000,
                        },
                        "secondary": None,
                    },
                },
                "rateLimitResetCredits": {
                    "availableCount": 1,
                    "credits": [
                        {
                            "status": "available",
                            "expiresAt": 1_789_000_000,
                            "title": "Full reset (Weekly + 5 hr)",
                            "description": "One free reset.",
                        }
                    ],
                },
            },
        }
        proc = FakeCodexProcess(response)
        with (
            patch.object(limits_module, "_find_codex", return_value=r"C:\Codex\codex.exe"),
            patch.object(limits_module, "resolve_gui_binary", side_effect=lambda path: path),
            patch.object(limits_module.subprocess, "Popen", return_value=proc),
        ):
            result = limits_module.fetch_codex_limits(timeout=1)

        self.assertIsNone(result.error)
        self.assertEqual(result.plan, "Plus")
        self.assertEqual(
            [window.label for window in result.windows],
            ["5-hour", "Weekly", "Luna Reserve"],
        )
        self.assertEqual([window.remaining_percent for window in result.windows], [75, 60, 100])
        self.assertEqual(result.windows[2].duration_minutes, 10_080)
        self.assertEqual(result.windows[2].identifier, "base_model_inference.primary")
        self.assertEqual(result.reset_credits_available, 1)
        self.assertEqual(len(result.reset_credits), 1)
        self.assertEqual(result.reset_credits[0].title, "Full reset (Weekly + 5 hr)")
        self.assertEqual(result.reset_credits[0].expires_at.timestamp(), 1_789_000_000)
        self.assertTrue(proc.stdout.read_while_open)
        self.assertIn('"method":"account/rateLimits/read"', proc.stdin.getvalue())
        self.assertTrue(proc.stdin.was_closed)
        self.assertTrue(proc.terminated)


class PokemonAssetTests(unittest.TestCase):
    def test_item_sprite_uses_validated_runtime_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = PokeAPIClient(Path(tmp))
            cached = client.sprite_dir / "item-poke-ball.png"
            cached.write_bytes(b"cached")
            self.assertEqual(client.item_sprite_path("poke-ball"), cached)
            with self.assertRaises(ValueError):
                client.item_sprite_path("../not-an-item")


class FormattingTests(unittest.TestCase):
    def test_compact_tokens(self):
        self.assertEqual(compact_tokens(200_700_000), "200.7M")
        self.assertEqual(compact_tokens(1_000_000_000), "1B")

    def test_companion_progress_uses_pokemon_level_copy(self):
        self.assertEqual(companion_level_text(91), "Lv. 91")
        self.assertEqual(companion_level_text(150), "Lv. 100")

    def test_limit_display_mode_is_explicit_and_defaults_to_used(self):
        self.assertEqual(normalize_limit_display_mode(None), "used")
        self.assertEqual(normalize_limit_display_mode("remaining"), "remaining")
        self.assertEqual(limit_percent_text(75, "used"), "75% used")
        self.assertEqual(limit_percent_text(75, "remaining"), "25% remaining")
        self.assertEqual(limit_percent_text(75, "remaining", compact=True), "25% left")
        self.assertEqual(
            limit_alert_body("Codex", "Weekly", 95, "remaining"),
            "Codex Weekly: 95% used.",
        )

    def test_timed_limit_forecast_extrapolates_average_window_utilization(self):
        now = datetime(2026, 8, 31, 10, 0, tzinfo=timezone.utc)
        fast = LimitWindow(
            "5-hour",
            75,
            now + timedelta(hours=2),
            duration_minutes=300,
        )
        forecast = limit_forecast(fast, now)
        self.assertIsNotNone(forecast)
        self.assertTrue(forecast.before_reset)
        self.assertEqual(forecast.depletion_at, now + timedelta(hours=1))

        slow = LimitWindow(
            "5-hour",
            30,
            now + timedelta(hours=2),
            duration_minutes=300,
        )
        self.assertFalse(limit_forecast(slow, now).before_reset)
        unstable = LimitWindow(
            "5-hour",
            4,
            now + timedelta(hours=2),
            duration_minutes=300,
        )
        self.assertIsNone(limit_forecast(unstable, now))
        self.assertEqual(
            limit_forecast_unavailable_reason(unstable, now),
            "not enough data yet",
        )

        weekly = LimitWindow(
            "Weekly",
            60,
            now + timedelta(days=3),
            duration_minutes=10_080,
        )
        weekly_forecast = limit_forecast(weekly, now)
        self.assertIsNotNone(weekly_forecast)
        self.assertTrue(weekly_forecast.before_reset)

    def test_limit_time_modes_use_countdowns_or_short_dates_consistently(self):
        now = datetime(2026, 8, 26, 0, 0, tzinfo=timezone.utc)
        reset = datetime(2026, 8, 26, 3, 37, tzinfo=timezone.utc)
        forecast = now + timedelta(hours=1, minutes=40)

        self.assertEqual(normalize_limit_time_mode(None), "remaining")
        self.assertEqual(normalize_limit_time_mode("datetime"), "datetime")
        self.assertEqual(format_limit_countdown(reset, now), "3h 37m")
        self.assertEqual(
            format_limit_event_time("resets", reset, "remaining", now),
            "resets in 3h 37m",
        )
        self.assertEqual(
            format_limit_event_time(
                "full",
                forecast,
                "remaining",
                now,
                approximate=True,
            ),
            "full in ~2h",
        )
        self.assertEqual(
            format_limit_datetime(reset),
            "26 Aug, 03:37",
        )
        self.assertEqual(
            format_limit_event_time("resets", reset, "datetime", now),
            "resets 26 Aug, 03:37",
        )

    def test_limit_reset_summary_is_optional_and_compact(self):
        self.assertEqual(limit_reset_summary(ProviderLimits(provider="codex")), "")
        limits = ProviderLimits(
            provider="codex",
            reset_credits_available=1,
            reset_credits=[
                RateLimitResetCredit(
                    title="Full reset (Weekly + 5 hr)",
                    status="available",
                    expires_at=datetime(2026, 9, 21, 1, 5, tzinfo=timezone.utc),
                )
            ],
        )
        now = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(
            limit_reset_summary(limits, now),
            "Full reset available · Weekly + 5h · expires in 20d 1h",
        )
        self.assertEqual(
            limit_reset_summary(limits, now, time_mode="datetime"),
            "Full reset available · Weekly + 5h · expires 21 Sep, 01:05",
        )

    def test_reset_row_stays_last_in_provider_block(self):
        now = datetime(2026, 8, 26, 8, 0, tzinfo=timezone.utc)
        limits = ProviderLimits(
            provider="codex",
            plan="Plus",
            windows=[
                LimitWindow("5-hour", 10, now + timedelta(hours=6)),
                LimitWindow("Weekly", 14, now + timedelta(days=6)),
                LimitWindow("Luna Reserve", 5, now + timedelta(days=3)),
            ],
            reset_credits_available=1,
            reset_credits=[
                RateLimitResetCredit(
                    title="Full reset (Weekly + 5 hr)",
                    expires_at=now + timedelta(days=5),
                )
            ],
        )

        rows = provider_limit_rows("Codex", limits, now)
        self.assertIn("5-hour", rows[0].text)
        self.assertIn("10% used", rows[0].text)
        self.assertIn("Weekly:", rows[1].text)
        self.assertIn("Luna Reserve", rows[2].text)
        self.assertTrue(rows[3].text.startswith("[⚠ Codex · Full reset available"))
        self.assertEqual(rows[3].urgency, "warning")

    def test_reset_is_amber_under_one_week_even_after_weekly(self):
        now = datetime(2026, 8, 26, 8, 0, tzinfo=timezone.utc)
        limits = ProviderLimits(
            provider="codex",
            windows=[LimitWindow("Weekly", 14, now + timedelta(days=2))],
            reset_credits_available=1,
            reset_credits=[RateLimitResetCredit(expires_at=now + timedelta(days=6))],
        )
        self.assertEqual(limit_reset_urgency(limits, now), "warning")
        self.assertEqual(limit_reset_tray_warning(limits, now), "🟠 reset expires in 6d 0h")
        self.assertEqual(
            limit_reset_tray_warning(limits, now, time_mode="datetime"),
            "🟠 reset expires 01 Sep, 08:00",
        )

    def test_reset_is_amber_before_weekly_even_over_one_week_away(self):
        now = datetime(2026, 8, 26, 8, 0, tzinfo=timezone.utc)
        limits = ProviderLimits(
            provider="codex",
            windows=[LimitWindow("Weekly", 14, now + timedelta(days=10))],
            reset_credits_available=1,
            reset_credits=[RateLimitResetCredit(expires_at=now + timedelta(days=8))],
        )
        self.assertEqual(limit_reset_urgency(limits, now), "warning")

    def test_reset_turns_red_at_72_hours(self):
        now = datetime(2026, 8, 26, 8, 0, tzinfo=timezone.utc)
        limits = ProviderLimits(
            provider="codex",
            windows=[LimitWindow("Weekly", 14, now + timedelta(days=6))],
            reset_credits_available=1,
            reset_credits=[RateLimitResetCredit(expires_at=now + timedelta(hours=72))],
        )
        self.assertEqual(limit_reset_urgency(limits, now), "critical")
        self.assertEqual(limit_reset_tray_warning(limits, now), "🔴 reset expires in 3d 0h")
        self.assertEqual(
            limit_reset_tray_warning(limits, now, time_mode="datetime"),
            "🔴 reset expires 29 Aug, 08:00",
        )

    def test_reset_stays_neutral_after_weekly_and_one_week(self):
        now = datetime(2026, 8, 26, 8, 0, tzinfo=timezone.utc)
        limits = ProviderLimits(
            provider="codex",
            windows=[LimitWindow("Weekly", 14, now + timedelta(days=6))],
            reset_credits_available=1,
            reset_credits=[RateLimitResetCredit(expires_at=now + timedelta(days=20))],
        )
        self.assertEqual(limit_reset_urgency(limits, now), "neutral")
        self.assertEqual(limit_reset_tray_warning(limits, now), "")


if __name__ == "__main__":
    unittest.main()
