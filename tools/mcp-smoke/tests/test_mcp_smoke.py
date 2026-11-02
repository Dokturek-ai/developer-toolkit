"""Regression tests with synthetic tokens; no network, browser or system keychain."""
import contextlib
import importlib.util
import io
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, mock_open, patch


SPEC = importlib.util.spec_from_file_location(
    "mcp_smoke", Path(__file__).resolve().parent.parent / "mcp-smoke.py")
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)

CAPABILITY = json.dumps({"resourceType": "CapabilityStatement", "fhirVersion": "4.0.1"})
DISCOVERY = {"issuer": "synthetic-issuer", "token_endpoint": "synthetic-token-endpoint",
             "authorization_endpoint": "synthetic-authorization-endpoint",
             "code_challenge_methods_supported": ["S256"]}


class DiscoveryTest(unittest.TestCase):
    def check_failure(self, body, code):
        output = io.StringIO()
        with patch.object(smoke, "http_request", return_value=(200, {}, body)), \
                patch.object(smoke, "secret_store_get", return_value=None) as get, \
                patch.object(smoke, "authorize_interactive", return_value={"access_token": "synthetic-access"}) as authorize, \
                patch.object(smoke.sys, "argv", ["mcp-smoke.py", "medplum"]), \
                contextlib.redirect_stdout(output):
            self.assertEqual(smoke.main(), code)
        get.assert_not_called()
        authorize.assert_not_called()
        self.assertIn("[FAIL] " + ("TRANSPORT" if code == 3 else "AUTH"), output.getvalue())
        self.assertNotIn("all checks passed", output.getvalue())

    def test_non_json_discovery_is_transport_failure(self):
        self.check_failure(b"<html>login page</html>", 3)

    def test_invalid_discovery_shape_is_transport_failure(self):
        for value in ([], None, {}, "text"):
            with self.subTest(value=value):
                self.check_failure(json.dumps(value).encode(), 3)
        for field in ("issuer", "token_endpoint", "authorization_endpoint"):
            for value in (None, "", " ", 1, []):
                with self.subTest(field=field, value=value):
                    self.check_failure(json.dumps(dict(DISCOVERY, **{field: value})).encode(), 3)
        for value in (None, "S256", {"S256": True}, [1]):
            with self.subTest(methods=value):
                self.check_failure(json.dumps(dict(
                    DISCOVERY, code_challenge_methods_supported=value)).encode(), 3)

    def test_missing_s256_remains_auth_failure(self):
        meta = dict(DISCOVERY, code_challenge_methods_supported=["plain"])
        self.check_failure(json.dumps(meta).encode(), 2)


class McpResponseTest(unittest.TestCase):
    def run_responses(self, payloads, sse=False):
        responses = []
        for msg_id, payload in enumerate(payloads, 1):
            text = json.dumps(dict(payload, jsonrpc="2.0", id=msg_id))
            content_type = "text/event-stream" if sse else "application/json"
            if sse:
                text = "data: " + text + "\n\n"
            responses.append((200, {"Content-Type": content_type}, text.encode()))
            if msg_id == 1:
                responses.append((202, {}, b""))  # notifications/initialized
        output = io.StringIO()
        with patch.object(smoke, "coolify_token", return_value=("synthetic-token", "test")), \
                patch.object(smoke, "http_request", side_effect=responses), \
                patch.object(smoke.sys, "argv", ["mcp-smoke.py", "coolify"]), \
                contextlib.redirect_stdout(output):
            code = smoke.main()
        return code, output.getvalue()

    def valid_handshake(self):
        return [{"result": {"protocolVersion": smoke.PROTOCOL_VERSION, "capabilities": {},
                            "serverInfo": {"name": "synthetic", "version": "1"}}},
                {"result": {"tools": [{"name": name, "inputSchema": {"type": "object"}}
                                      for name in ("get_current_team", "get_infrastructure_overview")]}}]

    def test_invalid_rpc_envelopes_fail_cli_as_transport(self):
        payloads = [{}, {"error": None}, {"error": []}, {"error": {}},
                    {"error": {"code": True, "message": "synthetic"}},
                    {"error": {"code": -32603, "message": None}},
                    {"result": {}, "error": {"code": -32603, "message": "synthetic"}}]
        payloads += [{"result": value} for value in (None, [], "text", 1, True)]
        for sse in (False, True):
            for payload in payloads:
                with self.subTest(sse=sse, payload=payload):
                    code, output = self.run_responses([payload], sse)
                    self.assertEqual(code, 3)
                    self.assertIn("[FAIL] TRANSPORT", output)
                    self.assertNotIn("all checks passed", output)

    def test_invalid_handshake_results_fail_as_transport(self):
        for result in ({}, {"protocolVersion": None},
                       dict(self.valid_handshake()[0]["result"], serverInfo=None),
                       dict(self.valid_handshake()[0]["result"], serverInfo={"name": "synthetic"}),
                       dict(self.valid_handshake()[0]["result"], capabilities=[])):
            with self.subTest(result=result):
                self.assertEqual(self.run_responses([{"result": result}])[0], 3)
        for tools in (None, {}, [None], [{}], [{"name": 1}],
                      [{"name": "synthetic", "inputSchema": None}]):
            with self.subTest(tools=tools):
                self.assertEqual(self.run_responses(
                    self.valid_handshake()[:1] + [{"result": {"tools": tools}}])[0], 3)
        self.assertEqual(self.run_responses(self.valid_handshake()[:1] + [{"result": {}}])[0], 3)

    def test_invalid_tool_results_cannot_pass_coolify_checks(self):
        results = [{}, {"content": None}, {"content": {}}, {"content": [None]},
                   {"content": [{}]}, {"content": [{"type": "text"}]},
                   {"content": [{"type": "text", "text": 1}]},
                   {"content": [], "isError": "false"}]
        for sse in (False, True):
            for result in results:
                with self.subTest(sse=sse, result=result):
                    code, output = self.run_responses(
                        self.valid_handshake() + [{"result": result}] * 2, sse)
                    self.assertEqual(code, 3)
                    self.assertIn("TRANSPORT", output)
                    self.assertNotIn("[OK] tools/call", output)
                    self.assertNotIn("all checks passed", output)

    def test_valid_success_and_errors_keep_exit_codes(self):
        for sse in (False, True):
            for content in ([], [{"type": "text", "text": "synthetic"}],
                            [{"type": "image", "data": "", "mimeType": "image/png"}]):
                with self.subTest(sse=sse, content=content):
                    self.assertEqual(self.run_responses(self.valid_handshake() + [
                        {"result": {"content": content}}] * 2, sse)[0], 0)
            self.assertEqual(self.run_responses([
                {"error": {"code": -32603, "message": "synthetic"}}], sse)[0], 4)
            self.assertEqual(self.run_responses(self.valid_handshake() + [
                {"result": {"content": [{"type": "text", "text": "synthetic failure"}],
                            "isError": True}}] * 2, sse)[0], 5)

    def test_wrong_or_missing_id_cannot_pass_cli_checks(self):
        for response_id in (999, "1", None, True):
            for payload in ({"result": {}}, {"error": {"code": -32603, "message": "synthetic"}}):
                with self.subTest(response_id=response_id, payload=payload):
                    response = dict(payload, jsonrpc="2.0")
                    if response_id is not None:
                        response["id"] = response_id
                    output = io.StringIO()
                    with patch.object(smoke, "coolify_token", return_value=("synthetic-token", "test")), \
                            patch.object(smoke, "http_request", return_value=(
                                200, {"Content-Type": "application/json"}, json.dumps(response).encode())), \
                            patch.object(smoke.sys, "argv", ["mcp-smoke.py", "coolify"]), \
                            contextlib.redirect_stdout(output):
                        self.assertEqual(smoke.main(), 3)
                    self.assertIn("[FAIL] TRANSPORT", output.getvalue())
                    self.assertNotIn("all checks passed", output.getvalue())

    def test_matching_id_is_accepted_for_json_and_sse(self):
        result = {"tools": []}
        response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": result})
        for content_type, text in (("application/json", response),
                                   ("text/event-stream", "data: " + response + "\n\n")):
            with self.subTest(content_type=content_type), patch.object(
                    smoke, "http_request", return_value=(200, {"Content-Type": content_type}, text.encode())):
                client = smoke.McpClient("synthetic-url", "synthetic-token")
                self.assertEqual(client.request("tools/list"), result)

    def test_boolean_id_is_rejected_in_sse(self):
        response = json.dumps({"jsonrpc": "2.0", "id": True, "result": {"tools": []}})
        with patch.object(smoke, "http_request", return_value=(
                200, {"Content-Type": "text/event-stream"}, ("data: " + response + "\n\n").encode())):
            client = smoke.McpClient("synthetic-url", "synthetic-token")
            with self.assertRaises(smoke.SmokeError) as error:
                client.request("tools/list")
        self.assertEqual(error.exception.kind, "TRANSPORT")

    def test_sse_boolean_id_does_not_replace_matching_response(self):
        result = {"tools": []}
        valid = 'data: ' + json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}) + "\n\n"
        invalid = 'data: ' + json.dumps({"jsonrpc": "2.0", "id": True, "result": "wrong"}) + "\n\n"
        for text in (invalid + valid, valid + invalid):
            with self.subTest(text=text), patch.object(smoke, "http_request", return_value=(
                    200, {"Content-Type": "text/event-stream"}, text.encode())):
                client = smoke.McpClient("synthetic-url", "synthetic-token")
                self.assertEqual(client.request("tools/list"), result)

    def test_sse_reader_waits_past_boolean_id_and_stops_at_matching_id(self):
        invalid = b'data: {"jsonrpc":"2.0","id":true,"result":"wrong"}\n\n'
        valid = b'data: {"jsonrpc":"2.0","id":1,"result":{}}\n\n'
        trailing = b'data: {"jsonrpc":"2.0","id":2,"result":{}}\n\n'
        stream = io.BytesIO(invalid + valid + trailing)
        self.assertEqual(smoke.read_sse_until(stream, 1), invalid + valid)
        self.assertEqual(stream.read(), trailing)


class CoolifyTokenTest(unittest.TestCase):
    def test_both_toml_string_quotes_load_token(self):
        for quote in ('"', "'"):
            with self.subTest(quote=quote):
                config = ('[mcp_servers.coolify-selfhosted.http_headers]\n'
                          'Authorization = {0}Bearer synthetic-coolify{0}\n').format(quote)
                with patch.dict(smoke.os.environ, {}, clear=True), \
                        patch.object(smoke.os.path, "exists", return_value=True), \
                        patch("builtins.open", mock_open(read_data=config)):
                    self.assertEqual(smoke.coolify_token("synthetic-config.toml"),
                                     ("synthetic-coolify", "synthetic-config.toml"))


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
        stack.enter_context(patch.object(smoke, "http_request", return_value=(
            200, {}, json.dumps(DISCOVERY).encode())))
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

    def test_check_refresh_warns_when_second_token_save_fails(self):
        self.get.return_value = None
        self.args.check_refresh = True
        self.put.side_effect = ["test secure store", None]
        tokens, _, error = smoke.medplum_token(self.args)
        self.assertIsNone(error)
        self.assertEqual(tokens["refresh_token"], "synthetic-refresh-new")
        self.assertEqual(self.put.call_args_list, [
            call("synthetic-browser-refresh"), call("synthetic-refresh-new")])
        self.authorize.assert_called_once()
        self.assertIn("[OK] refresh token storage", self.output.getvalue())
        self.assertIn("[WARN] refresh token storage", self.output.getvalue())
        self.assertNotIn("synthetic-browser-refresh", self.output.getvalue())
        self.assertNotIn("synthetic-refresh-new", self.output.getvalue())

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
