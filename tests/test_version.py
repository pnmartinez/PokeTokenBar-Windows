from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path

from poketokenbar_windows import __version__
from poketokenbar_windows.limits import _codex_request_lines
from poketokenbar_windows.version import build_identity
from scripts.write_version_info import version_resource


class VersionTests(unittest.TestCase):
    def test_source_checkout_is_identified_as_development_build(self):
        identity = build_identity()
        self.assertEqual(identity.version, __version__)
        self.assertFalse(identity.release)
        self.assertIn("-dev", identity.label)
        self.assertEqual(len(identity.commit), 40)
        self.assertIn(identity.commit[:7], identity.label)

    def test_manifest_release_and_development_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "build-info.json"
            commit = "a" * 40
            for release in (False, True):
                with self.subTest(release=release):
                    path.write_text(json.dumps({
                        "version": __version__, "commit": commit, "release": release
                    }), encoding="utf-8")
                    identity = build_identity(manifest_path=path)
                    self.assertEqual(identity.label, f"v{__version__}" if release else f"v{__version__}-dev · aaaaaaa")
            path.write_text('{"version": "9.9.9", "commit": "wrong", "release": true}', encoding="utf-8")
            identity = build_identity(manifest_path=path)
            self.assertFalse(identity.release)
            self.assertIn("-dev", identity.label)

    def test_client_and_windows_resource_use_package_version(self):
        first = json.loads(_codex_request_lines().splitlines()[0])
        self.assertEqual(first["params"]["clientInfo"]["version"], __version__)
        resource = version_resource(f"v{__version__}-dev+abcdef0")
        ast.parse(resource, mode="eval")
        self.assertIn(f"ProductVersion', 'v{__version__}-dev+abcdef0'", resource)
        self.assertIn(f"filevers=({', '.join(__version__.split('.'))}, 0)", resource)


if __name__ == "__main__":
    unittest.main()

