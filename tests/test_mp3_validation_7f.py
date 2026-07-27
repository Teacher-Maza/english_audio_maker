
from _rc_bootstrap import V2_ROOT

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4


ROOT = V2_ROOT
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v2_kokoro.app.core.ffmpeg_runner import validate_mp3_complete  # noqa: E402


test_root = V2_ROOT / "temp" / "phase_7f" / uuid4().hex
test_root.mkdir(parents=True)
mp3 = test_root / "placeholder.mp3"
mp3.write_bytes(b"ID3 test placeholder")

metadata = subprocess.CompletedProcess([], 1, "", "Duration: 00:01:02.50, start: 0.000000, bitrate: 128 kb/s")
decoded = subprocess.CompletedProcess([], 0, "", "")
with patch("v2_kokoro.app.core.ffmpeg_runner.subprocess.run", side_effect=[metadata, decoded]) as runner:
    result = validate_mp3_complete(mp3)

assert result.path == mp3.resolve()
assert result.duration_seconds == 62.5 and result.size_bytes == mp3.stat().st_size
assert "-f" in runner.call_args_list[1].args[0] and "null" in runner.call_args_list[1].args[0]

invalid = subprocess.CompletedProcess([], 1, "", "Duration: N/A")
with patch("v2_kokoro.app.core.ffmpeg_runner.subprocess.run", return_value=invalid):
    try:
        validate_mp3_complete(mp3)
        raise AssertionError("MP3 without a duration was accepted")
    except RuntimeError:
        pass
assert mp3.exists()

print("7F MP3 validation: duration, full decode contract and invalid-MP3 preservation OK")
