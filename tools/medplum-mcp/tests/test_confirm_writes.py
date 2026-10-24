"""Testy hooku confirm-writes (stdlib unittest, Python 3.9+)."""
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "confirm-writes.sh"


def run_hook(payload, env=None):
    data = payload if isinstance(payload, str) else json.dumps(payload)
    result = subprocess.run(["sh", str(HOOK)], input=data, capture_output=True, text=True, env=env, timeout=20)
    return result.returncode, result.stdout.strip()


def event(method, path="Patient"):
    return {"hook_event_name": "PreToolUse", "tool_name": "mcp__plugin_medplum-mcp_medplum-dev__fhir-request",
            "tool_input": {"method": method, "path": path}}


def decision(stdout):
    return json.loads(stdout)["hookSpecificOutput"]["permissionDecision"]


class ConfirmWritesTest(unittest.TestCase):
    def test_get_passes_without_output(self):
        for method in ("GET", "get", " Get "):
            code, out = run_hook(event(method))
            self.assertEqual((code, out), (0, ""), method)

    def test_writes_require_confirmation(self):
        for method in ("POST", "PUT", "PATCH", "DELETE", "delete", ""):
            code, out = run_hook(event(method))
            self.assertEqual(code, 0, method)
            self.assertEqual(decision(out), "ask", method)

    def test_batch_on_base_url_requires_confirmation(self):
        code, out = run_hook(event("POST", ""))
        self.assertEqual(decision(out), "ask")
        self.assertIn("batch", json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"])

    def test_invalid_input_fails_closed(self):
        for payload in ("not json", "", "[]", json.dumps({"tool_input": "x"})):
            code, out = run_hook(payload)
            self.assertEqual(code, 0, payload)
            self.assertEqual(decision(out), "ask", payload)

    def test_missing_python_fails_closed(self):
        empty_bin = Path(__file__).resolve().parent / "_empty_path"
        empty_bin.mkdir(exist_ok=True)
        try:
            env = {"PATH": str(empty_bin)}
            sh = shutil.which("sh")
            data = json.dumps(event("GET"))
            result = subprocess.run([sh, str(HOOK)], input=data, capture_output=True, text=True, env=env, timeout=20)
            self.assertEqual(decision(result.stdout.strip()), "ask")
        finally:
            empty_bin.rmdir()


if __name__ == "__main__":
    unittest.main()
