# AGENTS.md

Pravidla pro AI agenty (Claude Code, Codex), kteří v tomhle repu pracují.

Repo obsahuje nástroje s přístupem k datům a k Medplumu. Každou změnu ber jako bezpečnostně citlivou.

- Nepřidávej tokeny, secrets, klíče ani data pacientů, ani jako příklad. Příklady musí být zjevně syntetické.
- Nepřidávej nové hostitele ani prostředí bez výslovného pokynu. Allowlist je v `scripts/check_repo.py`.
- Neoslabuj ochrany (hook pro potvrzení zápisů, připnuté verze, allowlist hostitelů) bez výslovného pokynu. Když je měníš, uprav i `RISK.md`.
- Když měníš konfiguraci nástroje, uprav jeho `README.md` a `RISK.md` ve stejném commitu a zvyš verzi v `plugin.json` i v `marketplace.json`.
- Při ověřování proti Medplumu posílej jen čtecí požadavky (`GET`). Smoke testy jsou read-only a tak to má zůstat.
- Před commitem spusť `python3 scripts/check_repo.py` a `for d in tools/*/tests; do python3 -m unittest discover -s "$d" -p 'test_*.py'; done`.
- Skripty musí běžet na Pythonu 3.9 (systémový `python3` na macOS) jen se standardní knihovnou.
- Dokumentace je česky, tykáním, technické termíny anglicky. Kód a identifikátory anglicky.
