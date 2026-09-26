"""Asynchronous discovery of the latest normal Windows GitHub Release."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import __version__
from .version import BuildIdentity, build_identity

LATEST_RELEASE_API = "https://api.github.com/repos/pnmartinez/PokeTokenBar-Windows/releases/latest"
_RELEASE_PATH = "/pnmartinez/PokeTokenBar-Windows/releases/tag/"
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True)
class UpdateState:
    status: str  # idle, checking, available, current, no_release, offline, invalid
    version: str = ""
    url: str = ""
    detail: str = ""


def version_tuple(value: str) -> tuple[int, int, int] | None:
    match = _VERSION.fullmatch(value)
    return tuple(map(int, match.groups())) if match else None


def interpret_latest_release(
    status_code: int | None,
    body: bytes,
    error: str | None,
    identity: BuildIdentity,
) -> UpdateState:
    if status_code == 404:
        return UpdateState("no_release")
    if error is not None:
        return UpdateState("offline", detail=error)
    if status_code != 200:
        return UpdateState("offline", detail=f"HTTP {status_code}")
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("Release response is not an object")
        tag = payload["tag_name"]
        url = payload["html_url"]
        if not isinstance(tag, str) or not isinstance(url, str):
            raise ValueError("Release tag or URL is invalid")
        latest = version_tuple(tag)
        current = version_tuple(identity.version)
        parsed = urlparse(url)
        if (latest is None or current is None or
            parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or
            parsed.path != _RELEASE_PATH + tag or
            payload.get("draft") is not False or
            payload.get("prerelease") is not False):
            raise ValueError("Release response failed validation")
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        return UpdateState("invalid", detail=str(exc))
    if latest > current or (latest == current and not identity.release):
        return UpdateState("available", tag, url)
    return UpdateState("current", tag, url)


class GitHubReleaseTransport(QObject):
    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self._replies: set[QNetworkReply] = set()

    def get(self, callback: Callable[[int | None, bytes, str | None], None]) -> None:
        request = QNetworkRequest(QUrl(LATEST_RELEASE_API))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"User-Agent", f"PokeTokenBar-Windows/{__version__}".encode("ascii"))
        request.setTransferTimeout(8000)
        reply = self.manager.get(request)
        self._replies.add(reply)

        def finished() -> None:
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            data = bytes(reply.readAll())
            error = None if reply.error() == QNetworkReply.NetworkError.NoError else reply.errorString()
            self._replies.discard(reply)
            reply.deleteLater()
            callback(status if isinstance(status, int) else None, data, error)

        reply.finished.connect(finished)


class UpdateChecker(QObject):
    stateChanged = Signal(object)

    def __init__(
        self,
        identity: BuildIdentity | None = None,
        transport: GitHubReleaseTransport | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.identity = identity or build_identity()
        self.transport = transport or GitHubReleaseTransport(self)
        self.state = UpdateState("idle")
        self.automatic_started = False
        self.in_flight = False

    def start_automatic(self) -> bool:
        if self.automatic_started:
            return False
        self.automatic_started = True
        return self.check_now()

    def check_now(self) -> bool:
        if self.in_flight:
            return False
        self.in_flight = True
        self._set_state(UpdateState("checking"))
        try:
            self.transport.get(self._on_result)
        except Exception as exc:
            self._on_result(None, b"", str(exc))
        return True

    def _on_result(self, status: int | None, body: bytes, error: str | None) -> None:
        self.in_flight = False
        self._set_state(interpret_latest_release(status, body, error, self.identity))

    def _set_state(self, state: UpdateState) -> None:
        self.state = state
        self.stateChanged.emit(state)
