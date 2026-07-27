from __future__ import annotations


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def progress_label(stage: str, labels: dict[str, str]) -> str:
    return labels.get(stage, stage)
