from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import threading
from pathlib import Path

import psutil


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    install_root = Path(sys.argv[1]).resolve()
    data_root = Path(sys.argv[2]).resolve()
    result_path = Path(sys.argv[3]).resolve()
    os.environ["VTS_V2_HUMANIZATION_A_DATA_ROOT"] = str(data_root)
    sys.path.insert(0, str(install_root))

    from v2_kokoro.app.security.offline_guard import OfflineNetworkError, install_offline_guard

    install_offline_guard()
    try:
        socket.create_connection(("127.0.0.1", 9), timeout=0.01)
        raise AssertionError("Installed runtime allowed a network connection")
    except OfflineNetworkError:
        pass

    from v2_kokoro.app.core.generation_contracts import GenerationRequest, MODE_DIALOGUE_AB, MODE_NARRATION
    from v2_kokoro.app.core.job_runner import run_generation

    requests = [
        GenerationRequest(
            mode=MODE_NARRATION,
            project_name="installer_narration",
            text="Hello. This is a short offline installer narration test.",
            narration_voice_id="af_heart",
        ),
        GenerationRequest(
            mode=MODE_DIALOGUE_AB,
            project_name="installer_dialogue",
            text="A: Hello. Are you ready?\nB: Yes. Let us test the installed application.",
            voice_a_id="bf_emma",
            voice_b_id="am_puck",
        ),
    ]
    results = []
    for request in requests:
        result = run_generation(request)
        if not result.success or not result.log_file:
            raise RuntimeError(f"Installed generation failed: {result.errors}")
        log_path = Path(result.log_file)
        log = json.loads(log_path.read_text(encoding="utf-8"))
        if log.get("full_text_saved") is not False or log.get("offline") is not True:
            raise RuntimeError("Installed generation log is unsafe")
        final_mp3 = next(Path(path) for path in result.created_files if path.endswith("_complete.mp3"))
        isolation = result.metadata.get("process_isolation", {})
        worker_pid = isolation.get("worker_pid")
        if not result.metadata.get("process_isolated") or not isolation.get("worker_exited"):
            raise RuntimeError("Installed generation was not process-isolated")
        if isinstance(worker_pid, int) and psutil.pid_exists(worker_pid):
            raise RuntimeError(f"Installed generation left an orphan worker: {worker_pid}")
        if any(path.endswith(".wav") for path in result.created_files):
            raise RuntimeError("Installed generation published an unexpected WAV")
        results.append({
            "mode": request.mode,
            "mp3": str(final_mp3),
            "mp3_bytes": final_mp3.stat().st_size,
            "mp3_sha256": sha256(final_mp3),
            "log": str(log_path),
            "worker_pid": worker_pid,
            "worker_exited": isolation.get("worker_exited"),
        })

    cancel = threading.Event()

    def progress(event) -> None:
        if event.stage == "synthesizing" and event.current == 1:
            cancel.set()

    cancelled = run_generation(
        GenerationRequest(
            mode=MODE_NARRATION,
            project_name="installer_cancel",
            text="This sentence starts a real synthesis step and is then cancelled safely.",
            narration_voice_id="af_heart",
        ),
        progress_callback=progress,
        cancel_event=cancel,
    )
    if cancelled.success or not cancelled.metadata.get("cancelled") or cancelled.log_file is not None:
        raise RuntimeError("Installed cancellation contract failed")
    cancel_isolation = cancelled.metadata.get("process_isolation", {})
    cancel_pid = cancel_isolation.get("worker_pid")
    if not cancel_isolation.get("worker_exited") or (isinstance(cancel_pid, int) and psutil.pid_exists(cancel_pid)):
        raise RuntimeError("Cancelled installed job left an orphan worker")
    if (data_root / "audios" / "generated" / "installer_cancel").exists():
        raise RuntimeError("Cancelled installed job kept partial output")

    payload = {
        "offline_guard": True,
        "generation_results": results,
        "cancelled": True,
        "cancel_log": None,
        "cancel_worker_pid": cancel_pid,
    }
    result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
