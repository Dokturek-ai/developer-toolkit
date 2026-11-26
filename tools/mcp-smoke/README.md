# Připojení agentů k MCP serverům Coolify a Medplum dev

> Interní vývojářský nástroj přesunutý z `dokturek-docs` PR #21 (revize `3154d8025710e60b526ebc62de0e4149ea751d57`) dne 30. 10. 2026. Před použitím si přečti [RISK.md](RISK.md); živé ověření zůstává otevřené. Příkazy níže spouštěj z kořene `developer-toolkit`.

> Původní síťové sondy v tomto návodu jsou z 29. 10. 2026. Dne 19. 11. 2026 vrátil připojený testovací konektor v aplikaci FHIR metadata s verzí `5.2.15-4d86215`, počet číselníků přes `fhir-request` a zástupný dokument přes `search`. Samostatný skript i obnova relace v aplikaci čekají na ověření s reálnými přístupy (§6).
> **Značky:** [Z] zjištěno (kód, odpověď serveru, test), [N] neověřeno, [P] návrh.
> **Zdroje:** Medplum `v5.2.1` (`e0db1fc`, build hlášený `/healthcheck` k 29. 10. 2026; od 9. 11. 2026 server hlásí `5.2.15-4d86215`), `@modelcontextprotocol/sdk` 1.30.1 (verze pinovaná v Medplum serveru), `Dokturek-ai/dokturek-medplum` `18b53e7` (`integrations/openai/`), Claude Code 2.1.312.

## 1. Servery

| Server | URL | Transport | Autentizace |
|---|---|---|---|
| Coolify self-hosted | `https://coolify.infra.dokturek.ai/mcp` | Streamable HTTP | `Authorization: Bearer <COOLIFY_API_TOKEN>` |
| Medplum dev | `https://medplum.test.dokturek.ai/mcp/stream` | Streamable HTTP, bezstavový (bez `Mcp-Session-Id`) | OAuth 2.0 Authorization Code + PKCE S256. Pro běžné připojení přes toolkit `openid profile`; skript `mcp-smoke.py` žádá navíc `offline_access` (§5). |

Odpovědi z 29. 10. 2026 bez tokenu [Z]:

- Coolify `initialize` vrací `401` a `WWW-Authenticate: Bearer realm="mcp", error="invalid_token"`.
- Medplum `/healthcheck` vrací `200` s verzí `5.2.1-e0db1fc` a Postgres i Redis jsou OK. `initialize` vrací `401` s `OperationOutcome` `login`, ne `404`, takže MCP je zapnuté.
- Discovery `/.well-known/oauth-authorization-server` inzeruje `S256` a `registration_endpoint`. `offline_access` mezi `scopes_supported` chybí.

## 2. OAuth klienti Medplum dev

Medplum 5.2.1 při DCR (`/oauth2/register`) nic neregistruje; kód `register.ts` ve verzi 5.2.15 se chová stejně. Podle první `redirect_uri` jen vyhledá klienta v `MEDPLUM_DEFAULT_OAUTH_CLIENTS` (`packages/server/src/oauth/register.ts`). Seznam je v `dokturek-medplum/integrations/openai/oauth-clients.dev.json`:

| Agent | `client_id` | Přesná callback URL |
|---|---|---|
| Claude Code | `dokturek-claude-code-dev` | `http://localhost:1458/callback` (povolená je i `http://127.0.0.1:1458/callback`) |
| Konektor claude.ai (i v Claude Desktopu) | `dokturek-claude-desktop-dev` | `https://claude.ai/api/mcp/auth_callback`, `https://claude.com/api/mcp/auth_callback` |
| Codex CLI | `dokturek-codex-dev` | `http://127.0.0.1:1457/callback/uAEkM6bonMJI` |
| ChatGPT | `dokturek-chatgpt-dev` | `https://chatgpt.com/connector/oauth/nSvqXqv_vpdT` |

Všichni jsou veřejní klienti bez secretu, s povinným PKCE a výchozím scope `openid profile offline_access`.

Živá DCR sonda 29. 10. [Z]: `http://localhost:9615` vrací `medplum-cli` a `https://claude.ai/api/mcp/auth_callback` vrací `dokturek-claude-desktop-dev`. Neznámé callbacky vracejí `400 Invalid redirect URI`, například `http://localhost:1455/auth/callback` nebo `http://localhost:6274/oauth/callback` (MCP Inspector).

**Jiný typ agenta** potřebuje vlastní záznam v `oauth-clients.dev.json` s přesnou callback URL bez wildcardu. Pak se zkopíruje do `MEDPLUM_DEFAULT_OAUTH_CLIENTS` v Coolify (build i runtime) a stack se znovu nasadí (`integrations/openai/README.md`). Bez toho DCR vrátí `400`.

## 3. Konfigurace Claude Code (user scope, tokeny mimo repozitář)

> [!WARNING]
> Coolify spravuje i produkční služby. Připojený agent může přes nástroje Coolify MCP měnit infrastrukturu a žádný hook toolkitu ho nehlídá. Používej token, který smí jen číst, nepovoluj nástroje Coolify MCP trvale a potvrzuj každé volání. Bez tohoto omezení agenta nepřipojuj.

```bash
claude mcp add-json --scope user coolify-selfhosted '{"type":"http","url":"https://coolify.infra.dokturek.ai/mcp","headers":{"Authorization":"Bearer ${COOLIFY_API_TOKEN}"}}'
```

`${COOLIFY_API_TOKEN}` se rozvine až při připojení. Do `~/.claude.json` se zapíše jen zástupný text. Ověřeno lokálním echo serverem: Claude Code 2.1.312 poslal `Bearer <hodnota proměnné>` [Z]. Token stačí exportovat v shellu, ze kterého se `claude` spouští. Na Macu ho lze vzít z Keychainu, nikdy ne z repozitáře.

Pro připojení k Medplumu z Claude Code, Claude Desktop, Codexu nebo ChatGPT použij [návod k medplum-mcp](../medplum-mcp/README.md#nastavení).

## 4. Nálezy k chybě `-32603 Internal error`

### N1. Cesta `/fhir/R4/metadata` se zdvojí [Z]

`fhir-request` volá `concatUrls(<base>/fhir/R4, path)` (`packages/server/src/mcp/server.ts`). `concatUrls` odstraní úvodní lomítko (`packages/core/src/utils.ts:1483`), takže z `/fhir/R4/metadata` vznikne `<base>/fhir/R4/fhir/R4/metadata`.

**Správná hodnota je `path: "metadata"`.** Cesty jsou relativní k `/fhir/R4/`.

Na replice se stejným SDK skončí zdvojená cesta jako chyba nástroje (`isError: true`), ne jako `-32603`.

### N2. `search` a `fetch` jsou atrapy [Z]

Původní server vracel pevný `dummy-doc`. V připojené aplikaci vrátil `search` zástupný dokument i 19. 11. 2026. Pro FHIR dotazy použij `fhir-request`.

### N3. Původní chybu `-32603` se nepodařilo při opakování potvrdit

SDK 1.30.1 výjimku z handleru nástroje převede na výsledek s `isError: true` (`dist/cjs/server/mcp.js:144`). Neznámý nástroj skončí také jako `isError` (`-32602` v textu).

Replika `mcp/routes.ts` a `mcp/server.ts` (bezstavový `StreamableHTTPServerTransport`) to potvrdila: `initialize`, `notifications/initialized` (`202`), `tools/list` i `search` prošly.

Pozdější `GET metadata` z připojené aplikace prošel. Příčina dřívějšího `-32603` zůstává neověřená. K jejímu určení je potřeba skutečná konfigurace aplikace a související záznamy serveru ze stejného času. [Výsledek diagnostiky](https://github.com/Dokturek-ai/dokturek-medplum/pull/40)

### N4. Obnova tokenu výchozího klienta může vrátit `Invalid client`

Lokální test Medplumu 5.2.15 bez opravy reprodukoval `Invalid client` při obnově tokenu výchozího klienta z `defaultOAuthClients`. Po opravě obnovu ověřil lokální test. Nasazení opravy a obnova tokenu v připojené aplikaci zůstávají neověřené. [Oprava a ověření](https://github.com/Dokturek-ai/dokturek-medplum/pull/40)

## 5. Ověřovací skript `mcp-smoke.py`

Skript potřebuje jen standardní knihovnu Pythonu 3.9+ (systémový `python3` na macOS stačí). Provádí jen čtecí operace a tokeny nikdy nevypisuje.

| Cíl | Postup |
|---|---|
| `coolify` | Token vezme z `$COOLIFY_API_TOKEN`, jinak ze sekce `[mcp_servers.coolify-selfhosted.http_headers]` v `~/.codex/config.toml`. Pak `initialize` → `notifications/initialized` → `tools/list` → `get_current_team` a `get_infrastructure_overview`. |
| `medplum` | Discovery (kontrola `S256` a toho, že `token_endpoint` i `authorization_endpoint` míří přes `https` přesně na `medplum.test.dokturek.ai`) → přihlášení v prohlížeči (Authorization Code + PKCE S256, scope `openid profile offline_access`, `state`, kontrola `iss`) → výměna kódu → refresh token do macOS Keychainu (`security -i`, hodnota nejde přes argv), na Linuxu do libsecret → handshake → `fhir-request GET metadata`. Pro srovnání s N1 zavolá i `GET /fhir/R4/metadata`, to jen jako varování. |

Rozlišení chyb (návratový kód):

| Třída | Kód | Kdy |
|---|---|---|
| `AUTH` | 2 | HTTP 401/403 (s `WWW-Authenticate`), chyba token endpointu, OAuth endpoint z discovery mimo `https://medplum.test.dokturek.ai`, nesoulad `state` nebo `iss`, chybějící token |
| `TRANSPORT` | 3 | DNS, TLS, spojení, timeout; HTTP mimo 200/202 (404, 406, 5xx); neplatná JSON-RPC obálka nebo struktura používaných polí výsledku; chybějící odpověď v SSE |
| `PROTOCOL` | 4 | JSON-RPC objekt `error` (například `-32603`, `-32602`) |
| `TOOL` | 5 | `result.isError: true`, nástroj chybí v `tools/list` nebo povinné FHIR metadata nejsou JSON objekt typu `CapabilityStatement` |

Na rozdíl od konfigurací v `medplum-mcp` (Claude Code, most pro Claude Desktop i Codex žádají jen `openid profile`) skript žádá scope `offline_access`, aby `--check-refresh` mohl ověřit obnovu tokenu. Vydaný refresh token uloží do macOS Keychainu nebo libsecret, nikdy ne do `~/.mcp-auth/`. S `--no-store` ho nečte ani neuloží. Skript používá stejného OAuth klienta `dokturek-claude-code-dev` jako Claude Code a most pro Claude Desktop v `medplum-mcp`. Zablokování nebo změna tohoto klienta na serveru proto zasáhne obojí.

Skript je ověřený proti lokální replice Medplum MCP (SDK 1.30.1) a Coolify [Z]. Rozlišil platný token, `401` jako `AUTH`, odmítnuté spojení jako `TRANSPORT` a výjimku i neznámý nástroj jako `TOOL`.

Opravy z 30. 10. 2026 ověřují regresní testy bez sítě a systémového úložiště: povinný `GET metadata` při neplatném JSON nebo jiném typu zdroje skončí `FAIL TOOL` a kódem 5. Stejná chyba u diagnostické absolutní cesty zůstává pouze varováním. Po obnově z uloženého refresh tokenu se náhradní token uloží před návratem; pokud ho server nevydá, původní zůstává zachovaný. Neúspěšné uložení vypíše varování. `--no-store` úložiště nečte ani do něj nezapisuje.

Opravy z 1. 11. 2026 přidávají stejné varování i pro druhé uložení tokenu při `--check-refresh`. Neplatný JSON nebo chybějící či chybně typovaná povinná pole OAuth discovery skončí `TRANSPORT` a kódem 3; chybějící podpora S256 dál končí `AUTH`. JSON i SSE odpověď musí mít ID odeslaného požadavku; boolean `true` není číselné ID `1`. Při čtení tokenu z podporované TOML sekce může být hodnota v dvojitých uvozovkách i apostrofech.

Oprava z 2. 11. 2026 vyžaduje právě jedno z polí `result` a `error`: výsledek musí být objekt, chyba musí mít celočíselný `code` a textový `message`. Handshake kontroluje typy povinných polí a seznam nástrojů. `tools/call` vyžaduje pole `content`, objekty s textovým `type`, textový `text` u textových bloků a případné boolean `isError`. Vadné tvary skončí `TRANSPORT` / 3 místo pádu nebo falešného `OK`. Platné prázdné `content: []` zůstává povolené; platné chyby serveru a nástroje zachovávají kódy 4 a 5. Syntetické regresní testy pokrývají JSON i SSE. Jde o kontrolu polí používaných diagnostikou, nikoli úplnou validaci všech vnořených MCP schémat.

Token endpoint musí vrátit JSON objekt a při HTTP 200 neprázdný textový `access_token`. Pokud odpověď obsahuje `refresh_token`, musí být také neprázdný text; jeho vynechání zůstává povolené. Vadný tvar skončí `TRANSPORT` / 3; při obnově uloženého tokenu se místo pádu spustí přihlášení v prohlížeči. Chybová OAuth odpověď v objektu při HTTP mimo 200 dál končí `AUTH` / 2. Syntetické regresní testy ověřují i tento fallback a zachování prvního tokenu při vadné odpovědi na `--check-refresh`.

Oprava z 23. 11. 2026: `token_endpoint` a `authorization_endpoint` z OAuth discovery musí mít schéma `https`, přesně hostitele `medplum.test.dokturek.ai` a výchozí port 443, bez userinfo, fragmentu, zpětného lomítka a bílých či řídicích znaků. Jinak skript skončí `AUTH` / 2 dřív, než přečte uložený refresh token, takže ho ani autorizační kód nepošle jinam. Syntetické regresní testy pokrývají podvržené hostitele (cizí doména přidaná za `medplum.test.dokturek.ai` nebo před něj), `http://`, userinfo, jiný port a relativní URL a ověřují, že se úložiště tokenů vůbec nečte.

Souhrnný výpis FHIR metadat uvádí pouze typ zdroje a `fhirVersion`. Volitelné pole `software` nečte, takže jeho nečekaný tvar neshodí povinnou ani diagnostickou cestu. Kontrola tím není úplnou validací FHIR zdroje.

```bash
python3 -m unittest discover -s tools/mcp-smoke/tests -p 'test_*.py' -v
```

## 6. Co zbývá ověřit (Petrův Mac)

```bash
python3 tools/mcp-smoke/mcp-smoke.py coolify
```

```bash
python3 tools/mcp-smoke/mcp-smoke.py medplum --check-refresh
```

Očekávaný výsledek:

- Coolify: všechny kroky `OK`.
- Medplum: `fhir-request GET metadata` vrátí `CapabilityStatement`. Výsledek `--check-refresh` vyhodnoť zvlášť. `FAIL AUTH … Invalid client` znamená, že server obnovu odmítl, a skript skončí kódem 2.
- Pokud se vrátí `PROTOCOL -32603`, zaznamenej čas a dostupné ID požadavku a porovnej je s logy serveru a konektoru.

V cloudové session 29. 10. nebyl k dispozici `COOLIFY_API_TOKEN` ani přihlášení do Medplumu v prohlížeči. Proto se volání nástrojů s reálnými tokeny zatím neprovedla [N].

## 7. Odhlášení a odebrání

Uložený refresh token Medplumu, token Coolify a připojení osobních agentů odstraníš podle [RISK.md → Vypnutí a odvolání přístupu](RISK.md#vypnutí-a-odvolání-přístupu). Most pro Claude Desktop v `medplum-mcp` používá klienta `dokturek-claude-code-dev`, ne `dokturek-claude-desktop-dev`.
