"""Runs the hermetic node:test suite for adapters/chatgpt/observer.js.

No browser: tests run against an in-repo fake DOM. Skipped (not failed)
when node is unavailable.
"""
import os
import shutil
import subprocess
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ChatgptObserverTest(unittest.TestCase):
    def test_observer_js_suite(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("node not available")
        proc = subprocess.run(
            [node, "--test", "tests/chatgpt/observer.test.mjs"],
            cwd=REPO, capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0,
                         msg=proc.stdout[-2000:] + proc.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
