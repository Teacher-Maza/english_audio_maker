
from _rc_bootstrap import V2_ROOT

import os
import shutil
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = V2_ROOT
sys.path.insert(0, str(PROJECT_ROOT))

from v2_kokoro.app.core.export_manager import create_export_layout  # noqa: E402
from v2_kokoro.app.core.project_paths import DATA_ROOT_ENV, confine_output_path, load_paths, user_data_root  # noqa: E402


fake_local = Path(tempfile.gettempdir()) / "vts_phase_7b_fake_localappdata"
data_root = fake_local / "EnglishAudioMakerV2HumanizationAData"
old_local = os.environ.get("LOCALAPPDATA")
old_data = os.environ.get(DATA_ROOT_ENV)
try:
    os.environ["LOCALAPPDATA"] = str(fake_local)
    os.environ[DATA_ROOT_ENV] = str(data_root)
    assert user_data_root() == data_root.resolve()
    paths = load_paths()
    assert paths["generation_output_dir"] == (data_root / "audios" / "generated").resolve()
    layout = create_export_layout("installed_contract")
    assert data_root.resolve() in layout.root.parents
    assert confine_output_path(layout.log_file) == layout.log_file.resolve()
    try:
        confine_output_path(fake_local.parent / "escape.txt")
        raise AssertionError("Installed output escaped LOCALAPPDATA data root")
    except ValueError:
        pass
finally:
    if old_local is None:
        os.environ.pop("LOCALAPPDATA", None)
    else:
        os.environ["LOCALAPPDATA"] = old_local
    if old_data is None:
        os.environ.pop(DATA_ROOT_ENV, None)
    else:
        os.environ[DATA_ROOT_ENV] = old_data
    if fake_local.exists():
        shutil.rmtree(fake_local)

print("7B installed data: external user output confined, dev behavior preserved and cleanup OK")
