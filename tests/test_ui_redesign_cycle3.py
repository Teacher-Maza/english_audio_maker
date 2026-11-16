from _rc_bootstrap import V2_ROOT

import sys
import threading
import tkinter as tk

from v2_kokoro.app.ui.main_window import KokoroV2Window


class FakePreview:
    voice_id = None

    def stop(self):
        self.voice_id = None

    def close(self):
        self.stop()

    def current_mode(self):
        return "idle"


def bottom(widget: tk.Widget) -> int:
    return widget.winfo_rooty() + widget.winfo_height()


def assert_dialogue_output_visible(window: KokoroV2Window) -> None:
    for button in (window.choose_output_button, window.open_output_button):
        assert button.winfo_ismapped()
        assert bottom(button) <= bottom(window.footer)
        assert button.winfo_rootx() + button.winfo_width() <= window.root.winfo_rootx() + window.root.winfo_width(), (button.winfo_rootx(), button.winfo_width(), window.root.winfo_width(), window.root.tk.call("tk", "scaling"))



before_audio = tuple(sorted(V2_ROOT.rglob("*.wav"))) + tuple(sorted(V2_ROOT.rglob("*.mp3")))
root = tk.Tk()
root.withdraw()
window = KokoroV2Window(root, job_runner=lambda *_args, **_kwargs: None, preview_player=FakePreview())
window.set_mode("Conversação A/B")
root.deiconify()
root.update()
window.output_directory_var.set("C:\\" + "pasta_muito_longa\\" * 18 + "destino")
window.output_var.set("C:\\" + "resultado_muito_longo\\" * 18 + "audio_final.mp3")
window.dialogue_text_input.insert("1.0", ("A: This is a deliberately long accessibility and wrapping test.\nB: It remains inside the editor.\n" * 80))

for dpi, geometry in ((100, "1280x800+0+0"), (125, "1200x800+0+0"), (150, "1203x800+0+0")):
    root.tk.call("tk", "scaling", (dpi / 100) * (96 / 72))
    root.geometry(geometry)
    root.update()
    assert_dialogue_output_visible(window)
    assert window.dialogue_text_input.winfo_height() > 180, dpi
    assert bottom(window.dialogue_text_input) <= bottom(window.dialogue_tab)

restored_geometry = "1440x800+0+0"
root.geometry(restored_geometry)
root.update()
assert_dialogue_output_visible(window)
root.state("zoomed")
root.update()
assert_dialogue_output_visible(window)
root.state("normal")
root.geometry(restored_geometry)
root.update()
assert_dialogue_output_visible(window)

window.generate_button.focus_force()
root.update()
assert root.focus_get() is window.generate_button
assert str(window.generate_button.cget("takefocus")) not in ("", "0")
assert not window.dialogue_text_input.bind("<MouseWheel>")
assert window.preview_canvas.bind("<MouseWheel>")
assert "bind all" not in str(root.bind())

generation_body_height = window.body.winfo_height()
window.workspace_tabs.select(window.samples_tab)
window._on_workspace_tab_changed()
root.update()
assert window.action_bar.winfo_manager() == ""
assert not window.action_bar.winfo_ismapped()
assert window.body.winfo_height() >= generation_body_height + 60
samples_body_height = window.body.winfo_height()
samples_height = window.preview_canvas.winfo_height()
assert samples_height > 300

window.set_mode("Narração")
root.update()
assert window.action_bar.winfo_manager() == "grid"
assert window.action_bar.winfo_ismapped()
assert window.body.winfo_height() < samples_body_height
assert window.generate_button.cget("state") == "normal"

window.is_running = True
window.cancel_event = threading.Event()
window.pause_event = threading.Event()
window._set_running_controls(True)
window.workspace_tabs.select(window.samples_tab)
window._on_workspace_tab_changed()
root.update()
assert window.action_bar.winfo_manager() == ""
window.set_mode("Conversação A/B")
root.update()
assert window.action_bar.winfo_manager() == "grid"
assert window.generate_button.cget("state") == "disabled"
assert not window.pause_buttons[0].instate(["disabled"])
assert not window.cancel_button.instate(["disabled"])
window.is_running = False
window.cancel_event = None
window.pause_event = None
window._set_running_controls(False)

window.on_close()
after_audio = tuple(sorted(V2_ROOT.rglob("*.wav"))) + tuple(sorted(V2_ROOT.rglob("*.mp3")))
assert after_audio == before_audio
assert "torch" not in sys.modules and "kokoro" not in sys.modules
assert "v2_kokoro.app.core.job_runner" not in sys.modules
print("Cycle 3 UI: DPI viewports, full A/B output, maximize/restore, long content, focus, wheel and Samples bar OK")
