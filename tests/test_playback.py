import threading
import time
import unittest

from macro_model import Action
from macro_playback import PlaybackGate, iter_execution_steps, progress_total


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

    def test_repeat_block_order_and_progress(self):
        actions = [
            Action(kind="key", keys="a"), Action(kind="key", keys="b"),
            Action(kind="loop_start", repeats=3),
            Action(kind="key", keys="c", repeats=2),
            Action(kind="key", keys="d"),
            Action(kind="loop_end"),
            Action(kind="key", keys="e"),
        ]
        expected = ["a", "b"] + (["c", "c", "d"] * 3) + ["e"]
        self.assertEqual([action.keys for _, action in iter_execution_steps(actions)], expected)
        self.assertEqual([i for i, _ in iter_execution_steps(actions)][:5], [0, 1, 3, 3, 4])
        self.assertEqual(progress_total(actions, 2), len(expected) * 2)

    def test_disabled_actions_inside_loop(self):
        actions = [
            Action(kind="loop_start", repeats=4),
            Action(kind="wait", repeats=99, enabled=False),
            Action(kind="key", keys="x", repeats=2),
            Action(kind="loop_end"),
        ]
        self.assertEqual(len(list(iter_execution_steps(actions))), 8)
        self.assertEqual(progress_total(actions, 3), 24)

    def test_repeat_blocks_stream_without_expansion(self):
        from itertools import islice
        actions = [Action(kind="loop_start", repeats=10**9),
                   Action(kind="key", keys="x"),
                   Action(kind="loop_end")]
        self.assertEqual(len(list(islice(iter_execution_steps(actions), 4))), 4)
        self.assertEqual(progress_total(actions, 2), 2 * 10**9)

    def test_progress_ignores_disabled_actions(self):
        actions = [Action(kind="wait", repeats=3), Action(kind="wait", repeats=9, enabled=False)]
        self.assertEqual(progress_total(actions, 2), 6)


if __name__ == "__main__":
    unittest.main()
