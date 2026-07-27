
from _rc_bootstrap import V2_ROOT

import sys
import tkinter as tk
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4


ROOT = V2_ROOT
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v2_kokoro.app.core.generation_contracts import GenerationResult  # noqa: E402
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


v2_root = V2_ROOT
before_wav = len(list((v2_root / "audios").rglob("*.wav")))
before_mp3 = len(list((v2_root / "audios").rglob("*.mp3")))
test_root = v2_root / "temp" / "phase_7e" / uuid4().hex
first = test_root / "first"
second = test_root / "second"
first.mkdir(parents=True)
second.mkdir()
opened: list[str] = []

with (
    patch("v2_kokoro.app.ui.main_window.current_output_directory", return_value=first.resolve()),
    patch("v2_kokoro.app.ui.main_window.save_selected_output_directory", side_effect=lambda path: Path(path).resolve()),
):
    root = tk.Tk()
    root.withdraw()
    window = KokoroV2Window(
        root,
        job_runner=lambda *_args, **_kwargs: None,
        preview_player=FakePreview(),
        folder_chooser=lambda _initial: str(second),
        folder_opener=opened.append,
    )
    assert window.output_directory_var.get() == str(first.resolve())
    window.on_choose_output_directory()
    assert window.output_directory == second.resolve()
    assert window.output_directory_var.get() == str(second.resolve())
    window.folder_chooser = lambda _initial: ""
    window.on_choose_output_directory()
    assert window.output_directory == second.resolve()
    window.on_open_output_directory()
    assert opened == [str(second.resolve())]

    window.project_var.set("output_folder_contract")
    window.text_input.insert("1.0", "Short local output test.")
    window.narration_voice_var.set(window.voice_by_id["af_heart"]["display_label"])
    request = window.build_request()
    assert request.output_base_dir == second.resolve()
    mp3_path = second / "output_folder_contract" / "mp3" / "narration_complete.mp3"
    window._finish_result(
        GenerationResult(
            success=True,
            mode="narration",
            project_name="output_folder_contract",
            created_files=[str(mp3_path), str(second / "output_folder_contract" / "log.json")],
        )
    )
    assert window.output_var.get() == f"MP3 salvo em: {mp3_path.resolve()}"
    assert "WAV" not in window.output_var.get() and "Log" not in window.output_var.get()
    window.on_close()

assert len(list((v2_root / "audios").rglob("*.wav"))) == before_wav
assert len(list((v2_root / "audios").rglob("*.mp3"))) == before_mp3
print("7E UI output folder: selection, cancellation, opening, request path and MP3-only result OK")
