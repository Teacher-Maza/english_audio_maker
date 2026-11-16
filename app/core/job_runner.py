from __future__ import annotations

import gc
import multiprocessing as multiprocessing
import os
import queue as queue_module
import shutil
import threading
import time
from collections import Counter
from dataclasses import replace
from shutil import copy2
from pathlib import Path
from typing import Callable

import psutil

from .audio_processor import assemble_wav_files, save_wav
from .dialogue_parser import DialogueTurn, parse_dialogue_ab
from .export_manager import ExportLayout, create_export_layout
from .ffmpeg_runner import convert_wav_to_mp3, validate_mp3_complete
from .generation_contracts import GenerationRequest, GenerationResult, MODE_DIALOGUE_AB, MODE_NARRATION
from .log_manager import write_safe_log
from .progress_events import ProgressCallback, ProgressEvent, emit
from .project_paths import confine_output_path, load_paths, relative_to_v2
from .resource_manager import (
    PROFILE_AUTOMATIC,
    PROFILE_BALANCED,
    ResourcePressureError,
    ResourceCallback,
    ResourceMonitor,
    ResourceSnapshot,
    AdaptiveController,
    apply_runtime_limits,
    evaluate_resources,
    load_resource_policy,
    resolve_profile,
    wait_for_memory_recovery,
)
from .prosodic_segmenter import SEGMENTER_ID, segment_text_with_diagnostics
from .validators import validate_request
from .voice_registry import VoiceRegistry
from .recovery_store import RecoveryStore
from v2_kokoro.app.security.offline_guard import install_offline_guard


_GENERATION_LOCK = threading.Lock()


class GenerationCancelled(RuntimeError):
    pass


def _plan_items(request: GenerationRequest, *, max_chunk_chars: int = 280) -> tuple[list[tuple[str, str]], str, dict]:
    if request.mode == MODE_NARRATION:
        result = segment_text_with_diagnostics(request.text, max_chars=max_chunk_chars)
        return (
            [(request.narration_voice_id or "", chunk) for chunk in result.texts],
            "narration_complete",
            {**result.diagnostics(), "mode": MODE_NARRATION},
        )
    turns: list[DialogueTurn] = parse_dialogue_ab(request.text)
    items: list[tuple[str, str]] = []
    turn_diagnostics: list[dict] = []
    for turn in turns:
        result = segment_text_with_diagnostics(turn.text, max_chars=max_chunk_chars)
        voice_id = (request.voice_a_id if turn.speaker == "A" else request.voice_b_id) or ""
        items.extend((voice_id, chunk) for chunk in result.texts)
        turn_diagnostics.append(result.diagnostics())
    lengths = [len(text) for _, text in items]
    boundary_counts = Counter()
    for diagnostics in turn_diagnostics:
        boundary_counts.update(diagnostics["boundary_counts"])
    diagnostics = {
        "strategy": SEGMENTER_ID,
        "mode": MODE_DIALOGUE_AB,
        "max_chars": max_chunk_chars,
        "source_char_count": sum(item["source_char_count"] for item in turn_diagnostics),
        "turn_count": len(turns),
        "segment_count": len(items),
        "segment_lengths": lengths,
        "max_generated_chars": max(lengths, default=0),
        "boundary_counts": dict(sorted(boundary_counts.items())),
        "oversized_segment_count": sum(item["oversized_segment_count"] for item in turn_diagnostics),
        "text_preserved": all(item["text_preserved"] for item in turn_diagnostics),
        "full_text_saved": False,
    }
    return items, "dialogue_complete", diagnostics


def _check_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise GenerationCancelled("generation_cancelled")


def _wait_if_paused(pause_event: threading.Event | None, cancel_event: threading.Event | None) -> None:
    while pause_event is not None and pause_event.is_set():
        _check_cancelled(cancel_event)
        time.sleep(0.1)


def _work_root(layout: ExportLayout) -> Path:
    return layout.work_root or layout.root


def _assert_job_artifact(layout: ExportLayout, path: Path) -> Path:
    candidate = Path(path).resolve(strict=False)
    allowed_roots = (_work_root(layout), layout.root, layout.log_file.parent)
    if not any(candidate != root.resolve(strict=False) and root.resolve(strict=False) in candidate.parents for root in allowed_roots):
        raise ValueError("Job artifact is outside its authorized job roots")
    return confine_output_path(candidate, label="job artifact")


def _remove_known_artifacts(layout: ExportLayout, artifacts: list[Path], *, keep: set[Path] | None = None) -> int:
    """Remove only paths explicitly registered by this job, never a folder scan."""
    retained = {path.resolve(strict=False) for path in (keep or set())}
    removed = 0
    for artifact in reversed(artifacts):
        path = Path(artifact).resolve(strict=False)
        if path in retained or not path.exists():
            continue
        _assert_job_artifact(layout, path)
        for _attempt in range(20):
            try:
                path.unlink()
                removed += 1
                break
            except PermissionError:
                time.sleep(0.1)
        else:
            raise RuntimeError(f"Could not release job artifact: {path.name}")
    return removed


def _remove_empty_job_directories(layout: ExportLayout, *, remove_output_root: bool) -> None:
    """Remove only this job's known empty directories, from leaf to root."""
    directories = [layout.temp_dir, layout.wav_dir, layout.mp3_dir, _work_root(layout)]
    if remove_output_root:
        directories.append(layout.root)
    for directory in directories:
        try:
            _assert_job_artifact(layout, directory / ".directory-check")
            directory.rmdir()
        except (FileNotFoundError, OSError):
            continue


def _run_generation_local(
    request: GenerationRequest,
    progress_callback: ProgressCallback | None = None,
    *,
    resource_profile: str = PROFILE_AUTOMATIC,
    resource_callback: ResourceCallback | None = None,
    cancel_event: threading.Event | None = None,
    pause_event: threading.Event | None = None,
    _resource_evaluator: Callable | None = None,
    _monitor_factory: Callable | None = None,
    _engine_factory: Callable | None = None,
    _mp3_validator: Callable | None = None,
    _execution_metadata: dict | None = None,
    _lifecycle_callback: Callable[[dict], None] | None = None,
    _checkpoint_factory: Callable | None = None,
) -> GenerationResult:
    install_offline_guard()
    if not _GENERATION_LOCK.acquire(blocking=False):
        return GenerationResult(
            success=False,
            mode=request.mode,
            project_name=request.project_name,
            errors=["generation_already_running"],
            metadata={"engine": "kokoro", "offline": True, "full_text_saved": False},
        )

    registry = VoiceRegistry()
    layout: ExportLayout | None = None
    engine = None
    monitor: ResourceMonitor | None = None
    resource_summary: dict = {}
    runtime: dict = {}
    created: list[str] = []
    job_artifacts: list[Path] = []
    wav_artifacts: list[Path] = []
    mp3_artifacts: list[Path] = []
    chunk_wavs: list[Path] = []
    item_count = 0
    voices: list[str] = []
    warnings: list[str] = []
    audio = None
    profile = None
    resource_plan: dict = {}
    checkpoint = None
    reused_chunks = 0
    try:
        _check_cancelled(cancel_event)
        _wait_if_paused(pause_event, cancel_event)
        emit(progress_callback, "validating", 5)
        validate_request(request, registry)
        evaluator = _resource_evaluator or evaluate_resources
        decision = evaluator(resource_profile, output_dir=request.output_base_dir)
        profile = resolve_profile(resource_profile, snapshot=decision.snapshot, text_characters=len(request.text))
        controller = AdaptiveController(profile)
        runtime = {**(_execution_metadata or {}), **apply_runtime_limits(profile)}
        resource_plan = {"initial": decision.plan or {"profile": profile.to_dict()}}
        warnings.extend(decision.warnings)
        if not decision.allowed:
            return GenerationResult(
                success=False,
                mode=request.mode,
                project_name=request.project_name,
                warnings=warnings,
                errors=list(decision.blocks),
                metadata={
                    "engine": "kokoro",
                    "offline": True,
                    "full_text_saved": False,
                    "resource_profile": profile.profile_id,
                    "resource_preflight": decision.snapshot.to_dict(),
                    "resource_plan": resource_plan,
                    **runtime,
                },
            )

        if _engine_factory is None or _checkpoint_factory is not None:
            emit(progress_callback, "checking_recovery", 7)
            checkpoint = (_checkpoint_factory or RecoveryStore)(request, registry, profile.chunk_chars)
            profile = replace(profile, chunk_chars=checkpoint.chunk_chars)
            controller = AdaptiveController(profile)
            runtime['chunk_chars'] = profile.chunk_chars
        items, final_stem, segmentation = _plan_items(request, max_chunk_chars=profile.chunk_chars)
        resource_plan["segmentation"] = segmentation
        item_count = len(items)
        voices = sorted({voice_id for voice_id, _ in items})
        _check_cancelled(cancel_event)
        _wait_if_paused(pause_event, cancel_event)
        emit(progress_callback, "preparing", 10, 0, item_count)
        layout = create_export_layout(request.project_name, request.output_base_dir)
        if _lifecycle_callback is not None:
            _lifecycle_callback(
                {
                    "event": "layout",
                    "job_id": layout.job_id,
                    "root": str(layout.root),
                    "work_root": str(_work_root(layout)),
                    "log_file": str(layout.log_file),
                    "final_stem": final_stem,
                    "recovery_root": str(checkpoint.root) if checkpoint is not None else None,
                }
            )
        monitor_factory = _monitor_factory or ResourceMonitor
        def observe_resources(snapshot: dict) -> None:
            controller.observe(ResourceSnapshot(**snapshot))
            if resource_callback is not None:
                resource_callback(snapshot)

        monitor = monitor_factory(layout.root, observe_resources)
        monitor.start()

        for index, (voice_id, text) in enumerate(items, start=1):
            _check_cancelled(cancel_event)
            _wait_if_paused(pause_event, cancel_event)
            if _resource_evaluator is None:
                percent = 15 + round(55 * (index - 1) / max(1, item_count))

                def recovering(snapshot: dict) -> None:
                    observe_resources(snapshot)
                    if snapshot["available_ram_gb"] < resource_plan["initial"].get("minimum_start_available_gb", 0):
                        emit(progress_callback, "waiting_resources", percent, index, item_count)

                runtime_snapshot = wait_for_memory_recovery(
                    request.output_base_dir,
                    callback=recovering,
                    cancel_event=cancel_event,
                )
                _check_cancelled(cancel_event)
                runtime_decision = evaluate_resources(
                    profile.profile_id,
                    snapshot=runtime_snapshot,
                    output_dir=request.output_base_dir,
                    text_characters=len(request.text),
                )
                warnings.extend(item for item in runtime_decision.warnings if item not in warnings)
                if not runtime_decision.allowed:
                    raise ResourcePressureError("Recursos deixaram de ser seguros durante a geracao: " + " ".join(runtime_decision.blocks))
                if profile.adaptive:
                    updated_profile = controller.observe(runtime_snapshot)
                    if updated_profile.threads != profile.threads:
                        profile = updated_profile
                        runtime = {**runtime, **apply_runtime_limits(profile)}
                        set_threads = getattr(engine, "set_threads", None)
                        if callable(set_threads):
                            set_threads(profile.threads)
                    else:
                        profile = updated_profile
                    runtime.update(profile.to_dict())
                resource_plan["latest"] = {**runtime_decision.plan, "profile": profile.to_dict()}
            percent = 15 + round(55 * (index - 1) / max(1, item_count))
            stage = "synthesizing_reduced" if profile.adaptive and profile.throttle_seconds else "synthesizing"
            emit(progress_callback, stage, percent, index, item_count)
            partial = layout.temp_dir / f"item_{index:03d}.wav"
            if checkpoint is not None and checkpoint.restore(index, partial):
                reused_chunks += 1
                emit(progress_callback, "restoring_audio", percent, index, item_count)
            else:
                if engine is None:
                    if _engine_factory is None:
                        from .kokoro_engine import KokoroEngine
                        engine = KokoroEngine(registry, threads=profile.threads)
                    else:
                        engine = _engine_factory(registry, profile.threads)
                audio = engine.synthesize(text, voice_id, request.speed)
                _check_cancelled(cancel_event)
                _wait_if_paused(pause_event, cancel_event)
                save_wav(partial, audio)
                if checkpoint is not None:
                    checkpoint.save(index, partial)
            job_artifacts.append(partial)
            wav_artifacts.append(partial)
            chunk_wavs.append(partial)
            created.append(relative_to_v2(partial))
            release_voicepacks = getattr(engine, "release_voicepacks", None)
            if callable(release_voicepacks):
                release_voicepacks()
            del audio
            audio = None
            gc.collect()
            if profile.throttle_seconds and index < item_count:
                if cancel_event is not None:
                    cancel_event.wait(profile.throttle_seconds)
                    _check_cancelled(cancel_event)
                else:
                    time.sleep(profile.throttle_seconds)

        _check_cancelled(cancel_event)
        _wait_if_paused(pause_event, cancel_event)
        emit(progress_callback, "assembling_wav", 78, item_count, item_count)
        wav_path = layout.wav_dir / f"{final_stem}.wav"
        assemble_wav_files(chunk_wavs, wav_path)
        job_artifacts.append(wav_path)
        wav_artifacts.append(wav_path)
        created.append(relative_to_v2(wav_path))

        _check_cancelled(cancel_event)
        _wait_if_paused(pause_event, cancel_event)
        emit(progress_callback, "creating_mp3", 90)
        provisional_mp3 = layout.mp3_dir / f"{final_stem}.mp3"
        convert_wav_to_mp3(wav_path, provisional_mp3)
        job_artifacts.append(provisional_mp3)
        mp3_artifacts.append(provisional_mp3)
        validator = _mp3_validator or validate_mp3_complete
        validator(provisional_mp3)
        _check_cancelled(cancel_event)
        _wait_if_paused(pause_event, cancel_event)
        final_mp3 = layout.root / f"{final_stem}.mp3"
        copy2(provisional_mp3, final_mp3)
        job_artifacts.append(final_mp3)
        mp3_artifacts.append(final_mp3)
        mp3_validation = validator(final_mp3)
        _check_cancelled(cancel_event)
        removed_artifacts = _remove_known_artifacts(layout, job_artifacts, keep={final_mp3})
        removed_wavs = len(wav_artifacts)
        _remove_empty_job_directories(layout, remove_output_root=False)
        created = [relative_to_v2(final_mp3)]

        resource_summary = {**monitor.stop(), **runtime}
        monitor = None
        _check_cancelled(cancel_event)
        emit(progress_callback, "saving_log", 97)
        log_relative = relative_to_v2(layout.log_file)
        write_safe_log(
            layout.log_file,
            success=True,
            mode=request.mode,
            project_name=request.project_name,
            voices=voices,
            speed=request.speed,
            item_count=item_count,
            files=created,
            resource_profile=profile.profile_id,
            resource_summary=resource_summary,
            resource_plan=resource_plan,
            job_id=layout.job_id,
            export_validation={
                "mp3_validated": True,
                "mp3_duration_seconds": float(mp3_validation.duration_seconds),
                "mp3_size_bytes": int(mp3_validation.size_bytes),
                "removed_wav_files": removed_wavs,
                "removed_artifact_files": removed_artifacts,
            },
        )
        job_artifacts.append(layout.log_file)
        created.append(log_relative)
        _check_cancelled(cancel_event)
        emit(progress_callback, "completed", 100, item_count, item_count)
        if checkpoint is not None:
            try:
                checkpoint.discard()
            except OSError:
                warnings.append('Audio concluido; alguns arquivos de recuperacao permaneceram no disco.')
        return GenerationResult(
            success=True,
            mode=request.mode,
            project_name=request.project_name,
            created_files=created,
            warnings=warnings,
            log_file=log_relative,
            metadata={
                "engine": "kokoro",
                "offline": True,
                "device": "cpu",
                "reused_chunks": reused_chunks,
                "item_count": item_count,
                "speed_factor": float(request.speed),
                "full_text_saved": False,
                "resource_profile": profile.profile_id,
                "resource_summary": resource_summary,
                "resource_plan": resource_plan,
                "segmentation": segmentation,
                "mp3_duration_seconds": float(mp3_validation.duration_seconds),
                "mp3_size_bytes": int(mp3_validation.size_bytes),
                "removed_wav_files": removed_wavs,
                "removed_artifact_files": removed_artifacts,
                "job_id": layout.job_id,
                **runtime,
            },
        )
    except GenerationCancelled:
        if monitor is not None:
            resource_summary = {**monitor.stop(), **runtime}
            monitor = None
        if layout is not None:
            if layout.log_file.exists():
                job_artifacts.append(layout.log_file)
            _remove_known_artifacts(layout, job_artifacts)
            _remove_empty_job_directories(layout, remove_output_root=True)
        recovery_discarded = True
        if checkpoint is not None:
            try:
                checkpoint.discard()
            except (OSError, ValueError):
                recovery_discarded = False
                warnings.append('Nao foi possivel apagar todo o progresso temporario.')
        emit(progress_callback, "cancelled", 100)
        return GenerationResult(
            success=False,
            mode=request.mode,
            project_name=request.project_name,
            warnings=warnings,
            errors=["generation_cancelled"],
            log_file=None,
            metadata={
                "engine": "kokoro",
                "offline": True,
                "full_text_saved": False,
                "cancelled": True,
                "recovery_discarded": recovery_discarded,
                "job_id": layout.job_id if layout else None,
                "resource_profile": profile.profile_id if profile else resource_profile,
                "resource_summary": resource_summary,
                "resource_plan": resource_plan,
            },
        )
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        if monitor is not None:
            resource_summary = {**monitor.stop(), **runtime}
            monitor = None
        if layout is not None:
            _remove_known_artifacts(layout, mp3_artifacts)
            _remove_empty_job_directories(layout, remove_output_root=True)
            log_relative = relative_to_v2(layout.log_file)
            write_safe_log(
                layout.log_file,
                success=False,
                mode=request.mode,
                project_name=request.project_name,
                voices=voices,
                speed=request.speed,
                item_count=item_count,
                files=created,
                error=message,
                resource_profile=profile.profile_id if profile else resource_profile,
                resource_summary=resource_summary,
                resource_plan=resource_plan,
                job_id=layout.job_id,
                export_validation={"mp3_validated": False, "removed_wav_files": 0},
            )
        else:
            log_relative = None
        emit(progress_callback, "error", 100)
        return GenerationResult(
            success=False,
            mode=request.mode,
            project_name=request.project_name,
            warnings=warnings,
            errors=[message],
            log_file=log_relative,
            metadata={
                "engine": "kokoro",
                "offline": True,
                "full_text_saved": False,
                "resource_profile": profile.profile_id if profile else resource_profile,
                "resource_summary": resource_summary,
                "resource_plan": resource_plan,
                "job_id": layout.job_id if layout else None,
            },
        )
    finally:
        if checkpoint is not None:
            checkpoint.close()
        audio = None
        chunk_wavs.clear()
        if monitor is not None:
            monitor.stop()
        if engine is not None:
            try:
                engine.close()
            except Exception:
                pass
        _GENERATION_LOCK.release()


def _worker_settings() -> dict[str, float]:
    """Read bounded coordinator timings without changing global machine state."""
    try:
        policy = load_resource_policy()
        raw = policy.get("process_isolation", {})
    except Exception:
        policy = {}
        raw = {}
    return {
        "poll_seconds": min(1.0, max(0.05, float(raw.get("poll_seconds", 0.10)))),
        "cancel_grace_seconds": max(2.0, float(raw.get("cancel_grace_seconds", 20.0))),
        "join_seconds": max(1.0, float(raw.get("join_seconds", 8.0))),
        "emergency_free_ram_gb": max(0.25, float(policy.get("adaptive", {}).get("emergency_free_ram_gb", 0.5))),
    }


def _memory_sample(process: psutil.Process | None = None) -> dict[str, float]:
    memory = psutil.virtual_memory()
    target = process or psutil.Process()
    try:
        rss_mb = round(target.memory_info().rss / (1024**2), 1)
    except (psutil.Error, OSError):
        rss_mb = 0.0
    return {
        "rss_mb": rss_mb,
        "available_ram_gb": round(memory.available / (1024**3), 3),
    }


def _queue_progress(queue, event: ProgressEvent) -> None:
    try:
        queue.put(("progress", event))
    except (OSError, ValueError):
        pass


def _queue_resource(queue, snapshot: dict) -> None:
    try:
        queue.put(("resource", snapshot))
    except (OSError, ValueError):
        pass


def _queue_lifecycle(queue, payload: dict) -> None:
    try:
        queue.put(("lifecycle", payload))
    except (OSError, ValueError):
        pass


def _child_generation_entry(
    result_queue,
    event_queue,
    request: GenerationRequest,
    resource_profile: str,
    cancel_event,
    pause_event,
) -> None:
    """Load Kokoro only in this disposable Windows child process."""
    install_offline_guard()
    try:
        result = _run_generation_local(
            request,
            progress_callback=lambda event: _queue_progress(event_queue, event),
            resource_profile=resource_profile,
            resource_callback=lambda snapshot: _queue_resource(event_queue, snapshot),
            cancel_event=cancel_event,
            pause_event=pause_event,
            _execution_metadata={
                "process_isolated": True,
                "worker_process_pid": os.getpid(),
                "worker_start_method": "spawn",
            },
            _lifecycle_callback=lambda payload: _queue_lifecycle(event_queue, payload),
        )
    except BaseException as exc:
        result = GenerationResult(
            success=False,
            mode=request.mode,
            project_name=request.project_name,
            errors=[f"generation_worker_exception:{exc.__class__.__name__}"],
            metadata={
                "engine": "kokoro",
                "offline": True,
                "full_text_saved": False,
                "process_isolated": True,
                "worker_process_pid": os.getpid(),
            },
        )
    try:
        result_queue.put(result)
    except (OSError, ValueError):
        pass


def _consume_worker_events(
    event_queue,
    progress_callback: ProgressCallback | None,
    resource_callback: ResourceCallback | None,
    layout_info: dict | None,
) -> dict | None:
    while True:
        try:
            kind, payload = event_queue.get_nowait()
        except queue_module.Empty:
            return layout_info
        if kind == "progress" and isinstance(payload, ProgressEvent):
            if progress_callback is not None:
                try:
                    progress_callback(payload)
                except Exception:
                    pass
        elif kind == "resource" and isinstance(payload, dict):
            if resource_callback is not None:
                try:
                    resource_callback(payload)
                except Exception:
                    pass
        elif kind == "lifecycle" and isinstance(payload, dict) and payload.get("event") == "layout":
            layout_info = payload


def _worker_result(result_queue, timeout: float = 0.0) -> GenerationResult | None:
    try:
        result = result_queue.get(timeout=timeout) if timeout else result_queue.get_nowait()
    except queue_module.Empty:
        return None
    return result if isinstance(result, GenerationResult) else None


def _stop_worker(worker, join_seconds: float) -> bool:
    # Also release tools started by this worker (for example FFmpeg).
    descendants = []
    if worker.is_alive() and worker.pid is not None:
        try:
            descendants = psutil.Process(worker.pid).children(recursive=True)
        except psutil.Error:
            pass
    for child in descendants:
        try:
            child.kill()
        except psutil.Error:
            pass
    if worker.is_alive():
        worker.terminate()
        worker.join(timeout=join_seconds)
    if worker.is_alive() and hasattr(worker, "kill"):
        worker.kill()
        worker.join(timeout=join_seconds)
    return not worker.is_alive()


def _recover_orphaned_worker_artifacts(layout_info: dict | None) -> dict[str, bool]:
    """Clean only the child job's private temp tree and known unpublished MP3."""
    outcome = {"work_root_removed": False, "partial_final_mp3_removed": False, "empty_output_root_removed": False}
    if not layout_info:
        return outcome

    raw_work_root = layout_info.get("work_root")
    if isinstance(raw_work_root, str):
        try:
            jobs_root = (load_paths()["audio_dir"].parent / "temp" / "jobs").resolve(strict=False)
            work_root = Path(raw_work_root).resolve(strict=False)
            if work_root.parent == jobs_root and work_root.exists() and not work_root.is_symlink():
                shutil.rmtree(work_root)
                outcome["work_root_removed"] = True
        except (OSError, ValueError):
            pass

    raw_root = layout_info.get("root")
    final_stem = layout_info.get("final_stem")
    if not isinstance(raw_root, str) or final_stem not in {"narration_complete", "dialogue_complete"}:
        return outcome
    try:
        output_root = confine_output_path(Path(raw_root), label="orphaned child output", must_exist=True)
        partial_final = output_root / f"{final_stem}.mp3"
        if partial_final.is_file() and not partial_final.is_symlink():
            partial_final.unlink()
            outcome["partial_final_mp3_removed"] = True
        try:
            output_root.rmdir()
            outcome["empty_output_root_removed"] = True
        except OSError:
            pass
    except (OSError, ValueError):
        pass
    return outcome


def _write_worker_failure_log(
    request: GenerationRequest,
    layout_info: dict | None,
    error: str,
    isolation: dict,
) -> str | None:
    if not layout_info or not isinstance(layout_info.get("log_file"), str):
        return None
    try:
        log_file = confine_output_path(Path(layout_info["log_file"]), label="worker failure log")
        voices = [
            voice_id
            for voice_id in (request.narration_voice_id, request.voice_a_id, request.voice_b_id)
            if voice_id
        ]
        write_safe_log(
            log_file,
            success=False,
            mode=request.mode,
            project_name=request.project_name,
            voices=voices,
            speed=request.speed,
            item_count=0,
            files=[],
            error=error,
            resource_profile=None,
            resource_summary={"process_isolation": isolation},
            resource_plan={},
            job_id=layout_info.get("job_id"),
            export_validation={"mp3_validated": False, "worker_recovery": True},
        )
        return relative_to_v2(log_file)
    except (OSError, ValueError):
        return None


def _isolated_result_metadata(
    worker_pid: int | None,
    worker_peak_ram_mb: float,
    parent_before: dict[str, float],
    parent_after: dict[str, float],
    worker_exit_code: int | None,
    worker_exited: bool,
    forced_termination: bool,
) -> dict:
    return {
        "strategy": "temporary_spawned_kokoro_worker",
        "worker_pid": worker_pid,
        "worker_peak_ram_mb": worker_peak_ram_mb,
        "worker_exit_code": worker_exit_code,
        "worker_exited": worker_exited,
        "forced_termination": forced_termination,
        "coordinator_before": parent_before,
        "coordinator_after": parent_after,
    }


def _worker_failure_result(
    request: GenerationRequest,
    progress_callback: ProgressCallback | None,
    layout_info: dict | None,
    error: str,
    isolation: dict,
) -> GenerationResult:
    recovery = _recover_orphaned_worker_artifacts(layout_info)
    isolation = {**isolation, "recovery": recovery}
    log_file = _write_worker_failure_log(request, layout_info, error, isolation)
    emit(progress_callback, "error", 100)
    return GenerationResult(
        success=False,
        mode=request.mode,
        project_name=request.project_name,
        errors=[error],
        log_file=log_file,
        metadata={
            "engine": "kokoro",
            "offline": True,
            "full_text_saved": False,
            "process_isolated": True,
            "process_isolation": isolation,
            "recovery_safe": True,
        },
    )


def _run_generation_isolated(
    request: GenerationRequest,
    progress_callback: ProgressCallback | None,
    *,
    resource_profile: str,
    resource_callback: ResourceCallback | None,
    cancel_event: threading.Event | None,
    pause_event: threading.Event | None,
) -> GenerationResult:
    install_offline_guard()
    if not _GENERATION_LOCK.acquire(blocking=False):
        return GenerationResult(
            success=False,
            mode=request.mode,
            project_name=request.project_name,
            errors=["generation_already_running"],
            metadata={"engine": "kokoro", "offline": True, "full_text_saved": False},
        )

    settings = _worker_settings()
    context = multiprocessing.get_context("spawn")
    worker = None
    result_queue = None
    event_queue = None
    layout_info: dict | None = None
    parent_before = _memory_sample()
    worker_peak_ram_mb = 0.0
    forced_termination = False
    try:
        child_cancel = context.Event()
        child_pause = context.Event()
        result_queue = context.Queue()
        event_queue = context.Queue()
        worker = context.Process(
            target=_child_generation_entry,
            args=(result_queue, event_queue, request, resource_profile, child_cancel, child_pause),
            name="vts-kokoro-worker",
        )
        worker.start()
        worker_pid = worker.pid
        child_process = psutil.Process(worker_pid) if worker_pid is not None else None
        cancel_deadline: float | None = None
        worker_memory = parent_before

        while True:
            if cancel_event is not None and cancel_event.is_set():
                child_cancel.set()
                if cancel_deadline is None:
                    cancel_deadline = time.monotonic() + settings["cancel_grace_seconds"]
            if pause_event is not None and pause_event.is_set():
                child_pause.set()
            else:
                child_pause.clear()

            if child_process is not None:
                worker_memory = _memory_sample(child_process)
                worker_peak_ram_mb = max(worker_peak_ram_mb, worker_memory["rss_mb"])
            layout_info = _consume_worker_events(event_queue, progress_callback, resource_callback, layout_info)
            result = _worker_result(result_queue)
            if result is not None:
                worker.join(timeout=settings["join_seconds"])
                if worker.is_alive():
                    forced_termination = True
                    _stop_worker(worker, settings["join_seconds"])
                parent_after = _memory_sample()
                isolation = _isolated_result_metadata(
                    worker_pid,
                    worker_peak_ram_mb,
                    parent_before,
                    parent_after,
                    worker.exitcode,
                    not worker.is_alive(),
                    forced_termination,
                )
                result.metadata = {**result.metadata, "process_isolated": True, "process_isolation": isolation}
                return result

            if not worker.is_alive():
                result = _worker_result(result_queue, timeout=settings["poll_seconds"])
                layout_info = _consume_worker_events(event_queue, progress_callback, resource_callback, layout_info)
                parent_after = _memory_sample()
                isolation = _isolated_result_metadata(
                    worker_pid,
                    worker_peak_ram_mb,
                    parent_before,
                    parent_after,
                    worker.exitcode,
                    True,
                    False,
                )
                if result is not None:
                    result.metadata = {**result.metadata, "process_isolated": True, "process_isolation": isolation}
                    return result
                return _worker_failure_result(
                    request,
                    progress_callback,
                    layout_info,
                    "generation_worker_terminated",
                    isolation,
                )

            if worker_memory["available_ram_gb"] < settings["emergency_free_ram_gb"]:
                child_cancel.set()
                forced_termination = True
                stopped = _stop_worker(worker, settings["join_seconds"])
                isolation = _isolated_result_metadata(
                    worker_pid, worker_peak_ram_mb, parent_before, _memory_sample(),
                    worker.exitcode, stopped, True,
                )
                return _worker_failure_result(
                    request, progress_callback, layout_info if stopped else None,
                    "Memoria do computador em nivel critico; geracao interrompida para liberar recursos.",
                    isolation,
                )

            if cancel_deadline is not None and time.monotonic() >= cancel_deadline:
                forced_termination = True
                stopped = _stop_worker(worker, settings["join_seconds"])
                recovery_discarded = stopped
                if stopped and layout_info and layout_info.get('recovery_root'):
                    try:
                        RecoveryStore.discard_abandoned(Path(layout_info['recovery_root']))
                    except (OSError, ValueError, RuntimeError):
                        recovery_discarded = False
                parent_after = _memory_sample()
                isolation = _isolated_result_metadata(
                    worker_pid,
                    worker_peak_ram_mb,
                    parent_before,
                    parent_after,
                    worker.exitcode,
                    not worker.is_alive(),
                    True,
                )
                cancelled_result = _worker_failure_result(
                    request,
                    progress_callback,
                    layout_info if stopped else None,
                    "generation_worker_cancel_timeout",
                    isolation,
                )
                cancelled_result.metadata.update(cancelled=True, recovery_discarded=recovery_discarded)
                return cancelled_result
            time.sleep(settings["poll_seconds"])
    except Exception as exc:
        if worker is not None:
            forced_termination = True
            _stop_worker(worker, settings["join_seconds"])
        parent_after = _memory_sample()
        isolation = _isolated_result_metadata(
            worker.pid if worker is not None else None,
            worker_peak_ram_mb,
            parent_before,
            parent_after,
            worker.exitcode if worker is not None else None,
            worker is None or not worker.is_alive(),
            forced_termination,
        )
        return _worker_failure_result(
            request,
            progress_callback,
            layout_info,
            f"generation_worker_start_or_supervision_failed:{exc.__class__.__name__}",
            isolation,
        )
    finally:
        for queue in (result_queue, event_queue):
            if queue is None:
                continue
            try:
                queue.close()
                queue.join_thread()
            except (AttributeError, OSError, ValueError):
                pass
        _GENERATION_LOCK.release()


def _should_use_isolated_worker(
    request: GenerationRequest,
    cancel_event: threading.Event | None,
    *,
    _resource_evaluator: Callable | None,
    _monitor_factory: Callable | None,
    _engine_factory: Callable | None,
    _mp3_validator: Callable | None,
    _use_child_process: bool | None,
) -> bool:
    if _use_child_process is False:
        return False
    if any((_resource_evaluator, _monitor_factory, _engine_factory, _mp3_validator)):
        return False
    if cancel_event is not None and cancel_event.is_set():
        return False
    try:
        validate_request(request, VoiceRegistry())
    except Exception:
        return False
    return True


def run_generation(
    request: GenerationRequest,
    progress_callback: ProgressCallback | None = None,
    *,
    resource_profile: str = PROFILE_AUTOMATIC,
    resource_callback: ResourceCallback | None = None,
    cancel_event: threading.Event | None = None,
    pause_event: threading.Event | None = None,
    _resource_evaluator: Callable | None = None,
    _monitor_factory: Callable | None = None,
    _engine_factory: Callable | None = None,
    _mp3_validator: Callable | None = None,
    _use_child_process: bool | None = None,
) -> GenerationResult:
    """Coordinate a single job while the native Kokoro runtime lives in a child."""
    if _should_use_isolated_worker(
        request,
        cancel_event,
        _resource_evaluator=_resource_evaluator,
        _monitor_factory=_monitor_factory,
        _engine_factory=_engine_factory,
        _mp3_validator=_mp3_validator,
        _use_child_process=_use_child_process,
    ):
        return _run_generation_isolated(
            request,
            progress_callback,
            resource_profile=resource_profile,
            resource_callback=resource_callback,
            cancel_event=cancel_event,
            pause_event=pause_event,
        )
    return _run_generation_local(
        request,
        progress_callback,
        resource_profile=resource_profile,
        resource_callback=resource_callback,
        cancel_event=cancel_event,
        pause_event=pause_event,
        _resource_evaluator=_resource_evaluator,
        _monitor_factory=_monitor_factory,
        _engine_factory=_engine_factory,
        _mp3_validator=_mp3_validator,
    )
