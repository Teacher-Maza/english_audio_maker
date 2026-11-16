from _rc_bootstrap import V2_ROOT

import threading
import unittest
from unittest.mock import patch

from v2_kokoro.app.core import resource_manager as resources


def snapshot(free, total=8):
    return resources.ResourceSnapshot(free, 20, None, None, 10, 100, total)


class ResourceSafetyTests(unittest.TestCase):
    def test_automatic_leaves_cpu_capacity(self):
        for cores, maximum in ((1, 1), (2, 1), (4, 2), (8, 4)):
            with self.subTest(cores=cores), patch.object(resources, '_logical_cores', return_value=cores):
                profile = resources.resolve_profile(snapshot=snapshot(8))
                self.assertLessEqual(profile.threads, maximum)

    def test_recovery_waits_until_generation_can_continue(self):
        for total, low, recovered in ((8, 1.5, 2), (32, 3, 6)):
            with self.subTest(total=total), patch.object(resources, 'capture_snapshot', side_effect=[snapshot(low, total), snapshot(recovered, total)]), patch.object(resources.time, 'sleep') as sleep:
                result = resources.wait_for_memory_recovery(None)
                self.assertTrue(resources.evaluate_resources(snapshot=result).allowed)
                sleep.assert_called_once()

    def test_cancel_during_recovery(self):
        event = threading.Event()
        event.set()
        with patch.object(resources, 'capture_snapshot', return_value=snapshot(.5)), patch.object(resources.time, 'sleep') as sleep:
            resources.wait_for_memory_recovery(None, cancel_event=event)
            sleep.assert_not_called()

    def test_recovery_timeout(self):
        with patch.object(resources, 'capture_snapshot', return_value=snapshot(.5)), patch.object(resources.time, 'monotonic', side_effect=[0, 21]):
            with self.assertRaises(resources.ResourcePressureError):
                resources.wait_for_memory_recovery(None)


if __name__ == '__main__':
    unittest.main()
