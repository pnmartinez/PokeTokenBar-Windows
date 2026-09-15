from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# User-facing branding is intentionally shorter than the stable Windows IDs below.
APP_NAME = "PokeTokenBar"
REGISTRY_VALUE_NAME = "PokeTokenBar Windows"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CAPTION = 0x00C00000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000


def user_profile() -> Path:
    return Path(os.environ.get("USERPROFILE") or Path.home()).expanduser()


def roaming_appdata() -> Path:
    return Path(os.environ.get("APPDATA") or (user_profile() / "AppData/Roaming")).expanduser()


def local_appdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or (user_profile() / "AppData/Local")).expanduser()


def state_dir() -> Path:
    override = os.environ.get("PTB_STATE_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return roaming_appdata() / "PokeTokenBar-Windows"


def cache_dir() -> Path:
    override = os.environ.get("PTB_CACHE_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return local_appdata() / "PokeTokenBar-Windows/Cache"


def claude_desktop_roots() -> list[Path]:
    """Best-effort native Windows Claude Desktop embedded-session roots."""
    roots: list[Path] = []
    for data_root in claude_desktop_data_roots():
        roots.extend([
            data_root / "local-agent-mode-sessions",
            data_root / "claude-code-sessions",
        ])
    return roots


def claude_desktop_data_roots() -> list[Path]:
    """Return classic and Microsoft Store data roots for Claude Desktop."""
    roots = [roaming_appdata() / "Claude", local_appdata() / "Claude"]
    packages = local_appdata() / "Packages"
    try:
        store_packages = sorted(packages.glob("Claude_*"))
    except OSError:
        store_packages = []
    roots.extend(
        package / "LocalCache/Roaming/Claude"
        for package in store_packages
        if package.is_dir()
    )

    out: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve(strict=False)).casefold()
        if key not in seen:
            seen.add(key)
            out.append(root)
    return out


def claude_plan_usage_paths() -> list[Path]:
    """Candidate local histories written by current Claude Desktop builds."""
    return [root / "plan-usage-history.json" for root in claude_desktop_data_roots()]


def cursor_database_candidates() -> list[Path]:
    return [
        roaming_appdata() / "Cursor/User/globalStorage/state.vscdb",
        roaming_appdata() / "Cursor - Nightly/User/globalStorage/state.vscdb",
        roaming_appdata() / "Cursor Nightly/User/globalStorage/state.vscdb",
    ]


def kiro_database_candidates() -> list[Path]:
    # Kiro CLI's Windows installer/runtime lives under Local AppData.  The
    # conversation database has moved between per-user application-data layouts
    # across Kiro generations, so probe both native AppData roots plus the
    # portable ~/.kiro fallback and honor KIRO_CLI_HOME before these candidates.
    return [
        local_appdata() / "kiro-cli/data.sqlite3",
        local_appdata() / "Kiro-Cli/data.sqlite3",
        roaming_appdata() / "kiro-cli/data.sqlite3",
        user_profile() / ".kiro/data.sqlite3",
    ]


def hidden_subprocess_kwargs() -> dict:
    """Prevent Windows from flashing a console when spawning CLI helpers."""
    if os.name != "nt":
        return {}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {"creationflags": flags, "startupinfo": startupinfo}


def resolve_gui_binary(path: str) -> str:
    candidate = Path(path)
    if candidate.suffix.lower() in {".cmd", ".bat"}:
        exe = candidate.with_suffix(".exe")
        if exe.exists():
            return str(exe)
    return path


def gui_python() -> Path:
    python = Path(sys.executable)
    if python.name.lower() == "python.exe":
        pythonw = python.with_name("pythonw.exe")
        if pythonw.exists():
            return pythonw
    return python


def startup_command() -> str:
    """Command stored in HKCU Run. Prefer a frozen GUI exe, then console-free Python."""
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable)}" --background'
    return f'"{gui_python()}" -m poketokenbar_windows --background'


def autostart_enabled() -> bool:
    if os.name != "nt":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, kind = winreg.QueryValueEx(key, REGISTRY_VALUE_NAME)
        return kind == winreg.REG_SZ and bool(str(value).strip())
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    if os.name != "nt":
        raise RuntimeError("Windows login startup is only available on Windows")
    import winreg

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, REGISTRY_VALUE_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, REGISTRY_VALUE_NAME)
            except FileNotFoundError:
                pass


def refresh_autostart_registration() -> None:
    """Upgrade this executable's old login entry without claiming another build."""
    if os.name != "nt":
        return
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            command, kind = winreg.QueryValueEx(key, REGISTRY_VALUE_NAME)
        if kind != winreg.REG_SZ:
            return
        if getattr(sys, "frozen", False):
            old_command = f'"{Path(sys.executable)}"'
        else:
            old_command = f'"{gui_python()}" -m poketokenbar_windows'
        if str(command).strip().casefold() == old_command.casefold():
            set_autostart(True)
    except OSError:
        pass


def apply_native_window_icon(hwnd: int, ico_path: Path) -> None:
    """Force the Win32 window/taskbar icon; Qt alone often keeps pythonw.exe."""
    if os.name != "nt" or not hwnd or not ico_path.exists():
        return
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = wintypes.LPARAM

    image_icon = 1
    load_from_file = 0x00000010
    path = str(ico_path)
    small = user32.LoadImageW(None, path, image_icon, 16, 16, load_from_file)
    big = user32.LoadImageW(None, path, image_icon, 256, 256, load_from_file) or user32.LoadImageW(
        None, path, image_icon, 32, 32, load_from_file
    )
    if small:
        user32.SendMessageW(hwnd, 0x0080, 0, small)
    if big:
        user32.SendMessageW(hwnd, 0x0080, 1, big)


def _window_long_functions(user32):
    """Return pointer-width Win32 style accessors for 32- and 64-bit Python."""
    import ctypes
    from ctypes import wintypes

    get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    get_long.argtypes = [wintypes.HWND, ctypes.c_int]
    get_long.restype = ctypes.c_ssize_t
    set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    set_long.restype = ctypes.c_ssize_t
    return get_long, set_long


def apply_floating_tool_window_style(hwnd: int) -> None:
    """Keep the interactive pet above windows but out of taskbar and Alt+Tab."""
    if os.name != "nt" or not hwnd:
        return
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    get_long, set_long = _window_long_functions(user32)
    ex_style = int(get_long(hwnd, GWL_EXSTYLE))
    ex_style = (ex_style | WS_EX_TOOLWINDOW | WS_EX_TOPMOST) & ~WS_EX_APPWINDOW
    set_long(hwnd, GWL_EXSTYLE, ex_style)
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    hwnd_topmost = wintypes.HWND(-1)
    swp_nomove = 0x0002
    swp_nosize = 0x0001
    swp_noactivate = 0x0010
    swp_framechanged = 0x0020
    user32.SetWindowPos(
        hwnd,
        hwnd_topmost,
        0,
        0,
        0,
        0,
        swp_nomove | swp_nosize | swp_noactivate | swp_framechanged,
    )


def native_window_styles(hwnd: int) -> dict[str, int]:
    """Read native style bits for diagnostic/QA tooling without changing the window."""
    if os.name != "nt" or not hwnd:
        return {"style": 0, "ex_style": 0}
    import ctypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    get_long, _ = _window_long_functions(user32)
    return {
        "style": int(get_long(hwnd, GWL_STYLE)),
        "ex_style": int(get_long(hwnd, GWL_EXSTYLE)),
    }


def open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
        return
    subprocess.Popen(["xdg-open", str(path)])
