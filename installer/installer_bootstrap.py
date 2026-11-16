from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path


APP_DIR_NAME = "EnglishAudioMakerV2HumanizationA"
DATA_DIR_NAME = "EnglishAudioMakerV2HumanizationAData"
APP_DISPLAY_NAME = "English Audio Maker"


def default_locations() -> tuple[Path, Path, Path]:
    local = Path(os.environ["LOCALAPPDATA"]).resolve()
    roaming = Path(os.environ["APPDATA"]).resolve()
    return (
        local / "Programs" / APP_DIR_NAME,
        local / DATA_DIR_NAME,
        roaming / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{APP_DISPLAY_NAME}.cmd",
    )


def _confine(path: Path, root: Path, label: str) -> Path:
    root = root.resolve(strict=False)
    candidate = path.resolve(strict=False)
    if candidate == root or root not in candidate.parents:
        raise ValueError(f"Unsafe {label}")
    current = root
    for part in candidate.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Symlink not allowed in {label}")
    return candidate


def validate_locations(install_root: Path, data_root: Path, *, allowed_root: Path | None = None) -> tuple[Path, Path]:
    root = (allowed_root or Path(os.environ["LOCALAPPDATA"])).resolve(strict=False)
    return _confine(install_root, root, "install root"), _confine(data_root, root, "data root")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_inno_deployment_artifact(relative: str) -> bool:
    """Allow only Inno's root-level files in an otherwise exact payload set."""
    parts = Path(relative).parts
    if len(parts) != 1:
        return False
    name = parts[0].lower()
    return name == ".installation.json" or (
        name.startswith("unins") and name.endswith((".exe", ".dat", ".msg"))
    )


def verify_payload(payload_root: Path) -> dict:
    manifest_path = payload_root / "PAYLOAD_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_paths: set[str] = set()
    for item in manifest.get("files", []):
        relative = item["path"]
        if relative.startswith("/") or ".." in Path(relative).parts:
            raise ValueError("Unsafe payload manifest path")
        path = (payload_root / relative).resolve()
        if payload_root.resolve() not in path.parents or not path.is_file():
            raise FileNotFoundError(relative)
        if path.stat().st_size != int(item["size"]) or sha256(path) != item["sha256"]:
            raise ValueError("Payload integrity check failed")
        expected_paths.add(relative.replace("\\", "/"))
    actual_paths = {
        path.relative_to(payload_root).as_posix()
        for path in payload_root.rglob("*")
        if path.is_file()
        and path.name != "PAYLOAD_MANIFEST.json"
        and not _is_inno_deployment_artifact(path.relative_to(payload_root).as_posix())
    }
    if actual_paths != expected_paths:
        raise ValueError("Payload file set does not match manifest")
    return manifest


def finalize_direct_install(
    install_root: Path,
    data_root: Path,
    *,
    allowed_root: Path | None = None,
) -> dict:
    """Validate the payload Inno already copied, without a second full copy."""
    install_root, data_root = validate_locations(install_root, data_root, allowed_root=allowed_root)
    manifest = verify_payload(install_root)
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "audios" / "generated").mkdir(parents=True, exist_ok=True)
    marker = {
        "schema_version": "1.0",
        "version": manifest["version"],
        "installed_utc": datetime.now(timezone.utc).isoformat(),
        "data_root": str(data_root),
    }
    (install_root / ".installation.json").write_text(json.dumps(marker, indent=2), encoding="utf-8")
    return marker


def install_payload(
    payload_root: Path,
    install_root: Path,
    data_root: Path,
    *,
    start_menu_launcher: Path | None = None,
    allowed_root: Path | None = None,
) -> dict:
    payload_root = payload_root.resolve()
    manifest = verify_payload(payload_root)
    install_root, data_root = validate_locations(install_root, data_root, allowed_root=allowed_root)
    install_root.parent.mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "audios" / "generated").mkdir(parents=True, exist_ok=True)

    # Torch contains deeply nested files, so transaction paths must stay short
    # enough for Windows installations without long-path support enabled.
    transaction = install_root.parent / f".v2i-{uuid.uuid4().hex[:8]}"
    previous = install_root.parent / f".v2p-{uuid.uuid4().hex[:8]}"
    shutil.copytree(payload_root, transaction)
    # Inno creates its uninstaller in {app}.  The transactional payload swap
    # must carry those files forward instead of replacing them with the app
    # payload.  Only Inno's root-level uninstaller artifacts are preserved.
    if install_root.is_dir():
        for pattern in ("unins*.exe", "unins*.dat", "unins*.msg"):
            for uninstaller in install_root.glob(pattern):
                if uninstaller.is_file() and not uninstaller.is_symlink():
                    shutil.copy2(uninstaller, transaction / uninstaller.name)
    marker = {
        "schema_version": "1.0",
        "version": manifest["version"],
        "installed_utc": datetime.now(timezone.utc).isoformat(),
        "data_root": str(data_root),
    }
    (transaction / ".installation.json").write_text(json.dumps(marker, indent=2), encoding="utf-8")
    try:
        if install_root.exists():
            install_root.rename(previous)
        transaction.rename(install_root)
        if previous.exists():
            shutil.rmtree(previous)
    except Exception:
        if transaction.exists():
            shutil.rmtree(transaction)
        if previous.exists() and not install_root.exists():
            previous.rename(install_root)
        raise

    if start_menu_launcher is not None:
        start_menu_launcher.parent.mkdir(parents=True, exist_ok=True)
        start_menu_launcher.write_text(f'@echo off\r\ncall "{install_root / "Launch.cmd"}"\r\n', encoding="utf-8")
    return marker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--payload")
    parser.add_argument("--direct-finalize", action="store_true")
    parser.add_argument("--install-root")
    args = parser.parse_args(argv)
    install_root, data_root, start_menu = default_locations()
    if args.direct_finalize:
        if not args.install_root:
            raise ValueError("--install-root is required for direct finalization")
        install_root = Path(args.install_root).resolve()
    elif not args.payload:
        raise ValueError("--payload is required for transactional installation")

    try:
        if args.direct_finalize:
            finalize_direct_install(install_root, data_root)
        else:
            install_payload(Path(args.payload).resolve(), install_root, data_root, start_menu_launcher=start_menu)
    except Exception:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
