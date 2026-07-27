from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import psutil

from _rc_bootstrap import V2_ROOT


if str(V2_ROOT) not in sys.path:
    sys.path.insert(0, str(V2_ROOT))

from v2_kokoro.app.core.ffmpeg_runner import validate_mp3_complete  # noqa: E402
from v2_kokoro.app.core.generation_contracts import GenerationRequest, MODE_DIALOGUE_AB, MODE_NARRATION  # noqa: E402
from v2_kokoro.app.core.job_runner import run_generation  # noqa: E402
from v2_kokoro.app.core.resource_manager import PROFILE_AUTOMATIC, PROFILE_BALANCED, PROFILE_ECONOMIC  # noqa: E402


def memory_snapshot() -> dict:
    system = psutil.virtual_memory()
    return {
        "app_rss_mb": round(psutil.Process().memory_info().rss / (1024**2), 1),
        "system_available_ram_gb": round(system.available / (1024**3), 3),
    }


def post_job_memory(full: bool) -> dict:
    samples = {"after_0s": memory_snapshot()}
    if not full:
        return samples
    for seconds, delay in ((10, 10), (30, 20), (60, 30)):
        time.sleep(delay)
        samples[f"after_{seconds}s"] = memory_snapshot()
    return samples


def output_mp3(result) -> Path:
    matches = [V2_ROOT / value for value in result.created_files if value.endswith(".mp3")]
    if len(matches) != 1:
        raise AssertionError(f"Expected one final MP3, got {result.created_files}")
    return matches[0]


def valid_narration(project_name: str, text: str, output_base: Path) -> GenerationRequest:
    return GenerationRequest(
        mode=MODE_NARRATION,
        project_name=project_name,
        text=text,
        narration_voice_id="af_heart",
        output_base_dir=output_base,
    )


def valid_dialogue(project_name: str, text: str, output_base: Path) -> GenerationRequest:
    return GenerationRequest(
        mode=MODE_DIALOGUE_AB,
        project_name=project_name,
        text=text,
        voice_a_id="af_heart",
        voice_b_id="bf_emma",
        output_base_dir=output_base,
    )


def assert_isolated(result) -> dict:
    isolation = result.metadata.get("process_isolation", {})
    if not result.metadata.get("process_isolated"):
        raise AssertionError("Kokoro was not isolated from the app process")
    if not isolation.get("worker_exited"):
        raise AssertionError(f"Worker still active: {isolation}")
    worker_pid = isolation.get("worker_pid")
    if not isinstance(worker_pid, int) or worker_pid <= 0:
        raise AssertionError(f"Invalid worker pid: {isolation}")
    if psutil.pid_exists(worker_pid):
        raise AssertionError(f"Orphan Kokoro worker remains: {worker_pid}")
    return isolation


def run_success(name: str, request: GenerationRequest, profile: str, *, full_recovery: bool, pause_once: bool = False) -> dict:
    events = []
    pause_event = threading.Event()
    paused = threading.Event()

    def on_progress(event) -> None:
        events.append({"stage": event.stage, "current": event.current, "total": event.total})
        if pause_once and event.stage == "synthesizing" and event.current == 1 and not paused.is_set():
            pause_event.set()
            paused.set()

    before = memory_snapshot()
    if pause_once:
        holder = []
        worker = threading.Thread(
            target=lambda: holder.append(run_generation(request, on_progress, resource_profile=profile, pause_event=pause_event)),
            daemon=True,
        )
        worker.start()
        if not paused.wait(timeout=60):
            raise AssertionError("Pause was not requested from the first child progress event")
        time.sleep(1.0)
        if not worker.is_alive():
            raise AssertionError("Generation finished before pause could take effect")
        pause_event.clear()
        worker.join(timeout=300)
        if worker.is_alive() or not holder:
            raise AssertionError("Paused generation did not resume safely")
        result = holder[0]
    else:
        result = run_generation(request, on_progress, resource_profile=profile)
    if not result.success:
        raise AssertionError(f"Generation failed: {result.errors}")
    isolation = assert_isolated(result)
    mp3 = output_mp3(result)
    validation = validate_mp3_complete(mp3)
    if validation.duration_seconds <= 0 or validation.size_bytes <= 0:
        raise AssertionError("Final MP3 did not decode completely")
    if result.metadata.get("removed_wav_files", 0) < 2:
        raise AssertionError("Sequential job WAV artifacts were not accounted for")
    return {
        "name": name,
        "success": True,
        "profile": profile,
        "mode": request.mode,
        "characters": len(request.text),
        "before": before,
        "worker": isolation,
        "mp3": str(mp3),
        "mp3_duration_seconds": validation.duration_seconds,
        "mp3_size_bytes": validation.size_bytes,
        "progress_stages": events,
        "post_job_memory": post_job_memory(full_recovery),
        "pause_resume": pause_once,
    }


def run_cancellation(output_base: Path, full_recovery: bool) -> dict:
    request = valid_narration("cancelled", " ".join(["Cancellation remains cooperative and safe."] * 40), output_base)
    cancel_event = threading.Event()
    observed = threading.Event()

    def on_progress(event) -> None:
        # Cancel at the first worker-side preparation event. This keeps the
        # control deterministic even when the RAM guard would intervene before
        # the first synthesis event on a busy 16 GB workstation.
        if event.stage == "preparing":
            observed.set()
            cancel_event.set()

    before = memory_snapshot()
    result = run_generation(request, on_progress, resource_profile=PROFILE_ECONOMIC, cancel_event=cancel_event)
    if not observed.is_set() or result.success or result.errors != ["generation_cancelled"]:
        raise AssertionError(f"Cancellation did not complete safely: {result.errors}")
    isolation = assert_isolated(result)
    if (output_base / "cancelled").exists():
        raise AssertionError("Cancelled job retained its user output folder")
    return {
        "name": "cancelled",
        "success": False,
        "errors": result.errors,
        "before": before,
        "worker": isolation,
        "post_job_memory": post_job_memory(full_recovery),
    }


def run_failure(output_base: Path, full_recovery: bool) -> dict:
    request = valid_narration("failed_profile", "A controlled worker failure remains recoverable.", output_base)
    before = memory_snapshot()
    result = run_generation(request, resource_profile="unsupported-profile")
    if result.success:
        raise AssertionError("Unsupported profile unexpectedly succeeded")
    isolation = assert_isolated(result)
    return {
        "name": "failed_profile",
        "success": False,
        "errors": result.errors,
        "before": before,
        "worker": isolation,
        "post_job_memory": post_job_memory(full_recovery),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Collect 0/10/30/60-second recovery samples after every case.")
    parser.add_argument("--controls-only", action="store_true", help="Run cancellation and controlled-failure checks only.")
    args = parser.parse_args()
    test_root = V2_ROOT / "temp" / "rc20_process_isolation" / uuid4().hex
    output_base = test_root / "output"
    output_base.mkdir(parents=True)
    medium = " ".join(["This medium narration verifies sequential audio generation."] * 12)
    long_text = " ".join(["The long job verifies that each completed worker releases its native allocations before the next job."] * 18)
    dialogue = "\n".join(
        [
            "A: The application keeps the interface responsive.",
            "B: The Kokoro worker is temporary and sequential.",
            "A: Progress, pause, resume, and cancellation remain available.",
            "B: Final audio is validated before it is published.",
        ] * 4
    )
    cases = []
    if not args.controls_only:
        cases.extend([
            run_success("short_auto", valid_narration("short_auto", "A short isolated narration.", output_base), PROFILE_AUTOMATIC, full_recovery=args.full),
            run_success("medium_economic", valid_narration("medium_economic", medium, output_base), PROFILE_ECONOMIC, full_recovery=args.full),
            run_success("dialogue_balanced", valid_dialogue("dialogue_balanced", dialogue, output_base), PROFILE_BALANCED, full_recovery=args.full, pause_once=True),
            run_success("dialogue_auto", valid_dialogue("dialogue_auto", dialogue, output_base), PROFILE_AUTOMATIC, full_recovery=args.full),
            run_success("long_balanced", valid_narration("long_balanced", long_text, output_base), PROFILE_BALANCED, full_recovery=args.full),
        ])
    cases.extend([run_cancellation(output_base, args.full), run_failure(output_base, args.full)])
    report = {
        "schema_version": "1.0",
        "full_recovery_samples": args.full,
        "cases": cases,
        "successful_sequential_generations": sum(1 for case in cases if case.get("success")),
        "manual_listening_targets": [case["mp3"] for case in cases if case.get("success")],
    }
    report_path = V2_ROOT / "temp" / "rc20_validation" / "process_isolation_memory_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(report_path), "successes": report["successful_sequential_generations"], "cases": len(cases)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
