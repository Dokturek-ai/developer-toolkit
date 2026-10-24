# medplum-mcp

Připojí tvého agenta k MCP serveru Medplumu v prostředí dev-pre-production (`https://medplum.test.dokturek.ai`). Agent pak čte a mění FHIR data s oprávněními tvého Medplum účtu.

Než začneš, přečti [RISK.md](RISK.md). Nástroj umí i mazat.

## Co server nabízí

| Tool | Co dělá |
|---|---|
| `fhir-request` | Libovolný požadavek na FHIR R4 API: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`. `path` je relativní k `/fhir/R4/`, např. `Patient?name=Novak` nebo `metadata`. Prázdná `path` míří na base URL (batch a transaction Bundle). |
| `search`, `fetch` | V Medplum 5.2.1 vrací jen zástupný dokument — existují kvůli kompatibilitě s ChatGPT. Pro FHIR dotazy je nepoužívej. |

## Předpoklady

- Účet v Medplumu dev-pre-production (přihlášení na `app.test.dokturek.ai`).
- Claude Code s podporou pluginů. Plugin prošel `claude plugin validate --strict` na 2.1.290 a 2.1.310.
- Pro hook, který hlídá zápisy, `sh` a `python3` (macOS a Linux). Bez `python3` se hook ptá u každého volání.
- Pro Claude Desktop Node.js (`npx`) a `python3`.
- Pro Codex Codex CLI (konfigurace odpovídá verzi 0.163.0).

## Nastavení

Pro každého klienta vyber jednu cestu. Callback porty jsou pevné — server zná jen redirecty na portu 1458 (Claude) a 1457 (Codex).

### Claude Code — plugin (doporučeno)

Jen plugin má hook, který před každým zápisem žádá potvrzení.

1. Pokud máš Medplum MCP přidaný ručně (např. `dokturek-medplum-dev`), odeber ho. Ruční konfigurace se stejným URL má přednost a Claude Code by plugin server skryl jako duplicitu — a s ním i hook.

   ```bash
   claude mcp remove dokturek-medplum-dev -s user
   ```

2. Přidej marketplace a nainstaluj plugin:

   ```text
   /plugin marketplace add Dokturek-ai/developer-toolkit
   /plugin install medplum-mcp@dokturek-dev-toolkit
   ```

3. Spusť `/mcp`, vyber `plugin:medplum-mcp:medplum-dev` a přihlas se. Otevře se prohlížeč s přihlášením do Medplumu.

Přihlášení vydrží hodinu, pak ho v `/mcp` zopakuješ. Proč, popisuje [Známé omezení](#známé-omezení).

### Claude Code — ruční konfigurace

Bez pluginu nemáš hook a zápisy hlídáš jen schvalováním v Claude Code.

```bash
claude mcp add-json dokturek-medplum-dev \
  '{"type":"http","url":"https://medplum.test.dokturek.ai/mcp/stream","oauth":{"clientId":"dokturek-claude-code-dev","callbackPort":1458,"scopes":"openid profile"}}' \
  --scope user
```

Pak `/mcp` a přihlášení.

### Claude Desktop — stdio most

Claude Desktop nepřipojí vzdálený server zapsaný přímo v `claude_desktop_config.json` a vlastní konektory můžou být v organizaci povolené jen adminům. Proto se server spouští přes most `mcp-remote`, připnutý na verzi 0.14.3.

1. Podívej se, co skript změní. Nic nezapisuje:

   ```bash
   python3 tools/medplum-mcp/scripts/install_claude_desktop.py
   ```

2. Úplně ukonči Claude Desktop (Cmd+Q). Běžící Desktop si drží vlastní kopii konfigurace a změnu by přepsal, proto skript zápis za běhu odmítne.
3. Zapiš konfiguraci. Skript předtím vytvoří zálohu `claude_desktop_config.json.bak-<čas>`:

   ```bash
   python3 tools/medplum-mcp/scripts/install_claude_desktop.py --apply
   ```

4. Spusť Claude Desktop. Most otevře prohlížeč s přihlášením do Medplumu. Po přihlášení má Claude v chatu nástroje Medplumu.
5. U `fhir-request` nepovoluj trvalé schválení. Hook tu neplatí, zápisy hlídáš jen ty.

Most ukládá tokeny do `~/.mcp-auth/`. Most i Claude Code používají callback port 1458 — nepřihlašuj se v obou ve stejnou chvíli.

### Codex

1. Přidej do `~/.codex/config.toml` obsah [`clients/codex.toml`](clients/codex.toml).
2. Přihlas se:

   ```bash
   codex mcp login dokturek-medplum-dev --oauth-client-registration dcr --scopes openid,profile
   ```

3. Hook pro potvrzení zápisů je jen v Claude Code pluginu. V Codexu zápisy hlídáš schvalováním tool callů.

Callback URL v `codex.toml` končí ID odvozeným z URL serveru (prvních 9 bajtů SHA-256 v base64url). Pro všechny je stejné, dokud se URL nezmění.

### ChatGPT

Callback ChatGPT konektoru je jiný pro každé spojení, takže každé nové spojení vyžaduje registraci redirectu na serveru. Toolkit tuhle cestu nepokrývá.

## Ověření

1. Kontroly bez přihlášení — healthcheck, 401 bez tokenu, OAuth discovery, registrace klientů:

   ```bash
   python3 tools/medplum-mcp/scripts/smoke_test.py
   ```

2. Celá cesta přes most včetně přihlášení a jednoho čtecího dotazu:

   ```bash
   python3 tools/medplum-mcp/scripts/smoke_test.py --e2e
   ```

3. V agentovi zadej:

   > Přes Medplum `fhir-request` proveď GET na relativní cestu `CodeSystem?_summary=count`. Vypiš počet číselníků, nic neměň.

   Výsledek je `Bundle` typu `searchset` s vyplněným `total`.

Smoke test posílá jen čtecí požadavky. `--e2e` se přihlašuje přes most, takže token skončí v `~/.mcp-auth/` stejně jako u Claude Desktopu a Claude Desktop ho pak hodinu používá.

## Řešení problémů

| Příznak | Pravděpodobná příčina | Co udělat |
|---|---|---|
| Plugin server v `/mcp` chybí nebo je skrytý | Ruční konfigurace se stejným URL má přednost | Odeber ruční server (krok 1 u pluginu) |
| Prohlížeč hlásí `Invalid redirect URI` | Klient poslal callback, který server nezná | Zkontroluj port 1458 (Claude) nebo 1457 (Codex). Kdo port drží: `lsof -nP -iTCP:1458 -sTCP:LISTEN` |
| Server se v Claude Desktopu nespustí | Desktop nenajde `npx` | Spusť instalační skript znovu, nastaví absolutní cestu |
| Po hodině je potřeba nové přihlášení | Známé omezení Medplumu, viz níže | Přihlas se znovu (`/mcp`, restart Claude Desktopu, `codex mcp login`) |
| Most v Claude Desktopu nebo `smoke_test.py --e2e` padá s `Invalid client` | V `~/.mcp-auth/` zůstal refresh token ze starší konfigurace | Přesuň `~/.mcp-auth/mcp-remote-v1/13e0418b9b881fb80d3e1bb146eebf29_tokens.json` do koše a restartuj Desktop |
| Instalační skript skončí s „Claude Desktop běží“ | Desktop by změnu přepsal | Ukonči Desktop (Cmd+Q) a spusť skript znovu |
| `fhir-request` vrací `Invalid path` | `path` je absolutní URL | Použij cestu relativní k `/fhir/R4/` |

## Známé omezení

Obnova tokenu přes refresh token u Medplum klientů z `MEDPLUM_DEFAULT_OAUTH_CLIENTS` nefunguje. Grant `refresh_token` v Medplumu hledá klienta jen v databázi (`systemRepo.readResource` v `handleRefreshToken`, `packages/server/src/oauth/token.ts`), ne mezi výchozími klienty z konfigurace — a vrátí `Invalid client`. Týká se to Medplum 5.2.1 i aktuální verze 5.2.8. Authorization code flow funguje, protože používá `getClientApplication`.

Nástroj proto žádá scope `openid profile` bez `offline_access`. Klient tak refresh token nedostane a po vypršení access tokenu (1 hodina) se přihlásí znovu, místo aby opakovaně narážel na chybu. S `offline_access` most `mcp-remote` při každém startu spadne, dokud token ručně nesmažeš.

Až bude oprava v Medplumu nasazená, vrátí se `offline_access` do scope a přihlášení bude vydržet.

## Odhlášení a odebrání

- Claude Code plugin: v `/mcp` vyber server a zvol odhlášení (Clear authentication). Plugin odinstaluješ přes `/plugin`.
- Claude Code ruční konfigurace: `claude mcp logout dokturek-medplum-dev`, odebrání `claude mcp remove dokturek-medplum-dev -s user`.
- Claude Desktop: `python3 tools/medplum-mcp/scripts/install_claude_desktop.py --remove --apply`. Tokeny mostu jsou v `~/.mcp-auth/mcp-remote-v1/` v souborech s prefixem `13e0418b9b881fb80d3e1bb146eebf29` (MD5 URL serveru) — přesuň je do koše.
- Codex: `codex mcp logout dokturek-medplum-dev`.

Smazání tokenu na disku nezneplatní relaci na serveru. Při podezření na únik postupuj podle [SECURITY.md](../../SECURITY.md).

## Technické detaily

| | |
|---|---|
| Endpoint | `https://medplum.test.dokturek.ai/mcp/stream` (Streamable HTTP) |
| Medplum | 5.2.1 |
| OAuth | authorization code + PKCE (S256), veřejní klienti bez secretu |
| Scope | `openid profile` |
| Platnost access tokenu | 1 hodina, refresh token se nepoužívá (viz Známé omezení) |

| Client ID | Redirect URI | Používá |
|---|---|---|
| `dokturek-claude-code-dev` | `http://localhost:1458/callback`, `http://127.0.0.1:1458/callback` | Claude Code, most pro Claude Desktop |
| `dokturek-claude-desktop-dev` | `https://claude.ai/api/mcp/auth_callback`, `https://claude.com/api/mcp/auth_callback` | konektor v claude.ai |
| `dokturek-codex-dev` | `http://127.0.0.1:1457/callback/uAEkM6bonMJI` | Codex |

Registrace klientů žije na straně serveru — v `integrations/openai/oauth-clients.dev.json` v repu `Dokturek-ai/dokturek-medplum`, odkud se kopíruje do proměnné `MEDPLUM_DEFAULT_OAUTH_CLIENTS` v Coolify. Nový klient nebo redirect je změna tam, ne tady.
