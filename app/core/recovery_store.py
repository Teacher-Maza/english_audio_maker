"""Local, atomic checkpoints. Store audio and fingerprints, never input text."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import shutil
from pathlib import Path

import soundfile as sf
from filelock import FileLock, Timeout

from .project_paths import confine_output_path, load_paths
from .audio_processor import SAMPLE_RATE


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def request_key(request, registry) -> str:
    paths = load_paths()
    voices = sorted({v for v in (request.narration_voice_id, request.voice_a_id, request.voice_b_id) if v})
    assets = [paths['kokoro_model'], paths['kokoro_config']]
    assets.extend(registry.get(voice)['voicepack'] for voice in voices)
    assets.extend(Path(__file__).parent / name for name in (
        'kokoro_engine.py', 'prosodic_segmenter.py', 'audio_processor.py',
        'dialogue_parser.py', 'job_runner.py', 'recovery_store.py',
    ))
    identity = {
        'schema': 1, 'mode': request.mode, 'text': request.text,
        'voices': [request.narration_voice_id, request.voice_a_id, request.voice_b_id],
        'speed': request.speed, 'assets': [digest(path) for path in assets],
        'packages': {name: importlib.metadata.version(name) for name in ('kokoro', 'torch', 'misaki', 'numpy', 'soundfile')},
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode('utf-8')).hexdigest()


class RecoveryStore:
    def __init__(self, request, registry, chunk_chars: int) -> None:
        key = request_key(request, registry)
        self.root = confine_output_path(load_paths()['audio_dir'].parent / 'temp' / 'recovery' / key)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(str(self._path('checkpoint.lock')))
        try:
            self.lock.acquire(timeout=0)
        except Timeout as exc:
            raise RuntimeError('Este texto ja esta sendo gerado em outra instancia.') from exc
        self.manifest = self._path('checkpoint.json')
        self.data = {'schema': 1, 'key': key, 'chunk_chars': chunk_chars, 'chunks': {}}
        try:
            if self.manifest.stat().st_size <= 2 * 1024 * 1024:
                saved = json.loads(self.manifest.read_text(encoding='utf-8'))
                if (saved.get('schema') == 1 and saved.get('key') == key and
                        type(saved.get('chunk_chars')) is int and 32 <= saved['chunk_chars'] <= 2000 and
                        isinstance(saved.get('chunks'), dict)):
                    self.data = saved
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        self.chunk_chars = self.data['chunk_chars']

    def _path(self, name: str) -> Path:
        return confine_output_path(self.root / name, label='recovery file')

    @staticmethod
    def valid_audio(path: Path) -> bool:
        info = sf.info(path)
        return info.samplerate == SAMPLE_RATE and info.channels == 1 and info.frames > 0

    def restore(self, index: int, destination: Path) -> bool:
        source = self._path(f'{index:06d}.wav')
        expected = self.data['chunks'].get(str(index))
        try:
            if (not isinstance(expected, str) or not source.is_file() or
                    source.stat().st_size > 32 * 1024 * 1024 or
                    digest(source) != expected or not self.valid_audio(source)):
                return False
            shutil.copyfile(source, confine_output_path(destination))
            return True
        except (OSError, ValueError, RuntimeError):
            return False

    def save(self, index: int, source: Path) -> None:
        source = confine_output_path(source, must_exist=True)
        # Keep disk headroom for the final WAV/MP3 and the operating system.
        if shutil.disk_usage(self.root).free < 2 * 1024**3:
            raise RuntimeError('Espaco insuficiente para salvar o progresso com seguranca.')
        target = self._path(f'{index:06d}.wav')
        pending = self._path(f'{index:06d}.pending')
        with source.open('rb') as incoming, pending.open('wb') as outgoing:
            shutil.copyfileobj(incoming, outgoing)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        if not self.valid_audio(pending):
            raise ValueError('Invalid recovery audio')
        checksum = digest(pending)
        os.replace(pending, target)
        self.data['chunks'][str(index)] = checksum
        temporary = self._path('checkpoint.pending')
        with temporary.open('w', encoding='utf-8') as handle:
            json.dump(self.data, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.manifest)

    def discard(self) -> None:
        # Delete only our known files; never recursively delete a directory.
        for path in self.root.iterdir():
            if re.fullmatch(r'\d{6}\.(wav|pending)', path.name) and not path.is_symlink():
                self._path(path.name).unlink(missing_ok=True)
        self._path('checkpoint.pending').unlink(missing_ok=True)
        self.manifest.unlink(missing_ok=True)
        try:
            self.root.rmdir()
        except OSError:
            pass

    def close(self) -> None:
        self.lock.release()

    @classmethod
    def discard_abandoned(cls, root: Path) -> None:
        """Called only after a cancelled worker has stopped and released its lock."""
        parent = confine_output_path(load_paths()['audio_dir'].parent / 'temp' / 'recovery')
        root = confine_output_path(root)
        if root.parent != parent or not re.fullmatch(r'[a-f0-9]{64}', root.name):
            raise ValueError('Unsafe recovery cleanup path')
        if not root.is_dir():
            return
        store = cls.__new__(cls)
        store.root = root
        store.manifest = store._path('checkpoint.json')
        store.lock = FileLock(str(store._path('checkpoint.lock')))
        with store.lock.acquire(timeout=0):
            store.discard()
