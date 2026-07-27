from _rc_bootstrap import V2_ROOT

import hashlib
import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import numpy as np
import soundfile as sf


if str(V2_ROOT) not in sys.path:
    sys.path.insert(0, str(V2_ROOT))

from v2_kokoro.app.core import job_runner  # noqa: E402
from v2_kokoro.app.core.audio_processor import SAMPLE_RATE, assemble_wav_files, save_wav  # noqa: E402
from v2_kokoro.app.core.ffmpeg_runner import Mp3Validation  # noqa: E402
from v2_kokoro.app.core.generation_contracts import GenerationRequest, MODE_NARRATION  # noqa: E402
from v2_kokoro.app.core.resource_manager import (  # noqa: E402
    PROFILE_AUTOMATIC,
    ResourceDecision,
    ResourceSnapshot,
    resolve_profile,
)
from v2_kokoro.installer.installer_bootstrap import finalize_direct_install, verify_payload  # noqa: E402


test_root = V2_ROOT / "temp" / "rc19_contract" / uuid4().hex
test_root.mkdir(parents=True)
try:
    conservative = resolve_profile(
        PROFILE_AUTOMATIC,
        snapshot=ResourceSnapshot(2.0, 20.0, None, None, 85.0, 300.0, total_ram_gb=8.0),
        text_characters=4000,
    )
    normal = resolve_profile(
        PROFILE_AUTOMATIC,
        snapshot=ResourceSnapshot(8.0, 20.0, None, None, 10.0, 300.0, total_ram_gb=8.0),
        text_characters=4000,
    )
    assert conservative.threads == 1 and conservative.chunk_chars == 160 and conservative.sequential
    assert normal.threads >= 2 and normal.chunk_chars == 280

    chunks = test_root / "chunks"
    chunks.mkdir()
    tone = np.sin(np.linspace(0, 10, SAMPLE_RATE // 10, dtype=np.float32)) * 0.1
    first, second = chunks / "first.wav", chunks / "second.wav"
    save_wav(first, tone)
    save_wav(second, tone)
    streamed = test_root / "streamed.wav"
    assemble_wav_files([first, second], streamed)
    assert sf.info(streamed).frames == round(SAMPLE_RATE * 1.4)

    class FakeMonitor:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def start(self) -> None:
            pass

        def stop(self) -> dict:
            return {"samples": 1, "max_process_ram_mb": 64.0}

    class FakeEngine:
        released = 0

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def synthesize(self, *_args, **_kwargs) -> np.ndarray:
            return np.zeros(SAMPLE_RATE // 10, dtype=np.float32)

        def release_voicepacks(self) -> None:
            FakeEngine.released += 1

        def close(self) -> None:
            pass

    healthy = ResourceDecision(True, ResourceSnapshot(8.0, 20.0, None, None, 10.0, 100.0, total_ram_gb=8.0))
    request = GenerationRequest(
        mode=MODE_NARRATION,
        project_name="streaming",
        text=" ".join("Sentence %d." % index for index in range(100)),
        narration_voice_id="af_heart",
        output_base_dir=test_root / "output",
    )
    request.output_base_dir.mkdir()

    def fake_convert(_wav: Path, mp3: Path) -> None:
        mp3.write_bytes(b"ID3 synthetic RC19")

    def validate(mp3: Path) -> Mp3Validation:
        return Mp3Validation(mp3, 1.0, mp3.stat().st_size)

    with patch.object(job_runner, "convert_wav_to_mp3", fake_convert):
        result = job_runner.run_generation(
            request,
            resource_profile=PROFILE_AUTOMATIC,
            _resource_evaluator=lambda *_args, **_kwargs: healthy,
            _monitor_factory=FakeMonitor,
            _engine_factory=FakeEngine,
            _mp3_validator=validate,
        )
    assert result.success and FakeEngine.released == result.metadata["item_count"]
    assert result.metadata["sequential"] is True

    payload = test_root / "direct_payload"
    (payload / "runtime").mkdir(parents=True)
    (payload / "runtime" / "runtime.txt").write_text("runtime", encoding="utf-8")
    (payload / "Launch.cmd").write_text("@echo off\r\n", encoding="utf-8")
    files = []
    for path in sorted(item for item in payload.rglob("*") if item.is_file()):
        files.append({
            "path": path.relative_to(payload).as_posix(),
            "size": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    (payload / "PAYLOAD_MANIFEST.json").write_text(json.dumps({"version": "2.0.0-rc19", "files": files}), encoding="utf-8")
    (payload / "unins000.exe").write_bytes(b"inno")
    marker = finalize_direct_install(payload, test_root / "data", allowed_root=test_root)
    assert marker["version"] == "2.0.0-rc19"
    assert verify_payload(payload)["version"] == "2.0.0-rc19"
finally:
    if test_root.exists():
        shutil.rmtree(test_root)

print("RC-19: adaptive profile, streamed WAV assembly, sequential release and direct Inno finalization OK")
