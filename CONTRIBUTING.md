# Přidání nebo změna nástroje

## Co sem patří

Nástroj, který čte nebo mění data, přihlašuje se k našim systémům nebo jinak může napáchat škodu: MCP server, konfigurace agenta, skript, agent. Skill nebo plugin bez přístupu k datům patří do [plugin-marketplace-healthcare-dev](https://github.com/Dokturek-ai/plugin-marketplace-healthcare-dev).

## Postup

1. Zkopíruj `tools/_template/` do `tools/<nazev>/`. Název je kebab-case a stejný jako název pluginu.
2. Vyplň `README.md` a `RISK.md`. Všechny sekce `RISK.md` jsou povinné, kontrola v CI hlídá jejich nadpisy.
3. Konfiguraci drž bez secrets. Verze balíčků připni (`balicek@1.2.3`, nikdy `@latest`). Hostitelé musí být v allowlistu v `scripts/check_repo.py`.
4. Pokud je nástroj Claude Code plugin, přejmenuj `.claude-plugin/plugin.json.example` na `plugin.json`, vyplň ho a přidej záznam do `.claude-plugin/marketplace.json`.
5. Přidej řádek do tabulky nástrojů v hlavním `README.md`.
6. Spusť kontroly:

   ```bash
   python3 scripts/check_repo.py
   for d in tools/*/tests; do python3 -m unittest discover -s "$d" -p 'test_*.py'; done
   claude plugin validate . --strict
   claude plugin validate tools/<nazev> --strict
   ```

7. Vyzkoušej nástroj lokálně proti testovacímu prostředí. V PR popiš, co přesně jsi ověřil, jakým příkazem a s jakým výsledkem.
8. Otevři PR. Review dělá vlastník z `.github/CODEOWNERS`, merge je squash.

## Verzování

Každá změna nástroje zvyšuje `version` v jeho `plugin.json` i ve stejném záznamu v `marketplace.json` (semver). Bez zvýšení verze se změna kolegům v Claude Code nemusí projevit.

## Nový hostitel nebo prostředí

Přidání hostitele do allowlistu je bezpečnostní změna. Patří do samostatného commitu se zdůvodněním v PR a s aktualizovaným `RISK.md` nástroje. Produkční prostředí do toolkitu nepřidávej bez samostatného rozhodnutí týmu.
