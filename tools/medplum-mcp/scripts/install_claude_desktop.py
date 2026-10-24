#!/usr/bin/env python3
"""Přidá nebo odebere medplum-mcp v konfiguraci Claude Desktopu.

Claude Desktop nepřipojí vzdálený MCP server zapsaný přímo
v claude_desktop_config.json, proto se server spouští přes stdio most
mcp-remote (šablona v clients/claude-desktop.json).

Bez --apply skript jen vypíše, co by změnil. S --apply nejdřív zazálohuje
konfiguraci (claude_desktop_config.json.bak-<čas>) a pak ji atomicky přepíše.
Na macOS zápis odmítne, dokud Claude Desktop běží: běžící Desktop si drží
vlastní kopii konfigurace a cizí změnu by později přepsal.
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SERVER = "dokturek-medplum-dev"
TEMPLATE = Path(__file__).resolve().parent.parent / "clients" / "claude-desktop.json"


def default_config_path():
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if system == "Windows":
        return Path(os.environ["APPDATA"]) / "Claude" / "claude_desktop_config.json"
    sys.exit("Claude Desktop běží na macOS a Windows. Na tomhle systému konfiguraci nastav ručně podle README.")


def build_entry():
    entry = json.loads(TEMPLATE.read_text(encoding="utf-8"))["mcpServers"][SERVER]
    npx = shutil.which("npx")
    if not npx:
        sys.exit("npx nenalezen. Nainstaluj Node.js a spusť skript znovu ze stejného terminálu.")
    # Claude Desktop spouští servery s omezeným PATH: absolutní cesta k npx
    # a adresář s node v PATH zajistí, že most najde node i npm.
    entry["command"] = npx
    entry["env"] = {"PATH": os.pathsep.join([os.path.dirname(npx), "/usr/bin", "/bin"])}
    return entry


def desktop_running():
    if platform.system() != "Darwin":
        return False
    try:
        output = subprocess.run(["ps", "-axo", "comm="], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return any(line.strip().endswith("Claude.app/Contents/MacOS/Claude") for line in output.splitlines())


def load_config(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_config(path, config):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(path.name + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
        shutil.copy2(str(path), str(backup))
        print("Záloha: {}".format(backup))
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".claude_desktop_config.")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="změnu opravdu zapsat (jinak suchý běh)")
    parser.add_argument("--remove", action="store_true", help="server z konfigurace odebrat")
    parser.add_argument("--force", action="store_true", help="přepsat existující odlišnou konfiguraci serveru")
    parser.add_argument("--config", type=Path, help="cesta ke claude_desktop_config.json (výchozí podle OS)")
    args = parser.parse_args()

    path = args.config or default_config_path()
    config = load_config(path)
    servers = config.setdefault("mcpServers", {})
    current = servers.get(SERVER)
    print("Konfigurace: {}".format(path))

    if args.remove:
        if current is None:
            print("Server {} v konfiguraci není. Nic k odebrání.".format(SERVER))
            return 0
        del servers[SERVER]
        print("Odeberu server {}.".format(SERVER))
    else:
        entry = build_entry()
        if current == entry:
            print("Server {} je už nastavený přesně podle šablony. Nic se nemění.".format(SERVER))
            return 0
        if current is not None and not args.force:
            print("Server {} už v konfiguraci je, ale liší se od šablony:".format(SERVER))
            print(json.dumps(current, indent=2, ensure_ascii=False))
            print("Když ho chceš nahradit, spusť skript s --force.")
            return 2
        servers[SERVER] = entry
        print("Nastavím server {}:".format(SERVER))
        print(json.dumps(entry, indent=2, ensure_ascii=False))

    if not args.apply:
        print("Suchý běh — nic se nezapsalo. Pro zápis ukonči Claude Desktop (Cmd+Q) a spusť skript znovu s --apply.")
        return 0
    if desktop_running():
        print("Claude Desktop běží a změnu by přepsal. Ukonči ho (Cmd+Q) a spusť skript znovu s --apply.")
        return 3
    write_config(path, config)
    print("Hotovo. Spusť Claude Desktop.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
