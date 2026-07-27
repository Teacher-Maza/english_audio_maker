
from _rc_bootstrap import V2_ROOT

import sys
from pathlib import Path

sys.path.insert(0, str(V2_ROOT))

from v2_kokoro.app.ui.audio_preview import PreviewError, PreviewPlayer


commands: list[str] = []


def fake_sender(command: str) -> str:
    commands.append(command)
    return "playing" if command.startswith("status ") else ""


root = Path(__file__).resolve().parents[1]
first = root / "audios" / "blind_english_voices_6u" / "sample_08.wav"
second = root / "audios" / "blind_english_voices_6u" / "sample_06.wav"
player = PreviewPlayer(sender=fake_sender)

player.play("af_heart", first)
assert player.voice_id == "af_heart" and player.state == "playing"
assert any(command.startswith("open ") for command in commands)
assert any(command.startswith("play ") for command in commands)

assert player.pause_resume() == "paused"
assert player.pause_resume() == "playing"
player.restart()
assert any(command.startswith("seek ") for command in commands)

player.play("bf_emma", second)
assert player.voice_id == "bf_emma"
assert commands.count(f"close {PreviewPlayer.ALIAS}") >= 2
player.stop()
assert player.voice_id is None and player.state == "idle"

try:
    player.play("missing", root / "audios" / "missing.wav")
except PreviewError as exc:
    assert "não foi encontrada" in str(exc)
else:
    raise AssertionError("Missing preview must fail")

print("6X preview player: play/pause/resume/restart/stop and single alias OK")

