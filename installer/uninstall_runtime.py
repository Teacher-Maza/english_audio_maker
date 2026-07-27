from __future__ import annotations

import base64
import os
import shutil
import subprocess
from pathlib import Path
from tkinter import messagebox


APP_DIR_NAME = "EnglishAudioMakerV2HumanizationA"
DATA_DIR_NAME = "EnglishAudioMakerV2HumanizationAData"
APP_DISPLAY_NAME = "English Audio Maker V2 – Humanization A"


def default_locations() -> tuple[Path, Path, Path]:
    local = Path(os.environ["LOCALAPPDATA"]).resolve()
    roaming = Path(os.environ["APPDATA"]).resolve()
    return (
        local / "Programs" / APP_DIR_NAME,
        local / DATA_DIR_NAME,
        roaming / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{APP_DISPLAY_NAME}.cmd",
    )


def _validate_install_root(install_root: Path, allowed_root: Path) -> Path:
    resolved = install_root.resolve(strict=False)
    allowed = allowed_root.resolve(strict=False)
    if resolved == allowed or allowed not in resolved.parents:
        raise ValueError("Unsafe uninstall path")
    return resolved


def remove_installation(
    install_root: Path,
    data_root: Path,
    start_menu_launcher: Path | None,
    *,
    allowed_root: Path,
    immediate: bool = False,
) -> None:
    install_root = _validate_install_root(install_root, allowed_root)
    if start_menu_launcher is not None and start_menu_launcher.is_file():
        start_menu_launcher.unlink()
    if immediate:
        if install_root.exists():
            shutil.rmtree(install_root)
        return

    quoted = str(install_root).replace("'", "''")
    command = f"Start-Sleep -Seconds 2; if (Test-Path -LiteralPath '{quoted}') {{ Remove-Item -LiteralPath '{quoted}' -Recurse -Force }}"
    encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        shell=False,
        close_fds=True,
        creationflags=flags,
    )


def main() -> int:
    install_root, data_root, start_menu = default_locations()
    if not messagebox.askyesno(
        "Desinstalar",
        "Remover o aplicativo? Seus WAV, MP3 e logs serao preservados.",
    ):
        return 1
    remove_installation(
        install_root,
        data_root,
        start_menu,
        allowed_root=Path(os.environ["LOCALAPPDATA"]),
        immediate=False,
    )
    messagebox.showinfo("Desinstalacao iniciada", f"Dados preservados em:\n{data_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
