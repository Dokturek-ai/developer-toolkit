"""PreToolUse hook pro nástroje Medplum MCP (medplum-mcp).

- fhir-request: GET na běžný FHIR zdroj vrací "{}" (bez rozhodnutí), takže platí běžné
  schvalování Claude Code. Každá jiná metoda a čtení citlivých nebo zapisujících
  cest vrací permissionDecision "ask". Cesta, která může opustit /fhir/R4/
  (absolutní URL, `..`, `%`, řídicí nebo bílý znak, `#`, zpětné lomítko), vrací "deny".
- search a fetch na serverech toolkitu a známé nástroje dokumentačního serveru jen čtou a projdou.
- Každý jiný nástroj Medplum MCP vrací "ask" (fail closed).
Při chybě čtení vstupu hook také vrací "ask", aby zápis nikdy neprošel bez potvrzení.
Hook vždy vypíše JSON; "{}" znamená bez rozhodnutí (běžné schvalování). Wrapper
confirm-writes.sh jiný výstup nepřijme a požádá o potvrzení.
"""
import json
import re
import sys

# search a fetch projdou jen na serverech toolkitu; jinde mohou vracet skutečná data.
READ_ONLY_TOOLS = {"search", "fetch"}
TOOLKIT_SERVERS = ("plugin_medplum-mcp_medplum-dev", "dokturek-medplum-dev")
DOCS_TOOLS = {"medplum_doc_get", "medplum_doc_list", "medplum_doc_search", "medplum_repo_get"}
# Operace, které jen čtou. Ostatní $operace (např. $execute, $export, $graphql) mohou zapisovat.
READ_ONLY_OPERATIONS = {"$expand", "$lookup", "$validate-code", "$translate", "$subsumes", "$everything", "$meta"}
SENSITIVE_SEGMENTS = {"project", "projectmembership", "clientapplication", "user", "login", "bot",
                      "admin", "auth", "oauth2", "accesspolicy", "useraccessrequest", "usersecurityrequest",
                      "jsonwebkey", "passwordchangerequest", "domainconfiguration", "smartapplaunch",
                      "userconfiguration", "asyncjob", "subscription", "scim"}
# WHATWG URL parser maže úvodní mezery a řídicí znaky a všechny tabulátory a konce řádků;
# fragment (#) se neodešle. Takový znak by schoval únik nebo citlivou cestu.
HIDDEN = re.compile(r"[\x00-\x20\x7f-\x9f#\\]")
# Cesta před "?" smí obsahovat jen tyto znaky. Bez "%", aby kódování nic neschovalo (např. %24execute).
ROUTE = re.compile(r"[A-Za-z0-9$_.\-/]*")
ESCAPE = re.compile(r"(^[a-z][a-z0-9+.-]*:|^//|\.\.|%2e|%2f|%5c|\\)", re.IGNORECASE)
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]+")
MAX_SHOWN = 160


def shown(text):
    text = CONTROL.sub(" ", str(text))
    return text if len(text) <= MAX_SHOWN else text[:MAX_SHOWN] + "…"


def no_decision():
    print("{}")


def decide(kind, reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": kind,
            "permissionDecisionReason": reason,
        }
    }, ensure_ascii=False))


def ask(reason):
    decide("ask", reason)


def sensitive_read(path):
    """Vrátí důvod, proč GET vyžaduje potvrzení, nebo None."""
    route = path.split("?", 1)[0].strip("/")
    for segment in route.split("/"):
        if segment.lower() in SENSITIVE_SEGMENTS:
            return "čtení správy projektu, identit nebo Botů ({})".format(segment)
        if segment.startswith("$") and segment.lower() not in READ_ONLY_OPERATIONS:
            return "operace {} může zapisovat".format(segment)
    return None


def check_fhir_request(tool_input):
    # strip() je záměrně volnější než server (ten metodu neořezává a "GET " odmítne): chyba vede k potvrzení, ne k průchodu.
    method = str(tool_input.get("method", "")).strip().upper()
    path = str(tool_input.get("path", ""))
    if HIDDEN.search(path) or not ROUTE.fullmatch(path.split("?", 1)[0]) or ESCAPE.search(path):
        decide("deny", "medplum-mcp: cesta `{}` může opustit /fhir/R4/ (absolutní URL, `..` nebo kódovaný znak). "
                       "Použij cestu relativní k /fhir/R4/.".format(shown(path)))
        return
    if method == "GET":
        reason = sensitive_read(path)
        if reason:
            ask("medplum-mcp: GET {} — {}. Zkontroluj cestu, než potvrdíš.".format(shown(path), reason))
        else:
            no_decision()
        return
    ask("medplum-mcp: zápis do Medplum dev — {} {}. Zkontroluj metodu, cestu a tělo požadavku, než potvrdíš.".format(
        shown(method) or "(bez metody)", shown(path) or "(prázdná cesta = base URL, batch/transaction)"))


def main():
    try:
        event = json.load(sys.stdin)
        tool_name = str(event.get("tool_name", ""))
        tool_input = event.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            raise ValueError("tool_input")
    except Exception:
        ask("medplum-mcp: vstup hooku nejde přečíst. Zkontroluj operaci a potvrď ručně.")
        return
    server, _, tool = tool_name.rpartition("__")
    if tool in DOCS_TOOLS and "docs" in server.lower():
        no_decision()
        return
    if tool in READ_ONLY_TOOLS and server.endswith(TOOLKIT_SERVERS):
        no_decision()
        return
    if tool == "fhir-request":
        check_fhir_request(tool_input)
        return
    ask("medplum-mcp: neznámý nástroj Medplum MCP `{}`. Zkontroluj, co dělá, než potvrdíš.".format(shown(tool_name)))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        ask("medplum-mcp: kontrola hooku selhala. Zkontroluj operaci a potvrď ručně.")
