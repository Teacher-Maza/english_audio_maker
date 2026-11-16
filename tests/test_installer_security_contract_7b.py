
from _rc_bootstrap import V2_ROOT

import ast
import sys
from pathlib import Path


PROJECT_ROOT = V2_ROOT
sys.path.insert(0, str(PROJECT_ROOT))

installer = V2_ROOT / "installer"
bootstrap = (installer / "installer_bootstrap.py").read_text(encoding="utf-8")
runtime_main = (V2_ROOT / "app" / "main.py").read_text(encoding="utf-8")
build = (installer / "build_installer.py").read_text(encoding="utf-8")
launcher = (installer / "Launch.cmd").read_text(encoding="utf-8")
inno = (installer / "EnglishAudioMakerV2_RC.iss").read_text(encoding="utf-8")

for forbidden in (
    "KeyValidator",
    "request_install_key",
    "needs_key",
    "key_saved",
    "_EXPECTED_DIGEST",
    "MAX_ATTEMPTS",
    "simpledialog",
    "hmac.compare_digest",
):
    assert forbidden not in bootstrap
assert "askstring(" not in bootstrap and 'show="*"' not in bootstrap
assert "VTS_V2_HUMANIZATION_A_DATA_ROOT=%LOCALAPPDATA%\\EnglishAudioMakerV2HumanizationAData" in launcher
assert "HF_HUB_OFFLINE=1" in launcher
assert "TCL_LIBRARY=%~dp0runtime\\tcl\\tcl8.6" in launcher
assert "TK_LIBRARY=%~dp0runtime\\tcl\\tk8.6" in launcher
assert "tests" in build and "backups" in build
assert 'AppId={{A47E24D7-8D8E-4E0C-A2B4-7F6B4DD67A20}' in inno
assert 'DefaultDirName={localappdata}\\Programs\\EnglishAudioMakerV2HumanizationA' in inno
assert "CreateUninstallRegKey=yes" in inno
uninstall_delete = inno.split("[UninstallDelete]", 1)[1].split("[", 1)[0]
assert 'Type: filesandordirs;' not in uninstall_delete, "Uninstall must preserve user-added files"
assert 'Type: dirifempty; Name: "{app}"' in uninstall_delete
assert 'Type: files; Name: "{app}\\.installation.json"' in uninstall_delete
assert 'AppName=English Audio Maker' in inno
assert 'AppVersion=2.0.0' in inno
assert 'OutputBaseFilename=EnglishAudioMaker_2.0.0_Setup' in inno
assert 'OutputDir=..\\temp\\final_candidate' in inno
assert 'Compression=lzma2/normal' in inno and 'SolidCompression=no' in inno
assert 'SetupIconFile=..\\app\\ui\\assets\\EnglishAudioMaker.ico' in inno
assert 'UninstallDisplayIcon={app}\\v2_kokoro\\app\\ui\\assets\\EnglishAudioMaker.ico' in inno
assert inno.count('IconFilename: "{app}\\v2_kokoro\\app\\ui\\assets\\EnglishAudioMaker.ico"') == 1
assert 'Name: "desktopicon"' in inno and 'Flags: unchecked' in inno
assert 'Name: "{autodesktop}\\English Audio Maker"' not in inno
assert "procedure CreateDesktopShortcutAfterPayload();" in inno
assert "DesktopIconFilename := ExpandConstant('{app}\\v2_kokoro\\app\\ui\\assets\\EnglishAudioMaker.ico');" in inno
assert "if not FileExists(DesktopIconFilename) then begin" in inno
assert "CreateShellLink(" in inno and "DesktopIconFilename," in inno
assert "CreateDesktopShortcutAfterPayload();" in inno
assert 'Type: files; Name: "{autodesktop}\\English Audio Maker.lnk"' in inno
assert 'Source: "{#PayloadRoot}\\*"; DestDir: "{app}"' in inno
assert '{tmp}\\EAMV2RC' not in inno
assert '--direct-finalize --install-root' in inno
assert 'WizardForm.ProgressGauge.Style := npbstMarquee;' in inno
assert 'Installer stage start:' in inno and 'Installer stage end:' in inno
assert (V2_ROOT / "app" / "ui" / "assets" / "EnglishAudioMaker.ico").is_file()
assert 'Uninstall.cmd", PAYLOAD_DIR' not in build
assert 'uninstall_runtime.py", PAYLOAD_DIR' not in build
assert '("unins*.exe", "unins*.dat", "unins*.msg")' in bootstrap
assert 'def finalize_direct_install(' in bootstrap
assert 'def _is_inno_deployment_artifact(' in bootstrap
assert 'ignored.add("inno_setup_6_7_3")' in build
assert 'create_deterministic_zip' not in build and 'IExpress' not in build

for path in (installer / "installer_bootstrap.py", installer / "uninstall_runtime.py", installer / "build_installer.py"):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess":
                shell = [keyword for keyword in node.keywords if keyword.arg == "shell"]
                assert shell and isinstance(shell[0].value, ast.Constant) and shell[0].value.value is False

print("Installer security: zero installation authentication, direct runtime, offline launcher and shell=False OK")
