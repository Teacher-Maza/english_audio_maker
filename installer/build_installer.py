from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
INSTALLER_DIR = V2_ROOT / "installer"
TERMS_OF_USE_SOURCE = INSTALLER_DIR / "TERMS_OF_USE_PTBR.txt"
# Keep every generated file under the release candidate.  This makes the
# packaging process reproducible and avoids relying on a machine-wide TEMP
# directory (which also makes diagnostic cleanup safer).
BUILD_DIR = V2_ROOT / "temp" / "build_humanization_a"
PAYLOAD_DIR = BUILD_DIR / "payload"
PYTHON_BASE = V2_ROOT / "runtime"
SITE_PACKAGES = PYTHON_BASE / "Lib" / "site-packages"
VERSION = "2.0.0"
FIXED_TIMESTAMP = 1735689600
CONFIG_ALLOWLIST = (
    "paths.json",
    "resource_policy.json",
    "voices.json",
    "voice_preview_catalog.json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_remove(path: Path) -> None:
    resolved = path.resolve(strict=False)
    build_root = BUILD_DIR.resolve(strict=False)
    if resolved != build_root and build_root not in resolved.parents:
        raise ValueError("Refusing to clean outside installer staging")
    if resolved.exists():
        shutil.rmtree(resolved)


def common_ignore(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in {"__pycache__", "tests", "test"} or name.endswith((".pyc", ".pyo"))
    }


def site_packages_ignore(directory: str, names: list[str]) -> set[str]:
    ignored = common_ignore(directory, names)
    current = Path(directory).resolve()
    if current == SITE_PACKAGES.resolve():
        ignored.update({"pip", "pip-25.0.1.dist-info"})
    if current == (SITE_PACKAGES / "torch").resolve():
        # Runtime inference needs the Python modules and DLLs, not the C++/CUDA
        # development headers. Excluding them also avoids legacy MAX_PATH
        # failures in deeply nested ATen include names.
        ignored.add("include")
    torch_metadata = SITE_PACKAGES / "torch-2.13.0.dist-info"
    if current == torch_metadata.resolve():
        # Torch ships a very deep third-party license archive that exceeds the
        # traditional Windows path limit. Its primary license is bundled in
        # the installer's consolidated licenses directory instead.
        ignored.add("licenses")
    return ignored


def tools_ignore(directory: str, names: list[str]) -> set[str]:
    ignored = common_ignore(directory, names)
    if Path(directory).resolve() == (V2_ROOT / "tools").resolve():
        ignored.add("inno_setup_6_7_3")
    return ignored


def base_ignore(directory: str, names: list[str]) -> set[str]:
    ignored = common_ignore(directory, names)
    current = Path(directory).resolve()
    if current == PYTHON_BASE:
        ignored.update(name for name in names if name in {"Scripts", "Tools", "Doc", "include", "libs", "NEWS.txt"})
    if current == PYTHON_BASE / "Lib":
        ignored.update({"site-packages", "ensurepip", "idlelib", "venv"})
    return ignored


def copy_runtime() -> None:
    runtime = PAYLOAD_DIR / "runtime"
    shutil.copytree(PYTHON_BASE, runtime, ignore=base_ignore)
    target_site = runtime / "Lib" / "site-packages"
    shutil.copytree(SITE_PACKAGES, target_site, ignore=site_packages_ignore)


def copy_application() -> None:
    app_root = PAYLOAD_DIR / "v2_kokoro"
    shutil.copytree(V2_ROOT / "app", app_root / "app", ignore=common_ignore)
    target_config = app_root / "config"
    target_config.mkdir(parents=True)
    for name in CONFIG_ALLOWLIST:
        shutil.copy2(V2_ROOT / "config" / name, target_config / name)
    # Ship only the selected voices, even if other local voicepacks remain.
    catalog = json.loads((V2_ROOT / "config" / "voices.json").read_text(encoding="utf-8"))
    model_files = ["models/Kokoro-82M/config.json", "models/Kokoro-82M/kokoro-v1_0.pth"]
    model_files.extend(voice["voicepack_path"] for voice in catalog["voices"])
    for relative in model_files:
        source = (V2_ROOT / relative).resolve()
        if (V2_ROOT / "models").resolve() not in source.parents:
            raise ValueError("Unsafe model asset path")
        destination = app_root / source.relative_to(V2_ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    shutil.copytree(V2_ROOT / "tools", app_root / "tools", ignore=tools_ignore)
    shutil.copy2(V2_ROOT / "requirements.lock.txt", app_root / "requirements.lock.txt")

    assets = app_root / "assets" / "voice_previews"
    assets.mkdir(parents=True)
    voices_path = app_root / "config" / "voices.json"
    voices = json.loads(voices_path.read_text(encoding="utf-8"))
    for voice in voices["voices"]:
        source = V2_ROOT / voice["preview_wav_path"]
        destination = assets / source.name
        shutil.copy2(source, destination)
        voice["preview_wav_path"] = f"assets/voice_previews/{source.name}"
        voice.pop("preview_mp3_path", None)
        voice.pop("mp3_path", None)
        voice.pop("wav_path", None)
    voices_path.write_text(json.dumps(voices, indent=2), encoding="utf-8")

    preview_catalog = app_root / "config" / "voice_preview_catalog.json"
    catalog = json.loads(preview_catalog.read_text(encoding="utf-8"))
    for voice in catalog["voices"]:
        sample_name = Path(voice["preview_wav_path"]).name
        voice["preview_wav_path"] = f"assets/voice_previews/{sample_name}"
        voice.pop("preview_mp3_path", None)
        voice.pop("mp3_path", None)
        voice.pop("wav_path", None)
    preview_catalog.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    shutil.copy2(INSTALLER_DIR / "Launch.cmd", PAYLOAD_DIR / "Launch.cmd")


def copy_essential_documents() -> None:
    shutil.copy2(TERMS_OF_USE_SOURCE, PAYLOAD_DIR / "TERMS_OF_USE.txt")
    shutil.copy2(V2_ROOT / "LICENSE", PAYLOAD_DIR / "LICENSE.txt")


def spdx_id(name: str) -> str:
    return "SPDXRef-" + re.sub(r"[^A-Za-z0-9.-]", "-", name)


def create_licenses_and_sbom() -> None:
    licenses = PAYLOAD_DIR / "licenses"
    licenses.mkdir(parents=True)
    shutil.copy2(PYTHON_BASE / "LICENSE.txt", licenses / "PYTHON_LICENSE.txt")
    kokoro_license = SITE_PACKAGES / "kokoro-0.9.4.dist-info" / "licenses" / "LICENSE"
    shutil.copy2(kokoro_license, licenses / "KOKORO_APACHE_2_0.txt")
    gpl3_license = SITE_PACKAGES / "phonemizer_fork-3.3.2.dist-info" / "licenses" / "LICENSE"
    shutil.copy2(gpl3_license, licenses / "GPL_3_0.txt")
    torch_licenses = INSTALLER_DIR / "legal" / "TORCH_LICENSES.txt"
    shutil.copy2(torch_licenses, licenses / "TORCH_LICENSES.txt")

    packages = []
    notices = ["# Third-party notices", "", "Generated from installed package metadata; no network lookup was used.", ""]
    distributions = sorted(importlib.metadata.distributions(path=[str(SITE_PACKAGES)]), key=lambda item: (item.metadata.get("Name") or "").lower())
    for distribution in distributions:
        name = distribution.metadata.get("Name") or "unknown"
        if name.lower() == "pip":
            continue
        version = distribution.version or "unknown"
        declared = distribution.metadata.get("License-Expression") or distribution.metadata.get("License") or "NOASSERTION"
        packages.append({
            "SPDXID": spdx_id(f"pkg-{name}-{version}"),
            "name": name,
            "versionInfo": version,
            "downloadLocation": "NOASSERTION",
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": declared if len(declared) < 200 else "NOASSERTION",
            "supplier": "NOASSERTION",
        })
        notices.append(f"- {name} {version}: {declared[:200]}")

    packages.extend([
        {"SPDXID": "SPDXRef-App", "name": "English Audio Maker", "versionInfo": VERSION, "downloadLocation": "NOASSERTION", "licenseConcluded": "MIT", "licenseDeclared": "MIT", "supplier": "NOASSERTION"},
        {"SPDXID": "SPDXRef-KokoroModel", "name": "Kokoro-82M model and voicepacks", "versionInfo": "1.0", "downloadLocation": "NOASSERTION", "licenseConcluded": "Apache-2.0", "licenseDeclared": "Apache-2.0", "supplier": "Organization: hexgrad"},
        {"SPDXID": "SPDXRef-FFmpeg", "name": "FFmpeg portable", "versionInfo": "8.1.2", "downloadLocation": "NOASSERTION", "licenseConcluded": "NOASSERTION", "licenseDeclared": "GPL-3.0-or-later", "supplier": "Organization: FFmpeg project / Gyan.dev build"},
        {"SPDXID": "SPDXRef-Python", "name": "Python", "versionInfo": "3.12.10", "downloadLocation": "NOASSERTION", "licenseConcluded": "Python-2.0", "licenseDeclared": "Python-2.0", "supplier": "Organization: Python Software Foundation"},
    ])
    notices.extend([
        "",
        "- Kokoro-82M model and voicepacks: Apache-2.0.",
        "- Python 3.12.10: Python Software Foundation License; full text included.",
        "- PyTorch 2.13.0+cpu: wheel license files included in TORCH_LICENSES.txt.",
        "- FFmpeg portable 8.1.2: GPL-enabled build; source and license information: https://ffmpeg.org/ and https://www.gyan.dev/ffmpeg/builds/.",
    ])
    (licenses / "THIRD_PARTY_NOTICES.md").write_text("\n".join(notices) + "\n", encoding="utf-8")

    namespace_seed = "|".join(f"{item['name']}:{item['versionInfo']}" for item in packages)
    namespace = hashlib.sha256(namespace_seed.encode("utf-8")).hexdigest()
    sbom = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"English-Audio-Maker-V2-{VERSION}",
        "documentNamespace": f"urn:uuid:{namespace[:8]}-{namespace[8:12]}-{namespace[12:16]}-{namespace[16:20]}-{namespace[20:32]}",
        "creationInfo": {"created": "2026-07-11T00:00:00Z", "creators": ["Tool: v2_kokoro/installer/build_installer.py"]},
        "packages": packages,
    }
    (PAYLOAD_DIR / "SBOM.spdx.json").write_text(json.dumps(sbom, indent=2), encoding="utf-8")


def create_payload_manifest() -> dict:
    files = []
    for path in sorted(item for item in PAYLOAD_DIR.rglob("*") if item.is_file() and item.name != "PAYLOAD_MANIFEST.json"):
        files.append({"path": path.relative_to(PAYLOAD_DIR).as_posix(), "size": path.stat().st_size, "sha256": sha256(path)})
    manifest = {
        "schema_version": "1.0",
        "version": VERSION,
        "created_utc": "2026-07-11T00:00:00Z",
        "files": files,
        "exclusions": ["tests", "cache", "generated audio", "backups", "build scripts"],
        "bundled_assets": {"voice_preview_wav": len(json.loads((V2_ROOT / "config" / "voices.json").read_text(encoding="utf-8"))["voices"])},
    }
    path = PAYLOAD_DIR / "PAYLOAD_MANIFEST.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def validate_payload(manifest: dict) -> None:
    forbidden_prefixes = (
        "v2_kokoro/tests/",
        "v2_kokoro/backups/",
        "v2_kokoro/installer/",
        "v2_kokoro/scripts/",
        "v2_kokoro/cache/",
        "v2_kokoro/.venv/",
    )
    for item in manifest["files"]:
        normalized = item["path"].replace("\\", "/")
        if normalized.startswith(forbidden_prefixes) or "/__pycache__/" in f"/{normalized}" or normalized.endswith((".pyc", ".pyo")):
            raise RuntimeError(f"Forbidden payload entry: {item['path']}")
def normalize_timestamps() -> None:
    for path in sorted(PAYLOAD_DIR.rglob("*"), reverse=True):
        os.utime(path, (FIXED_TIMESTAMP, FIXED_TIMESTAMP))
    os.utime(PAYLOAD_DIR, (FIXED_TIMESTAMP, FIXED_TIMESTAMP))


def build(resume: bool = False) -> dict:
    """Stage the single payload consumed directly by the Inno installer."""
    if not resume:
        safe_remove(BUILD_DIR)
    if not resume:
        PAYLOAD_DIR.mkdir(parents=True)
    elif not (PAYLOAD_DIR / "PAYLOAD_MANIFEST.json").is_file():
        raise RuntimeError("No completed payload staging is available to resume")
    result_dir = BUILD_DIR / "stage_result"
    result_dir.mkdir(parents=True, exist_ok=True)

    if resume:
        payload_app = PAYLOAD_DIR / "v2_kokoro" / "app"
        if payload_app.exists():
            shutil.rmtree(payload_app)
        shutil.copytree(V2_ROOT / "app", payload_app, ignore=common_ignore)
    else:
        copy_runtime()
        copy_application()
        create_licenses_and_sbom()
    copy_essential_documents()
    manifest = create_payload_manifest()
    validate_payload(manifest)
    normalize_timestamps()

    shutil.copy2(PAYLOAD_DIR / "PAYLOAD_MANIFEST.json", result_dir / "PAYLOAD_MANIFEST.json")
    shutil.copy2(PAYLOAD_DIR / "SBOM.spdx.json", result_dir / "SBOM.spdx.json")

    result_data = {
        "schema_version": "1.0",
        "version": VERSION,
        "build_tool": "Inno Setup direct payload staging",
        "payload_files": len(manifest["files"]),
        "payload_bytes": sum(item["size"] for item in manifest["files"]),
        "payload_manifest_sha256": sha256(PAYLOAD_DIR / "PAYLOAD_MANIFEST.json"),
        "sbom_sha256": sha256(PAYLOAD_DIR / "SBOM.spdx.json"),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    (result_dir / "BUILD_RESULT_7B.json").write_text(json.dumps(result_data, indent=2), encoding="utf-8")
    return result_data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(resume=args.resume), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
