from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


MODE_NARRATION = "narration"
MODE_DIALOGUE_AB = "dialogue_ab"
ALLOWED_MODES = {MODE_NARRATION, MODE_DIALOGUE_AB}


@dataclass(frozen=True)
class GenerationRequest:
    mode: str
    project_name: str
    text: str
    narration_voice_id: str | None = None
    voice_a_id: str | None = None
    voice_b_id: str | None = None
    speed: float = 1.0
    output_base_dir: Path | None = None


@dataclass
class GenerationResult:
    success: bool
    mode: str
    project_name: str
    created_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    log_file: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

