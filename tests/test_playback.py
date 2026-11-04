import threading
import time
import unittest

from macro_model import Action
from macro_playback import PlaybackGate, progress_total


class PlaybackTests(unittest.TestCase):
    def test_pause_then_stop(self):
        gate = PlaybackGate()
        gate.pause()
        result = []
        thread = threading.Thread(target=lambda: self._record_wait(gate, result))
        thread.start()
        time.sleep(0.08)
        self.assertTrue(thread.is_alive())
        gate.stop()
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, ["Stopped"])

    def _record_wait(self, gate, result):
        try:
            gate.wait(1)
        except RuntimeError as exc:
            result.append(str(exc))

    def test_pause_does_not_consume_wait(self):
        gate = PlaybackGate()
        finished = threading.Event()
        worker = threading.Thread(target=lambda: (gate.wait(0.15), finished.set()))
        worker.start()
        time.sleep(0.04)
        gate.pause()
        time.sleep(0.19)
        self.assertFalse(finished.is_set())
        gate.resume()
        worker.join(timeout=1)
        self.assertTrue(finished.is_set())

    def test_progress_ignores_disabled_actions(self):
        actions = [Action(kind="wait", repeats=3), Action(kind="wait", repeats=9, enabled=False)]
        self.assertEqual(progress_total(actions, 2), 6)


if __name__ == "__main__":
    unittest.main()
