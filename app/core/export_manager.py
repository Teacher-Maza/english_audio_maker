from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .project_paths import confine_output_path, load_paths


@dataclass(frozen=True)
class ExportLayout:
    root: Path
    wav_dir: Path
    mp3_dir: Path
    temp_dir: Path
    log_file: Path
    job_id: str = ""
    work_root: Path | None = None


def next_available_dir(base: Path, project_name: str) -> Path:
    candidate = base / project_name
    suffix = 2
    while candidate.exists():
        candidate = base / f"{project_name}_{suffix}"
        suffix += 1
    return candidate


def create_export_layout(project_name: str, output_base_dir: Path | None = None) -> ExportLayout:
    if not project_name or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for character in project_name):
        raise ValueError("Unsafe project name")
    if len(project_name) > 64:
        raise ValueError("Project name is too long")
    base = confine_output_path(output_base_dir or load_paths()["generation_output_dir"], label="output base", allow_root=True)
    base.mkdir(parents=True, exist_ok=True)
    base = confine_output_path(base, label="output base", must_exist=True, allow_root=True)
    root = next_available_dir(base, project_name)
    root.mkdir(exist_ok=False)
    root = confine_output_path(root, label="job output", must_exist=True)
    job_id = uuid4().hex
    internal_base = load_paths()["audio_dir"].parent / "temp"
    internal_base.mkdir(parents=True, exist_ok=True)
    internal_base = confine_output_path(internal_base, label="internal job base", must_exist=True)
    work_root = internal_base / "jobs" / job_id
    work_root.mkdir(parents=True, exist_ok=False)
    work_root = confine_output_path(work_root, label="job work directory", must_exist=True)
    wav_dir = work_root / "wav"
    mp3_dir = work_root / "mp3"
    temp_dir = work_root / "temp"
    for directory in (wav_dir, mp3_dir, temp_dir):
        directory.mkdir(exist_ok=False)
        confine_output_path(directory, label="job directory", must_exist=True)
    log_dir = internal_base / "job_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_dir = confine_output_path(log_dir, label="internal job logs", must_exist=True)
    return ExportLayout(
        root=root,
        wav_dir=wav_dir,
        mp3_dir=mp3_dir,
        temp_dir=temp_dir,
        log_file=log_dir / f"{job_id}.json",
        job_id=job_id,
        work_root=work_root,
    )
