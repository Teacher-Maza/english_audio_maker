
from _rc_bootstrap import V2_ROOT

import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(V2_ROOT))

from v2_kokoro.app.core.generation_contracts import GenerationRequest, MODE_DIALOGUE_AB, MODE_NARRATION
from v2_kokoro.app.core.progress_events import ProgressEvent
from v2_kokoro.app.ui.main_window import KokoroV2Window, MODE_DIALOGUE_LABEL


class FakePreview:
    def __init__(self) -> None:
        self.voice_id = None
        self.state = "idle"
        self.calls: list[tuple] = []

    def play(self, voice_id, path) -> None:
        self.calls.append(("play", voice_id, path.name))
        self.voice_id = voice_id
        self.state = "playing"

    def pause_resume(self) -> str:
        self.calls.append(("pause_resume",))
        self.state = "paused" if self.state == "playing" else "playing"
        return self.state

    def restart(self) -> None:
        self.calls.append(("restart",))
        self.state = "playing"

    def stop(self) -> None:
        self.calls.append(("stop",))
        self.voice_id = None
        self.state = "idle"

    def close(self) -> None:
        self.calls.append(("close",))
        self.stop()

    def current_mode(self) -> str:
        return "playing" if self.state == "playing" else "stopped"


v2_root = Path(__file__).resolve().parents[1]
before_wav = len(list((v2_root / "audios").rglob("*.wav")))
before_mp3 = len(list((v2_root / "audios").rglob("*.mp3")))
root = tk.Tk()
root.withdraw()
preview = FakePreview()
window = KokoroV2Window(root, job_runner=lambda *_args, **_kwargs: None, preview_player=preview)
root.update_idletasks()

assert root.title() == "English Audio Maker"
assert len(window.voices) == 9 and len(window.preview_rows) == 9
assert window.narration_voice_var.get() == ""
assert window.voice_a_var.get() == "" and window.voice_b_var.get() == ""
assert len(window.narration_box["values"]) == 10
assert window.voice_display_values == [item["display_label"] for item in window.voices]
favorite_count = sum(item["favorite"] for item in window.voices)
assert favorite_count > 0
assert all(item["display_label"].startswith("★ ") for item in window.voices[:favorite_count])
assert all(not item["display_label"].startswith("★ ") for item in window.voices[favorite_count:])
assert [item["display_name"] for item in window.voices[:favorite_count]] == sorted(item["display_name"] for item in window.voices[:favorite_count])
assert [item["display_name"] for item in window.voices[favorite_count:]] == sorted(item["display_name"] for item in window.voices[favorite_count:])
assert window.progress_stage_var.get() == "Aguardando"
assert window.progress_percent_var.get() == "0%"

window.narration_voice_var.set(window.voice_by_id["af_heart"]["display_label"])
root.update_idletasks()
assert not any(call[0] == "play" for call in preview.calls)

window.on_preview_voice("af_heart")
assert preview.voice_id == "af_heart"
assert window.preview_rows["af_heart"][0].cget("style") == "V2.PreviewPlaying.TFrame"
window.on_preview_pause()
assert preview.state == "paused"
window.on_preview_restart()
assert preview.state == "playing"
window.on_preview_stop()
assert preview.voice_id is None

window.project_var.set("ui_contract")
window.text_input.insert("1.0", "Hello from the UI contract test.")
request = window.build_request()
assert isinstance(request, GenerationRequest)
assert request.mode == MODE_NARRATION and request.narration_voice_id == "af_heart"

window.mode_var.set(MODE_DIALOGUE_LABEL)
root.update_idletasks()
window.text_input.delete("1.0", "end")
window.text_input.insert("1.0", "A: Hello.\nB: Hi.")
window.voice_a_var.set(window.voice_by_id["bf_emma"]["display_label"])
window.voice_b_var.set(window.voice_by_id["am_puck"]["display_label"])
request = window.build_request()
assert isinstance(request, GenerationRequest)
assert request.mode == MODE_DIALOGUE_AB
assert request.voice_a_id == "bf_emma" and request.voice_b_id == "am_puck"

window._apply_progress(ProgressEvent(stage="synthesizing", percent=50, current=1, total=2))
assert window.progress_value.get() == 50
assert window.progress_percent_var.get() == "50%"
assert window.progress_item_var.get() == "Item 1 de 2"

window.on_close()
assert len(list((v2_root / "audios").rglob("*.wav"))) == before_wav
assert len(list((v2_root / "audios").rglob("*.mp3"))) == before_mp3
print("6X UI smoke: 9 voices, neutral selection, preview controls, modes and progress OK")
