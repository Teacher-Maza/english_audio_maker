from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class DialogueTurn:
    speaker: str
    text: str


_TURN_MARKER_RE = re.compile(r"^[ \t]*([AB]):(.*)$")


def parse_dialogue_ab(text: str) -> list[DialogueTurn]:
    turns: list[DialogueTurn] = []
    speaker: str | None = None
    lines: list[str] = []
    turn_start_line = 0

    def finish_turn() -> None:
        nonlocal speaker, lines, turn_start_line
        if speaker is None:
            return
        content = "\n".join(lines).strip()
        if not content:
            raise ValueError(f"Dialogue turn starting at line {turn_start_line} has no text")
        turns.append(DialogueTurn(speaker=speaker, text=content))

    for line_number, raw in enumerate(text.splitlines(), start=1):
        marker = _TURN_MARKER_RE.match(raw)
        if marker is not None:
            finish_turn()
            speaker = marker.group(1)
            lines = [marker.group(2).strip()]
            turn_start_line = line_number
            continue
        if speaker is None:
            if raw.strip():
                raise ValueError(f"Invalid dialogue line {line_number}; start the first turn with A: or B:")
            continue
        lines.append(raw.strip())

    finish_turn()
    if not turns:
        raise ValueError("Dialogue has no valid A/B turns")
    return turns
