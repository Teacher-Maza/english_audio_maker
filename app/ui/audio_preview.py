from __future__ import annotations

import ctypes
import os
import wave
from pathlib import Path
from typing import Any, Callable

from v2_kokoro.app.core.project_paths import confine_path


class PreviewError(RuntimeError):
    pass


class _WaveFormatEx(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", ctypes.c_ushort),
        ("nChannels", ctypes.c_ushort),
        ("nSamplesPerSec", ctypes.c_uint),
        ("nAvgBytesPerSec", ctypes.c_uint),
        ("nBlockAlign", ctypes.c_ushort),
        ("wBitsPerSample", ctypes.c_ushort),
        ("cbSize", ctypes.c_ushort),
    ]


class _WaveHeader(ctypes.Structure):
    pass


_WaveHeader._fields_ = [
    ("lpData", ctypes.c_void_p),
    ("dwBufferLength", ctypes.c_uint),
    ("dwBytesRecorded", ctypes.c_uint),
    ("dwUser", ctypes.c_size_t),
    ("dwFlags", ctypes.c_uint),
    ("dwLoops", ctypes.c_uint),
    ("lpNext", ctypes.POINTER(_WaveHeader)),
    ("reserved", ctypes.c_size_t),
]


class _WindowsWaveOutApi:
    WAVE_MAPPER = ctypes.c_size_t(-1).value

    def __init__(self) -> None:
        if os.name != "nt":
            raise PreviewError("A prévia local está disponível somente no Windows.")
        winmm = ctypes.WinDLL("winmm")
        self._open = winmm.waveOutOpen
        self._open.argtypes = [
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_size_t,
            ctypes.POINTER(_WaveFormatEx),
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_uint,
        ]
        self._open.restype = ctypes.c_uint
        self._prepare = winmm.waveOutPrepareHeader
        self._prepare.argtypes = [ctypes.c_void_p, ctypes.POINTER(_WaveHeader), ctypes.c_uint]
        self._prepare.restype = ctypes.c_uint
        self._write = winmm.waveOutWrite
        self._write.argtypes = [ctypes.c_void_p, ctypes.POINTER(_WaveHeader), ctypes.c_uint]
        self._write.restype = ctypes.c_uint
        self._pause = winmm.waveOutPause
        self._pause.argtypes = [ctypes.c_void_p]
        self._pause.restype = ctypes.c_uint
        self._restart = winmm.waveOutRestart
        self._restart.argtypes = [ctypes.c_void_p]
        self._restart.restype = ctypes.c_uint
        self._reset = winmm.waveOutReset
        self._reset.argtypes = [ctypes.c_void_p]
        self._reset.restype = ctypes.c_uint
        self._unprepare = winmm.waveOutUnprepareHeader
        self._unprepare.argtypes = [ctypes.c_void_p, ctypes.POINTER(_WaveHeader), ctypes.c_uint]
        self._unprepare.restype = ctypes.c_uint
        self._close = winmm.waveOutClose
        self._close.argtypes = [ctypes.c_void_p]
        self._close.restype = ctypes.c_uint
        self._error_text = winmm.waveOutGetErrorTextW
        self._error_text.argtypes = [ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
        self._error_text.restype = ctypes.c_uint

    def open(self, wave_format: _WaveFormatEx) -> tuple[int, ctypes.c_void_p]:
        handle = ctypes.c_void_p()
        code = self._open(ctypes.byref(handle), self.WAVE_MAPPER, ctypes.byref(wave_format), 0, 0, 0)
        return code, handle

    def prepare(self, handle: Any, header: _WaveHeader) -> int:
        return self._prepare(handle, ctypes.byref(header), ctypes.sizeof(header))

    def write(self, handle: Any, header: _WaveHeader) -> int:
        return self._write(handle, ctypes.byref(header), ctypes.sizeof(header))

    def pause(self, handle: Any) -> int:
        return self._pause(handle)

    def resume(self, handle: Any) -> int:
        return self._restart(handle)

    def reset(self, handle: Any) -> int:
        return self._reset(handle)

    def unprepare(self, handle: Any, header: _WaveHeader) -> int:
        return self._unprepare(handle, ctypes.byref(header), ctypes.sizeof(header))

    def close(self, handle: Any) -> int:
        return self._close(handle)

    def error_text(self, code: int) -> str:
        buffer = ctypes.create_unicode_buffer(256)
        self._error_text(code, buffer, len(buffer))
        return buffer.value or f"Erro waveOut {code}."


class _WaveOutBackend:
    WHDR_DONE = 0x00000001

    def __init__(self, api: Any | None = None) -> None:
        self._api = api
        self._handle: Any | None = None
        self._buffer: ctypes.Array | None = None
        self._header: _WaveHeader | None = None
        self._prepared = False
        self._paused = False

    def _get_api(self) -> Any:
        if self._api is None:
            self._api = _WindowsWaveOutApi()
        return self._api

    def _check(self, code: int, action: str) -> None:
        if code:
            raise PreviewError(f"{action}: {self._get_api().error_text(code)}")

    def play(self, path: Path) -> None:
        self.stop()
        try:
            with wave.open(str(path), "rb") as source:
                if source.getcomptype() != "NONE":
                    raise PreviewError("A amostra WAV usa compressão não suportada.")
                channels = source.getnchannels()
                sample_width = source.getsampwidth()
                sample_rate = source.getframerate()
                frames = source.readframes(source.getnframes())
        except (OSError, wave.Error) as exc:
            raise PreviewError("Não foi possível ler a amostra WAV.") from exc
        if not frames or channels < 1 or sample_width not in (1, 2, 3, 4) or sample_rate < 1:
            raise PreviewError("A amostra WAV possui formato inválido.")

        block_align = channels * sample_width
        wave_format = _WaveFormatEx(
            1,
            channels,
            sample_rate,
            sample_rate * block_align,
            block_align,
            sample_width * 8,
            0,
        )
        self._buffer = ctypes.create_string_buffer(frames)
        code, handle = self._get_api().open(wave_format)
        self._handle = handle if code == 0 else None
        try:
            self._check(code, "Não foi possível abrir o dispositivo de áudio")
            self._queue_from_start()
        except Exception:
            self.stop()
            raise

    def _queue_from_start(self) -> None:
        if self._handle is None or self._buffer is None:
            raise PreviewError("O dispositivo de prévia não está aberto.")
        self._header = _WaveHeader(
            ctypes.addressof(self._buffer),
            len(self._buffer) - 1,
            0,
            0,
            0,
            0,
            None,
            0,
        )
        self._check(self._get_api().prepare(self._handle, self._header), "Não foi possível preparar a prévia")
        self._prepared = True
        self._check(self._get_api().write(self._handle, self._header), "Não foi possível iniciar a prévia")
        self._paused = False

    def pause(self) -> None:
        if self._handle is not None:
            self._check(self._get_api().pause(self._handle), "Não foi possível pausar a prévia")
            self._paused = True

    def resume(self) -> None:
        if self._handle is not None:
            self._check(self._get_api().resume(self._handle), "Não foi possível retomar a prévia")
            self._paused = False

    def restart(self) -> None:
        if self._handle is None:
            return
        self._check(self._get_api().reset(self._handle), "Não foi possível reiniciar a prévia")
        if self._prepared and self._header is not None:
            self._check(
                self._get_api().unprepare(self._handle, self._header),
                "Não foi possível reiniciar a prévia",
            )
        self._prepared = False
        self._queue_from_start()

    def mode(self) -> str:
        if self._handle is None or self._header is None:
            return "stopped"
        if self._header.dwFlags & self.WHDR_DONE:
            return "stopped"
        return "paused" if self._paused else "playing"

    def stop(self) -> None:
        handle = self._handle
        header = self._header
        if handle is not None:
            try:
                self._get_api().reset(handle)
            except Exception:
                pass
            if self._prepared and header is not None:
                try:
                    self._get_api().unprepare(handle, header)
                except Exception:
                    pass
            try:
                self._get_api().close(handle)
            except Exception:
                pass
        self._handle = None
        self._buffer = None
        self._header = None
        self._prepared = False
        self._paused = False


class _MciSenderBackend:
    """Compatibility adapter retained for the existing deterministic unit test."""

    def __init__(self, sender: Callable[[str], str], alias: str) -> None:
        self._send = sender
        self._alias = alias
        self._opened = False

    def play(self, path: Path) -> None:
        self._send(f'open "{path}" type waveaudio alias {self._alias}')
        self._send(f"play {self._alias}")
        self._opened = True

    def pause(self) -> None:
        self._send(f"pause {self._alias}")

    def resume(self) -> None:
        self._send(f"resume {self._alias}")

    def restart(self) -> None:
        self._send(f"seek {self._alias} to start")
        self._send(f"play {self._alias}")

    def mode(self) -> str:
        return self._send(f"status {self._alias} mode").strip().lower()

    def stop(self) -> None:
        if self._opened:
            try:
                self._send(f"stop {self._alias}")
            except Exception:
                pass
        try:
            self._send(f"close {self._alias}")
        except Exception:
            pass
        self._opened = False


class PreviewPlayer:
    ALIAS = "vts_v2_voice_preview"

    def __init__(
        self,
        sender: Callable[[str], str] | None = None,
        *,
        wave_api: Any | None = None,
    ) -> None:
        if sender is not None and wave_api is not None:
            raise ValueError("Use sender ou wave_api, não ambos.")
        self._backend = _MciSenderBackend(sender, self.ALIAS) if sender is not None else _WaveOutBackend(wave_api)
        self.voice_id: str | None = None
        self.path: Path | None = None
        self.state = "idle"

    def play(self, voice_id: str, path: Path) -> None:
        try:
            resolved = confine_path(path, label="preview sample", must_exist=True)
        except (FileNotFoundError, ValueError) as exc:
            raise PreviewError("A amostra desta voz não foi encontrada.") from exc
        if not resolved.is_file():
            raise PreviewError("A amostra desta voz não foi encontrada.")
        self.stop()
        try:
            self._backend.play(resolved)
        except PreviewError:
            self._backend.stop()
            raise
        except Exception as exc:
            self._backend.stop()
            raise PreviewError("Não foi possível reproduzir a prévia. Verifique o dispositivo de áudio.") from exc
        self.voice_id = voice_id
        self.path = resolved
        self.state = "playing"

    def pause_resume(self) -> str:
        if not self.voice_id:
            return self.state
        if self.state == "playing":
            self._backend.pause()
            self.state = "paused"
        elif self.state == "paused":
            self._backend.resume()
            self.state = "playing"
        return self.state

    def restart(self) -> None:
        if not self.voice_id:
            return
        self._backend.restart()
        self.state = "playing"

    def current_mode(self) -> str:
        if not self.voice_id:
            return "stopped"
        try:
            return self._backend.mode()
        except Exception:
            return "stopped"

    def stop(self) -> None:
        self._backend.stop()
        self.voice_id = None
        self.path = None
        self.state = "idle"

    close = stop
