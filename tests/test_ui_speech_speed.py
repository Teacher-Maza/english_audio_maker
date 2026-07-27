from _rc_bootstrap import V2_ROOT

import sys
import tkinter as tk

sys.path.insert(0, str(V2_ROOT))

from v2_kokoro.app.core.generation_contracts import GenerationRequest, MODE_DIALOGUE_AB, MODE_NARRATION
from v2_kokoro.app.ui.main_window import (
    KokoroV2Window,
    MODE_DIALOGUE_LABEL,
    MODE_NARRATION_LABEL,
    SPEECH_SPEED_LABELS,
)


class FakePreview:
    voice_id = None

    def play(self, *_args):
        pass

    def pause_resume(self):
        return "paused"

    def restart(self):
        pass

    def stop(self):
        self.voice_id = None

    def close(self):
        pass

    def current_mode(self):
        return "stopped"


root = tk.Tk()
root.withdraw()
window = KokoroV2Window(root, job_runner=lambda *_args, **_kwargs: None, preview_player=FakePreview())
root.update_idletasks()

assert SPEECH_SPEED_LABELS == {"Devagar": 0.90, "Normal": 1.00, "Rápido": 1.10}
assert window.speed_var.get() == "Normal"
assert len(window.speed_boxes) == 2
assert tuple(window.speed_boxes[0]["values"]) == ("Devagar", "Normal", "Rápido")
assert tuple(window.speed_boxes[1]["values"]) == ("Devagar", "Normal", "Rápido")
assert window.speed_boxes[0].cget("textvariable") == window.speed_boxes[1].cget("textvariable")
assert window.speed_boxes[0].cget("textvariable") != window.profile_boxes[0].cget("textvariable")

window.project_var.set("speed_project")
window.narration_voice_var.set(window.voice_by_id["af_heart"]["display_label"])
window.narration_text_input.insert("1.0", "A narration uses one project speed.")
window.speed_var.set("Devagar")
narration = window.build_request()
assert isinstance(narration, GenerationRequest)
assert narration.mode == MODE_NARRATION and narration.speed == 0.90

window.set_mode(MODE_DIALOGUE_LABEL)
window.dialogue_text_input.insert("1.0", "A: Both speakers use the same speed.\nB: The setting belongs to the project.")
window.voice_a_var.set(window.voice_by_id["af_heart"]["display_label"])
window.voice_b_var.set(window.voice_by_id["bf_emma"]["display_label"])
assert window.speed_var.get() == "Devagar"
window.speed_var.set("Rápido")
dialogue = window.build_request()
assert isinstance(dialogue, GenerationRequest)
assert dialogue.mode == MODE_DIALOGUE_AB and dialogue.speed == 1.10

window.set_mode(MODE_NARRATION_LABEL)
assert window.speed_var.get() == "Rápido"
window._set_running_controls(True)
assert all(box.instate(["disabled"]) for box in window.speed_boxes)
window._set_running_controls(False)
assert all(box.instate(["readonly"]) for box in window.speed_boxes)

window.speed_var.set("Normal")
normal = window.build_request()
assert isinstance(normal, GenerationRequest) and normal.speed == 1.00
window.on_close()

print("UI speech speed: minimal selectors, shared project persistence, profile separation and request mapping OK")
