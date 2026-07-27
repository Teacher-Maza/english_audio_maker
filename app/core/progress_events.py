from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ProgressEvent:
    stage: str
    percent: int
    current: int | None = None
    total: int | None = None


ProgressCallback = Callable[[ProgressEvent], None]


def emit(callback: ProgressCallback | None, stage: str, percent: int, current: int | None = None, total: int | None = None) -> None:
    if callback:
        callback(ProgressEvent(stage=stage, percent=max(0, min(100, percent)), current=current, total=total))

