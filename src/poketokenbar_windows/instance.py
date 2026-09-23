"""Hold an operating-system lock while a save directory is in use."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class InstanceAlreadyRunning(RuntimeError):
    """Another current build already owns this save directory."""


@contextmanager
def exclusive_state_instance(state_path: Path) -> Iterator[None]:
    """Reject a second process using the same state.json until this one exits."""
    lock_path = state_path.with_name(f".{state_path.name}.instance.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as stream:
        try:
            if os.name == "nt":
                import msvcrt

                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise InstanceAlreadyRunning(f"Save directory is already in use: {state_path.parent}") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
