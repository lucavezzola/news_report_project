# Rassegna Audio v2 — note di implementazione

Stato rispetto al piano: **Fasi 0-7 implementate**. Le Fasi 5-7 (mappa, entità/immagini,
PWA e rifinitura) sono state provate con servizi simulati e jsdom, NON su browser e API reali:
vedi la checklist qui sotto.

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

## Fasi 5-7: mappa, schede, PWA

Nuovo flusso nella Fase 2: `arricchimento.py` risolve luoghi (poligoni locali + Nominatim) ed entità
(Wikidata + Commons), poi parte la fonetica. Se fallisce, l'episodio esce comunque senza mappa/immagini.

    python arricchimento.py --data 2026-10-23           # solo questo passo
    python arricchimento.py --offline                   # solo cache, override, poligoni locali
    python main.py --no-arricchimento                   # salta del tutto mappa e immagini
    python scarica_geo.py                               # rigenera i confini (opzionale, sono già nel progetto)
    python serve_locale.py                              # server locale con Range (necessario per il salto nell'audio)

**Obbligatorio per mappa e immagini:** `CONTATTO_EMAIL` nel `.env` (Wikimedia e Nominatim lo richiedono nello
user agent). Senza, quelle chiamate vengono saltate e restano solo cache e poligoni locali.

Dati in `data/`: `geo/` (confini), `cache/` (luoghi, entità, immagini; potata dopo 90 giorni di non uso),
`luoghi_override.json` e `entita_override.json` (correzioni manuali, vedi `docs/policy_immagini.md`).

Leggi `docs/confini_contesi.md` e `docs/policy_immagini.md`: contengono scelte editoriali tue.

## Test

    python -m pytest                          # 84 test, senza rete né GPU
    npm install --prefix tests/js jsdom       # opzionale: abilita il test di fumo del front-end (+7 test)

## Checklist di accettazione da fare tu (cosa non posso verificare da qui)

1. `python main.py --usa-fixture --data 2099-01-01 --audio-finto --no-deploy --no-telegram` poi `python serve_locale.py`:
   guarda mappa e carte; salta con lo slider e con i clic (avanti e indietro): la mappa deve restare coerente.
2. Da telefono (Wi-Fi locale): il pannello mappa/carte non deve coprire troppo testo; prova "Mappa e immagini" (spunta/togli).
3. Con `CONTATTO_EMAIL` impostata, su 5-10 giorni reali guarda `logs/arricchimento.log` e `logs/wikidata.log`:
   quante entità risolte, quali scartate e perché. Obiettivo del piano: nessuna immagine sbagliata su 20 episodi,
   almeno il 90% delle entità giuste. Soglie da calibrare in `config.py` (`SOGLIA_*`, `MARGINE_*`).
4. Le classi Wikidata in `config.WIKIDATA_CLASSI` e la proprietà colore P465 sono scritte a memoria: verificale.
5. PWA: serve https (Cloudflare Pages va bene). Prova "Aggiungi a Home" e la riapertura con rete assente.
   Il service worker non mette mai in cache l'audio.
