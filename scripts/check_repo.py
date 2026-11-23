#!/usr/bin/env python3
"""Kontroly repa developer-toolkit. Spouští se lokálně i v CI.

Kontroluje:
- validitu všech JSON souborů,
- marketplace: unikátní názvy, existující zdroje, shodu názvu a verze s plugin.json,
- strukturu nástrojů: README.md, RISK.md s povinnými sekcemi, záznam v marketplace a v README,
- URL a hostitele v celém repu (viz check_hosts_and_versions):
  - každý hostitel *.dokturek.ai musí přesně odpovídat allowlistu, podvržené tvary
    jako medplum.test.dokturek.ai.evil.example kontrola odmítne,
  - http:// jen pro loopback callback (127.0.0.1, localhost), jinak https,
  - URL s userinfo (uzivatel@hostitel) nejsou povolené,
  - v konfiguraci a kódu (*.json, *.toml, *.py, *.sh, *.mjs, *.yml, *.yaml, *.example)
    jen hostitelé z allowlistu, loopback a hostitelé s odůvodněním v CODE_EXTERNAL_HOSTS;
    dokumentace (*.md, *.txt) smí odkazovat i na jiné weby přes https,
  - testy (adresáře tests/) obsahují záměrně nepřátelské URL, proto pro ně platí jen
    kontrola hostitelů *.dokturek.ai,
- připnuté verze balíčků spouštěných přes npx (žádné @latest, žádná verze bez čísla),
- vzory secrets a osobních vazeb na účty.

Kontroly zachytí nejčastější chyby, nejsou úplnou ochranou.
"""
import json
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELF = Path(__file__).resolve()
TOOLS = ROOT / "tools"
TEMPLATE_DIR = "_template"

# Hostitelé *.dokturek.ai povolení v nástrojích. Přidání hostitele je bezpečnostní
# změna: samostatný commit, zdůvodnění v PR, aktualizovaný RISK.md (viz CONTRIBUTING.md).
ALLOWED_DOKTUREK_HOSTS = {
    "coolify.infra.dokturek.ai",
    "medplum.test.dokturek.ai",
    "app.test.dokturek.ai",
}

# Loopback hostitelé pro OAuth callbacky (RFC 8252); jen pro ně je povolené http://.
LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}

# Externí hostitelé povolení v konfiguraci a kódu. Každý má důvod; přidání je bezpečnostní
# změna stejně jako u ALLOWED_DOKTUREK_HOSTS. Dokumentace tímto seznamem omezená není.
CODE_EXTERNAL_HOSTS = {
    "github.com": "pole repository a owner.url v plugin.json a marketplace.json",
    "json.schemastore.org": "$schema v marketplace.json, nástroje na adresu nevolají",
    "claude.ai": "registrovaná callback URL konektoru claude.ai v smoke_test.py; skript ji jen posílá do DCR",
}

CODE_SUFFIXES = {".json", ".toml", ".py", ".sh", ".mjs", ".yml", ".yaml", ".example"}
DOC_SUFFIXES = {".md", ".txt"}

RISK_SECTIONS = [
    "## Shrnutí",
    "## Přístup k datům",
    "## Co se může pokazit",
    "## Ochrany",
    "## Co ochrany nepokrývají",
    "## Vypnutí a odvolání přístupu",
    "## Vlastník a revize",
]

SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "privátní klíč"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "GitHub token"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "API klíč (sk-…)"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."), "JWT"),
    (re.compile(r"[\"']?client_secret[\"']?\s*[:=]\s*[\"'][^\"']+[\"']"), "client_secret s hodnotou"),
    (re.compile(r"\basdk_app_[0-9a-f]{16,}"), "osobní ID ChatGPT aplikace"),
]

# Celý řetězec ze znaků hostitele kolem "dokturek.ai", aby podvrh nešel zkrátit na povolený prefix.
DOKTUREK_RUN = re.compile(r"[A-Za-z0-9.-]*dokturek\.ai[A-Za-z0-9.-]*", re.IGNORECASE)
URL_PATTERN = re.compile(r"\bhttps?://(?:\[[^\]\s]*\])?[^\s\"'`<>()\[\]{}|^,;]*", re.IGNORECASE)
MCP_REMOTE_PATTERN = re.compile(r"mcp-remote(?![-\w])(@[^\s\"'`,\]\)]*)?")
SEMVER_SUFFIX = re.compile(r"^@\d+\.\d+\.\d+$")
PINNED_PACKAGE = re.compile(r"^(@[a-z0-9-._~]+/)?[a-z0-9-._~]+@\d+\.\d+\.\d+$")
TEXT_SUFFIXES = CODE_SUFFIXES | DOC_SUFFIXES

errors = []


def error(path, message):
    errors.append("{}: {}".format(path.relative_to(ROOT) if isinstance(path, Path) else path, message))


def repo_files():
    for path in sorted(ROOT.rglob("*")):
        if ".git" in path.parts or "__pycache__" in path.parts or not path.is_file():
            continue
        yield path


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        error(path, "neplatný JSON ({})".format(exc))
        return None


def check_json_files():
    for path in repo_files():
        if path.suffix == ".json" or path.name.endswith(".json.example"):
            load_json(path)


def check_marketplace():
    path = ROOT / ".claude-plugin" / "marketplace.json"
    data = load_json(path)
    if not data:
        return {}
    for field in ("name", "owner", "plugins"):
        if field not in data:
            error(path, "chybí pole '{}'".format(field))
    entries = {}
    for entry in data.get("plugins", []):
        name = entry.get("name")
        if name in entries:
            error(path, "duplicitní plugin '{}'".format(name))
        entries[name] = entry
        source = entry.get("source")
        if not isinstance(source, str) or not source.startswith("./tools/"):
            error(path, "plugin '{}': source musí být ./tools/<nástroj>".format(name))
            continue
        plugin_dir = (ROOT / source).resolve()
        plugin_json = plugin_dir / ".claude-plugin" / "plugin.json"
        if not plugin_json.exists():
            error(path, "plugin '{}': chybí {}".format(name, plugin_json.relative_to(ROOT)))
            continue
        manifest = load_json(plugin_json) or {}
        if manifest.get("name") != name:
            error(plugin_json, "name '{}' neodpovídá marketplace '{}'".format(manifest.get("name"), name))
        if manifest.get("version") != entry.get("version"):
            error(plugin_json, "version '{}' neodpovídá marketplace '{}'".format(manifest.get("version"), entry.get("version")))
    return entries


def check_tools(entries):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for tool in sorted(p for p in TOOLS.iterdir() if p.is_dir()):
        required = ["README.md", "RISK.md"]
        for name in required:
            if not (tool / name).exists():
                error(tool, "chybí {}".format(name))
        risk = tool / "RISK.md"
        if risk.exists():
            text = risk.read_text(encoding="utf-8")
            for section in RISK_SECTIONS:
                if section not in text:
                    error(risk, "chybí sekce '{}'".format(section))
        if tool.name == TEMPLATE_DIR:
            continue
        if (tool / ".claude-plugin" / "plugin.json").exists() and tool.name not in entries:
            error(tool, "plugin není v .claude-plugin/marketplace.json")
        if "tools/{}/".format(tool.name) not in readme:
            error(ROOT / "README.md", "chybí odkaz na tools/{}/ v tabulce nástrojů".format(tool.name))


def dokturek_host_problems(text):
    """Hostitelé *.dokturek.ai, kteří nejsou přesně v allowlistu, včetně podvržených tvarů."""
    problems = []
    for match in DOKTUREK_RUN.finditer(text):
        run = match.group(0)
        # Zástupný zápis *.dokturek.ai v textu není konkrétní hostitel.
        if run.startswith(".") and match.start() > 0 and text[match.start() - 1] == "*":
            run = run.lstrip(".")
            if run.lower() == "dokturek.ai":
                continue
        host = run.strip(".").lower()
        if host in ALLOWED_DOKTUREK_HOSTS:
            continue
        if re.search(r"dokturek\.ai[.-]", host) or not re.search(r"(^|\.)dokturek\.ai$", host):
            problems.append("hostitel '{}' jen napodobuje *.dokturek.ai".format(host))
        else:
            problems.append("hostitel '{}' není v allowlistu (scripts/check_repo.py)".format(host))
    return problems


def url_problems(text, kind):
    """Kontrola URL podle druhu souboru: 'code', 'doc' nebo 'test'."""
    problems = []
    if kind == "test":
        return problems
    for match in URL_PATTERN.finditer(text):
        raw = match.group(0).rstrip(".:!?*_")
        if raw.endswith("://"):
            continue  # samotné schéma v textu („http://“), ne odkaz na hostitele
        try:
            url = urllib.parse.urlsplit(raw)
            url.port
        except ValueError:
            problems.append("neplatná URL '{}'".format(raw))
            continue
        scheme = url.scheme.lower()
        host = (url.hostname or "").lower()
        if not host:
            problems.append("URL bez hostitele '{}'".format(raw))
            continue
        if "@" in url.netloc or "\\" in raw:
            problems.append("URL s userinfo nebo zpětným lomítkem '{}'".format(raw))
            continue
        if scheme == "http" and host not in LOOPBACK_HOSTS:
            problems.append("http:// je povolené jen pro loopback callback, nalezeno '{}'".format(raw))
            continue
        if kind == "code" and host not in ALLOWED_DOKTUREK_HOSTS | LOOPBACK_HOSTS | set(CODE_EXTERNAL_HOSTS):
            problems.append("hostitel '{}' není povolený v konfiguraci ani kódu (scripts/check_repo.py)".format(host))
    return problems


def file_kind(path):
    rel_parts = path.relative_to(ROOT).parts
    if "tests" in rel_parts[:-1]:
        return "test"
    if path.suffix in DOC_SUFFIXES:
        return "doc"
    return "code"


def check_hosts_and_versions():
    for path in repo_files():
        if path == SELF or (path.suffix not in TEXT_SUFFIXES and path.name not in ("CODEOWNERS",)):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        problems = dokturek_host_problems(text) + url_problems(text, file_kind(path))
        for message in sorted(set(problems)):
            error(path, message)
        for match in MCP_REMOTE_PATTERN.finditer(text):
            suffix = match.group(1)
            if suffix is not None and not SEMVER_SUFFIX.match(suffix):
                error(path, "mcp-remote musí mít přesnou verzi, nalezeno '{}'".format(match.group(0)))
        if path.suffix != ".md" and "@latest" in text:
            error(path, "obsahuje '@latest'")
        for pattern, label in SECRET_PATTERNS:
            if pattern.search(text):
                error(path, "vypadá to na {}".format(label))


def check_npx_args():
    for path in repo_files():
        if path.suffix != ".json":
            continue
        data = load_json(path)
        if not isinstance(data, dict):
            continue
        for name, server in (data.get("mcpServers") or {}).items():
            command = str(server.get("command", ""))
            if not command.endswith("npx"):
                continue
            packages = [arg for arg in server.get("args", []) if not arg.startswith("-")]
            if not packages or not PINNED_PACKAGE.match(packages[0]):
                error(path, "server '{}': balíček pro npx musí mít přesnou verzi (balicek@1.2.3)".format(name))


def main():
    check_json_files()
    entries = check_marketplace()
    check_tools(entries)
    check_hosts_and_versions()
    check_npx_args()
    if errors:
        print("Kontroly selhaly:")
        for message in errors:
            print("  - " + message)
        return 1
    print("Kontroly prošly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
