@echo off
setlocal
set "PTB_STATE_DIR=%APPDATA%\PokeTokenBar-Windows-Test"
set "PTB_CACHE_DIR=%LOCALAPPDATA%\PokeTokenBar-Windows-Test\Cache"
if not exist "%~dp0PokeTokenBar-Windows.exe" (
    echo Non se atopou PokeTokenBar-Windows.exe xunto a este lanzador.
    pause
    exit /b 1
)
start "" "%~dp0PokeTokenBar-Windows.exe"
