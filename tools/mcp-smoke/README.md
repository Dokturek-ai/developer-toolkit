# Připojení agentů k MCP serverům Coolify a Medplum dev

> Interní vývojářský nástroj přesunutý z `dokturek-docs` PR #21 (revize `3154d8025710e60b526ebc62de0e4149ea751d57`) dne 30. 10. 2026. Před použitím si přečti [RISK.md](RISK.md); skript má známá omezení a živé ověření zůstává otevřené. Příkazy níže spouštěj z kořene `developer-toolkit`.

> **Datum:** 2026-10-29. **Stav:** konfigurace a ověřovací skript jsou hotové. Ověření end-to-end s reálnými tokeny čeká na běh na Petrově Macu (§6).
> **Značky:** [Z] zjištěno (kód, odpověď serveru, test), [N] neověřeno, [P] návrh.
> **Zdroje:** Medplum `v5.2.1` (`e0db1fc`, stejný build hlásí `/healthcheck`), `@modelcontextprotocol/sdk` 1.30.1 (verze pinovaná v Medplum serveru), `Dokturek-ai/dokturek-medplum` `18b53e7` (`integrations/openai/`), Claude Code 2.1.312.

## 1. Servery

| Server | URL | Transport | Autentizace |
|---|---|---|---|
| Coolify self-hosted | `https://coolify.infra.dokturek.ai/mcp` | Streamable HTTP | `Authorization: Bearer <COOLIFY_API_TOKEN>` |
| Medplum dev | `https://medplum.test.dokturek.ai/mcp/stream` | Streamable HTTP, bezstavový (bez `Mcp-Session-Id`) | OAuth 2.0 Authorization Code + PKCE S256, scope `openid profile offline_access` |

Odpovědi z 29. 10. 2026 bez tokenu [Z]:

- Coolify `initialize` vrací `401` a `WWW-Authenticate: Bearer realm="mcp", error="invalid_token"`.
- Medplum `/healthcheck` vrací `200` s verzí `5.2.1-e0db1fc` a Postgres i Redis jsou OK. `initialize` vrací `401` s `OperationOutcome` `login`, ne `404`, takže MCP je zapnuté.
- Discovery `/.well-known/oauth-authorization-server` inzeruje `S256` a `registration_endpoint`. `offline_access` mezi `scopes_supported` chybí.

## 2. OAuth klienti Medplum dev

Medplum 5.2.1 při DCR (`/oauth2/register`) nic neregistruje. Podle první `redirect_uri` jen vyhledá klienta v `MEDPLUM_DEFAULT_OAUTH_CLIENTS` (`packages/server/src/oauth/register.ts`). Seznam je v `dokturek-medplum/integrations/openai/oauth-clients.dev.json`:

| Agent | `client_id` | Přesná callback URL |
|---|---|---|
| Claude Code | `dokturek-claude-code-dev` | `http://localhost:1458/callback` (povolená je i `http://127.0.0.1:1458/callback`) |
| Claude Desktop / claude.ai | `dokturek-claude-desktop-dev` | `https://claude.ai/api/mcp/auth_callback`, `https://claude.com/api/mcp/auth_callback` |
| Codex CLI | `dokturek-codex-dev` | `http://127.0.0.1:1457/callback/uAEkM6bonMJI` |
| ChatGPT | `dokturek-chatgpt-dev` | `https://chatgpt.com/connector/oauth/nSvqXqv_vpdT` |

Všichni jsou veřejní klienti bez secretu, s povinným PKCE a výchozím scope `openid profile offline_access`.

Živá DCR sonda 29. 10. [Z]: `http://localhost:9615` vrací `medplum-cli` a `https://claude.ai/api/mcp/auth_callback` vrací `dokturek-claude-desktop-dev`. Neznámé callbacky vracejí `400 Invalid redirect URI`, například `http://localhost:1455/auth/callback` nebo `http://localhost:6274/oauth/callback` (MCP Inspector).

**Jiný typ agenta** potřebuje vlastní záznam v `oauth-clients.dev.json` s přesnou callback URL bez wildcardu. Pak se zkopíruje do `MEDPLUM_DEFAULT_OAUTH_CLIENTS` v Coolify (build i runtime) a stack se znovu nasadí (`integrations/openai/README.md`). Bez toho DCR vrátí `400`.

## 3. Konfigurace Claude Code (user scope, tokeny mimo repozitář)

```bash
claude mcp add-json --scope user coolify-selfhosted '{"type":"http","url":"https://coolify.infra.dokturek.ai/mcp","headers":{"Authorization":"Bearer ${COOLIFY_API_TOKEN}"}}'
```

```bash
claude mcp add-json --scope user dokturek-medplum-dev '{"type":"http","url":"https://medplum.test.dokturek.ai/mcp/stream","oauth":{"clientId":"dokturek-claude-code-dev","callbackPort":1458,"scopes":"openid profile offline_access"}}'
```

- `${COOLIFY_API_TOKEN}` se rozvine až při připojení. Do `~/.claude.json` se zapíše jen zástupný text. Ověřeno lokálním echo serverem: Claude Code 2.1.312 poslal `Bearer <hodnota proměnné>` [Z]. Token stačí exportovat v shellu, ze kterého se `claude` spouští. Na Macu ho lze vzít z Keychainu, nikdy ne z repozitáře.
- Medplum: přihlášení se spouští z `/mcp`, callback je `http://localhost:1458/callback`. `oauth.scopes` přepíše scope z discovery, protože ten `offline_access` neobsahuje. Tokeny ukládá Claude Code ve vlastním úložišti, na macOS v Keychainu [N, dokumentace to pro MCP tokeny výslovně neuvádí]. `claude mcp get dokturek-medplum-dev` po přidání ukazuje `Needs authentication` a `client_id configured, callback_port 1458` [Z].
- Port 1458 nesmí současně používat jiný klient (například most `mcp-remote` pro Claude Desktop).
- Ostatní agenti: Codex používá `[mcp_servers.dokturek-medplum-dev.oauth]` s `callback_port = 1457` a `codex mcp login … --scopes openid,profile,offline_access`. Claude Desktop používá nativní konektor. ChatGPT používá vlastní MCP spojení s `token_endpoint_auth_method=none`. Postupy jsou v `dokturek-medplum/integrations/openai/README.md`.

## 4. Nálezy k chybě `-32603 Internal error`

### N1. Cesta `/fhir/R4/metadata` se zdvojí [Z]

`fhir-request` volá `concatUrls(<base>/fhir/R4, path)` (`packages/server/src/mcp/server.ts`). `concatUrls` odstraní úvodní lomítko (`packages/core/src/utils.ts:1483`), takže z `/fhir/R4/metadata` vznikne `<base>/fhir/R4/fhir/R4/metadata`.

**Správná hodnota je `path: "metadata"`.** Cesty jsou relativní k `/fhir/R4/`.

Na replice se stejným SDK skončí zdvojená cesta jako chyba nástroje (`isError: true`), ne jako `-32603`.

### N2. `search` a `fetch` jsou atrapy [Z]

Oba nástroje vždy vracejí pevný `dummy-doc` a na serveru nemají jak selhat. Existují jen kvůli požadavku ChatGPT. Pro FHIR dotazy se používá pouze `fhir-request`.

### N3. Server Medplum `-32603` u `tools/call` nevrací [Z]

SDK 1.30.1 výjimku z handleru nástroje převede na výsledek s `isError: true` (`dist/cjs/server/mcp.js:144`). Neznámý nástroj skončí také jako `isError` (`-32602` v textu).

Replika `mcp/routes.ts` a `mcp/server.ts` (bezstavový `StreamableHTTPServerTransport`) to potvrdila: `initialize`, `notifications/initialized` (`202`), `tools/list` i `search` prošly.

Protože `search` selhat nemůže, **`-32603` hlášené u `search` i `fhir-request` téměř jistě vzniká v hostitelském konektoru**. Konektor tak hlásí neúspěšné volání na upstream [P].

### N4. Refresh token pro výchozí klienty nefunguje (Medplum 5.2.1–5.2.8) [Z]

`handleRefreshToken` čte klienta přes `systemRepo.readResource('ClientApplication', …)` (`packages/server/src/oauth/token.ts`). Klienti z `defaultOAuthClients` v databázi nejsou, takže výsledkem je `invalid_request: Invalid client`.

Refresh token se vydá, ale nedá se použít. Po vypršení access tokenu (výchozí doba 1 h [N pro toto nasazení]) konektor nemá jak token obnovit. Nejpravděpodobnější vysvětlení `-32603` je tedy **chyba autentizace maskovaná konektorem** [P]: připojení a `tools/list` proběhnou s čerstvým tokenem, pozdější volání nástrojů selžou.

Ověří se to během pod §6: po čerstvém přihlášení musí `fhir-request GET metadata` projít a `--check-refresh` musí vrátit `Invalid client`.

**Náprava [P]**, jedna z možností:

1. upstream oprava `token.ts` (`getClientApplication` místo `readResource`) a upgrade Medplumu;
2. pro dev založit `ClientApplication` jako skutečný zdroj v Projectu se stejnými `redirectUris` a agentům dát jeho `id`. DCR se pak nepoužije, protože `client_id` je pevné.

Do té doby počítat s novým přihlášením po vypršení access tokenu.

## 5. Ověřovací skript `mcp-smoke.py`

Skript potřebuje jen standardní knihovnu Pythonu 3.9+ (systémový `python3` na macOS stačí). Provádí jen čtecí operace a tokeny nikdy nevypisuje.

| Cíl | Postup |
|---|---|
| `coolify` | Token vezme z `$COOLIFY_API_TOKEN`, jinak ze sekce `[mcp_servers.coolify-selfhosted.http_headers]` v `~/.codex/config.toml`. Pak `initialize` → `notifications/initialized` → `tools/list` → `get_current_team` a `get_infrastructure_overview`. |
| `medplum` | Discovery (kontrola `S256`) → přihlášení v prohlížeči (Authorization Code + PKCE S256, `state`, kontrola `iss`) → výměna kódu → refresh token do macOS Keychainu (`security -i`, hodnota nejde přes argv), na Linuxu do libsecret → handshake → `fhir-request GET metadata`. Pro srovnání s N1 zavolá i `GET /fhir/R4/metadata`, to jen jako varování. |

Rozlišení chyb (návratový kód):

| Třída | Kód | Kdy |
|---|---|---|
| `AUTH` | 2 | HTTP 401/403 (s `WWW-Authenticate`), chyba token endpointu, nesoulad `state` nebo `iss`, chybějící token |
| `TRANSPORT` | 3 | DNS, TLS, spojení, timeout; HTTP mimo 200/202 (404, 406, 5xx); tělo, které není JSON-RPC; chybějící odpověď v SSE |
| `PROTOCOL` | 4 | JSON-RPC objekt `error` (například `-32603`, `-32602`) |
| `TOOL` | 5 | `result.isError: true` nebo nástroj chybí v `tools/list` |

Skript je ověřený proti lokální replice Medplum MCP (SDK 1.30.1) a Coolify [Z]. Rozlišil platný token, `401` jako `AUTH`, odmítnuté spojení jako `TRANSPORT` a výjimku i neznámý nástroj jako `TOOL`.

## 6. Co zbývá ověřit (Petrův Mac)

```bash
python3 tools/mcp-smoke/mcp-smoke.py coolify
```

```bash
python3 tools/mcp-smoke/mcp-smoke.py medplum --check-refresh
```

Očekávaný výsledek:

- Coolify: všechny kroky `OK`.
- Medplum: `fhir-request GET metadata` vrátí `CapabilityStatement`, `GET /fhir/R4/metadata` skončí jako `WARN … TOOL` (N1) a `refresh_token grant` skončí jako `FAIL AUTH … Invalid client` (N4), takže skript skončí kódem 2.
- Pokud Medplum hned po přihlášení vrátí `PROTOCOL -32603`, hypotéza N4 neplatí a chyba je na straně serveru. Pak je potřeba dohledat `x-request-id` v logu Medplumu.

V cloudové session 29. 10. nebyl k dispozici `COOLIFY_API_TOKEN` ani přihlášení do Medplumu v prohlížeči. Proto se volání nástrojů s reálnými tokeny zatím neprovedla [N].
