
from _rc_bootstrap import V2_ROOT

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(V2_ROOT))

from v2_kokoro.app.core.audio_processor import SAMPLE_RATE, assemble_audio
from v2_kokoro.app.core.export_manager import next_available_dir
from v2_kokoro.app.core.log_manager import write_safe_log


root = Path(__file__).resolve().parents[1]
test_root = root / "temp" / "phase_6w" / "unit_outputs"
test_root.mkdir(parents=True, exist_ok=True)

existing = test_root / "overwrite_case"
existing.mkdir(exist_ok=True)
candidate = next_available_dir(test_root, "overwrite_case")
assert candidate != existing and not candidate.exists()

tone = np.sin(np.linspace(0, 30, SAMPLE_RATE, dtype=np.float32)) * 0.1
assembled = assemble_audio([tone, tone])
assert assembled.size > tone.size * 2
assert np.max(np.abs(assembled)) <= 0.11

log_path = test_root / "safe_log.json"
write_safe_log(
    log_path,
    success=True,
    mode="narration",
    project_name="unit",
    voices=["af_heart"],
    speed=1.0,
    item_count=2,
    files=["one.wav", "one.mp3"],
)
log = json.loads(log_path.read_text(encoding="utf-8"))
assert log["full_text_saved"] is False
assert "input_text" not in log and "text" not in log
assert log["pitch_changed"] is False and log["offline"] is True
print("6W audio/export: synthetic assembly, overwrite protection and safe log OK")
