# Bezpečnost

## Co do repa nikdy nepatří

- tokeny, client secrets, API klíče, hesla, privátní klíče
- data pacientů ani exporty dat z jakéhokoli prostředí
- osobní vazby na účty, třeba ID tvé ChatGPT aplikace — patří do tvé lokální konfigurace
- produkční endpointy

`scripts/check_repo.py` a gitleaks v CI zachytí nejčastější případy. Úplnou ochranu nedávají.

## Podezření na únik nebo zneužití

1. Přestaň nástroj používat.
2. Odhlas klienta podle sekce „Odhlášení a odebrání“ v README nástroje.
3. Dej vědět vlastníkovi nástroje (uvedený v jeho `RISK.md`) napřímo, ne ve veřejném kanálu.
4. Vlastník rozhodne o zásahu na straně serveru podle sekce „Vypnutí a odvolání přístupu“ v `RISK.md`.

Když unikl token, nestačí ho smazat z disku. Nech vlastníka zneplatnit relace na serveru.

## Hlášení zranitelnosti

Napiš vlastníkovi nástroje. Uveď nástroj a verzi (`version` v `plugin.json`), klienta a jeho verzi, co se stalo a kdy. Nepřikládej tokeny ani data.
