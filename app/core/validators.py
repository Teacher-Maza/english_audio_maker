from __future__ import annotations

import re

from .dialogue_parser import parse_dialogue_ab
from .generation_contracts import ALLOWED_MODES, GenerationRequest, MODE_DIALOGUE_AB, MODE_NARRATION
from .speech_speed import ALLOWED_SPEECH_SPEEDS
from .voice_registry import VoiceRegistry


PROJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MAX_TEXT_CHARS = 50_000
MAX_TEXT_LINES = 1_000
MAX_LINE_CHARS = 2_000
MAX_INPUT_FILE_BYTES = 512 * 1024


def validate_text_content(text: object) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Text cannot be empty")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"Text exceeds the {MAX_TEXT_CHARS} character limit")
    lines = text.splitlines() or [text]
    if len(lines) > MAX_TEXT_LINES:
        raise ValueError(f"Text exceeds the {MAX_TEXT_LINES} line limit")
    if any(len(line) > MAX_LINE_CHARS for line in lines):
        raise ValueError(f"A text line exceeds the {MAX_LINE_CHARS} character limit")
    if any(ord(character) < 32 and character not in "\n\r\t" for character in text):
        raise ValueError("Text contains unsupported control characters")
    return text.strip()


def validate_request(request: GenerationRequest, registry: VoiceRegistry) -> None:
    if request.mode not in ALLOWED_MODES:
        raise ValueError("Mode must be narration or dialogue_ab")
    validate_text_content(request.text)
    if not PROJECT_RE.fullmatch(request.project_name or ""):
        raise ValueError("Project name must use only letters, numbers, underscore or hyphen")
    if float(request.speed) not in ALLOWED_SPEECH_SPEEDS:
        raise ValueError("Speech speed must be 0.75, 1.00 or 1.25")
    if request.mode == MODE_NARRATION:
        if not request.narration_voice_id:
            raise ValueError("Narration requires an explicit voice selection")
        registry.get(request.narration_voice_id)
    elif request.mode == MODE_DIALOGUE_AB:
        parse_dialogue_ab(request.text)
        if not request.voice_a_id or not request.voice_b_id:
            raise ValueError("Dialogue A/B requires explicit voice A and voice B selections")
        registry.get(request.voice_a_id)
        registry.get(request.voice_b_id)
