
from _rc_bootstrap import V2_ROOT

import sys
import threading
import tkinter as tk
from pathlib import Path


PROJECT_ROOT = V2_ROOT
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from v2_kokoro.app.core.resource_manager import ResourceDecision, ResourceSnapshot  # noqa: E402
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


healthy = ResourceDecision(True, ResourceSnapshot(8.0, 20.0, None, None, 10.0, 200.0))
root = tk.Tk()
root.withdraw()
window = KokoroV2Window(
    root,
    job_runner=lambda *_args, **_kwargs: None,
    preview_player=FakePreview(),
    resource_checker=lambda _profile: healthy,
)
assert window.profile_var.get() == "Automatico (recomendado)"
assert window.cancel_button.instate(["disabled"])
assert all(button.instate(["disabled"]) for button in window.pause_buttons)

window.is_running = True
window.cancel_event = threading.Event()
window.pause_event = threading.Event()
window._set_running_controls(True)
assert not window.cancel_button.instate(["disabled"])
assert all(not button.instate(["disabled"]) for button in window.pause_buttons)
window.on_pause()
assert window.pause_event.is_set()
assert window.progress_stage_var.get() == "Pausado"
window.on_pause()
assert not window.pause_event.is_set()
window.on_cancel()
assert window.cancel_event.is_set()
assert not window.pause_event.is_set()
assert "Cancelando" in window.status_var.get()

window.is_running = False
window.cancel_event = None
window._set_running_controls(False)
window._apply_resource_snapshot(
    {"system_cpu_percent": 25.0, "process_ram_mb": 512.0, "available_ram_gb": 7.5, "disk_free_gb": 18.0}
)
assert "CPU do sistema: 25%" in window.resource_status_var.get()

root.destroy()
print("6Z/RC-19 UI resources/cancel: automatic default, pause/resume, monitoring text and cancel control OK")
