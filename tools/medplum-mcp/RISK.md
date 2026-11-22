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
| Hook `hooks/confirm-writes.sh` hlídá všechny MCP nástroje se jménem obsahujícím medplum (plugin, ruční server i synchronizovaný konektor): každý zápis přes `fhir-request`, čtení správy projektu, identit a Botů (`Project`, `ProjectMembership`, `ClientApplication`, `User`, `Login`, `Bot`, `admin`, `auth`, `oauth2`) a každá `$operace` mimo čtecí (`$expand`, `$lookup`, `$validate-code`, `$translate`, `$subsumes`, `$everything`, `$meta`) vyžaduje tvoje potvrzení. Cestu s absolutní URL, `..`, `%`, řídicím nebo bílým znakem, `#` nebo zpětným lomítkem zamítne (URL parser takové znaky maže a schoval by únik). Nástroje `search` a `fetch` pustí jen na serverech toolkitu, z dokumentačního serveru jen známé čtecí nástroje. Neznámý nástroj Medplum MCP vyžaduje potvrzení. Výstup Pythonu, který není jediné rozhodnutí hooku, vede také k potvrzení. Když hook nepřečte vstup, `python3` chybí, nespustí se nebo skončí chybou, ptá se taky. | jen Claude Code plugin |
| Medplum odmítne `path`, která míří na **jiný** origin — ochrana proti úniku tokenu na cizí server (Medplum ≥ 5.2.0). Únik z `/fhir/R4/` v rámci stejného originu server neblokuje (viz níže). | server |
| `mcp-remote` připnutý na 0.14.3 | most pro Claude Desktop |
| Allowlist hostitelů, kontrola připnutých verzí a vzorů secrets v CI (`scripts/check_repo.py`, gitleaks) | repo |
| Instalátor při konfliktu nevypisuje existující konfiguraci se secrets a náhradu vyžaduje povolit přes `--force` | instalátor Claude Desktopu, regresní test |

## Co ochrany nepokrývají

- Claude Desktop a Codex hook nemají. Zápisy, citlivá čtení i únik z `/fhir/R4/` hlídáš jen schvalováním v klientovi.
- **Únik z `/fhir/R4/` v rámci stejného originu:** audit z 16. 11. 2026 doložil, že `fhir-request` vrátil `/healthcheck` pro absolutní URL, `../../healthcheck` i `%2e%2e/%2e%2e/healthcheck` ([dokturek-docs, audit 47/10](https://github.com/Dokturek-ai/dokturek-docs/blob/main/47-audit-healthcare-2026-11-16/10-mcp-oprava-a-overeni.md)). Hook tyto cesty v Claude Code zamítne; serverová oprava není nasazená. Bez hooku jsou správa projektu a auth cesty dostupné i čtením.
- **Účet určuje rozsah.** Medplum zatím nemá schválené klinické AccessPolicy, takže token člověka s rolí správce projektu má téměř plná práva v projektu. Nepřipojuj se účtem super-admina ani správce projektu; pro agenta používej účet s co nejužším členstvím. Čtecí OAuth klient a AccessPolicy pro agenty jsou otevřené rozhodnutí vlastníka.
- **Test a produkce nejsou oddělené čistě.** Podle [mapy prostředí](https://github.com/Dokturek-ai/dokturek-docs/blob/main/07-reference/prostredi.md) běží produkční frontend (Coolify resource `production`) proti testovacímu Medplumu. Slib „jen syntetická data“ tedy platí, jen dokud přes tento frontend nikdo nezadá skutečná data. Klasifikaci dat v `medplum.test` musí potvrdit vlastník.
- **Timeout hooku:** když hook nedoběhne do 20 s (např. pomalý první start Pythonu), Claude Code bere timeout jako neblokující chybu a volání pustí. Pokud hook často trvá dlouho, nástroj nepoužívej a nahlas to vlastníkovi.
- **Serverová oprava cesty:** novější Medplum (`main`) kontroluje výslednou cestu `fhir-request` sám; nasazená verze 5.2.15 to podle auditu nedělá, takže v Claude Code je jedinou kontrolou hook.
- **Vynesení dat jinými nástroji:** text ve FHIR datech může agenta navést, aby přečtená data poslal ven přes WebFetch nebo `curl`. Když jsi připojený k Medplumu, nepovoluj trvale WebFetch ani síťové příkazy v shellu.
- **Podmínky poskytovatele modelu:** spotřebitelské plány mohou data použít k trénování. Používej organizační nebo API účet.
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
- Revize hooku: 2026-11-22 — verze 0.2.0: matcher na všechny nástroje Medplum MCP, zamítnutí úniku z `/fhir/R4/`, potvrzení citlivých čtení a neznámých nástrojů, fail closed i při nefunkčním `python3`; regresní testy. Server hlásí Medplum 5.2.15, úplná revize proti této verzi zbývá.
- Revize instalátoru: 2026-11-01 — verze 0.1.1 odstraňuje výpis existující konfigurace při konfliktu; testy používají pouze syntetická data a dočasný soubor.
- Revize nejpozději při upgradu Medplumu, změně OAuth klientů, novém klientovi nebo změně verze `mcp-remote`.
