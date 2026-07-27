from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .project_paths import confine_output_path


def write_safe_log(path: Path, *, success: bool, mode: str, project_name: str, voices: list[str], speed: float, item_count: int, files: list[str], error: str | None = None, resource_profile: str | None = None, resource_summary: dict | None = None, resource_plan: dict | None = None, cancelled: bool = False, export_validation: dict | None = None, job_id: str | None = None) -> None:
    path = confine_output_path(path, label="safe log")
    data: dict[str, Any] = {
        "schema_version": "2.0",
        "engine": "kokoro",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "success": success,
        "mode": mode,
        "project_name": project_name,
        "voices": voices,
        "speed_factor": float(speed),
        "item_count": item_count,
        "device": "cpu",
        "offline": True,
        "pitch_changed": False,
        "full_text_saved": False,
        "resource_profile": resource_profile,
        "resource_summary": resource_summary or {},
        "resource_plan": resource_plan or {},
        "cancelled": bool(cancelled),
        "job_id": job_id,
        "created_files": files,
        "export_validation": export_validation or {},
        "error": error,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
