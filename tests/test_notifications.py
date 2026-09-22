from __future__ import annotations

import unittest

from poketokenbar_windows.models import LimitWindow, ProviderLimits
from poketokenbar_windows.notifications import (
    CRITICAL_MAX,
    CRITICAL_MIN,
    DEFAULT_COMPANION_NOTIFICATIONS,
    DEFAULT_CRITICAL_THRESHOLD,
    DEFAULT_LIMIT_NOTIFICATIONS,
    DEFAULT_WARNING_THRESHOLD,
    WARNING_MAX,
    WARNING_MIN,
    companion_notification,
    evaluate_limit_alerts,
    evaluate_limit_changes,
    normalize_critical_threshold,
    normalize_warning_threshold,
)


def _limits(*windows: tuple[str, float]) -> dict[str, ProviderLimits]:
    return {
        "codex": ProviderLimits(
            provider="codex",
            windows=[LimitWindow(label, used) for label, used in windows],
        )
    }


class NotificationPreferenceTests(unittest.TestCase):
    def test_defaults_match_the_original_app(self):
        self.assertTrue(DEFAULT_LIMIT_NOTIFICATIONS)
        self.assertEqual(DEFAULT_WARNING_THRESHOLD, 80)
        self.assertEqual(DEFAULT_CRITICAL_THRESHOLD, 95)
        self.assertTrue(DEFAULT_COMPANION_NOTIFICATIONS)

    def test_thresholds_clamp_and_snap_to_five_percent_steps(self):
        self.assertEqual(normalize_warning_threshold(47), WARNING_MIN)
        self.assertEqual(normalize_warning_threshold(88), 90)
        self.assertEqual(normalize_warning_threshold(200), WARNING_MAX)
        self.assertEqual(normalize_critical_threshold(50), CRITICAL_MIN)
        self.assertEqual(normalize_critical_threshold(93), 95)
        self.assertEqual(normalize_critical_threshold(200), CRITICAL_MAX)

    def test_invalid_thresholds_use_defaults(self):
        self.assertEqual(normalize_warning_threshold("bad"), DEFAULT_WARNING_THRESHOLD)
        self.assertEqual(normalize_critical_threshold(float("nan")), DEFAULT_CRITICAL_THRESHOLD)


class LimitAlertTests(unittest.TestCase):
    def test_warning_and_critical_are_each_emitted_once(self):
        alerts, tiers = evaluate_limit_alerts(_limits(("5-hour", 80)))
        self.assertEqual([(alert.severity, alert.used_percent) for alert in alerts], [("warning", 80)])

        alerts, tiers = evaluate_limit_alerts(_limits(("5-hour", 90)), tiers)
        self.assertEqual(alerts, [])

        alerts, tiers = evaluate_limit_alerts(_limits(("5-hour", 95)), tiers)
        self.assertEqual([(alert.severity, alert.used_percent) for alert in alerts], [("critical", 95)])

        alerts, _ = evaluate_limit_alerts(_limits(("5-hour", 99)), tiers)
        self.assertEqual(alerts, [])

    def test_drop_below_warning_rearms_the_window(self):
        _, tiers = evaluate_limit_alerts(_limits(("Weekly", 96)))
        alerts, tiers = evaluate_limit_alerts(_limits(("Weekly", 20)), tiers)
        self.assertEqual(alerts, [])
        alerts, _ = evaluate_limit_alerts(_limits(("Weekly", 82)), tiers)
        self.assertEqual([alert.severity for alert in alerts], ["warning"])

    def test_custom_thresholds_are_used(self):
        alerts, _ = evaluate_limit_alerts(
            _limits(("Weekly", 90)), warning_percent=90, critical_percent=100
        )
        self.assertEqual([alert.severity for alert in alerts], ["warning"])

    def test_duplicate_display_labels_have_independent_keys(self):
        alerts, tiers = evaluate_limit_alerts(_limits(("Weekly", 81), ("Weekly", 81)))
        self.assertEqual(len(alerts), 2)
        self.assertEqual(len({alert.key for alert in alerts}), 2)
        self.assertEqual(len(tiers), 2)

    def test_spend_limit_is_included_for_system_notifications(self):
        alerts, _ = evaluate_limit_alerts(_limits(("Weekly spend", 96)))
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].window_label, "Weekly spend")

    def test_each_provider_is_independent(self):
        limits = _limits(("Weekly", 80))
        limits["claude"] = ProviderLimits(
            provider="claude", windows=[LimitWindow("Weekly", 80)]
        )
        alerts, _ = evaluate_limit_alerts(limits)
        self.assertEqual({alert.provider for alert in alerts}, {"claude", "codex"})


class LimitChangeTests(unittest.TestCase):
    def test_only_a_fully_used_limit_reset_and_a_real_credit_increase_notify(self):
        first = {
            "codex": ProviderLimits(
                "codex",
                windows=[LimitWindow("5-hour", 100, identifier="codex.primary")],
                reset_credits_available=1,
                reset_credits_known=True,
            )
        }
        changes, observations = evaluate_limit_changes(first)
        self.assertEqual(changes, [])

        next_reading = {
            "codex": ProviderLimits(
                "codex",
                windows=[LimitWindow("5-hour", 0, identifier="codex.primary")],
                reset_credits_available=2,
                reset_credits_known=True,
            )
        }
        changes, observations = evaluate_limit_changes(next_reading, observations)
        self.assertEqual(
            [(change.kind, change.previous_count, change.count) for change in changes],
            [("recovered", 0, 0), ("banked", 1, 2)],
        )
        changes, _ = evaluate_limit_changes(next_reading, observations)
        self.assertEqual(changes, [])

    def test_partial_usage_and_partial_recovery_do_not_notify(self):
        _, observations = evaluate_limit_changes(_limits(("Weekly", 99)))
        changes, observations = evaluate_limit_changes(_limits(("Weekly", 0)), observations)
        self.assertEqual(changes, [])
        _, observations = evaluate_limit_changes(_limits(("Weekly", 100)), observations)
        changes, _ = evaluate_limit_changes(_limits(("Weekly", 1)), observations)
        self.assertEqual(changes, [])

    def test_unknown_and_failed_credit_readings_do_not_create_false_grants(self):
        known = {"codex": ProviderLimits(
            "codex", reset_credits_available=1, reset_credits_known=True
        )}
        _, observations = evaluate_limit_changes(known)
        unknown = {"codex": ProviderLimits("codex")}
        changes, observations = evaluate_limit_changes(unknown, observations)
        self.assertEqual(changes, [])
        failed = {"codex": ProviderLimits("codex", error="unavailable")}
        changes, observations = evaluate_limit_changes(failed, observations)
        self.assertEqual(changes, [])
        gained = {"codex": ProviderLimits(
            "codex", reset_credits_available=2, reset_credits_known=True
        )}
        changes, _ = evaluate_limit_changes(gained, observations)
        self.assertEqual([(item.previous_count, item.count) for item in changes], [(1, 2)])


class CompanionNotificationTests(unittest.TestCase):
    def test_supported_companion_events_match_existing_windows_copy(self):
        cases = {
            "hatched:25": ("Pokemon hatched!", "Pikachu", True),
            "evolved:26": ("Evolution!", "Raichu", False),
            "graduated:26": ("Pokemon graduated!", "A new egg is ready.", False),
            "candy:2:codex": ("Rare Candy earned!", "You earned 2 Rare Candy.", False),
        }
        for event, expected in cases.items():
            with self.subTest(event=event):
                notification = companion_notification(event, "Pikachu" if "hatched" in event else "Raichu")
                self.assertIsNotNone(notification)
                assert notification is not None
                self.assertEqual(
                    (notification.title, notification.body, notification.use_sprite_icon), expected
                )

    def test_unknown_events_are_ignored(self):
        self.assertIsNone(companion_notification("unknown:event", "Pikachu"))


if __name__ == "__main__":
    unittest.main()
