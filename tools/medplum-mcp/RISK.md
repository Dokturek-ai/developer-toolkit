# RISK — medplum-mcp

## Shrnutí

Riziko: **vysoké**. Agent čte i zapisuje do Medplumu v rozsahu tvého účtu, včetně mazání. Odpovědi z Medplumu se stávají součástí konverzace a odcházejí k poskytovateli modelu.

## Přístup k datům

- Prostředí: Medplum dev-pre-production, `https://medplum.test.dokturek.ai`.
- Rozsah: všechny FHIR zdroje, které vidí tvůj účet. Určuje ho tvoje `ProjectMembership` a `AccessPolicy`. Token nenese SMART scopes, takže ho Medplum nad rámec účtu dál neomezuje.
- Operace: `GET`, `POST`, `PUT`, `PATCH`, `DELETE` přes `fhir-request`, včetně batch a transaction Bundle na base URL.
- Data mimo Medplum: obsah odpovědí jde k poskytovateli modelu — u Claude k Anthropicu, u Codexu k OpenAI. V testovacím prostředí smí být jen syntetická data.

## Co se může pokazit

- Smazání nebo přepsání dat (`DELETE`, `PUT`), i hromadně jedním batch nebo transaction Bundle.
- Prompt injection: text uložený ve FHIR zdroji (poznámka, popis) může agenta navést k operaci, kterou jsi nezadal.
- Únik dat do kontextu modelu, i při čistém čtení.
- Únik tokenu z lokálního úložiště (`~/.mcp-auth/`, úložiště Claude Code nebo Codexu). Access token platí 1 hodinu. Refresh token nástroj nežádá (viz Známé omezení v README).
- Konfigurace upravená tak, že míří na jiné prostředí.

## Ochrany

| Ochrana | Kde platí |
|---|---|
| Osobní OAuth přihlášení: authorization code + PKCE (S256), veřejní klienti bez secretu, přesná shoda redirect URI | všichni klienti |
| Hook `hooks/confirm-writes.sh`: každé volání `fhir-request` s jinou metodou než `GET` vyžaduje tvoje potvrzení. Když hook nepřečte vstup nebo chybí `python3`, ptá se taky. | jen Claude Code plugin |
| Medplum odmítne `path`, která míří mimo vlastní origin — ochrana proti SSRF a úniku tokenu (Medplum ≥ 5.2.0) | server |
| `mcp-remote` připnutý na 0.14.3 | most pro Claude Desktop |
| Allowlist hostitelů, kontrola připnutých verzí a vzorů secrets v CI (`scripts/check_repo.py`, gitleaks) | repo |

## Co ochrany nepokrývají

- Claude Desktop a Codex hook nemají. Zápisy hlídáš jen schvalováním v klientovi.
- Hook se zeptá, ale operaci neposoudí. Co potvrdíš, to se provede.
- Čtení (`GET`) hook nepotvrzuje — data jdou do kontextu modelu podle tvého nastavení oprávnění v klientovi.
- Read-only režim nástroj záměrně nemá. Oprávnění určuje tvůj Medplum účet.
- Ochrana tokenu na disku závisí na zabezpečení tvého stroje.

## Vypnutí a odvolání přístupu

Na tvém stroji: odhlášení podle [README](README.md#odhlášení-a-odebrání).

Na serveru — správce Medplumu v Coolify, resource `medplum` (projekt `dokturek-EHR`):

- Vypnout MCP pro všechny: `MEDPLUM_MCP_ENABLED=false` a redeploy. Server pak endpoint `/mcp` nepřipojí.
- Zablokovat jednoho klienta: odebrat ho z `MEDPLUM_DEFAULT_OAUTH_CLIENTS` a redeploy. Nová přihlášení přes něj selžou, už vydané access tokeny platí do vypršení (1 hodina).
- Odvolat relace konkrétního uživatele: zneplatnit jeho `Login` zdroje v Medplumu.

## Vlastník a revize

- Vlastník: Petr Sovadina (@petrsovadina)
- Poslední revize: 2026-10-24 — Medplum 5.2.1, mcp-remote 0.14.3, Claude Code 2.1.310, Codex CLI 0.163.0. Scope bez `offline_access` kvůli chybě refresh flow v Medplumu.
- Revize nejpozději při upgradu Medplumu, změně OAuth klientů, novém klientovi nebo změně verze `mcp-remote`.
