import sys
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.services.processing_queue import SerialProcessingQueue


class SerialProcessingQueueTests(unittest.TestCase):
    def test_runs_jobs_in_fifo_order_without_parallel_execution(self):
        started = []
        completed = []
        active_count = 0
        maximum_active_count = 0
        done = threading.Event()
        lock = threading.Lock()

        def runner(job_id):
            nonlocal active_count, maximum_active_count
            with lock:
                active_count += 1
                maximum_active_count = max(maximum_active_count, active_count)
            time.sleep(0.02)
            with lock:
                active_count -= 1

        queue = SerialProcessingQueue(
            runner,
            on_started=started.append,
            on_finished=completed.append,
            on_idle=done.set,
        )

        self.assertTrue(queue.enqueue("first"))
        self.assertTrue(queue.enqueue("second"))
        self.assertTrue(queue.enqueue("third"))
        self.assertFalse(queue.enqueue("second"))
        self.assertTrue(done.wait(2))

        self.assertEqual(started, ["first", "second", "third"])
        self.assertEqual(completed, ["first", "second", "third"])
        self.assertEqual(maximum_active_count, 1)
        self.assertIsNone(queue.active_job_id)
        self.assertEqual(queue.pending_ids(), [])

    def test_discard_removes_only_a_waiting_job(self):
        release_first = threading.Event()
        done = threading.Event()
        completed = []

        def runner(job_id):
            if job_id == "first":
                release_first.wait(2)

        queue = SerialProcessingQueue(runner, on_finished=completed.append, on_idle=done.set)
        self.assertTrue(queue.enqueue("first"))
        self.assertTrue(queue.enqueue("second"))
        time.sleep(0.02)
        self.assertTrue(queue.discard("second"))
        self.assertFalse(queue.discard("first"))
        release_first.set()
        self.assertTrue(done.wait(2))
        self.assertEqual(completed, ["first"])

    def test_accepts_another_project_while_the_active_project_keeps_running(self):
        first_started = threading.Event()
        release_first = threading.Event()
        second_started = threading.Event()
        done = threading.Event()

        def runner(job_id):
            if job_id == "project-a":
                first_started.set()
                release_first.wait(2)
            else:
                second_started.set()

        queue = SerialProcessingQueue(runner, on_idle=done.set)
        self.assertTrue(queue.enqueue("project-a"))
        self.assertTrue(first_started.wait(1))

        # Enqueue is non-blocking: UI work for project B can continue while A runs.
        self.assertTrue(queue.enqueue("project-b"))
        self.assertEqual(queue.active_job_id, "project-a")
        self.assertEqual(queue.pending_ids(), ["project-b"])
        self.assertTrue(queue.has_work)
        self.assertTrue(queue.contains("project-a"))
        self.assertTrue(queue.contains("project-b"))
        self.assertFalse(second_started.is_set())

        release_first.set()
        self.assertTrue(second_started.wait(1))
        self.assertTrue(done.wait(2))
        self.assertFalse(queue.has_work)

    def test_runner_failure_does_not_strand_the_next_project(self):
        started = []
        completed = []
        errors = []
        done = threading.Event()

        def runner(job_id):
            if job_id == "broken-project":
                raise RuntimeError("pipeline failed")

        queue = SerialProcessingQueue(
            runner,
            on_started=started.append,
            on_finished=completed.append,
            on_idle=done.set,
            on_error=lambda job_id, exc: errors.append((job_id, str(exc))),
        )
        self.assertTrue(queue.enqueue("broken-project"))
        self.assertTrue(queue.enqueue("next-project"))
        self.assertTrue(done.wait(2))

        self.assertEqual(started, ["broken-project", "next-project"])
        self.assertEqual(completed, ["broken-project", "next-project"])
        self.assertEqual(errors, [("broken-project", "pipeline failed")])
        self.assertFalse(queue.has_work)

    def test_start_callback_failure_is_reported_and_queue_continues(self):
        ran = []
        errors = []
        done = threading.Event()

        def on_started(job_id):
            if job_id == "invalid-project":
                raise ValueError("cannot start")

        queue = SerialProcessingQueue(
            ran.append,
            on_started=on_started,
            on_idle=done.set,
            on_error=lambda job_id, exc: errors.append((job_id, str(exc))),
        )
        self.assertTrue(queue.enqueue("invalid-project"))
        self.assertTrue(queue.enqueue("valid-project"))
        self.assertTrue(done.wait(2))

        self.assertEqual(ran, ["valid-project"])
        self.assertEqual(errors, [("invalid-project", "cannot start")])
