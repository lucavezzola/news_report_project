# Rassegna Audio v2 — note di implementazione

Stato rispetto al piano: **Fasi 0-4 implementate** (audio, sottotitoli, fonti, notifica).
Fasi 5 (mappa), 6 (entità/immagini) e 7 (rifinitura) non ancora fatte: il manifest e il
JSON di sintesi riservano già i campi (`entita`, `luoghi` per frase), il sito li ignora.

## Flusso
    python main.py                     # tutto
    python main.py --da-fase 3         # riusa notizie e parlato su disco
    python main.py --da-fase 1 --solo-sezione Esteri
    python main.py --no-deploy --no-telegram
    python main.py --usa-fixture --data 2099-01-01 --audio-finto --no-deploy --no-telegram
    python -m pytest                   # test unitari (senza rete né GPU)

Il sito generato in locale sta in `output/sito/t/<token>/` (aprire `index.html` del giorno
con un server statico: `python -m http.server -d output/sito`).

## Setup nuovo
1. `pip install -r requirements.txt` (jinja2 è nuovo).
2. `.env`: vedi `.env.example` (SITO_BASE_URL, CLOUDFLARE_*, TELEGRAM_ADMIN_CHAT_ID...).
3. Deploy: Node + `npx wrangler pages project create rassegna-audio` una volta.
4. Fonti Economia in `config.py`: i feed sono marcati `verified: False`, da provare con `python fetch.py`.
