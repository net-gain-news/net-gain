import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from run_lock import ShowBusy, show_lock


class ShowLockTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.dir = self._dir.name

    def tearDown(self):
        self._dir.cleanup()

    def test_a_second_pass_on_the_same_show_is_turned_away(self):
        with show_lock(16, directory=self.dir):
            with self.assertRaises(ShowBusy) as caught:
                with show_lock(16, directory=self.dir):
                    self.fail("the second pass must not run")
        self.assertEqual(caught.exception.show_id, 16)

    def test_reports_how_long_the_holder_has_held_it(self):
        with show_lock(16, directory=self.dir):
            time.sleep(1.1)
            with self.assertRaises(ShowBusy) as caught:
                with show_lock(16, directory=self.dir):
                    pass
        self.assertGreaterEqual(caught.exception.held_seconds, 1.0)
        self.assertLess(caught.exception.held_seconds, 30)

    def test_the_lock_is_free_again_after_the_block_even_when_it_fails(self):
        with self.assertRaises(RuntimeError):
            with show_lock(16, directory=self.dir):
                raise RuntimeError("boom")
        with show_lock(16, directory=self.dir):
            pass

    def test_shows_lock_independently(self):
        with show_lock(16, directory=self.dir):
            with show_lock(17, directory=self.dir):
                pass

    def test_can_wait_for_a_pass_that_finishes(self):
        released = threading.Event()

        def hold():
            with show_lock(16, directory=self.dir):
                released.wait(timeout=5)

        thread = threading.Thread(target=hold)
        thread.start()
        time.sleep(0.3)
        threading.Timer(1.0, released.set).start()
        started = time.monotonic()
        with show_lock(16, wait_seconds=10, directory=self.dir):
            waited = time.monotonic() - started
        thread.join()
        self.assertGreater(waited, 0.5)
        self.assertLess(waited, 5)

    def test_gives_up_after_the_wait(self):
        with show_lock(16, directory=self.dir):
            started = time.monotonic()
            with self.assertRaises(ShowBusy):
                with show_lock(16, wait_seconds=1.5, directory=self.dir):
                    pass
            self.assertGreaterEqual(time.monotonic() - started, 1.4)


if __name__ == "__main__":
    unittest.main()
