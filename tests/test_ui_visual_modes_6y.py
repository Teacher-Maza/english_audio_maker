
from _rc_bootstrap import V2_ROOT

import sys
import tkinter as tk
from pathlib import Path


sys.path.insert(0, str(V2_ROOT))

from v2_kokoro.app.ui.main_window import (  # noqa: E402
    KokoroV2Window,
    MODE_DIALOGUE_LABEL,
    MODE_NARRATION_LABEL,
    MODE_THEMES,
)


class FakePreview:
    def __init__(self) -> None:
        self.voice_id = None
        self.state = "idle"
        self.stop_count = 0

    def play(self, voice_id, _path) -> None:
        self.voice_id = voice_id
        self.state = "playing"

    def pause_resume(self) -> str:
        self.state = "paused" if self.state == "playing" else "playing"
        return self.state

    def restart(self) -> None:
        self.state = "playing"

    def stop(self) -> None:
        self.stop_count += 1
        self.voice_id = None
        self.state = "idle"

    def close(self) -> None:
        self.stop()

    def current_mode(self) -> str:
        return self.state


v2_root = Path(__file__).resolve().parents[1]
before_wav = len(list((v2_root / "audios").rglob("*.wav")))
before_mp3 = len(list((v2_root / "audios").rglob("*.mp3")))

root = tk.Tk()
root.withdraw()
preview = FakePreview()
window = KokoroV2Window(root, job_runner=lambda *_args, **_kwargs: None, preview_player=preview)
root.update_idletasks()

tabs = window.workspace_tabs.tabs()
assert [window.workspace_tabs.tab(tab, "text") for tab in tabs] == ["Narração", "Conversação", "Samples de vozes", "Como usar"]
assert window.mode_var.get() == MODE_NARRATION_LABEL
assert window.workspace_tabs.select() == str(window.narration_tab)
assert window.text_input is window.narration_text_input
assert len(window.narration_box["values"]) == 10
assert window.generate_button._palette["background"] == MODE_THEMES[MODE_NARRATION_LABEL]["primary"]
assert window.generate_button._palette["foreground"] == "#FFFFFF"
assert window.generate_button._palette["shadow"] is None
assert window.nav_buttons[MODE_NARRATION_LABEL].cget("style") == "V2.NavActive.TButton"

window.on_preview_voice("af_heart")
stops_before_switch = preview.stop_count
window.set_mode(MODE_DIALOGUE_LABEL)
root.update_idletasks()
assert preview.stop_count == stops_before_switch + 1
assert window.mode_var.get() == MODE_DIALOGUE_LABEL
assert window.workspace_tabs.select() == str(window.dialogue_tab)
assert window.text_input is window.dialogue_text_input
assert str(window.voice_a_box.cget("state")) == "readonly"
assert str(window.voice_b_box.cget("state")) == "readonly"
assert window.generate_button._palette["background"] == MODE_THEMES[MODE_DIALOGUE_LABEL]["primary"]
assert window.generate_button._palette["foreground"] == "#FFFFFF"
assert window.nav_buttons[MODE_DIALOGUE_LABEL].cget("style") == "V2.NavActive.TButton"

window.narration_voice_var.set("af_heart")
window.voice_a_var.set("bf_emma")
window.voice_b_var.set("am_puck")
window.workspace_tabs.select(window.samples_tab)
root.update_idletasks()
window._apply_workspace_tab_theme()
assert window.nav_buttons["Samples"].cget("style") == "V2.NavActive.TButton"
assert window.activity_panel.winfo_manager() == ""
assert int(window.workspace_tabs.grid_info().get("columnspan", 1)) == 1
assert window.text_input is window.dialogue_text_input
window.workspace_tabs.select(window.narration_tab)
root.update_idletasks()
window._apply_workspace_tab_theme()
assert window.activity_panel.winfo_manager() == "grid"
assert window.narration_voice_var.get() == "af_heart"
assert window.voice_a_var.get() == "bf_emma" and window.voice_b_var.get() == "am_puck"

window.on_close()
assert len(list((v2_root / "audios").rglob("*.wav"))) == before_wav
assert len(list((v2_root / "audios").rglob("*.mp3"))) == before_mp3
print("6Y visual modes: compact nav, generation workspaces, Samples focus and selections OK")
