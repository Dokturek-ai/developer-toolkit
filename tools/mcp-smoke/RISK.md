# RISK — mcp-smoke

## Shrnutí

Riziko: **vysoké**. Skript sice jen čte metadata, ale používá osobní OAuth a infrastrukturní token. Popsaná připojení agentů mohou mít širší oprávnění než samotný skript. Než ho spustíš, ověř prostředí a oprávnění účtu.

## Přístup k datům

- Medplum dev: `https://medplum.test.dokturek.ai`. Skript čte discovery a FHIR metadata přes MCP; nečte pacienty a nezapisuje klinická data. OAuth přihlášení a obnova tokenu používají token endpoint.
- Coolify: `https://coolify.infra.dokturek.ai/mcp`. Skript volá `get_current_team` a `get_infrastructure_overview`; může získat metadata infrastruktury v rozsahu tokenu, včetně údajů o spravovaných produkčních službách.
- Token Coolify načítá z prostředí nebo lokální konfigurace Codexu. Refresh token Medplumu ukládá do macOS Keychainu či libsecret; `--no-store` čtení a zápis do úložiště vypne.
- Skript odpovědi neposílá poskytovateli modelu. Pokud podle návodu připojíš agenta, jeho nástroje a předávání odpovědí poskytovateli modelu závisí na konfiguraci klienta a oprávněních tvého účtu. Používej jen syntetická klinická data.

## Co se může pokazit

- Únik infrastrukturního tokenu umožní operace podle jeho oprávnění; skript ho na čtecí oprávnění neomezuje.
- Agent s přímým připojením může provádět i zápisy. User-scope konfigurace v návodu sama neinstaluje hook pro potvrzování zápisů z pluginu `medplum-mcp`.
- Pokud selže uložení rotovaného refresh tokenu, další běh může použít starý token a přihlášení selže nebo ho server zneplatní. Sleduj varování úložiště; v takovém případě použij `--no-store` a nové přihlášení.

## Ochrany

| Ochrana | Kde platí |
|---|---|
| Pevné cílové adresy, pouze dva čtecí nástroje Coolify a FHIR `GET metadata` | skript |
| OAuth Authorization Code + PKCE S256, ověření `state` a případného `iss`, loopback callback | přihlášení skriptu k Medplumu |
| Systémové úložiště refresh tokenů, token není předán přes argv ani záměrně vypsán | skript |
| Kontrola znaků tokenu před vstupem do `security -i` | macOS úložiště skriptu |
| Povinné FHIR metadata musí být JSON objekt typu `CapabilityStatement`, jinak návratový kód 5; diagnostická absolutní cesta pouze varuje | skript, regresní testy |
| Při obnově z uloženého tokenu se náhradní refresh token uloží před návratem; `--no-store` úložiště obchází | skript, regresní testy |
| Allowlist povoluje schváleného hostitele Coolify; ostatní hostitelé zůstávají omezení | `scripts/check_repo.py` |

## Co ochrany nepokrývají

- Živé volání s reálnými tokeny nebylo při přesunu ověřeno. Původní ověřovací záznamy v README jsou datované k 29. 10. 2026.
- Kontrola `CapabilityStatement` nevaliduje celý FHIR zdroj ani funkčnost klinických operací. Úspěch diagnostiky není přejímka integrace.
- Regresní testy používají syntetické tokeny a simulované úložiště; funkčnost macOS Keychainu a libsecret na tvém stroji neověřují.
- Allowlist je statická kontrola repozitáře, ne síťová izolace. Neomezuje oprávnění tokenu, discovery endpointy ani chování vzdáleného serveru.

## Vypnutí a odvolání přístupu

Skript ukonči přes Ctrl+C. Pro další běhy použij `--no-store`; to již uložený token nesmaže. Z macOS Keychainu odstraň položku se službou `dokturek-medplum-dev-mcp` a účtem `dokturek-claude-code-dev`; v libsecret odstraň stejné atributy `service` a `account`. Token Coolify odvolej v Coolify a odstraň ho z prostředí a konfigurace Codexu. Pro serverové odvolání přihlášení požádej správce Medplumu o zneplatnění své relace. Připojení osobních agentů odeber zvlášť v jejich konfiguraci.

## Vlastník a revize

- Vlastník: Petr Sovadina (@petrsovadina).
- Poslední revize: 2026-10-30 — Petr výslovně schválil přidání `coolify.infra.dokturek.ai` do allowlistu pro stávající MCP diagnostiku. Samostatný bezpečnostní commit mění pouze allowlist a tento popis rizik; nemění prostředí ani oprávnění serveru.
- Opravy skriptu: 2026-10-30 — povinná kontrola FHIR metadat a ukládání rotovaného refresh tokenu, včetně regresních testů bez živých přístupů.
- Revize nejpozději při opravě známých omezení, změně hostitele, OAuth klientů, Medplumu nebo dostupných nástrojů Coolify.
