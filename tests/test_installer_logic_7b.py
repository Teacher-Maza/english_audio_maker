
from _rc_bootstrap import V2_ROOT

import hashlib
import json
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = V2_ROOT
sys.path.insert(0, str(PROJECT_ROOT))

from v2_kokoro.installer.installer_bootstrap import install_payload  # noqa: E402
from v2_kokoro.installer.uninstall_runtime import remove_installation  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(payload: Path, version: str) -> None:
    files = []
    for path in sorted(item for item in payload.rglob("*") if item.is_file() and item.name != "PAYLOAD_MANIFEST.json"):
        files.append({"path": path.relative_to(payload).as_posix(), "size": path.stat().st_size, "sha256": digest(path)})
    (payload / "PAYLOAD_MANIFEST.json").write_text(
        json.dumps({"schema_version": "1.0", "version": version, "files": files}, indent=2),
        encoding="utf-8",
    )


test_root = V2_ROOT / "temp" / "phase_7b_installer_logic"
payload = test_root / "payload"
install = test_root / "installed"
data = test_root / "data"
start_menu = test_root / "start_menu" / "English Audio Maker V2 – Humanization A.cmd"
if test_root.exists():
    shutil.rmtree(test_root)
try:
    (payload / "runtime").mkdir(parents=True)
    (payload / "Launch.cmd").write_text("@echo off\r\n", encoding="utf-8")
    (payload / "runtime" / "runtime.txt").write_text("version one", encoding="utf-8")
    write_manifest(payload, "2.0.0-pilot")
    install.mkdir(parents=True)
    (install / "unins000.exe").write_bytes(b"inno-exe")
    (install / "unins000.dat").write_bytes(b"inno-dat")
    install_payload(payload, install, data, start_menu_launcher=start_menu, allowed_root=test_root)
    assert (install / "unins000.exe").read_bytes() == b"inno-exe"
    assert (install / "unins000.dat").read_bytes() == b"inno-dat"
    marker = json.loads((install / ".installation.json").read_text(encoding="utf-8"))
    assert set(marker) == {"schema_version", "version", "installed_utc", "data_root"}
    sentinel = data / "audios" / "generated" / "keep.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    (payload / "runtime" / "runtime.txt").write_text("version two", encoding="utf-8")
    write_manifest(payload, "2.0.1-pilot")
    install_payload(payload, install, data, start_menu_launcher=start_menu, allowed_root=test_root)
    assert (install / "runtime" / "runtime.txt").read_text(encoding="utf-8") == "version two"
    assert (install / "unins000.exe").read_bytes() == b"inno-exe"
    assert (install / "unins000.dat").read_bytes() == b"inno-dat"
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert (install / ".installation.json").is_file()

    remove_installation(install, data, start_menu, allowed_root=test_root, immediate=True)
    assert not install.exists() and not start_menu.exists()
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert not list(test_root.glob(".v2i-*"))
    assert not list(test_root.glob(".v2p-*"))
finally:
    if test_root.exists():
        shutil.rmtree(test_root)

print("Installer logic: no authentication, safe update and data-preserving uninstall OK")
