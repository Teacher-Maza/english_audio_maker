from _rc_bootstrap import V2_ROOT

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np


sys.path.insert(0, str(V2_ROOT))

from v2_kokoro.app.core.audio_processor import (  # noqa: E402
    BETWEEN_ITEMS_MS,
    FADE_MS,
    FINAL_SILENCE_MS,
    INITIAL_SILENCE_MS,
    SAMPLE_RATE,
    assemble_audio,
)
from v2_kokoro.app.core.text_chunker import chunk_text  # noqa: E402


def verify_kokoro_inputs_in_child() -> None:
    from unittest.mock import patch

    from v2_kokoro.app.core.kokoro_engine import KokoroEngine

    pipeline_construction = []
    pipeline_calls = []
    voicepack = object()

    class FakePipeline:
        def __init__(self, **kwargs) -> None:
            pipeline_construction.append(kwargs)

        def __call__(self, text, **kwargs):
            pipeline_calls.append({"text": text, **kwargs})
            yield "graphemes-one", "phonemes-one", np.ones(2400, dtype=np.float32)
            yield "graphemes-two", "phonemes-two", np.full(2400, 0.5, dtype=np.float32)

    class FakeRegistry:
        def get(self, _voice_id: str) -> dict:
            return {"locale": "en_US", "voicepack": Path("voice.pt")}

    engine = KokoroEngine.__new__(KokoroEngine)
    engine.registry = FakeRegistry()
    engine.model = object()
    engine._pipelines = {}
    engine._voicepacks = {}
    with patch("v2_kokoro.app.core.kokoro_engine.KPipeline", FakePipeline), patch(
        "v2_kokoro.app.core.kokoro_engine.torch.load", return_value=voicepack
    ):
        audio = engine.synthesize("Line one.\nLine two.", "af_heart", speed=1.0)

    assert pipeline_construction == [
        {"lang_code": "a", "repo_id": "hexgrad/Kokoro-82M", "model": engine.model, "device": "cpu"}
    ]
    assert pipeline_calls == [
        {"text": "Line one.\nLine two.", "voice": voicepack, "speed": 1.0, "split_pattern": r"\n+"}
    ]
    assert audio.shape == (4800,)
    assert np.all(audio[:2400] == 1.0) and np.all(audio[2400:] == 0.5)


if os.environ.get("EAM_BASELINE_ENGINE_CHILD") == "1":
    verify_kokoro_inputs_in_child()
    print("Kokoro child contract OK")
    raise SystemExit(0)


corpus_path = V2_ROOT / "tests" / "corpus" / "humanization_a_baseline.json"
corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
contract = corpus["audio_contract"]
assert contract["humanization"] is False
assert contract["speed"] == 1.0
assert contract["resource_profile"] == "economic"
assert (SAMPLE_RATE, INITIAL_SILENCE_MS, BETWEEN_ITEMS_MS, FINAL_SILENCE_MS, FADE_MS) == (24000, 650, 250, 300, 50)

narration = corpus["cases"][0]
chunks = chunk_text(narration["text"], max_chars=280)
assert chunks == [
    "At sunrise, the research team opened the quiet studio and checked every cable. Clear speech, steady pacing, and careful punctuation make this passage useful for repeatable comparison. Numbers such as twelve, forty-seven, and two hundred should remain easy to understand.",
    "The final sentence closes calmly, without added emphasis or dramatic timing.",
]

child_env = os.environ.copy()
child_env["EAM_BASELINE_ENGINE_CHILD"] = "1"
completed = subprocess.run(
    [sys.executable, "-B", str(Path(__file__).resolve())],
    check=False,
    capture_output=True,
    text=True,
    shell=False,
    timeout=120,
    env=child_env,
)
assert completed.returncode == 0, completed.stderr
assert "Kokoro child contract OK" in completed.stdout

assembled = assemble_audio([np.ones(2400, dtype=np.float32), np.ones(2400, dtype=np.float32)])
assert assembled.shape == (33600,)
assert assembled[0] == 0.0 and assembled[-1] == 0.0
print("Humanization A baseline contract: fixed corpus, Kokoro inputs, gs/ps discard, chunking and assembly unchanged")
