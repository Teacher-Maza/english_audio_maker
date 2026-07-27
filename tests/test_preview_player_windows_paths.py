from _rc_bootstrap import V2_ROOT

import sys

from v2_kokoro.app.ui.audio_preview import PreviewError, PreviewPlayer


class FakeWaveOutApi:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.formats: list[tuple[int, int, int]] = []
        self.handle = object()

    def open(self, wave_format):
        self.calls.append("open")
        self.formats.append(
            (
                wave_format.nChannels,
                wave_format.wBitsPerSample,
                wave_format.nSamplesPerSec,
            )
        )
        return 0, self.handle

    def prepare(self, handle, header):
        assert handle is self.handle and header.dwBufferLength > 44
        self.calls.append("prepare")
        return 0

    def write(self, handle, header):
        assert handle is self.handle and header.lpData
        self.calls.append("write")
        header.dwFlags = 0x10
        return 0

    def pause(self, handle):
        assert handle is self.handle
        self.calls.append("pause")
        return 0

    def resume(self, handle):
        assert handle is self.handle
        self.calls.append("resume")
        return 0

    def reset(self, handle):
        assert handle is self.handle
        self.calls.append("reset")
        return 0

    def unprepare(self, handle, header):
        assert handle is self.handle
        self.calls.append("unprepare")
        header.dwFlags = 0x1
        return 0

    def close(self, handle):
        assert handle is self.handle
        self.calls.append("close")
        return 0

    @staticmethod
    def error_text(code):
        return f"fake waveOut error {code}"


sample_dir = V2_ROOT / "audios" / "blind_english_voices_6u"
first = sample_dir / "sample_08.wav"
second = sample_dir / "sample_06.wav"
assert " " in str(first) and len(str(first)) > 100
before = [(path.name, path.stat().st_size, path.stat().st_mtime_ns) for path in sample_dir.glob("*.wav")]

api = FakeWaveOutApi()
player = PreviewPlayer(wave_api=api)
player.play("af_heart", first)
assert player.voice_id == "af_heart"
assert player.path == first.resolve()
assert player.state == "playing" and player.current_mode() == "playing"
assert api.formats == [(1, 16, 24000)]

assert player.pause_resume() == "paused"
assert player.pause_resume() == "playing"
player.restart()
assert api.calls.count("prepare") == 2 and api.calls.count("write") == 2

player.play("bf_emma", second)
assert player.voice_id == "bf_emma"
assert api.calls.count("open") == 2
assert api.calls.count("close") >= 1
player.stop()
assert player.voice_id is None and player.state == "idle"
assert api.calls[-1] == "close"

try:
    player.play("missing", sample_dir / "missing.wav")
except PreviewError as exc:
    assert "não foi encontrada" in str(exc)
else:
    raise AssertionError("Missing preview must fail")

after = [(path.name, path.stat().st_size, path.stat().st_mtime_ns) for path in sample_dir.glob("*.wav")]
assert after == before
assert "torch" not in sys.modules and "kokoro" not in sys.modules
assert "v2_kokoro.app.core.job_runner" not in sys.modules
print("Preview Windows paths: waveOut handles long spaced paths and preserves one player/control state")
