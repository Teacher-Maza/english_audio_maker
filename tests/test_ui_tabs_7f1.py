
from _rc_bootstrap import V2_ROOT

import sys
import tkinter as tk
from pathlib import Path


ROOT = V2_ROOT
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v2_kokoro.app.ui.main_window import KokoroV2Window  # noqa: E402


class FakePreview:
    voice_id = None
    state = "idle"

    def stop(self) -> None:
        self.voice_id = None

    def close(self) -> None:
        self.stop()

    def current_mode(self) -> str:
        return "stopped"


root = tk.Tk()
root.withdraw()
window = KokoroV2Window(root, job_runner=lambda *_args, **_kwargs: None, preview_player=FakePreview())
root.update_idletasks()

tabs = window.workspace_tabs.tabs()
assert len(tabs) == 3
assert [window.workspace_tabs.tab(tab, "text") for tab in tabs] == ["Narração", "Conversação", "Samples de vozes"]
assert len(window.generate_buttons) == 1 and len(window.cancel_buttons) == 1 and len(window.pause_buttons) == 1
assert len(window.progress_bars) == 1 and len(window.job_status_labels) == 1
assert all(bar.winfo_manager() == "grid" for bar in window.progress_bars)
assert all(label.winfo_manager() == "grid" for label in window.job_status_labels)
assert all(button.instate(["disabled"]) for button in window.cancel_buttons)
assert all(button.instate(["disabled"]) for button in window.pause_buttons)
assert window.narration_text_input.winfo_manager() == "grid"
assert window.dialogue_text_input.winfo_manager() == "grid"
for tab in (window.narration_tab, window.dialogue_tab):
    cards = tab.winfo_children()
    assert len(cards) == 2
    assert sorted(int(card.grid_info()["column"]) for card in cards) == [0, 1]
assert not window.narration_text_input.bind("<MouseWheel>")
assert not window.dialogue_text_input.bind("<MouseWheel>")
assert window.preview_canvas.bind("<MouseWheel>")

heart_label = window.voice_by_id["af_heart"]["display_label"]
emma_label = window.voice_by_id["bf_emma"]["display_label"]
puck_label = window.voice_by_id["am_puck"]["display_label"]
window.narration_voice_var.set(heart_label)
window.voice_a_var.set(emma_label)
window.voice_b_var.set(puck_label)
window.workspace_tabs.select(window.samples_tab)
root.update_idletasks()
window._on_workspace_tab_changed()
assert window.narration_text_input.winfo_manager() == "grid"
assert window.dialogue_text_input.winfo_manager() == "grid"
assert window.nav_buttons["Samples"].cget("style") == "V2.NavActive.TButton"
assert window.activity_panel.winfo_manager() == ""
window.workspace_tabs.select(window.dialogue_tab)
root.update_idletasks()
window._on_workspace_tab_changed()
assert window.activity_panel.winfo_manager() == "grid"
assert window.narration_voice_var.get() == heart_label
assert window.voice_a_var.get() == emma_label and window.voice_b_var.get() == puck_label
assert window.narration_text_input.winfo_manager() == "grid"
assert window.dialogue_text_input.winfo_manager() == "grid"

window.on_close()
print("7F.1 UI tabs: persistent editors, single action bar, local Samples wheel and selections OK")
