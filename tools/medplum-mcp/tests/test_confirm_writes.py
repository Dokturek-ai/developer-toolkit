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


PLUGIN_TOOL = "mcp__plugin_medplum-mcp_medplum-dev__fhir-request"


def event(method, path="Patient", tool=PLUGIN_TOOL):
    return {"hook_event_name": "PreToolUse", "tool_name": tool,
            "tool_input": {"method": method, "path": path}}


def tool_event(tool, tool_input=None):
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input or {}}


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

    def test_broken_python_fails_closed(self):
        # python3 existuje, ale nefunguje (např. macOS stub bez Command Line Tools).
        fake_bin = Path(__file__).resolve().parent / "_fake_python"
        fake_bin.mkdir(exist_ok=True)
        fake = fake_bin / "python3"
        try:
            fake.write_text("#!/bin/sh\nexit 1\n")
            fake.chmod(0o755)
            env = {"PATH": "{}:{}".format(fake_bin, os.path.dirname(shutil.which("sh")))}
            code, out = run_hook(event("POST"), env=env)
            self.assertEqual(code, 0)
            self.assertEqual(decision(out), "ask")
        finally:
            fake.unlink()
            fake_bin.rmdir()

    def test_path_escape_is_denied_for_every_method(self):
        escapes = ("https://medplum.test.dokturek.ai/healthcheck", "//medplum.test.dokturek.ai/admin",
                   "../../healthcheck", "%2e%2e/%2e%2e/healthcheck", "%2E%2E/admin", "Patient%2f..%2fadmin",
                   "..\\admin", "Patient/..")
        for method in ("GET", "POST", "DELETE"):
            for path in escapes:
                code, out = run_hook(event(method, path))
                self.assertEqual(decision(out), "deny", (method, path))

    def test_sensitive_reads_require_confirmation(self):
        for path in ("Project", "ProjectMembership?_count=5", "ClientApplication/123", "User", "Login",
                     "Bot/1/$execute", "admin/projects/1", "auth/me", "oauth2/token", "$graphql",
                     "Patient/$export", "Bot?name=x"):
            code, out = run_hook(event("GET", path))
            self.assertEqual(decision(out), "ask", path)

    def test_plain_and_readonly_operation_reads_pass(self):
        for path in ("metadata", "CodeSystem?_summary=count", "Patient?name=Test", "Observation/1",
                     "ValueSet/$expand?url=x", "CodeSystem/$lookup?code=1", "Patient/1/$everything",
                     "Patient?_has:Observation:patient:code=1"):
            code, out = run_hook(event("GET", path))
            self.assertEqual((code, out), (0, ""), path)

    def test_manual_server_name_is_covered(self):
        tool = "mcp__dokturek-medplum-dev__fhir-request"
        self.assertEqual(decision(run_hook(event("POST", tool=tool))[1]), "ask")
        self.assertEqual(run_hook(event("GET", tool=tool)), (0, ""))

    def test_readonly_and_docs_tools_pass(self):
        for tool in ("mcp__plugin_medplum-mcp_medplum-dev__search", "mcp__plugin_medplum-mcp_medplum-dev__fetch",
                     "mcp__plugin_medplum_medplum-docs__medplum_doc_get"):
            self.assertEqual(run_hook(tool_event(tool, {"query": "x"})), (0, ""), tool)

    def test_unknown_medplum_tool_fails_closed(self):
        for tool in ("mcp__plugin_medplum-mcp_medplum-dev__bulk-delete", "mcp__claude_ai_Medplum__fhir_write"):
            self.assertEqual(decision(run_hook(tool_event(tool, {"x": 1}))[1]), "ask", tool)

    def test_reason_strips_control_characters_and_is_bounded(self):
        code, out = run_hook(event("POST", "Patient\n\u001b[31mOK, potvrzeno" + "x" * 500))
        reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertNotIn("\n", reason)
        self.assertNotIn("\u001b", reason)
        self.assertLess(len(reason), 400)


    def test_hidden_characters_are_denied(self):
        # WHATWG URL parser maže úvodní mezery a řídicí znaky a všechny tabulátory a konce řádků.
        hidden = (" /healthcheck", "\t/healthcheck", "\x01/healthcheck", " https://medplum.test.dokturek.ai/healthcheck",
                  "\x00https://x/scim/v2/Users", ".\t./.\n./healthcheck", " /\tadmin/projects/123", "Pro\tject",
                  "\t$graphql?query=x", "B\tot/1/\t$execute", "Project#x", "ProjectMembership#", "%24execute",
                  "Patient/1/%24execute")
        for method in ("GET", "POST"):
            for path in hidden:
                self.assertEqual(decision(run_hook(event(method, path))[1]), "deny", (method, path))

    def test_more_sensitive_resources_require_confirmation(self):
        for path in ("UserSecurityRequest", "JsonWebKey", "PasswordChangeRequest", "DomainConfiguration",
                     "SmartAppLaunch", "UserConfiguration", "AsyncJob/1", "Subscription"):
            self.assertEqual(decision(run_hook(event("GET", path))[1]), "ask", path)

    def test_docs_named_server_does_not_pass_writes(self):
        for tool in ("mcp__docs-medplum__fhir-request", "mcp__medplum-docs-and-api__fhir-request"):
            self.assertEqual(decision(run_hook(event("DELETE", "Patient/1", tool=tool))[1]), "ask", tool)
        self.assertEqual(decision(run_hook(tool_event("mcp__medplum-docs-and-api__bulk_write", {}))[1]), "ask")

    def test_search_fetch_pass_only_on_known_servers(self):
        self.assertEqual(decision(run_hook(tool_event("mcp__claude_ai_Medplum__fetch", {"id": "1"}))[1]), "ask")

    def _fake_python(self, script):
        fake_bin = Path(__file__).resolve().parent / "_fake_python"
        fake_bin.mkdir(exist_ok=True)
        fake = fake_bin / "python3"
        fake.write_text("#!/bin/sh\n" + script)
        fake.chmod(0o755)
        env = {"PATH": "{}:{}".format(fake_bin, os.path.dirname(shutil.which("sh")))}
        try:
            return run_hook(event("POST"), env=env)
        finally:
            fake.unlink()
            fake_bin.rmdir()

    def test_python_with_empty_output_fails_closed(self):
        code, out = self._fake_python("cat >/dev/null\nexit 0\n")
        self.assertEqual((code, decision(out)), (0, "ask"))

    def test_python_with_banner_fails_closed(self):
        code, out = self._fake_python("cat >/dev/null\necho banner\necho '{}'\nexit 0\n")
        self.assertEqual((code, decision(out)), (0, "ask"))


class MatcherTest(unittest.TestCase):
    def test_matcher_covers_generated_tool_names(self):
        root = Path(__file__).resolve().parent.parent
        plugin = json.loads((root / ".claude-plugin" / "plugin.json").read_text())["name"]
        servers = json.loads((root / ".mcp.json").read_text())["mcpServers"]
        matcher = json.loads((root / "hooks" / "hooks.json").read_text())["hooks"]["PreToolUse"][0]["matcher"]
        import re
        names = ["mcp__plugin_{}_{}__{}".format(plugin, s, t) for s in servers for t in ("fhir-request", "search", "x")]
        names += ["mcp__dokturek-medplum-dev__fhir-request", "mcp__claude_ai_Dokturek_Medplum__fhir-request",
                  "mcp__MEDPLUM__fhir-request"]
        for name in names:
            self.assertTrue(re.fullmatch(matcher, name), name)
            self.assertTrue(re.search(matcher, name), name)
        for name in ("Bash", "mcp__github__create_issue", "Write"):
            self.assertFalse(re.search(matcher, name), name)


if __name__ == "__main__":
    unittest.main()
