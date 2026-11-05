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

    def test_run_from_selected_skips_earlier_full_loop(self):
        actions = [
            Action(kind="key", keys="a"),
            Action(kind="loop_start", repeats=10**9),
            Action(kind="key", keys="b"),
            Action(kind="loop_end"),
            Action(kind="key", keys="c"),
        ]
        self.assertEqual(
            [a.keys for _, a in iter_execution_steps(actions, start_index=4)], ["c"]
        )
        self.assertEqual(progress_total(actions, 1, start_index=4), 1)

    def test_run_from_selected_inside_loop(self):
        actions = [
            Action(kind="key", keys="a"),
            Action(kind="loop_start", repeats=3),
            Action(kind="key", keys="b"),
            Action(kind="key", keys="c", repeats=2),
            Action(kind="loop_end"),
            Action(kind="key", keys="d"),
        ]
        expected = ["c", "c", "b", "c", "c", "b", "c", "c", "d"]
        self.assertEqual(
            [a.keys for _, a in iter_execution_steps(actions, start_index=3)], expected
        )
        self.assertEqual(progress_total(actions, 1, 3), len(expected))
        self.assertEqual(
            [a.keys for _, a in iter_execution_steps(actions, start_index=4)], ["d"]
        )
        self.assertEqual(progress_total(actions, 1, 4), 1)

    def test_step_permits_one_complete_action(self):
        gate = PlaybackGate()
        gate.pause()
        completed = []
        def worker():
            for index in range(2):
                gate.begin_action()
                try:
                    gate.wait(0.02)
                    completed.append(index)
                finally:
                    gate.end_action()
        thread = threading.Thread(target=worker)
        thread.start()
        time.sleep(0.04)
        self.assertEqual(completed, [])
        gate.step()
        time.sleep(0.09)
        self.assertEqual(completed, [0])
        self.assertTrue(thread.is_alive())
        gate.step()
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(completed, [0, 1])

    def test_step_completes_paused_in_progress_wait(self):
        gate = PlaybackGate()
        began = threading.Event()
        finished = threading.Event()
        def worker():
            gate.begin_action()
            try:
                began.set()
                gate.wait(0.25)
                finished.set()
            finally:
                gate.end_action()
        thread = threading.Thread(target=worker)
        thread.start()
        self.assertTrue(began.wait(0.5))
        time.sleep(0.06)
        gate.pause()
        time.sleep(0.09)
        self.assertFalse(finished.is_set())
        gate.step()
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        self.assertTrue(finished.is_set())
        self.assertTrue(gate.paused)
        # The step was spent on the old action, not queued for a new one.
        with self.assertRaises(RuntimeError):
            gate.stop()
            gate.begin_action()

    def test_stop_while_waiting_for_step(self):
        gate = PlaybackGate()
        gate.pause()
        errors = []
        def worker():
            try:
                gate.begin_action()
            except RuntimeError as exc:
                errors.append(str(exc))
        thread = threading.Thread(target=worker)
        thread.start()
        time.sleep(0.04)
        gate.stop()
        thread.join(timeout=1)
        self.assertEqual(errors, ["Stopped"])

    def test_resume_exits_step_mode(self):
        gate = PlaybackGate()
        gate.pause()
        gate.step()
        gate.resume()
        self.assertFalse(gate.paused)
        gate.begin_action()
        self.assertFalse(gate.end_action())
        gate.begin_action()
        self.assertFalse(gate.end_action())

    def test_step_keeps_pause_during_long_wait(self):
        gate = PlaybackGate()
        gate.pause()
        done = threading.Event()
        def worker():
            gate.begin_action()
            try:
                gate.wait(0.13)
                done.set()
            finally:
                gate.end_action()
        thread = threading.Thread(target=worker)
        thread.start()
        gate.step()
        thread.join(timeout=1)
        self.assertTrue(done.is_set())
        self.assertTrue(gate.paused)

    def test_progress_ignores_disabled_actions(self):
        actions = [Action(kind="wait", repeats=3), Action(kind="wait", repeats=9, enabled=False)]
        self.assertEqual(progress_total(actions, 2), 6)


if __name__ == "__main__":
    unittest.main()
