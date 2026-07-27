
from _rc_bootstrap import V2_ROOT

import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import numpy as np


PROJECT_ROOT = V2_ROOT
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v2_kokoro.app.core import job_runner  # noqa: E402
from v2_kokoro.app.core.ffmpeg_runner import Mp3Validation  # noqa: E402
from v2_kokoro.app.core.generation_contracts import GenerationRequest, MODE_DIALOGUE_AB, MODE_NARRATION  # noqa: E402
from v2_kokoro.app.core.resource_manager import ResourceDecision, ResourceSnapshot  # noqa: E402


class FakeMonitor:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def start(self) -> None:
        pass

    def stop(self) -> dict:
        return {"samples": 1, "max_process_ram_mb": 64.0}


class FakeEngine:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def synthesize(self, *_args, **_kwargs) -> np.ndarray:
        return np.zeros(2400, dtype=np.float32)

    def close(self) -> None:
        pass


test_root = V2_ROOT / "temp" / "phase_7f3_lifecycle" / uuid4().hex
output_base = test_root / "user_output"
output_base.mkdir(parents=True)
sentinel = output_base / "external_keep.txt"
sentinel.write_text("external", encoding="utf-8")
healthy = ResourceDecision(True, ResourceSnapshot(8.0, 20.0, None, None, 10.0, 100.0))


def narration(project_name: str) -> GenerationRequest:
    return GenerationRequest(
        mode=MODE_NARRATION,
        project_name=project_name,
        text="Synthetic lifecycle contract.",
        narration_voice_id="af_heart",
        output_base_dir=output_base,
    )


def dialogue(project_name: str) -> GenerationRequest:
    return GenerationRequest(
        mode=MODE_DIALOGUE_AB,
        project_name=project_name,
        text="A: First turn.\nB: Second turn.",
        voice_a_id="af_heart",
        voice_b_id="bf_emma",
        output_base_dir=output_base,
    )


def fake_convert(_wav_path: Path, mp3_path: Path) -> None:
    mp3_path.write_bytes(b"ID3 synthetic MP3")


def valid_mp3(mp3_path: Path) -> Mp3Validation:
    return Mp3Validation(path=mp3_path.resolve(), duration_seconds=1.0, size_bytes=mp3_path.stat().st_size)


def run(request: GenerationRequest, **kwargs):
    validator = kwargs.pop("_mp3_validator", valid_mp3)
    return job_runner.run_generation(
        request,
        _resource_evaluator=lambda *_args, **_kwargs: healthy,
        _monitor_factory=FakeMonitor,
        _engine_factory=FakeEngine,
        _mp3_validator=validator,
        **kwargs,
    )


with patch.object(job_runner, "convert_wav_to_mp3", fake_convert):
    success = run(narration("success"))
assert success.success
success_dir = output_base / "success"
assert [path.name for path in success_dir.iterdir()] == ["narration_complete.mp3"]
success_log = json.loads((V2_ROOT / success.log_file).read_text(encoding="utf-8"))
assert success_log["full_text_saved"] is False
assert success_log["job_id"] == success.metadata["job_id"]
assert success_log["export_validation"]["removed_wav_files"] == 2
assert not (V2_ROOT / "temp" / "jobs" / success.metadata["job_id"]).exists()


calls: list[Path] = []


def invalid_final(mp3_path: Path) -> Mp3Validation:
    calls.append(mp3_path)
    if len(calls) == 1:
        return valid_mp3(mp3_path)
    raise RuntimeError("final MP3 validation failed")


with patch.object(job_runner, "convert_wav_to_mp3", fake_convert):
    failed = run(narration("failure"), _mp3_validator=invalid_final)
assert not failed.success
failure_work = V2_ROOT / "temp" / "jobs" / failed.metadata["job_id"]
assert list((failure_work / "wav").glob("*.wav"))
assert list((failure_work / "temp").glob("*.wav"))
assert not (output_base / "failure").exists()


def wait_until(predicate) -> None:
    for _ in range(100):
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Timed out waiting for job state")


original_save_wav = job_runner.save_wav


def pause_after_first_wav(path: Path, audio: np.ndarray) -> None:
    original_save_wav(path, audio)
    if path.name == "item_001.wav":
        pause_resume.set()


pause_resume = threading.Event()
resume_result: list = []
with patch.object(job_runner, "save_wav", pause_after_first_wav), patch.object(job_runner, "convert_wav_to_mp3", fake_convert):
    thread = threading.Thread(target=lambda: resume_result.append(run(dialogue("pause_resume"), pause_event=pause_resume)))
    thread.start()
    wait_until(lambda: pause_resume.is_set() and thread.is_alive())
    pause_resume.clear()
    thread.join(timeout=5)
assert resume_result and resume_result[0].success


pause_cancel = threading.Event()
cancel_event = threading.Event()
cancel_result: list = []


def pause_for_cancel(path: Path, audio: np.ndarray) -> None:
    original_save_wav(path, audio)
    if path.name == "item_001.wav":
        pause_cancel.set()


with patch.object(job_runner, "save_wav", pause_for_cancel):
    thread = threading.Thread(target=lambda: cancel_result.append(run(dialogue("pause_cancel"), pause_event=pause_cancel, cancel_event=cancel_event)))
    thread.start()
    wait_until(lambda: pause_cancel.is_set() and thread.is_alive())
    cancel_event.set()
    thread.join(timeout=5)
assert cancel_result and cancel_result[0].metadata["cancelled"] is True
cancel_job_id = cancel_result[0].metadata["job_id"]
assert not (V2_ROOT / "temp" / "jobs" / cancel_job_id).exists()
assert not (output_base / "pause_cancel").exists()
assert sentinel.read_text(encoding="utf-8") == "external"

print("7F.3 lifecycle: success, failure, cancellation, pause/resume, pause/cancel and external isolation OK")
