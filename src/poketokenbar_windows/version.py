"""Build identity derived from the package version and the exact Git tag."""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import __version__


@dataclass(frozen=True)
class BuildIdentity:
    version: str
    commit: str
    release: bool

    @property
    def label(self) -> str:
        if self.release:
            return f"v{self.version}"
        short = self.commit[:7] if self.commit else "unknown"
        return f"v{self.version}-dev · {short}"


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True, capture_output=True, text=True, timeout=2,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""


def build_identity(
    manifest_path: Path | None = None,
    source_root: Path | None = None,
) -> BuildIdentity:
    """Read the bundled manifest; in a source checkout use Git at the current HEAD."""
    if manifest_path is None and getattr(sys, "frozen", False):
        manifest_path = Path(sys.executable).resolve().parent / "build-info.json"
    if manifest_path is not None:
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            if data.get("version") == __version__:
                commit = data.get("commit", "")
                release = data.get("release") is True
                if isinstance(commit, str) and (not release or len(commit) == 40):
                    return BuildIdentity(__version__, commit, release)
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        return BuildIdentity(__version__, "", False)
    root = source_root or Path(__file__).resolve().parents[2]
    commit = _git(root, "rev-parse", "HEAD")
    if len(commit) != 40:
        return BuildIdentity(__version__, "", False)
    tags = _git(root, "tag", "--points-at", "HEAD", "--list", f"v{__version__}").splitlines()
    return BuildIdentity(__version__, commit, f"v{__version__}" in tags)
