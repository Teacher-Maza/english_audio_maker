from __future__ import annotations

import os
import sys
import gc
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

from v2_kokoro.app.security.offline_guard import install_offline_guard

install_offline_guard()

# pythonw.exe has no console streams. Kokoro configures Loguru during import,
# so provide a process-local sink before importing the package.
_NULL_STREAMS = []
for _stream_name in ("stdout", "stderr"):
    if getattr(sys, _stream_name, None) is None:
        _stream = open(os.devnull, "w", encoding="utf-8")
        setattr(sys, _stream_name, _stream)
        _NULL_STREAMS.append(_stream)

import numpy as np
import torch
from kokoro import KModel, KPipeline

from .audio_processor import SAMPLE_RATE
from .project_paths import load_paths
from .voice_registry import VoiceRegistry


class KokoroEngine:
    def __init__(self, registry: VoiceRegistry, threads: int | None = None) -> None:
        paths = load_paths()
        config_path = paths["kokoro_config"]
        model_path = paths["kokoro_model"]
        if not config_path.is_file() or not model_path.is_file():
            raise FileNotFoundError("Local Kokoro model/config is missing")
        self.registry = registry
        if threads is not None:
            torch.set_num_threads(max(1, int(threads)))
        self.model = KModel(config=str(config_path), model=str(model_path))
        self._pipelines: dict[str, KPipeline] = {}
        self._voicepacks: dict[str, torch.Tensor] = {}

    def set_threads(self, threads: int) -> None:
        torch.set_num_threads(max(1, int(threads)))

    def _pipeline(self, locale: str) -> KPipeline:
        language_code = "a" if locale == "en_US" else "b"
        if language_code not in self._pipelines:
            self._pipelines[language_code] = KPipeline(
                lang_code=language_code,
                repo_id="hexgrad/Kokoro-82M",
                model=self.model,
                device="cpu",
            )
        return self._pipelines[language_code]

    def _voicepack(self, voice_id: str, path: Path) -> torch.Tensor:
        if voice_id not in self._voicepacks:
            # A job needs one voice at a time.  Do not retain every voicepack
            # encountered by a long A/B sequence when memory is constrained.
            self.release_voicepacks()
            self._voicepacks[voice_id] = torch.load(path, weights_only=True, map_location="cpu")
        return self._voicepacks[voice_id]

    def synthesize(self, text: str, voice_id: str, speed: float = 1.0) -> np.ndarray:
        voice = self.registry.get(voice_id)
        pipeline = self._pipeline(voice["locale"])
        voicepack = self._voicepack(voice_id, voice["voicepack"])
        pieces: list[np.ndarray] = []
        with torch.inference_mode():
            for _, _, audio in pipeline(text, voice=voicepack, speed=float(speed), split_pattern=r"\n+"):
                if hasattr(audio, "detach"):
                    audio = audio.detach().cpu().numpy()
                pieces.append(np.asarray(audio, dtype=np.float32))
        if not pieces:
            raise RuntimeError(f"Kokoro returned no audio for {voice_id}")
        combined = np.concatenate(pieces)
        pieces.clear()
        if combined.ndim != 1 or combined.size < SAMPLE_RATE // 10:
            raise RuntimeError(f"Kokoro returned invalid audio for {voice_id}")
        return combined

    def release_voicepacks(self) -> None:
        if self._voicepacks:
            self._voicepacks.clear()
            gc.collect()

    def close(self) -> None:
        self.release_voicepacks()
        self._pipelines.clear()
        if hasattr(self, "model"):
            del self.model
        gc.collect()
