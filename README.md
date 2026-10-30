# Doktůrek developer toolkit

Vývojářské nástroje core týmu Doktůrek.ai, které sahají na data — hlavně na Medplum. MCP servery, konfigurace agentů a pomocné skripty pro Claude Code, Claude Desktop a Codex.

> [!WARNING]
> Tohle není marketplace pluginů. Každý nástroj tady má přístup k datům, některé i k zápisu. Nepoužívej nástroj, dokud nepřečteš jeho `README.md` a `RISK.md` a nevyzkoušíš ho lokálně podle návodu.

Obecné pluginy a skilly bez přístupu k datům patří do [plugin-marketplace-healthcare-dev](https://github.com/Dokturek-ai/plugin-marketplace-healthcare-dev). Toolkit je oddělený záměrně: jiné riziko, jiná pravidla, přísnější review.

## Nástroje

| Nástroj | Co dělá | Prostředí | Zápis do dat | Klienti |
|---|---|---|---|---|
| [`medplum-mcp`](tools/medplum-mcp/) | MCP přístup k Medplum FHIR API | dev-pre-production | ano, v Claude Code s potvrzením | Claude Code, Claude Desktop, Codex |
| [`mcp-smoke`](tools/mcp-smoke/) | Nastavení agentů a samostatná MCP diagnostika; známá omezení v RISK.md | Medplum dev, Coolify infra | skript jen čte; připojení agentů podle oprávnění účtu | Python 3.9+, návody pro osobní agenty |

Každý nástroj má `README.md` (nastavení, ověření, odhlášení) a `RISK.md` (k čemu má přístup, co může pokazit, jak ho vypnout).

## Rychlý start — Claude Code

Předpoklad: máš účet v Medplumu prostředí dev-pre-production a přečetl jsi [RISK.md](tools/medplum-mcp/RISK.md) nástroje.

```text
/plugin marketplace add Dokturek-ai/developer-toolkit
/plugin install medplum-mcp@dokturek-dev-toolkit
/mcp
```

V `/mcp` vyber `plugin:medplum-mcp:medplum-dev` a přihlas se svým Medplum účtem. Claude Desktop a Codex mají vlastní postup v [README nástroje](tools/medplum-mcp/README.md#nastavení).

## Pravidla

Celé znění je v [docs/safe-usage.md](docs/safe-usage.md). Zkráceně:

1. Jen testovací prostředí a syntetická data. Produkční endpoint toolkit neobsahuje a kontrola v CI ho do nástrojů nepustí.
2. Každý se přihlašuje vlastním účtem. Tokeny se nesdílí, nekopírují a necommitují.
3. Zápisy do dat potvrzuješ ručně, u každého volání.
4. Když něco nesedí — reálná data v testu, podezření na únik tokenu — přestaň nástroj používat a postupuj podle [SECURITY.md](SECURITY.md).

## Struktura

```text
.claude-plugin/marketplace.json   Claude Code marketplace „dokturek-dev-toolkit“
tools/<nástroj>/                  jeden nástroj = jeden adresář (README.md, RISK.md, konfigurace, skripty)
tools/_template/                  šablona pro nový nástroj
docs/safe-usage.md                pravidla používání
scripts/check_repo.py             kontroly repa (allowlist hostitelů, připnuté verze, secrets, struktura)
```

## Nový nástroj

Postup, review a verzování: [CONTRIBUTING.md](CONTRIBUTING.md). Pravidla pro AI agenty, kteří v repu pracují: [AGENTS.md](AGENTS.md).
