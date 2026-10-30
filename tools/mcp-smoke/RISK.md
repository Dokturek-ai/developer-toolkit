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
- Výsledky diagnostiky mohou působit úspěšně i při neplatné odpovědi povinného FHIR testu.
- Opakované použití starého refresh tokenu může zneplatnit přihlášení, pokud server tokeny rotuje.

## Ochrany

| Ochrana | Kde platí |
|---|---|
| Pevné cílové adresy, pouze dva čtecí nástroje Coolify a FHIR `GET metadata` | skript |
| OAuth Authorization Code + PKCE S256, ověření `state` a případného `iss`, loopback callback | přihlášení skriptu k Medplumu |
| Systémové úložiště refresh tokenů, token není předán přes argv ani záměrně vypsán | skript |
| Kontrola znaků tokenu před vstupem do `security -i` | macOS úložiště skriptu |
| Allowlist hostitelů a kontrola secrets; Coolify vyžaduje samostatné rozšíření allowlistu | `scripts/check_repo.py` |

## Co ochrany nepokrývají

- Živé volání s reálnými tokeny nebylo při přesunu ověřeno. Původní ověřovací záznamy v README jsou datované k 29. 10. 2026.
- Skript byl přesunut beze změny: neplatný JSON povinného FHIR testu pouze varuje a očekávaný `CapabilityStatement` neověřuje. Úspěšný návratový kód proto není důkaz funkční integrace.
- Větev obnovy z uloženého refresh tokenu neukládá náhradní refresh token. Před opakovaným použitím oprav rotaci nebo použij `--no-store` a nové přihlášení.
- Allowlist je statická kontrola repozitáře, ne síťová izolace. Neomezuje oprávnění tokenu, discovery endpointy ani chování vzdáleného serveru.

## Vypnutí a odvolání přístupu

Skript ukonči přes Ctrl+C. Pro další běhy použij `--no-store`; to již uložený token nesmaže. Z macOS Keychainu odstraň položku se službou `dokturek-medplum-dev-mcp` a účtem `dokturek-claude-code-dev`; v libsecret odstraň stejné atributy `service` a `account`. Token Coolify odvolej v Coolify a odstraň ho z prostředí a konfigurace Codexu. Pro serverové odvolání přihlášení požádej správce Medplumu o zneplatnění své relace. Připojení osobních agentů odeber zvlášť v jejich konfiguraci.

## Vlastník a revize

- Vlastník: Petr Sovadina (@petrsovadina).
- Poslední revize: 2026-10-30 — přesun z produktových podkladů. Rozšíření allowlistu pro Coolify následuje v samostatném bezpečnostním commitu. Přesun nemění prostředí ani oprávnění serveru.
- Revize nejpozději při opravě známých omezení, změně hostitele, OAuth klientů, Medplumu nebo dostupných nástrojů Coolify.
