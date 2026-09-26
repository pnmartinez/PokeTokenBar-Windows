"""Write Windows EXE version resource for PyInstaller."""
from __future__ import annotations

import argparse
from pathlib import Path

from poketokenbar_windows import __version__


def version_resource(display_version: str) -> str:
    components = tuple(int(part) for part in __version__.split("."))
    if len(components) != 3:
        raise ValueError("Windows resource version requires three numeric components")
    numbers = (*components, 0)
    fields = {
        "CompanyName": "PokeTokenBar Windows contributors",
        "FileDescription": "PokeTokenBar for Windows",
        "FileVersion": display_version,
        "InternalName": "PokeTokenBar-Windows",
        "OriginalFilename": "PokeTokenBar-Windows.exe",
        "ProductName": "PokeTokenBar-Windows",
        "ProductVersion": display_version,
    }
    strings = ",\n            ".join(
        f"StringStruct({key!r}, {value!r})" for key, value in fields.items()
    )
    return f"""VSVersionInfo(
    ffi=FixedFileInfo(
        filevers={numbers!r}, prodvers={numbers!r},
        mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
        subtype=0x0, date=(0, 0)
    ),
    kids=[
        StringFileInfo([
            StringTable('040904B0', [
            {strings}
            ])
        ]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])])
    ]
)
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--display-version", required=True)
    args = parser.parse_args()
    args.path.write_text(version_resource(args.display_version), encoding="utf-8")


if __name__ == "__main__":
    main()

