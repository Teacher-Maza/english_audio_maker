from _rc_bootstrap import V2_ROOT

import unittest
from uuid import uuid4
from unittest.mock import Mock, patch

import numpy as np

from v2_kokoro.app.core import resource_manager as rm, job_runner as jobs
from v2_kokoro.app.core.generation_contracts import GenerationRequest, MODE_NARRATION
from v2_kokoro.app.core.ffmpeg_runner import Mp3Validation


def sample(free=8, cpu=10):
    return rm.ResourceSnapshot(free, 20, None, None, cpu, 100, 8)


class AdaptiveTests(unittest.TestCase):
    def setUp(self):
        self.cores = patch.object(rm, '_logical_cores', return_value=8)
        self.cores.start()
        self.addCleanup(self.cores.stop)

    def controller(self, snapshot):
        return rm.AdaptiveController(rm.resolve_profile(snapshot=snapshot))

    def test_pressure_reduces_immediately_without_changing_text_boundaries(self):
        control = self.controller(sample())
        result = control.observe(sample(cpu=90))
        self.assertEqual(result.threads, 1)
        self.assertEqual(result.chunk_chars, 280)
        self.assertGreater(result.throttle_seconds, 0)

    def test_speedup_needs_time_and_samples(self):
        control = self.controller(sample(cpu=90))
        with patch.object(rm.time, 'monotonic', side_effect=[0, 1, 4, 5]):
            for _ in range(3):
                self.assertEqual(control.observe(sample()).threads, 1)
            self.assertEqual(control.observe(sample()).threads, 4)
        self.assertEqual(control.current().chunk_chars, 160)

    def test_fluctuations_reset_speedup(self):
        control = self.controller(sample(cpu=90))
        with patch.object(rm.time, 'monotonic', side_effect=[0, 4, 5, 6]):
            control.observe(sample())
            control.observe(sample())
            control.observe(sample(cpu=90))
            control.observe(sample())
            self.assertEqual(control.observe(sample()).threads, 1)

    def test_throttle_changes_even_when_thread_count_matches(self):
        with patch.object(rm, '_logical_cores', return_value=2):
            control = self.controller(sample())
            self.assertEqual(control.current().threads, 1)
            self.assertEqual(control.observe(sample(cpu=90)).threads, 1)
            self.assertEqual(control.current().throttle_seconds, .75)

    def test_manual_profile_stays_manual(self):
        initial = rm.resolve_profile(rm.PROFILE_ECONOMIC)
        self.assertEqual(rm.AdaptiveController(initial).observe(sample(cpu=90)), initial)

    def test_critical_memory_stops_isolated_worker(self):
        context = Mock()
        worker = context.Process.return_value
        worker.pid, worker.exitcode = 123, -1
        worker.is_alive.return_value = True
        request = GenerationRequest(mode=MODE_NARRATION, project_name='guard', text='Hello.', narration_voice_id='af_heart')
        with patch.object(jobs.multiprocessing, 'get_context', return_value=context), patch.object(jobs.psutil, 'Process'), patch.object(jobs, '_memory_sample', return_value={'rss_mb': 100, 'available_ram_gb': .2}), patch.object(jobs, '_consume_worker_events', return_value=None), patch.object(jobs, '_worker_result', return_value=None), patch.object(jobs, '_stop_worker', return_value=True) as stop:
            result = jobs._run_generation_isolated(request, None, resource_profile=rm.PROFILE_AUTOMATIC, resource_callback=None, cancel_event=None, pause_event=None)
        self.assertFalse(result.success)
        self.assertIn('nivel critico', result.errors[0])
        stop.assert_called_once()
        self.assertTrue(result.metadata['process_isolation']['forced_termination'])
        self.assertFalse(jobs._GENERATION_LOCK.locked())

    def test_generation_applies_slowdown_and_exports_complete_audio(self):
        callbacks, threads, stages = [], [], []

        class Monitor:
            def __init__(self, output, callback):
                callbacks.append(callback)
            def start(self):
                pass
            def stop(self):
                return {'samples': 1}

        class Engine:
            def __init__(self, registry, count):
                threads.append(count)
            def set_threads(self, count):
                threads.append(count)
            def synthesize(self, *args):
                callbacks[0](sample(cpu=90).to_dict())
                return np.zeros(2400, dtype=np.float32)
            def close(self):
                pass

        output = V2_ROOT / 'temp' / 'adaptive_tests' / uuid4().hex
        request = GenerationRequest(mode=MODE_NARRATION, project_name='adaptive', text='A complete sentence for a listening exercise. ' * 20, narration_voice_id='af_heart', output_base_dir=output)

        def convert(source, target):
            target.write_bytes(b'ID3 test')

        with patch.object(rm, 'capture_snapshot', return_value=sample()), patch.object(jobs, 'convert_wav_to_mp3', convert), patch.object(jobs.time, 'sleep'):
            result = jobs.run_generation(request, lambda event: stages.append(event.stage), _monitor_factory=Monitor, _engine_factory=Engine, _mp3_validator=lambda path: Mp3Validation(path, 1, path.stat().st_size))
        self.assertTrue(result.success, result.errors)
        self.assertEqual(threads, [4, 1])
        self.assertIn('synthesizing_reduced', stages)
        self.assertNotIn('waiting_resources', stages)
        self.assertEqual(result.metadata['threads'], 1)
        self.assertEqual(result.metadata['chunk_chars'], 280)
        self.assertEqual(result.metadata['throttle_seconds'], .75)
        self.assertTrue((output / 'adaptive' / 'narration_complete.mp3').is_file())


if __name__ == '__main__':
    unittest.main()
