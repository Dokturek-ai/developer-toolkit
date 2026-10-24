#!/usr/bin/env python3
"""Read-only smoke test pro medplum-mcp.

Bez přepínačů ověří části, které nevyžadují přihlášení: healthcheck Medplumu,
že MCP endpoint bez tokenu vrací 401, OAuth discovery a registraci klientů
(POST /oauth2/register v Medplum 5.2.1 nic nevytváří, jen vrátí klienta
podle redirect URI).

S --e2e projde celou cestu přes stdio most mcp-remote se stejnými parametry
jako Claude Desktop: OAuth přihlášení v prohlížeči, initialize, tools/list
a jeden dotaz GET CodeSystem?_summary=count. Skript neposílá zápisové požadavky.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://medplum.test.dokturek.ai"
MCP_URL = BASE_URL + "/mcp/stream"
TEMPLATE = Path(__file__).resolve().parent.parent / "clients" / "claude-desktop.json"
EXPECTED_CLIENTS = {
    "http://localhost:1458/callback": "dokturek-claude-code-dev",
    "https://claude.ai/api/mcp/auth_callback": "dokturek-claude-desktop-dev",
    "http://127.0.0.1:1457/callback/uAEkM6bonMJI": "dokturek-codex-dev",
}
INITIALIZE = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "medplum-mcp-smoke-test", "version": "1"}},
}


class Report:
    def __init__(self):
        self.failures = 0

    def check(self, name, ok, detail=""):
        print("{} {}{}".format("OK  " if ok else "FAIL", name, " — " + detail if detail else ""))
        if not ok:
            self.failures += 1


def http(url, method="GET", body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    })
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def as_json(text):
    try:
        return json.loads(text)
    except ValueError:
        return {}


def basic_checks(report):
    status, text = http(BASE_URL + "/healthcheck")
    health = as_json(text)
    report.check("healthcheck", status == 200 and health.get("ok") is True,
                 "Medplum {}".format(health.get("version", "?")))

    status, _ = http(MCP_URL, method="POST", body=INITIALIZE)
    report.check("MCP endpoint bez tokenu vrací 401", status == 401, "HTTP {}".format(status))

    status, text = http(BASE_URL + "/.well-known/oauth-protected-resource")
    report.check("protected resource metadata", status == 200 and bool(as_json(text).get("authorization_servers")),
                 "HTTP {}".format(status))

    status, text = http(BASE_URL + "/.well-known/oauth-authorization-server")
    methods = as_json(text).get("code_challenge_methods_supported", [])
    report.check("authorization server metadata (PKCE S256)", status == 200 and "S256" in methods,
                 "HTTP {}".format(status))

    for redirect_uri, client_id in sorted(EXPECTED_CLIENTS.items()):
        status, text = http(BASE_URL + "/oauth2/register", method="POST", body={"redirect_uris": [redirect_uri]})
        got = as_json(text).get("client_id")
        report.check("klient pro {}".format(redirect_uri), status == 201 and got == client_id,
                     "HTTP {}, client_id {}".format(status, got))


def e2e_checks(report):
    npx = shutil.which("npx")
    if not npx:
        report.check("npx", False, "nenalezen, nainstaluj Node.js")
        return
    server = json.loads(TEMPLATE.read_text(encoding="utf-8"))["mcpServers"]["dokturek-medplum-dev"]
    command = [npx] + server["args"] + ["--auth-timeout", "300"]
    log = tempfile.NamedTemporaryFile(prefix="medplum-mcp-bridge-", suffix=".log", delete=False)
    print("Most mcp-remote: log v {}. Pokud se otevře prohlížeč, přihlas se do Medplumu.".format(log.name))
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                               universal_newlines=True, bufsize=1)

    def send(message):
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    def receive(message_id):
        for line in process.stdout:
            message = as_json(line)
            if message.get("id") == message_id:
                return message
        return {"error": "most skončil, detail v {}".format(log.name)}

    try:
        send(INITIALIZE)
        reply = receive(1)
        info = reply.get("result", {}).get("serverInfo", {})
        report.check("initialize", info.get("name") == "medplum",
                     "{} {}".format(info.get("name"), info.get("version")) if info else str(reply.get("error")))
        if "result" not in reply:
            return
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = [tool.get("name") for tool in receive(2).get("result", {}).get("tools", [])]
        report.check("tools/list obsahuje fhir-request", "fhir-request" in tools, ", ".join(tools))
        send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "fhir-request", "arguments": {"method": "GET", "path": "CodeSystem?_summary=count"}}})
        content = receive(3).get("result", {}).get("content") or [{}]
        bundle = as_json(content[0].get("text", ""))
        report.check("GET CodeSystem?_summary=count",
                     bundle.get("resourceType") == "Bundle" and isinstance(bundle.get("total"), int),
                     "total = {}".format(bundle.get("total")))
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--e2e", action="store_true", help="projít i celou cestu přes most s přihlášením")
    args = parser.parse_args()
    report = Report()
    basic_checks(report)
    if args.e2e:
        e2e_checks(report)
    print("\nVýsledek: {}".format("vše prošlo" if report.failures == 0 else "{} kontrol selhalo".format(report.failures)))
    return 0 if report.failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
