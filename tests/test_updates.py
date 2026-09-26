from __future__ import annotations

import json
import unittest

from PySide6.QtCore import QCoreApplication

from poketokenbar_windows.updates import (
    UpdateChecker,
    interpret_latest_release,
    version_tuple,
)
from poketokenbar_windows.version import BuildIdentity


def response(tag: str, *, url: str | None = None, **overrides) -> bytes:
    payload = {
        "tag_name": tag,
        "html_url": url or f"https://github.com/pnmartinez/PokeTokenBar-Windows/releases/tag/{tag}",
        "draft": False,
        "prerelease": False,
    }
    payload.update(overrides)
    return json.dumps(payload).encode("utf-8")


class FakeTransport:
    def __init__(self):
        self.calls = 0
        self.pending = None

    def get(self, callback):
        self.calls += 1
        self.pending = callback

    def complete(self, status, body=b"", error=None):
        callback, self.pending = self.pending, None
        callback(status, body, error)


class UpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_numeric_versions_and_release_identity(self):
        self.assertGreater(version_tuple("v1.10.0"), version_tuple("v1.9.9"))
        self.assertIsNone(version_tuple("v1.0.0-beta"))
        release = BuildIdentity("1.0.0", "a" * 40, True)
        development = BuildIdentity("1.0.0", "b" * 40, False)
        self.assertEqual(interpret_latest_release(200, response("v1.1.0"), None, release).status, "available")
        self.assertEqual(interpret_latest_release(200, response("v1.0.0"), None, release).status, "current")
        self.assertEqual(interpret_latest_release(200, response("v1.0.0"), None, development).status, "available")

    def test_missing_network_and_invalid_response_are_not_current(self):
        identity = BuildIdentity("1.0.0", "a" * 40, True)
        cases = [
            (404, b"", "HTTP 404", "no_release"),
            (None, b"", "Network unreachable", "offline"),
            (200, b"not-json", None, "invalid"),
            (200, response("v1.1.0", url="https://example.com/bad"), None, "invalid"),
            (200, response("v1.1.0", prerelease=True), None, "invalid"),
        ]
        for status, body, error, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(interpret_latest_release(status, body, error, identity).status, expected)

    def test_one_automatic_request_then_manual_retry(self):
        transport = FakeTransport()
        checker = UpdateChecker(BuildIdentity("1.0.0", "a" * 40, True), transport)
        seen = []
        checker.stateChanged.connect(lambda state: seen.append(state.status))
        self.assertTrue(checker.start_automatic())
        self.assertEqual(transport.calls, 1)
        self.assertFalse(checker.start_automatic())
        self.assertFalse(checker.check_now())  # no concurrent second request
        transport.complete(200, response("v1.1.0"))
        self.assertEqual(checker.state.status, "available")
        self.assertEqual(checker.state.version, "v1.1.0")
        self.assertTrue(checker.check_now())
        self.assertEqual(transport.calls, 2)
        transport.complete(None, error="offline")
        self.assertEqual(checker.state.status, "offline")
        self.assertEqual(seen, ["checking", "available", "checking", "offline"])


if __name__ == "__main__":
    unittest.main()
