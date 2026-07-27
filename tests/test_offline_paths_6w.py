
from _rc_bootstrap import V2_ROOT

import json
import sys
from pathlib import Path

sys.path.insert(0, str(V2_ROOT))

from v2_kokoro.app.core.project_paths import V2_ROOT, load_paths
from v2_kokoro.app.core.voice_registry import VoiceRegistry


paths = load_paths()
for key in ("ffmpeg_exe", "kokoro_config", "kokoro_model", "voices_catalog"):
    assert paths[key].is_file(), key
    assert V2_ROOT in paths[key].parents

catalog = json.loads(paths["voices_catalog"].read_text(encoding="utf-8"))
assert catalog["default_voice_id"] is None
assert catalog["ranking_enabled"] is True
assert catalog["decision_phase"] == "RC-15"
assert all("review_metadata" in item for item in catalog["voices"])
assert all(item["status"] == "approved" for item in catalog["voices"])
assert len(VoiceRegistry().validate_all()) == 28
print("6W offline paths: local model, FFmpeg and 28 voicepacks OK")
