from _rc_bootstrap import V2_ROOT

import sys

sys.path.insert(0, str(V2_ROOT))

from v2_kokoro.app.core.generation_contracts import GenerationRequest, MODE_NARRATION
from v2_kokoro.app.core.speech_speed import (
    ALLOWED_SPEECH_SPEEDS,
    SPEECH_SPEED_FAST,
    SPEECH_SPEED_NORMAL,
    SPEECH_SPEED_SLOW,
)
from v2_kokoro.app.core.validators import validate_request
from v2_kokoro.app.core.voice_registry import VoiceRegistry


assert (SPEECH_SPEED_SLOW, SPEECH_SPEED_NORMAL, SPEECH_SPEED_FAST) == (0.90, 1.00, 1.10)
assert ALLOWED_SPEECH_SPEEDS == frozenset({0.90, 1.00, 1.10})
assert GenerationRequest(mode=MODE_NARRATION, project_name="default", text="Text.").speed == 1.00

registry = VoiceRegistry()
voice_id = registry.validate_all()[0]
for speed in (SPEECH_SPEED_SLOW, SPEECH_SPEED_NORMAL, SPEECH_SPEED_FAST):
    validate_request(
        GenerationRequest(
            mode=MODE_NARRATION,
            project_name=f"speed_{str(speed).replace('.', '_')}",
            text="A valid narration.",
            narration_voice_id=voice_id,
            speed=speed,
        ),
        registry,
    )

for invalid_speed in (0.89, 0.95, 1.05, 1.11, 2.0):
    try:
        validate_request(
            GenerationRequest(
                mode=MODE_NARRATION,
                project_name="invalid_speed",
                text="A valid narration.",
                narration_voice_id=voice_id,
                speed=invalid_speed,
            ),
            registry,
        )
    except ValueError:
        pass
    else:
        raise AssertionError(f"Unsupported speed was accepted: {invalid_speed}")


source = (V2_ROOT / "app" / "core" / "kokoro_engine.py").read_text(encoding="utf-8").lower()
assert "speed=float(speed)" in source
for forbidden in ("atempo", "resample", "time_stretch", "pitch_shift"):
    assert forbidden not in source

print("Speech speed contract: exact presets, Normal default, strict validation and native Kokoro speed only OK")
