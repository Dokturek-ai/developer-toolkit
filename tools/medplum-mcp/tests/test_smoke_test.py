"""smoke_test.py --e2e log handling with a fake bridge process; no network, npx or browser."""
import contextlib
import functools
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "smoke_test", Path(__file__).resolve().parent.parent / "scripts" / "smoke_test.py")
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


class FakeBridge:
    def __init__(self, replies):
        self.stdin = io.StringIO()
        self.stdout = iter([json.dumps(reply) + "\n" for reply in replies])
        self.terminated = False

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


GOOD_REPLIES = [
    {"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "medplum", "version": "synthetic"}}},
    {"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "fhir-request"}]}},
    {"jsonrpc": "2.0", "id": 3, "result": {"content": [
        {"type": "text", "text": json.dumps({"resourceType": "Bundle", "total": 3})}]}},
]


class E2eLogTest(unittest.TestCase):
    def run_e2e(self, replies):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        bridge = FakeBridge(replies)
        report = smoke.Report()
        output = io.StringIO()
        with patch.object(smoke.shutil, "which", return_value="synthetic-npx"), \
                patch.object(smoke.subprocess, "Popen", return_value=bridge), \
                patch.object(smoke.tempfile, "NamedTemporaryFile", functools.partial(
                    tempfile.NamedTemporaryFile, dir=directory.name)), \
                contextlib.redirect_stdout(output):
            smoke.e2e_checks(report)
        self.assertTrue(bridge.terminated)
        return report, list(Path(directory.name).iterdir()), output.getvalue()

    def test_log_is_deleted_after_successful_run(self):
        report, logs, _ = self.run_e2e(GOOD_REPLIES)
        self.assertEqual(report.failures, 0)
        self.assertEqual(logs, [])

    def test_log_is_kept_when_a_check_fails(self):
        bad_total = GOOD_REPLIES[:2] + [{"jsonrpc": "2.0", "id": 3, "result": {"content": []}}]
        for replies in (bad_total, GOOD_REPLIES[:1], []):
            with self.subTest(replies=len(replies)):
                report, logs, output = self.run_e2e(replies)
                self.assertGreater(report.failures, 0)
                self.assertEqual(len(logs), 1)
                self.assertIn(str(logs[0]), output)


if __name__ == "__main__":
    unittest.main()
