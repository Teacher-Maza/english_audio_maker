from _rc_bootstrap import V2_ROOT

import json


inno = (V2_ROOT / "installer" / "EnglishAudioMakerV2_RC.iss").read_text(encoding="utf-8")
launcher = (V2_ROOT / "installer" / "Launch.cmd").read_text(encoding="utf-8")
paths = (V2_ROOT / "app" / "core" / "project_paths.py").read_text(encoding="utf-8")
ui = (V2_ROOT / "app" / "ui" / "main_window.py").read_text(encoding="utf-8")
output_location = json.loads((V2_ROOT / "config" / "output_location.json").read_text(encoding="utf-8"))

assert "English Audio Maker V2 – Humanization A" in inno
assert "English Audio Maker V2 — B2 Official" in ui
assert "AppId={{A47E24D7-8D8E-4E0C-A2B4-7F6B4DD67A20}" in inno
assert "AppId={{CD94E4FC-B974-45DB-8D28-D4C1D6D634A2}" not in inno
assert "Programs\\EnglishAudioMakerV2HumanizationA" in inno
assert "EnglishAudioMakerV2HumanizationAData" in launcher
assert "VTS_V2_HUMANIZATION_A_DATA_ROOT" in launcher and "VTS_V2_HUMANIZATION_A_DATA_ROOT" in paths
assert "VTS_V2_DATA_ROOT" not in launcher and "VTS_V2_DATA_ROOT" not in paths
assert output_location == {"schema_version": 1, "selected_output_dir": None}

source_rc20 = V2_ROOT.parent / "v2k_RC20_20260715" / "installer" / "EnglishAudioMakerV2_RC.iss"
if source_rc20.is_file():
    source_inno = source_rc20.read_text(encoding="utf-8")
    assert "AppId={{CD94E4FC-B974-45DB-8D28-D4C1D6D634A2}" in source_inno
    assert "AppId={{A47E24D7-8D8E-4E0C-A2B4-7F6B4DD67A20}" not in source_inno

print("Humanization B2 local UI identity with preserved A installer isolation OK")
