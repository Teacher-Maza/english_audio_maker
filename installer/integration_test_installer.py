from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = V2_ROOT / "dist"
BUILD_PAYLOAD = V2_ROOT / "temp" / "build_humanization_a" / "payload"
TEST_ROOT = Path(tempfile.gettempdir()) / "EAMV2HumanizationAInstallTest"
sys.path.insert(0, str(V2_ROOT))

from app.main import _bind_runtime_package

_bind_runtime_package()

from v2_kokoro.installer.installer_bootstrap import install_payload, verify_payload  # noqa: E402
from v2_kokoro.installer.uninstall_runtime import remove_installation  # noqa: E402


def run() -> dict:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)
    TEST_ROOT.mkdir()
    install_root = TEST_ROOT / "LocalAppData" / "Programs" / "EnglishAudioMakerV2HumanizationA"
    data_root = TEST_ROOT / "LocalAppData" / "EnglishAudioMakerV2HumanizationAData"
    start_menu = TEST_ROOT / "Roaming" / "StartMenu" / "English Audio Maker V2 – Humanization A.cmd"
    backend_result = TEST_ROOT / "installed_backend_result.json"
    try:
        manifest = verify_payload(BUILD_PAYLOAD)
        install_payload(
            BUILD_PAYLOAD,
            install_root,
            data_root,
            start_menu_launcher=start_menu,
            allowed_root=TEST_ROOT,
        )
        if not (install_root / ".installation.json").is_file():
            raise RuntimeError("Installation marker was not created")

        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(TEST_ROOT / "LocalAppData")
        env["APPDATA"] = str(TEST_ROOT / "Roaming")
        env["VTS_V2_HUMANIZATION_A_DATA_ROOT"] = str(data_root)
        runtime = install_root / "runtime" / "python.exe"
        helper = V2_ROOT / "installer" / "run_installed_backend_tests.py"
        completed = subprocess.run(
            [str(runtime), "-B", str(helper), str(install_root), str(data_root), str(backend_result)],
            check=False,
            capture_output=True,
            text=True,
            shell=False,
            timeout=600,
            env=env,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Installed backend tests failed: {completed.stderr[-2000:]}")
        backend = json.loads(backend_result.read_text(encoding="utf-8"))

        sentinel = data_root / "audios" / "generated" / "PRESERVE_ON_UPDATE.txt"
        sentinel.write_text("preserve", encoding="utf-8")
        install_payload(
            BUILD_PAYLOAD,
            install_root,
            data_root,
            start_menu_launcher=start_menu,
            allowed_root=TEST_ROOT,
        )
        if sentinel.read_text(encoding="utf-8") != "preserve":
            raise RuntimeError("Update did not preserve data")

        ui_process = subprocess.Popen(
            [str(install_root / "runtime" / "python.exe"), "-B", str(install_root / "v2_kokoro" / "app" / "main.py")],
            shell=False,
            env=env,
        )
        time.sleep(3)
        opened_directly = ui_process.poll() is None
        ui_process.terminate()
        try:
            ui_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            ui_process.kill()
        if not opened_directly:
            raise RuntimeError("Installed UI did not open directly")

        remove_installation(install_root, data_root, start_menu, allowed_root=TEST_ROOT, immediate=True)
        removed = not install_root.exists() and not start_menu.exists()
        data_preserved = sentinel.is_file()
        if not removed or not data_preserved:
            raise RuntimeError("Uninstall removal/preservation test failed")

        result = {
            "schema_version": "1.0",
            "payload_files": len(manifest["files"]),
            "installed_without_authentication": True,
            "later_open_directly": opened_directly,
            "offline": backend["offline_guard"],
            "narration_and_dialogue": len(backend["generation_results"]) == 2,
            "cancelled_safely": backend["cancelled"],
            "update_preserved_data": True,
            "uninstall_removed_app": removed,
            "uninstall_preserved_data": data_preserved,
            "generation_results": backend["generation_results"],
        }
        (DIST_DIR / "INTEGRATION_TEST_7B.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    finally:
        if TEST_ROOT.exists():
            shutil.rmtree(TEST_ROOT)


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
