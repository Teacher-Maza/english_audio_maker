
from _rc_bootstrap import V2_ROOT

import json
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4


ROOT = V2_ROOT
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v2_kokoro.app.core import project_paths  # noqa: E402
from v2_kokoro.app.core.output_location import (  # noqa: E402
    load_selected_output_directory,
    save_selected_output_directory,
    validate_output_directory,
)


test_root = V2_ROOT / "temp" / "phase_7e" / uuid4().hex
selected = test_root / "selected_output"
selected.mkdir(parents=True)
settings = test_root / "output_location.json"

saved = save_selected_output_directory(selected, settings_path=settings)
assert saved == selected.resolve()
assert load_selected_output_directory(settings_path=settings) == selected.resolve()
assert json.loads(settings.read_text(encoding="utf-8"))["selected_output_dir"] == str(selected.resolve())

with patch.object(project_paths, "OUTPUT_LOCATION_CONFIG", settings):
    allowed = project_paths.confine_output_path(selected / "project" / "mp3", label="selected output")
    assert selected.resolve() in allowed.parents
    try:
        project_paths.confine_output_path(Path("C:/VTS_unselected_output_7e/project"), label="unselected output")
        raise AssertionError("An unselected external folder was accepted")
    except ValueError:
        pass

try:
    validate_output_directory(Path("relative_output"))
    raise AssertionError("A relative output folder was accepted")
except ValueError:
    pass

try:
    validate_output_directory(selected, write_probe=lambda _directory: (_ for _ in ()).throw(PermissionError()))
    raise AssertionError("A non-writable output folder was accepted")
except PermissionError:
    pass

original_is_symlink = Path.is_symlink
with patch.object(Path, "is_symlink", autospec=True, side_effect=lambda path: path == selected or original_is_symlink(path)):
    try:
        validate_output_directory(selected, verify_writable=False)
        raise AssertionError("A symbolic-link output folder was accepted")
    except ValueError:
        pass

print("7E output location: persistence, authorization, cancellation-safe validation and path boundaries OK")
