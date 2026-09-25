from __future__ import annotations

import ctypes
import os
import sys

from .instance import InstanceAlreadyRunning, exclusive_state_instance
from .windows import APP_NAME, refresh_autostart_registration, state_dir


def _configure_windows_identity() -> None:
    if os.name != "nt":
        return
    try:
        app_id = "PokeTokenBar.Windows.Isolated" if os.environ.get("PTB_STATE_DIR", "").strip() else "PokeTokenBar.Windows"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except (AttributeError, OSError):
        pass


def _hide_console_window() -> None:
    if os.name != "nt":
        return
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except (AttributeError, OSError):
        pass


def _background_launch_requested(argv: list[str] | None = None) -> bool:
    arguments = sys.argv if argv is None else argv
    return "--background" in arguments[1:]


def main() -> int:
    background_launch = _background_launch_requested()
    refresh_autostart_registration()
    _configure_windows_identity()
    _hide_console_window()
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication, QMessageBox

    from .ui import TrayController, application_icon

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    qt_argv = [argument for argument in sys.argv if argument != "--background"]
    app = QApplication(qt_argv)
    icon = application_icon()
    app.setWindowIcon(icon)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("PokeTokenBar")
    app.setQuitOnLastWindowClosed(False)

    try:
        with exclusive_state_instance(state_dir() / "state.json"):
            controller = TrayController(app)
            # Interactive launches request the window after the first real snapshot.
            # The Windows login entry keeps the application in the tray.
            if not background_launch:
                controller.show_window()

            app._poketokenbar_controller = controller  # keep QObject graph alive
            return app.exec()
    except InstanceAlreadyRunning:
        if not background_launch:
            QMessageBox.warning(
                None,
                APP_NAME,
                "PokeTokenBar is already using this save folder. Open the existing "
                "window from the tray. To test another build, set PTB_STATE_DIR "
                "to a separate folder.",
            )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
