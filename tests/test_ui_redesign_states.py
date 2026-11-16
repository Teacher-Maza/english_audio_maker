from _rc_bootstrap import V2_ROOT

import sys
import threading
import tkinter as tk

from v2_kokoro.app.core.generation_contracts import MODE_DIALOGUE_AB, MODE_NARRATION
from v2_kokoro.app.ui.main_window import KokoroV2Window


class FakePreview:
    def __init__(self):
        self.voice_id = None
        self.state = "idle"

    def play(self, voice_id, _path):
        self.voice_id = voice_id
        self.state = "playing"

    def pause_resume(self):
        self.state = "paused" if self.state == "playing" else "playing"
        return self.state

    def restart(self):
        self.state = "playing"

    def stop(self):
        self.voice_id = None
        self.state = "idle"

    def close(self):
        self.stop()

    def current_mode(self):
        return self.state


before_audio = tuple(sorted(V2_ROOT.rglob("*.wav"))) + tuple(sorted(V2_ROOT.rglob("*.mp3")))
root = tk.Tk()
root.withdraw()
preview = FakePreview()
window = KokoroV2Window(root, job_runner=lambda *_args, **_kwargs: None, preview_player=preview)

heart = window.voice_by_id["af_heart"]["display_label"]
emma = window.voice_by_id["bf_emma"]["display_label"]
puck = window.voice_by_id["am_puck"]["display_label"]
window.project_var.set("cycle_2_contract")
window.narration_voice_var.set(heart)
window.speed_var.set("Slow (75%)")
window.narration_text_input.insert("1.0", "A safe narration contract.")
narration = window.build_request()
assert narration.mode == MODE_NARRATION and narration.narration_voice_id == "af_heart"
assert narration.speed == 0.75
window.on_preview_selected(window.narration_voice_var)
assert preview.voice_id == "af_heart"

window.set_mode("Conversação A/B")
window.voice_a_var.set(emma)
window.voice_b_var.set(puck)
window.speed_var.set("Fast (125%)")
window.dialogue_text_input.insert("1.0", "A: Hello.\nB: Welcome.")
dialogue = window.build_request()
assert dialogue.mode == MODE_DIALOGUE_AB
assert (dialogue.voice_a_id, dialogue.voice_b_id, dialogue.speed) == ("bf_emma", "am_puck", 1.25)

window.workspace_tabs.select(window.samples_tab)
window._on_workspace_tab_changed()
window.workspace_tabs.select(window.narration_tab)
window._on_workspace_tab_changed()
assert window.narration_text_input.get("1.0", "end").strip() == "A safe narration contract."
assert window.dialogue_text_input.get("1.0", "end").strip() == "A: Hello.\nB: Welcome."
assert window.voice_a_var.get() == emma and window.voice_b_var.get() == puck

window.is_running = True
window.cancel_event = threading.Event()
window.pause_event = threading.Event()
window._set_running_controls(True)
assert window.generate_button.cget("state") == "disabled"
pause_button = window.pause_buttons[0]
assert not pause_button.instate(["disabled"])
window.on_pause()
assert window.pause_event.is_set() and "RETOMAR" in pause_button.cget("text")
window.on_pause()
assert not window.pause_event.is_set() and "PAUSAR" in pause_button.cget("text")
window.on_cancel()
assert window.cancel_event.is_set()

window.on_close()
after_audio = tuple(sorted(V2_ROOT.rglob("*.wav"))) + tuple(sorted(V2_ROOT.rglob("*.mp3")))
assert after_audio == before_audio
assert "torch" not in sys.modules and "kokoro" not in sys.modules
assert "v2_kokoro.app.core.job_runner" not in sys.modules
print("Cycle 2 states: requests, selections, editors, preview and pause/cancel contracts preserved")
