"""PreToolUse hook pro fhir-request (medplum-mcp).

GET vrací prázdný výstup, takže platí běžné schvalování Claude Code.
Každá jiná metoda vrací permissionDecision "ask". Při chybě čtení vstupu
hook také vrací "ask", aby zápis nikdy neprošel bez potvrzení.
"""
import json
import sys


def ask(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }, ensure_ascii=False))


def main():
    try:
        event = json.load(sys.stdin)
        tool_input = event.get("tool_input") or {}
        method = str(tool_input.get("method", "")).strip().upper()
        path = str(tool_input.get("path", ""))
    except Exception:
        ask("medplum-mcp: vstup hooku nejde přečíst. Zkontroluj operaci a potvrď ručně.")
        return
    if method == "GET":
        return
    ask("medplum-mcp: zápis do Medplum dev — {} {}. Zkontroluj metodu, cestu a tělo požadavku, než potvrdíš.".format(
        method or "(bez metody)", path or "(prázdná cesta = base URL, batch/transaction)"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        ask("medplum-mcp: kontrola hooku selhala. Zkontroluj operaci a potvrď ručně.")
