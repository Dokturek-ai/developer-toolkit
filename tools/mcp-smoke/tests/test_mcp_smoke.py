"""Regression tests with synthetic tokens; no network, browser or system keychain."""
import contextlib
import importlib.util
import io
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "mcp_smoke", Path(__file__).resolve().parent.parent / "mcp-smoke.py")
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)

CAPABILITY = json.dumps({"resourceType": "CapabilityStatement", "fhirVersion": "4.0.1"})


class MetadataTest(unittest.TestCase):
    def run_cli(self, required_text, optional_text=None):
        output = io.StringIO()
        optional = (smoke.SmokeError("TOOL", "diagnostic path rejected")
                    if optional_text is None else ({}, [optional_text]))
        with patch.object(smoke, "medplum_token", return_value=(
                {"access_token": "synthetic-access"}, {}, None)), \
                patch.object(smoke, "McpClient") as client_class, \
                patch.object(smoke.sys, "argv", ["mcp-smoke.py", "medplum"]), \
                contextlib.redirect_stdout(output):
            client = client_class.return_value
            client.handshake.return_value = ["fhir-request"]
            client.call_tool.side_effect = [({}, [required_text]), optional]
            code = smoke.main()
        self.assertEqual(client.call_tool.call_args_list[0].args,
                         ("fhir-request", {"method": "GET", "path": "metadata"}))
        return code, output.getvalue()

    def test_capability_statement_passes_despite_optional_tool_error(self):
        code, output = self.run_cli(CAPABILITY)
        self.assertEqual(code, 0)
        self.assertIn("[WARN] tools/call fhir-request GET /fhir/R4/metadata", output)
        self.assertIn("all checks passed", output)

    def test_invalid_required_metadata_fails_with_tool_exit_code(self):
        for text in ("", "not JSON", "{}", "[]", "null", "1", '"text"',
                     '{"resourceType":"OperationOutcome"}'):
            with self.subTest(text=text):
                code, output = self.run_cli(text)
                self.assertEqual(code, 5)
                self.assertIn("[FAIL] tools/call fhir-request GET metadata", output)
                self.assertNotIn("all checks passed", output)

    def test_invalid_optional_metadata_only_warns(self):
        for text in ("", "not JSON", "{}", "[]", "null"):
            with self.subTest(text=text):
                code, output = self.run_cli(CAPABILITY, text)
                self.assertEqual(code, 0)
                self.assertIn("[WARN] tools/call fhir-request GET /fhir/R4/metadata", output)
                self.assertNotIn("[FAIL]", output)


class RefreshTokenTest(unittest.TestCase):
    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.output = io.StringIO()
        stack.enter_context(contextlib.redirect_stdout(self.output))
        meta = {"issuer": "synthetic-issuer", "token_endpoint": "synthetic-token-endpoint",
                "code_challenge_methods_supported": ["S256"]}
        stack.enter_context(patch.object(smoke, "http_request", return_value=(
            200, {}, json.dumps(meta).encode())))
        self.get = stack.enter_context(patch.object(
            smoke, "secret_store_get", return_value="synthetic-refresh-old"))
        self.put = stack.enter_context(patch.object(
            smoke, "secret_store_put", return_value="test secure store"))
        self.request = stack.enter_context(patch.object(smoke, "token_request", return_value={
            "access_token": "synthetic-access", "refresh_token": "synthetic-refresh-new"}))
        self.authorize = stack.enter_context(patch.object(smoke, "authorize_interactive", return_value={
            "access_token": "synthetic-access", "refresh_token": "synthetic-browser-refresh"}))
        self.args = SimpleNamespace(no_store=False, check_refresh=False)

    def test_next_run_uses_rotated_refresh_token_without_browser(self):
        stored = {"value": "synthetic-refresh-old"}
        self.get.side_effect = lambda: stored["value"]
        self.put.side_effect = lambda value: stored.update(value=value) or "test secure store"
        self.request.side_effect = [
            {"access_token": "synthetic-access", "refresh_token": "synthetic-refresh-new"},
            {"access_token": "synthetic-access", "refresh_token": "synthetic-refresh-newest"},
        ]
        for expected in ("synthetic-refresh-new", "synthetic-refresh-newest"):
            tokens, _, error = smoke.medplum_token(self.args)
            self.assertIsNone(error)
            self.assertEqual(tokens["refresh_token"], expected)
            self.assertEqual(stored["value"], expected)
        used = [call.args[1]["refresh_token"] for call in self.request.call_args_list]
        self.assertEqual(used, ["synthetic-refresh-old", "synthetic-refresh-new"])
        self.authorize.assert_not_called()
        self.assertNotIn("synthetic-refresh", self.output.getvalue())

    def test_refresh_without_replacement_preserves_stored_token(self):
        self.request.return_value = {"access_token": "synthetic-access"}
        tokens, _, error = smoke.medplum_token(self.args)
        self.assertEqual(tokens["access_token"], "synthetic-access")
        self.assertIsNone(error)
        self.put.assert_not_called()
        self.authorize.assert_not_called()

    def test_storage_failure_warns_without_restarting_login(self):
        self.put.return_value = None
        _, _, error = smoke.medplum_token(self.args)
        self.assertIsNone(error)
        self.assertIn("[WARN] refresh token storage", self.output.getvalue())
        self.authorize.assert_not_called()

    def test_no_store_uses_browser_and_never_reads_or_saves_tokens(self):
        self.args.no_store = True
        self.args.check_refresh = True
        tokens, _, error = smoke.medplum_token(self.args)
        self.assertIsNone(error)
        self.assertEqual(tokens["refresh_token"], "synthetic-refresh-new")
        self.get.assert_not_called()
        self.put.assert_not_called()
        self.authorize.assert_called_once()


if __name__ == "__main__":
    unittest.main()
