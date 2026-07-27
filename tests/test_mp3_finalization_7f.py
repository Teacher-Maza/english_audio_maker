
from _rc_bootstrap import V2_ROOT

"""Compatibility contract retained from 7F, updated by the 7F.3 job lifecycle."""

import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import numpy as np


PROJECT_ROOT = V2_ROOT
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v2_kokoro.app.core import job_runner  # noqa: E402
from v2_kokoro.app.core.ffmpeg_runner import Mp3Validation  # noqa: E402
from v2_kokoro.app.core.generation_contracts import GenerationRequest, MODE_NARRATION  # noqa: E402
from v2_kokoro.app.core.resource_manager import ResourceDecision, ResourceSnapshot  # noqa: E402


class FakeMonitor:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def start(self) -> None:
        pass

    def stop(self) -> dict:
        return {"samples": 1}


class FakeEngine:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def synthesize(self, *_args, **_kwargs) -> np.ndarray:
        return np.zeros(2400, dtype=np.float32)

    def close(self) -> None:
        pass


test_root = V2_ROOT / "temp" / "phase_7f_finalization" / uuid4().hex
test_root.mkdir(parents=True)
external_wav = test_root / "external_keep.wav"
external_wav.write_bytes(b"external WAV")
healthy = ResourceDecision(True, ResourceSnapshot(8.0, 20.0, None, None, 10.0, 100.0))

request = GenerationRequest(
    mode=MODE_NARRATION,
    project_name="success",
    text="Synthetic export contract text.",
    narration_voice_id="af_heart",
    output_base_dir=test_root,
)


def fake_convert(_wav_path: Path, mp3_path: Path) -> None:
    mp3_path.write_bytes(b"ID3 synthetic MP3")


def valid_mp3(mp3_path: Path) -> Mp3Validation:
    return Mp3Validation(path=mp3_path.resolve(), duration_seconds=1.0, size_bytes=mp3_path.stat().st_size)


with patch.object(job_runner, "convert_wav_to_mp3", fake_convert):
    result = job_runner.run_generation(
        request,
        _resource_evaluator=lambda *_args, **_kwargs: healthy,
        _monitor_factory=FakeMonitor,
        _engine_factory=FakeEngine,
        _mp3_validator=valid_mp3,
    )

assert result.success
success_root = test_root / "success"
assert [path.name for path in success_root.iterdir()] == ["narration_complete.mp3"]
assert external_wav.read_bytes() == b"external WAV"

print("7F MP3 finalization: validated final MP3 and job-local cleanup OK")
