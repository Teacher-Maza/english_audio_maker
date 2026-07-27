from _rc_bootstrap import V2_ROOT

import sys
import tkinter as tk
from tkinter import ttk

from v2_kokoro.app.ui.main_window import KokoroV2Window


class FakePreview:
    voice_id = None

    def stop(self):
        self.voice_id = None

    def close(self):
        self.stop()

    def current_mode(self):
        return "idle"


before_audio = tuple(sorted(V2_ROOT.rglob("*.wav"))) + tuple(sorted(V2_ROOT.rglob("*.mp3")))
root = tk.Tk()
root.withdraw()
window = KokoroV2Window(root, job_runner=lambda *_args, **_kwargs: None, preview_player=FakePreview())
root.update_idletasks()

assert root.geometry().split("+")[0] == "1440x800"
assert root.minsize() == (1180, 700)
assert len(window.nav_buttons) == 3
assert len(window.generate_buttons) == len(window.pause_buttons) == len(window.cancel_buttons) == 1
assert len(window.progress_bars) == len(window.job_status_labels) == 1
assert not hasattr(window, "generation_canvases")
assert not hasattr(window, "header_canvas")

for tab, editor in (
    (window.narration_tab, window.narration_text_input),
    (window.dialogue_tab, window.dialogue_text_input),
):
    cards = tab.winfo_children()
    assert len(cards) == 2
    assert sorted(int(card.grid_info()["column"]) for card in cards) == [0, 1]
    assert int(tab.grid_columnconfigure(1)["weight"]) > int(tab.grid_columnconfigure(0)["weight"])
    assert any(isinstance(child, ttk.Scrollbar) for child in editor.master.winfo_children())
    assert not editor.bind("<MouseWheel>")

button_texts = {str(widget.cget("text")) for widget in root.winfo_children() if isinstance(widget, ttk.Button)}
button_texts.update(str(button.cget("text")) for button in window.nav_buttons.values())
assert not any(label in " ".join(button_texts) for label in ("Configurações", "Como usar", "Colar", "Limpar", "F5", "F6"))

window.workspace_tabs.select(window.samples_tab)
window._on_workspace_tab_changed()
root.update_idletasks()
assert window.activity_panel.winfo_manager() == ""
assert int(window.workspace_tabs.grid_info()["columnspan"]) == 2
assert window.generate_button.cget("state") == "disabled"
assert window.preview_canvas.bind("<MouseWheel>")
window.set_mode("Narração")
root.update_idletasks()
assert window.activity_panel.winfo_manager() == "grid"
assert window.generate_button.cget("state") == "normal"

window.on_close()
after_audio = tuple(sorted(V2_ROOT.rglob("*.wav"))) + tuple(sorted(V2_ROOT.rglob("*.mp3")))
assert after_audio == before_audio
assert "torch" not in sys.modules and "kokoro" not in sys.modules
assert "v2_kokoro.app.core.job_runner" not in sys.modules
print("Cycle 2 layout: compact nav, two-column workspace + activity, fixed actions and local Samples wheel OK")
