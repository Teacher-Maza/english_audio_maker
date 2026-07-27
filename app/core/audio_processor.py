from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from .project_paths import confine_output_path


SAMPLE_RATE = 24000
INITIAL_SILENCE_MS = 650
FINAL_SILENCE_MS = 300
BETWEEN_ITEMS_MS = 250
FADE_MS = 50


def _silence(milliseconds: int) -> np.ndarray:
    return np.zeros(round(SAMPLE_RATE * milliseconds / 1000), dtype=np.float32)


def apply_fade(audio: np.ndarray, fade_ms: int = FADE_MS) -> np.ndarray:
    clean = np.asarray(audio, dtype=np.float32).copy()
    if clean.ndim != 1 or clean.size == 0 or not np.isfinite(clean).all():
        raise ValueError("Invalid mono audio returned by Kokoro")
    fade_samples = min(round(SAMPLE_RATE * fade_ms / 1000), clean.size // 2)
    if fade_samples:
        curve = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
        clean[:fade_samples] *= curve
        clean[-fade_samples:] *= curve[::-1]
    return clean


def assemble_audio(parts: list[np.ndarray], between_ms: int = BETWEEN_ITEMS_MS) -> np.ndarray:
    if not parts:
        raise ValueError("No audio parts to assemble")
    output = [_silence(INITIAL_SILENCE_MS)]
    for index, part in enumerate(parts):
        if index:
            output.append(_silence(between_ms))
        output.append(apply_fade(part))
    output.append(_silence(FINAL_SILENCE_MS))
    return np.concatenate(output)


def _faded_block(block: np.ndarray, *, offset: int, total_frames: int, fade_frames: int) -> np.ndarray:
    """Apply the existing edge fades without loading a complete job into RAM."""
    if fade_frames <= 0:
        return block
    positions = np.arange(offset, offset + block.size)
    gain = np.ones(block.size, dtype=np.float32)
    if fade_frames == 1:
        gain[positions == 0] = 0.0
        gain[positions == total_frames - 1] = 0.0
    else:
        leading = positions < fade_frames
        trailing = positions >= total_frames - fade_frames
        gain[leading] = positions[leading] / float(fade_frames - 1)
        gain[trailing] = (total_frames - 1 - positions[trailing]) / float(fade_frames - 1)
    return np.asarray(block, dtype=np.float32) * gain


def assemble_wav_files(parts: list[Path], destination: Path, between_ms: int = BETWEEN_ITEMS_MS) -> None:
    """Stream already-written chunks into the final WAV, retaining one block only."""
    if not parts:
        raise ValueError("No audio parts to assemble")
    destination = confine_output_path(destination, label="assembled WAV")
    destination.parent.mkdir(parents=True, exist_ok=True)
    silence_between = _silence(between_ms)
    with sf.SoundFile(destination, mode="w", samplerate=SAMPLE_RATE, channels=1, subtype="PCM_16") as output:
        output.write(_silence(INITIAL_SILENCE_MS))
        for index, part_path in enumerate(parts):
            part_path = confine_output_path(part_path, label="chunk WAV", must_exist=True)
            if index:
                output.write(silence_between)
            with sf.SoundFile(part_path, mode="r") as source:
                if source.samplerate != SAMPLE_RATE or source.channels != 1 or source.frames <= 0:
                    raise ValueError(f"Invalid chunk WAV: {part_path.name}")
                fade_frames = min(round(SAMPLE_RATE * FADE_MS / 1000), source.frames // 2)
                offset = 0
                while offset < source.frames:
                    block = source.read(min(8192, source.frames - offset), dtype="float32", always_2d=False)
                    if block.size == 0:
                        raise RuntimeError(f"Could not read chunk WAV: {part_path.name}")
                    output.write(_faded_block(block, offset=offset, total_frames=source.frames, fade_frames=fade_frames))
                    offset += block.size
        output.write(_silence(FINAL_SILENCE_MS))
    if not destination.is_file() or destination.stat().st_size <= 44:
        raise RuntimeError(f"WAV was not created: {destination.name}")


def save_wav(path: Path, audio: np.ndarray) -> None:
    path = confine_output_path(path, label="output WAV")
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.asarray(audio, dtype=np.float32), SAMPLE_RATE, subtype="PCM_16")
    if not path.is_file() or path.stat().st_size <= 44:
        raise RuntimeError(f"WAV was not created: {path.name}")
