#!/usr/bin/env python3
"""Read-only smoke test for the Coolify and Medplum remote MCP servers.

Runs: initialize -> notifications/initialized -> tools/list -> read-only tools/call.
Classifies every failure as AUTH, TRANSPORT, PROTOCOL or TOOL. Never prints tokens.

Usage (stdlib only, Python 3.9+):
  python3 mcp-smoke.py coolify            # token from $COOLIFY_API_TOKEN or ~/.codex/config.toml
  python3 mcp-smoke.py medplum            # OAuth Authorization Code + PKCE S256 in the browser
  python3 mcp-smoke.py medplum --no-store # do not save the refresh token

Exit codes: 0 ok, 2 AUTH, 3 TRANSPORT, 4 PROTOCOL, 5 TOOL, 1 usage/other.
"""

import argparse
import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

COOLIFY_URL = "https://coolify.infra.dokturek.ai/mcp"
MEDPLUM_URL = "https://medplum.test.dokturek.ai/mcp/stream"
MEDPLUM_DISCOVERY = "https://medplum.test.dokturek.ai/.well-known/oauth-authorization-server"
# Registered in dokturek-medplum integrations/openai/oauth-clients.dev.json.
MEDPLUM_CLIENT_ID = "dokturek-claude-code-dev"
# Both loopback forms are registered; the IP literal avoids localhost -> ::1 surprises (RFC 8252 §7.3).
MEDPLUM_REDIRECT_URI = "http://127.0.0.1:1458/callback"
MEDPLUM_SCOPE = "openid profile offline_access"
KEYCHAIN_SERVICE = "dokturek-medplum-dev-mcp"
PROTOCOL_VERSION = "2025-06-18"
TIMEOUT = 30

EXIT = {"AUTH": 2, "TRANSPORT": 3, "PROTOCOL": 4, "TOOL": 5}


class SmokeError(Exception):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def log(status, step, detail=""):
    print("[%s] %s%s" % (status, step, (" - " + detail) if detail else ""), flush=True)


def ssl_context():
    ctx = ssl.create_default_context()
    bundle = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if bundle and os.path.exists(bundle):
        ctx.load_verify_locations(bundle)
    return ctx


def http_request(url, data=None, headers=None, method=None, sse_id=None):
    """Returns (status, headers, body). Raises SmokeError(TRANSPORT) only for network-level failures.

    With sse_id, an event-stream body is read only up to the event answering that JSON-RPC id:
    a server may keep the stream open after the response.
    """
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ssl_context()) as resp:
            if sse_id is not None and "text/event-stream" in resp.headers.get("Content-Type", ""):
                return resp.status, resp.headers, read_sse_until(resp, sse_id)
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()
    except (urllib.error.URLError, socket.timeout, ssl.SSLError, ConnectionError) as e:
        raise SmokeError("TRANSPORT", "%s: %s" % (url, getattr(e, "reason", e)))


def read_sse_until(resp, msg_id):
    lines, data = [], []
    for raw in iter(resp.readline, b""):
        lines.append(raw)
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
        elif line == "" and data:
            try:
                event = json.loads("\n".join(data))
            except ValueError:
                event = None
            data = []
            if isinstance(event, dict) and event.get("id") == msg_id:
                break
    return b"".join(lines)


# ---------------------------------------------------------------- MCP client


class McpClient:
    def __init__(self, url, token):
        self.url = url
        self.token = token
        self.session_id = None
        self.protocol_version = None
        self.next_id = 1

    def _headers(self):
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer " + self.token,
        }
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        if self.protocol_version:
            h["MCP-Protocol-Version"] = self.protocol_version
        return h

    def _post(self, message):
        status, headers, body = http_request(self.url, json.dumps(message).encode(), self._headers(), "POST",
                                             message.get("id"))
        if status in (401, 403):
            www = headers.get("WWW-Authenticate", "")
            raise SmokeError("AUTH", "HTTP %d %s %s" % (status, www, body[:200].decode("utf-8", "replace")))
        sid = headers.get("Mcp-Session-Id")
        if sid:
            self.session_id = sid
        return status, headers, body

    def notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        status, _, body = self._post(msg)
        if status not in (200, 202, 204):
            raise SmokeError("TRANSPORT", "%s: HTTP %d %s" % (method, status, body[:200].decode("utf-8", "replace")))
        return status

    def request(self, method, params=None):
        msg_id = self.next_id
        self.next_id += 1
        msg = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}
        status, headers, body = self._post(msg)
        text = body.decode("utf-8", "replace")
        if status != 200:
            raise SmokeError("TRANSPORT", "%s: HTTP %d %s" % (method, status, text[:300]))
        ctype = headers.get("Content-Type", "")
        response = None
        try:
            if "text/event-stream" in ctype:
                for event in parse_sse(text):
                    if isinstance(event, dict) and event.get("id") == msg_id:
                        response = event
            else:
                response = json.loads(text)
        except ValueError:
            raise SmokeError("TRANSPORT", "%s: body is not JSON-RPC (%s): %s" % (method, ctype, text[:200]))
        if not isinstance(response, dict) or response.get("jsonrpc") != "2.0":
            raise SmokeError("TRANSPORT", "%s: no JSON-RPC response for id %d (%s)" % (method, msg_id, ctype))
        if "error" in response:
            err = response["error"]
            raise SmokeError("PROTOCOL", "%s: JSON-RPC %s %s" % (method, err.get("code"), err.get("message")))
        return response.get("result")

    def handshake(self):
        result = self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "dokturek-mcp-smoke", "version": "1"},
        })
        self.protocol_version = result.get("protocolVersion")
        info = result.get("serverInfo", {})
        log("OK", "initialize", "%s %s, protocol %s, session %s" % (
            info.get("name"), info.get("version"), self.protocol_version,
            "stateful" if self.session_id else "stateless"))
        status = self.notify("notifications/initialized")
        log("OK", "notifications/initialized", "HTTP %d" % status)
        tools = self.request("tools/list").get("tools", [])
        names = sorted(t.get("name") for t in tools)
        log("OK", "tools/list", "%d tools" % len(names))
        return names

    def call_tool(self, name, arguments):
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        texts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
        if result.get("isError"):
            raise SmokeError("TOOL", "%s: %s" % (name, " ".join(texts)[:400]))
        return result, texts


def parse_sse(text):
    data = []
    for line in text.splitlines() + [""]:
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
        elif line == "" and data:
            yield json.loads("\n".join(data))
            data = []


# ---------------------------------------------------------------- Coolify


def coolify_token(codex_config):
    token = os.environ.get("COOLIFY_API_TOKEN")
    if token:
        return token, "$COOLIFY_API_TOKEN"
    if os.path.exists(codex_config):
        with open(codex_config, encoding="utf-8") as f:
            section = None
            for raw in f:
                line = raw.strip()
                m = re.match(r"^\[([^\]]+)\]$", line)
                if m:
                    section = m.group(1).strip()
                    continue
                if section == "mcp_servers.coolify-selfhosted.http_headers":
                    m = re.match(r'^"?Authorization"?\s*=\s*"Bearer\s+([^"]+)"', line)
                    if m:
                        return m.group(1), codex_config
    raise SmokeError("AUTH", "no Coolify token: set COOLIFY_API_TOKEN or provide %s" % codex_config)


def run_coolify(args):
    token, source = coolify_token(os.path.expanduser(args.codex_config))
    log("OK", "token", "loaded from %s (not printed)" % source)
    client = McpClient(COOLIFY_URL, token)
    names = client.handshake()
    failures = []
    for tool in ("get_current_team", "get_infrastructure_overview"):
        if tool not in names:
            failures.append(SmokeError("TOOL", "%s missing in tools/list" % tool))
            log("FAIL", tool, "missing in tools/list")
            continue
        try:
            _, texts = client.call_tool(tool, {})
            log("OK", "tools/call " + tool, summarize(texts))
        except SmokeError as e:
            failures.append(e)
            log("FAIL", "tools/call " + tool, "%s: %s" % (e.kind, e))
    return failures


def summarize(texts):
    joined = " ".join(texts)
    try:
        data = json.loads(joined)
    except ValueError:
        return "%d chars of text" % len(joined)
    if isinstance(data, dict):
        return "JSON keys: " + ", ".join(sorted(data.keys())[:12])
    if isinstance(data, list):
        return "JSON list of %d items" % len(data)
    return type(data).__name__


# ---------------------------------------------------------------- Medplum OAuth


def secret_store_get():
    if sys.platform == "darwin" and shutil.which("security"):
        p = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
                            "-a", MEDPLUM_CLIENT_ID, "-w"], capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else None
    if shutil.which("secret-tool"):
        p = subprocess.run(["secret-tool", "lookup", "service", KEYCHAIN_SERVICE,
                            "account", MEDPLUM_CLIENT_ID], capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else None
    return None


def secret_store_put(value):
    """Stores the refresh token in macOS Keychain or libsecret; the value never goes on argv."""
    # The token comes from the server: allow only token characters, so it can never carry a
    # newline or quote into the `security -i` command parser (each input line is a command).
    if not re.fullmatch(r"[A-Za-z0-9._~+/=-]{1,8192}", value):
        log("WARN", "refresh token storage", "unexpected characters in refresh token, not saved")
        return None
    if sys.platform == "darwin" and shutil.which("security"):
        # `security -i` reads commands from stdin, keeping the secret out of the process list.
        cmd = 'add-generic-password -U -s "%s" -a "%s" -w "%s"\n' % (KEYCHAIN_SERVICE, MEDPLUM_CLIENT_ID, value)
        p = subprocess.run(["security", "-i"], input=cmd, capture_output=True, text=True)
        return "macOS Keychain" if p.returncode == 0 else None
    if shutil.which("secret-tool"):
        p = subprocess.run(["secret-tool", "store", "--label", KEYCHAIN_SERVICE, "service", KEYCHAIN_SERVICE,
                            "account", MEDPLUM_CLIENT_ID], input=value, capture_output=True, text=True)
        return "libsecret" if p.returncode == 0 else None
    return None


def token_request(token_endpoint, form):
    status, _, body = http_request(token_endpoint, urllib.parse.urlencode(form).encode(),
                                   {"Content-Type": "application/x-www-form-urlencoded"}, "POST")
    try:
        data = json.loads(body)
    except ValueError:
        raise SmokeError("TRANSPORT", "token endpoint HTTP %d, non-JSON body" % status)
    if status != 200 or "access_token" not in data:
        raise SmokeError("AUTH", "token endpoint HTTP %d: %s %s" % (
            status, data.get("error"), data.get("error_description")))
    return data


def authorize_interactive(meta):
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    redirect = urllib.parse.urlparse(MEDPLUM_REDIRECT_URI)
    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            if url.path != redirect.path:
                self.send_response(404)
                self.end_headers()
                return
            result.update({k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Medplum sign-in received, you can close this tab.".encode())
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        def log_message(self, *a):
            pass

    try:
        server = http.server.HTTPServer((redirect.hostname, redirect.port), Handler)
    except OSError as e:
        raise SmokeError("TRANSPORT", "cannot listen on %s (is Claude Code /mcp login running?): %s"
                         % (MEDPLUM_REDIRECT_URI, e))
    query = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": MEDPLUM_CLIENT_ID,
        "redirect_uri": MEDPLUM_REDIRECT_URI,
        "scope": MEDPLUM_SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    url = meta["authorization_endpoint"] + "?" + query
    log("..", "authorize", "opening browser; if it does not open, visit:\n    " + url)
    webbrowser.open(url)
    server.serve_forever()
    server.server_close()

    if result.get("state") != state:
        raise SmokeError("AUTH", "state mismatch in OAuth callback")
    if "error" in result:
        raise SmokeError("AUTH", "authorize: %s %s" % (result.get("error"), result.get("error_description", "")))
    if result.get("iss") and result["iss"] != meta["issuer"]:
        raise SmokeError("AUTH", "issuer mismatch in OAuth callback")
    return token_request(meta["token_endpoint"], {
        "grant_type": "authorization_code",
        "code": result["code"],
        "redirect_uri": MEDPLUM_REDIRECT_URI,
        "client_id": MEDPLUM_CLIENT_ID,
        "code_verifier": verifier,
    })


def medplum_token(args):
    status, _, body = http_request(MEDPLUM_DISCOVERY)
    if status != 200:
        raise SmokeError("TRANSPORT", "OAuth discovery HTTP %d" % status)
    meta = json.loads(body)
    if "S256" not in meta.get("code_challenge_methods_supported", []):
        raise SmokeError("AUTH", "authorization server does not advertise PKCE S256")
    log("OK", "OAuth discovery", meta["issuer"])

    stored = None if args.no_store else secret_store_get()
    if stored:
        try:
            tokens = token_request(meta["token_endpoint"], {
                "grant_type": "refresh_token", "refresh_token": stored, "client_id": MEDPLUM_CLIENT_ID})
            log("OK", "refresh_token grant", "stored refresh token accepted")
            return tokens, meta, None
        except SmokeError as e:
            # Medplum 5.2.1-5.2.8 rejects refresh for defaultOAuthClients with "Invalid client".
            log("WARN", "refresh_token grant", "%s: %s; falling back to browser sign-in" % (e.kind, e))
    tokens = authorize_interactive(meta)
    log("OK", "authorization_code + PKCE S256", "scope: %s, expires_in: %s, refresh token: %s" % (
        tokens.get("scope"), tokens.get("expires_in"), "yes" if tokens.get("refresh_token") else "no"))
    if tokens.get("refresh_token") and not args.no_store:
        where = secret_store_put(tokens["refresh_token"])
        log("OK" if where else "WARN", "refresh token storage", where or "no secure store available, not saved")
    refresh_error = None
    if args.check_refresh and not tokens.get("refresh_token"):
        refresh_error = SmokeError("AUTH", "--check-refresh: no refresh token issued")
        log("FAIL", "refresh_token grant", str(refresh_error))
    elif args.check_refresh:
        try:
            refreshed = token_request(meta["token_endpoint"], {
                "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
                "client_id": MEDPLUM_CLIENT_ID})
            log("OK", "refresh_token grant", "works")
            if refreshed.get("refresh_token") and not args.no_store:
                secret_store_put(refreshed["refresh_token"])
            tokens = refreshed
        except SmokeError as e:
            refresh_error = e
            log("FAIL", "refresh_token grant", "%s: %s" % (e.kind, e))
    return tokens, meta, refresh_error


def run_medplum(args):
    tokens, _, refresh_error = medplum_token(args)
    client = McpClient(MEDPLUM_URL, tokens["access_token"])
    names = client.handshake()
    log("OK", "tools", ", ".join(names))
    failures = [refresh_error] if refresh_error else []
    # The tool resolves `path` against <base>/fhir/R4/ after stripping a leading slash,
    # so "/fhir/R4/metadata" becomes /fhir/R4/fhir/R4/metadata. Only "metadata" must pass;
    # the absolute form is reported for diagnosis. Both are read-only.
    for path, required in (("metadata", True), ("/fhir/R4/metadata", False)):
        step = "tools/call fhir-request GET %s" % path
        try:
            _, texts = client.call_tool("fhir-request", {"method": "GET", "path": path})
            data = json.loads(" ".join(texts))
            log("OK", step, "%s fhirVersion=%s software=%s" % (
                data.get("resourceType"), data.get("fhirVersion"), (data.get("software") or {}).get("version")))
        except SmokeError as e:
            if required:
                failures.append(e)
            log("FAIL" if required else "WARN", step, "%s: %s" % (e.kind, e))
        except ValueError:
            log("WARN", step, "tool returned non-JSON text")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", choices=["coolify", "medplum"])
    parser.add_argument("--codex-config", default="~/.codex/config.toml")
    parser.add_argument("--no-store", action="store_true", help="do not read or save the refresh token")
    parser.add_argument("--check-refresh", action="store_true", help="exercise the refresh_token grant once")
    args = parser.parse_args()
    try:
        failures = run_coolify(args) if args.target == "coolify" else run_medplum(args)
    except SmokeError as e:
        log("FAIL", e.kind, str(e))
        return EXIT[e.kind]
    except KeyboardInterrupt:
        return 1
    if failures:
        return EXIT[failures[0].kind]
    log("OK", "done", "all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
