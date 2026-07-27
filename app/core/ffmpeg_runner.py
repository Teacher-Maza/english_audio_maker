from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .project_paths import confine_output_path, confine_path, load_paths


_DURATION_RE = re.compile(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)")


@dataclass(frozen=True)
class Mp3Validation:
    path: Path
    duration_seconds: float
    size_bytes: int


def _portable_ffmpeg() -> Path:
    ffmpeg = confine_path(load_paths()["ffmpeg_exe"], label="FFmpeg", must_exist=True)
    if not ffmpeg.is_file():
        raise FileNotFoundError("V2 portable FFmpeg is missing")
    return ffmpeg


def convert_wav_to_mp3(wav_path: Path, mp3_path: Path) -> None:
    ffmpeg = _portable_ffmpeg()
    wav_path = confine_output_path(wav_path, label="input WAV", must_exist=True)
    mp3_path = confine_output_path(mp3_path, label="output MP3")
    if not wav_path.is_file() or wav_path.stat().st_size <= 44:
        raise FileNotFoundError("Input WAV is missing or empty")
    if mp3_path.exists():
        raise FileExistsError(f"MP3 already exists: {mp3_path.name}")
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
        "-i", str(wav_path), "-codec:a", "libmp3lame", "-b:a", "128k", str(mp3_path),
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True, shell=False, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg MP3 conversion failed: {result.stderr.strip()[:500]}")
    if not mp3_path.is_file() or mp3_path.stat().st_size == 0:
        raise RuntimeError("FFmpeg did not create a valid MP3")


def validate_mp3_complete(mp3_path: Path) -> Mp3Validation:
    """Read metadata and decode the full MP3 with the portable FFmpeg binary."""
    ffmpeg = _portable_ffmpeg()
    mp3_path = confine_output_path(mp3_path, label="output MP3", must_exist=True)
    if not mp3_path.is_file() or mp3_path.stat().st_size == 0:
        raise RuntimeError("MP3 is missing or empty")

    inspect = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-nostdin", "-i", str(mp3_path)],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
        timeout=120,
    )
    match = _DURATION_RE.search(inspect.stderr)
    if match is None:
        raise RuntimeError("FFmpeg could not read the MP3 duration")
    hours, minutes, seconds = match.groups()
    duration_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    if duration_seconds <= 0:
        raise RuntimeError("MP3 duration is invalid")

    decode = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(mp3_path), "-map", "0:a:0", "-f", "null", "-"],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
        timeout=300,
    )
    if decode.returncode != 0:
        raise RuntimeError(f"FFmpeg could not read the full MP3: {decode.stderr.strip()[:500]}")
    return Mp3Validation(path=mp3_path, duration_seconds=duration_seconds, size_bytes=mp3_path.stat().st_size)
