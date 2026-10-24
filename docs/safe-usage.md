# Bezpečné používání toolkitu

Nástroje z toolkitu pracují s daty a s oprávněními tvého účtu. Tahle pravidla platí pro všechny nástroje. Konkrétní rizika a ochrany každého nástroje jsou v jeho `RISK.md`.

## Prostředí a data

Nástroje míří na testovací prostředí (dev-pre-production). Produkční endpoint v toolkitu není a `scripts/check_repo.py` v CI odmítne každého hostitele, který není v allowlistu.

V testovacím prostředí pracuj jen se syntetickými daty. Když narazíš na data, která vypadají jako skutečná data pacientů, nástroj dál nepoužívej a dej vědět vlastníkovi nástroje.

Všechno, co agent přečte, se stává součástí konverzace a odchází k poskytovateli modelu — u Claude k Anthropicu, u Codexu k OpenAI. Platí to i pro obyčejné čtení.

## Identita a tokeny

Každý se přihlašuje vlastním účtem přes OAuth. Sdílené účty ani sdílené tokeny toolkit nepoužívá.

Tokeny ukládá klient: Claude Code ve svém úložišti credentials, most `mcp-remote` pro Claude Desktop v `~/.mcp-auth/`, Codex ve svém úložišti. Tokeny nekopíruj, neposílej a necommituj. Refresh token, pokud ho nástroj používá, platí, dokud ho neodvoláš nebo nevyprší.

## Oprávnění a potvrzování

Nástroj má stejná oprávnění jako tvůj účet, včetně zápisu a mazání. Read-only režim nástroje záměrně nevynucují.

Zápisy potvrzuješ ručně, u každého volání:

- Claude Code plugin to vynucuje hookem — u každého zápisu se tě zeptá.
- V Claude Desktopu a v Codexu hook není. Nepovoluj zápisový nástroj trvale a potvrzuj každé volání.

Než potvrdíš, přečti si metodu a cestu. Hook se zeptá, ale operaci neposoudí — co potvrdíš, to se provede.

Pozor na prompt injection: text uložený v datech (poznámka, popis zdroje) může agenta navést k akci, kterou jsi nezadal. Když agent navrhne zápis, který nečekáš, odmítni ho.

## Verze a instalace

Balíčky spouštěné přes `npx` jsou připnuté na konkrétní verzi. Neměň je na `@latest` — nová verze cizího balíčku je nová důvěra a prochází review jako každá jiná změna.

Před instalací čehokoli mimo toolkit (skript, skill, MCP server) si projdi, co dělá.

## Když něco nesedí

Přestaň nástroj používat, odhlas se podle README nástroje a postupuj podle [SECURITY.md](../SECURITY.md).
