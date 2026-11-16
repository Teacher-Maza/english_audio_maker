from _rc_bootstrap import V2_ROOT

import json
import shutil
import os
import subprocess
import sys
import threading
from pathlib import Path
import unittest
from dataclasses import replace
from uuid import uuid4
from unittest.mock import patch

import numpy as np
import soundfile as sf

from v2_kokoro.app.core import recovery_store as recovery, job_runner as jobs
from v2_kokoro.app.core.generation_contracts import GenerationRequest, MODE_NARRATION
from v2_kokoro.app.core.resource_manager import ResourceDecision, ResourceSnapshot
from v2_kokoro.app.core.ffmpeg_runner import Mp3Validation


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.root = V2_ROOT / 'temp' / 'recovery_tests' / uuid4().hex
        self.root.mkdir(parents=True)
        self.request = GenerationRequest(mode=MODE_NARRATION, project_name='resume', text='An English sentence to recover safely. ' * 25, narration_voice_id='af_heart', output_base_dir=self.root / 'output')
        self.source = self.root / 'source.wav'
        sf.write(self.source, np.zeros(2400), 24000, subtype='PCM_16')
        self.key_patch = patch.object(recovery, 'request_key', return_value='a' * 64)
        self.paths_patch = patch.object(recovery, 'load_paths', return_value={'audio_dir': self.root / 'audios'})
        self.key_patch.start()
        self.paths_patch.start()
        self.addCleanup(self.paths_patch.stop)
        self.addCleanup(self.key_patch.stop)

    def store(self, size=280):
        return recovery.RecoveryStore(self.request, None, size)

    def test_reopen_preserves_boundaries_and_validated_audio(self):
        first = self.store()
        first.save(1, self.source)
        manifest = first.manifest.read_text()
        self.assertNotIn(self.request.text, manifest)
        first.close()
        second = self.store(160)
        try:
            self.assertEqual(second.chunk_chars, 280)
            destination = self.root / 'restored.wav'
            self.assertTrue(second.restore(1, destination))
            self.assertEqual(destination.read_bytes(), self.source.read_bytes())
        finally:
            second.close()

    def test_corrupted_or_uncommitted_audio_is_not_reused(self):
        store = self.store()
        try:
            store.save(1, self.source)
            (store.root / '000001.wav').write_bytes(b'broken')
            shutil.copyfile(self.source, store.root / '000002.wav')
            self.assertFalse(store.restore(1, self.root / 'bad.wav'))
            self.assertFalse(store.restore(2, self.root / 'uncommitted.wav'))
        finally:
            store.close()

    def test_concurrent_generation_is_blocked(self):
        store = self.store()
        try:
            with self.assertRaisesRegex(RuntimeError, 'outra instancia'):
                self.store()
        finally:
            store.close()

    def test_abrupt_process_exit_preserves_checkpoint_and_releases_lock(self):
        completed = subprocess.run(
            [sys.executable, '-B', __file__, '--checkpoint-crash', str(self.root)],
            cwd=V2_ROOT, timeout=30, capture_output=True, text=True, shell=False,
        )
        self.assertEqual(completed.returncode, 23, completed.stderr)
        store = self.store()
        try:
            self.assertTrue(store.restore(1, self.root / 'after_crash.wav'))
        finally:
            store.close()

    def test_low_disk_preserves_previous_checkpoint(self):
        store = self.store()
        try:
            store.save(1, self.source)
            before = store.manifest.read_bytes()
            with patch.object(recovery.shutil, 'disk_usage', return_value=shutil._ntuple_diskusage(100, 99, 1)):
                with self.assertRaises(RuntimeError):
                    store.save(2, self.source)
            self.assertEqual(store.manifest.read_bytes(), before)
        finally:
            store.close()

    def test_discard_removes_uncommitted_audio_and_preserves_other_files(self):
        store = self.store()
        store.save(1, self.source)
        pending = store.root / '000002.pending'
        pending.write_bytes(b'incomplete')
        sentinel = store.root / 'user_notes.txt'
        sentinel.write_text('keep')
        store.close()
        recovery.RecoveryStore.discard_abandoned(store.root)
        self.assertFalse(store.manifest.exists())
        self.assertFalse(pending.exists())
        self.assertFalse(list(store.root.glob('*.wav')))
        self.assertEqual(sentinel.read_text(), 'keep')

    def test_intentional_cancel_discards_saved_audio(self):
        cancel = threading.Event()
        calls = []

        class Monitor:
            def __init__(self, *args): pass
            def start(self): pass
            def stop(self): return {'samples': 1}

        class Engine:
            def __init__(self, *args): pass
            def synthesize(self, *args):
                calls.append(1)
                if len(calls) == 2:
                    cancel.set()
                return np.zeros(2400, dtype=np.float32)
            def close(self): pass

        healthy = ResourceDecision(True, ResourceSnapshot(8, 20, None, None, 10, 100, 8))
        result = jobs._run_generation_local(
            self.request, cancel_event=cancel,
            _resource_evaluator=lambda *a, **k: healthy,
            _engine_factory=Engine, _monitor_factory=Monitor,
            _checkpoint_factory=recovery.RecoveryStore,
        )
        self.assertTrue(result.metadata['cancelled'])
        self.assertTrue(result.metadata['recovery_discarded'])
        cache = self.root / 'temp' / 'recovery'
        self.assertFalse(list(cache.rglob('*.wav')))
        self.assertFalse(list(cache.rglob('checkpoint.json')))

    def test_failure_then_retry_reuses_completed_chunks(self):
        calls = []
        fail = [True]

        class Monitor:
            def __init__(self, *args): pass
            def start(self): pass
            def stop(self): return {'samples': 1}

        class Engine:
            def __init__(self, *args): pass
            def synthesize(self, text, *args):
                calls.append(text)
                if fail[0] and len(calls) == 2:
                    raise RuntimeError('Simulated interruption')
                return np.zeros(2400, dtype=np.float32)
            def close(self): pass

        healthy = ResourceDecision(True, ResourceSnapshot(8, 20, None, None, 10, 100, 8))
        kwargs = dict(_resource_evaluator=lambda *a, **k: healthy, _engine_factory=Engine, _monitor_factory=Monitor, _checkpoint_factory=recovery.RecoveryStore, _mp3_validator=lambda p: Mp3Validation(p, 1, p.stat().st_size))
        first = jobs._run_generation_local(self.request, **kwargs)
        self.assertFalse(first.success)
        fail[0] = False
        calls.clear()
        with patch.object(jobs, 'convert_wav_to_mp3', side_effect=lambda source, target: shutil.copyfile(source, target)):
            second = jobs._run_generation_local(self.request, **kwargs)
        self.assertTrue(second.success, second.errors)
        self.assertEqual(second.metadata['reused_chunks'], 1)
        self.assertEqual(len(calls), second.metadata['item_count'] - 1)
        self.assertFalse(list((self.root / 'temp' / 'recovery').rglob('checkpoint.json')))


class FingerprintTests(unittest.TestCase):
    def test_input_and_engine_changes_invalidate_recovery(self):
        request = GenerationRequest(mode=MODE_NARRATION, project_name='test', text='Hello', narration_voice_id='af_heart')
        from unittest.mock import MagicMock as Mock
        with patch.object(recovery, 'digest', return_value='original'), patch.object(recovery.importlib.metadata, 'version', return_value='1'):
            initial = recovery.request_key(request, Mock())
            for modified in (replace(request, text='Bye'), replace(request, speed=.9), replace(request, narration_voice_id='bf_emma')):
                self.assertNotEqual(recovery.request_key(modified, Mock()), initial)
            with patch.object(recovery, 'digest', return_value='changed'):
                self.assertNotEqual(recovery.request_key(request, Mock()), initial)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--checkpoint-crash':
        root = Path(sys.argv[2]).resolve()
        root.relative_to((V2_ROOT / 'temp' / 'recovery_tests').resolve())
        with patch.object(recovery, 'request_key', return_value='a' * 64), patch.object(recovery, 'load_paths', return_value={'audio_dir': root / 'audios'}):
            store = recovery.RecoveryStore(None, None, 280)
            store.save(1, root / 'source.wav')
            os._exit(23)  # Deliberately skip all Python cleanup in this test child.
    else:
        unittest.main()
