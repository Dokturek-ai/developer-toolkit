# medplum-mcp

Připojí tvého agenta k MCP serveru Medplumu v prostředí dev-pre-production (`https://medplum.test.dokturek.ai`). Agent pak čte a mění FHIR data s oprávněními tvého Medplum účtu.

Než začneš, přečti [RISK.md](RISK.md). Nástroj umí i mazat.

## Co server nabízí

| Tool | Co dělá |
|---|---|
| `fhir-request` | Požadavky na FHIR R4 API podle oprávnění účtu: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`. `path` je relativní k `/fhir/R4/`, např. `metadata` nebo `CodeSystem?_summary=count`. Prázdná `path` míří na base URL (batch a transaction Bundle). |
| `search`, `fetch` | Nástroje pro kompatibilitu s ChatGPT. Pro vyhledávání FHIR dat použij `fhir-request`. |

## Předpoklady

- Účet v Medplumu dev-pre-production (přihlášení na `app.test.dokturek.ai`).
- Claude Code s podporou pluginů. Plugin prošel `claude plugin validate --strict` na 2.1.290, 2.1.310 a 2.1.330.
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

Instalátor ve verzi 0.1.1 při odlišné existující konfiguraci nevypisuje její obsah, který může obsahovat secrets. Náhradu musíš výslovně povolit přepínačem `--force`; bez něj se konfigurace nezmění ani s `--apply`.

Od verze 0.2.0 instalátor:

- odmítne neplatný JSON, JSON, který není objekt, i `mcpServers`, které není objekt. Vypíše srozumitelnou chybu bez obsahu souboru, skončí kódem 4 a nic nezapíše,
- u konfigurace, která je symlink (např. z dotfiles), zapíše do cíle symlinku a symlink zachová; zálohu vytvoří vedle cíle. Symlink na neexistující soubor odmítne,
- zapíše konfiguraci i zálohu s oprávněním `0600`.

### Codex

1. Přidej do `~/.codex/config.toml` obsah [`clients/codex.toml`](clients/codex.toml). Pokud už máš sekci `[mcp_servers.dokturek-medplum-dev]`, uprav ji na místě. Ukázka obsahuje URL serveru i nastavení OAuth callbacku.
2. Přihlas se:

   ```bash
   codex mcp login dokturek-medplum-dev --oauth-client-registration dcr --scopes openid,profile
   ```

3. Hook pro potvrzení zápisů je jen v Claude Code pluginu. V Codexu zápisy hlídáš schvalováním tool callů.

Callback URL v `codex.toml` končí ID odvozeným z URL serveru (prvních 9 bajtů SHA-256 v base64url). Pro všechny je stejné, dokud se URL nezmění.

### ChatGPT

Pokud už máš v aplikaci připojení Doktůrek Medplum, přihlas se přes něj a použij čtecí dotaz z kroku 3 níže. Každé nové spojení vyžaduje registraci jeho přesné callback URL na serveru. [Nastavení ChatGPT a OAuth klienta](https://github.com/Dokturek-ai/dokturek-medplum/blob/main/integrations/openai/README.md#chatgpt)

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

Smoke test FHIR data jen čte. Jedinou záměrnou výjimkou z pravidla „jen `GET`“ je sonda DCR: `POST /oauth2/register` bez tokenu pro každou očekávanou callback URL. Medplum při ní nic neregistruje, jen podle callback URL vrátí existujícího klienta. Další `POST` jde jen na MCP endpoint jako JSON-RPC (`initialize` bez tokenu, s `--e2e` přes most `initialize`, `tools/list` a `tools/call` s `GET`).

`--e2e` se přihlašuje přes most, takže token skončí v `~/.mcp-auth/` stejně jako u Claude Desktopu a Claude Desktop ho pak hodinu používá. Log mostu v dočasném adresáři skript po úspěšném běhu smaže. Při chybě ho nechá pro diagnostiku a vypíše cestu; po přečtení ho smaž.

## Řešení problémů

| Příznak | Pravděpodobná příčina | Co udělat |
|---|---|---|
| Plugin server v `/mcp` chybí nebo je skrytý | Ruční konfigurace se stejným URL má přednost | Odeber ruční server (krok 1 u pluginu) |
| Prohlížeč hlásí `Invalid redirect URI` | Klient poslal callback, který server nezná | Zkontroluj port 1458 (Claude) nebo 1457 (Codex). Kdo port drží: `lsof -nP -iTCP:1458 -sTCP:LISTEN` |
| Server se v Claude Desktopu nespustí | Desktop nenajde `npx` | Spusť instalační skript znovu, nastaví absolutní cestu |
| Po hodině je potřeba nové přihlášení | Známé omezení Medplumu, viz níže | Přihlas se znovu (`/mcp`, restart Claude Desktopu, `codex mcp login`) |
| Most v Claude Desktopu nebo `smoke_test.py --e2e` padá s `Invalid client` | V `~/.mcp-auth/` zůstal refresh token ze starší konfigurace, která žádala `offline_access` (současná šablona ho nežádá) | Přesuň `~/.mcp-auth/mcp-remote-v1/13e0418b9b881fb80d3e1bb146eebf29_tokens.json` do koše a restartuj Desktop |
| Instalační skript skončí s „Claude Desktop běží“ | Desktop by změnu přepsal | Ukonči Desktop (Cmd+Q) a spusť skript znovu |
| Hook zamítl `fhir-request` s hláškou „může opustit /fhir/R4/“ | `path` je absolutní URL nebo obsahuje `..` či kódovaný znak; server sám takovou cestu neodmítne (viz RISK.md) | Použij cestu relativní k `/fhir/R4/` |

## Známé omezení

U výchozích OAuth klientů z `MEDPLUM_DEFAULT_OAUTH_CLIENTS` se na Medplumu 5.2.15 bez opravy podařilo lokálně reprodukovat chybu obnovy tokenu `Invalid client`. Oprava je v `dokturek-medplum`. Její nasazení a obnova relace v připojené aplikaci zatím zůstávají neověřené. [Oprava a ověření](https://github.com/Dokturek-ai/dokturek-medplum/pull/40)

Konfigurace v tomto nástroji (Claude Code plugin i ruční, most pro Claude Desktop, Codex) žádají scope `openid profile` bez `offline_access`. Po vypršení access tokenu se přihlas znovu. Pokud most `mcp-remote` použije starý refresh token z dřívější konfigurace a vrátí `Invalid client`, postupuj podle tabulky výše. Diagnostický skript [`mcp-smoke`](../mcp-smoke/README.md) naopak `offline_access` žádá a refresh token ukládá do macOS Keychainu nebo libsecret, ne do `~/.mcp-auth/`.

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
| Medplum | `5.2.15-4d86215`, verze hlášená testovacím serverem 19. 11. 2026 |
| OAuth | authorization code + PKCE (S256), veřejní klienti bez secretu |
| Scope | `openid profile` |
| Platnost access tokenu | 1 hodina; konfigurace toolkitu nežádá `offline_access` a refresh token nepoužívá (viz Známé omezení) |

| Client ID | Redirect URI | Používá |
|---|---|---|
| `dokturek-claude-code-dev` | `http://localhost:1458/callback`, `http://127.0.0.1:1458/callback` | Claude Code, most pro Claude Desktop, diagnostika `mcp-smoke` |
| `dokturek-claude-desktop-dev` | `https://claude.ai/api/mcp/auth_callback`, `https://claude.com/api/mcp/auth_callback` | konektor v claude.ai |
| `dokturek-codex-dev` | `http://127.0.0.1:1457/callback/uAEkM6bonMJI` | Codex |

Registrace klientů žije na straně serveru — v `integrations/openai/oauth-clients.dev.json` v repu `Dokturek-ai/dokturek-medplum`, odkud se kopíruje do proměnné `MEDPLUM_DEFAULT_OAUTH_CLIENTS` v Coolify. Nový klient nebo redirect je změna tam, ne tady.
