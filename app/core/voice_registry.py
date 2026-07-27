from __future__ import annotations

import json
from pathlib import Path

from .project_paths import V2_ROOT, confine_path, load_paths


class VoiceRegistry:
    def __init__(self, catalog_path: Path | None = None) -> None:
        paths = load_paths()
        self.catalog_path = confine_path(catalog_path or paths["voices_catalog"], label="voice catalog", must_exist=True)
        data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        if data.get("default_voice_id") is not None:
            raise ValueError("V2 voice catalog must not define a default voice")
        voices = data.get("voices", [])
        self._voices = {item["voice_id"]: item for item in voices}
        if len(voices) != 28 or len(self._voices) != 28:
            raise ValueError("V2 voice catalog must contain 28 unique voices")

    def list_voices(self) -> list[dict]:
        return [dict(self._voices[key]) for key in sorted(self._voices)]

    def get(self, voice_id: str) -> dict:
        try:
            voice = dict(self._voices[voice_id])
        except KeyError as exc:
            raise ValueError(f"Unknown V2 voice: {voice_id}") from exc
        if voice.get("status") != "approved":
            raise ValueError(f"Voice is not approved for V2 generation: {voice_id}")
        voicepack = confine_path(V2_ROOT / voice["voicepack_path"], label="voicepack", must_exist=True)
        if not voicepack.is_file():
            raise FileNotFoundError(f"Local voicepack is missing: {voice_id}")
        voice["voicepack"] = voicepack
        return voice

    def validate_all(self) -> list[str]:
        validated = []
        for voice_id in sorted(self._voices):
            self.get(voice_id)
            validated.append(voice_id)
        return validated
