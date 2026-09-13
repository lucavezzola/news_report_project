# Rassegna Stampa Audio Giornaliera

Implementazione della pipeline descritta in `progetto-rassegna-audio.md`:
RSS → sintesi imparziale (Claude) → audio (Piper) → invio Telegram.

## Struttura del progetto

```
config.py          configurazione: fonti RSS, sezioni, parametri
fetch.py           Fase 1 — raccolta articoli RSS
synthesize.py       Fase 2 — sintesi imparziale via Claude API
tts.py             Fase 3 — sintesi vocale locale con Piper
send_telegram.py    Fase 4 — invio audio su Telegram
main.py            orchestratore: esegue tutte le fasi in sequenza
requirements.txt    dipendenze Python
.env.example        template variabili d'ambiente (copialo in .env)
output/             file generati (JSON grezzo, testo, audio) — non versionare
logs/               log di ogni fase, un file per modulo
```

## Setup

### 1. Python e dipendenze

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 2. Variabili d'ambiente

```bash
copy .env.example .env
```

Poi apri `.env` e inserisci:
- `ANTHROPIC_API_KEY` — da [console.anthropic.com](https://console.anthropic.com) → API Keys
- `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` — vedi sezione sotto

### 3. Setup Telegram

1. Apri una chat con **@BotFather** su Telegram, manda `/newbot`, segui le istruzioni: ottieni il `TELEGRAM_BOT_TOKEN`.
2. Crea un canale o gruppo privato, invita i tuoi amici.
3. Aggiungi il bot al canale come **amministratore** (serve per poter pubblicare).
4. Manda un messaggio qualsiasi nel canale, poi apri nel browser:
   `https://api.telegram.org/bot<IL_TUO_TOKEN>/getUpdates`
   Cerca `"chat":{"id": ...}` nel JSON restituito: quel numero (di solito negativo per i canali, tipo `-1001234567890`) è il tuo `TELEGRAM_CHAT_ID`.

### 4. Setup Piper (TTS locale)

1. Scarica il binario Piper per Windows dalla [pagina release ufficiale](https://github.com/rhasspy/piper/releases) e metti la cartella `piper/` nella root del progetto.
2. Scarica una voce italiana pre-addestrata (es. `it_IT-riccardo-x_low` o `it_IT-paola-medium`) dal repository [rhasspy/piper-voices su Hugging Face](https://huggingface.co/rhasspy/piper-voices/tree/main/it/it_IT) — servono entrambi i file `.onnx` e `.onnx.json`.
3. Metti i file scaricati in una cartella `piper_models/` dentro `piper/`.
4. Assicurati che l'eseguibile `piper.exe` sia raggiungibile: imposta il percorso assoluto in `config.py` → `PIPER_EXECUTABLE`.
5. Installa **ffmpeg** (serve per convertire il wav in ogg) — [ffmpeg.org](https://ffmpeg.org/download.html), aggiungilo al PATH.

## Test fase per fase (consigliato, come da roadmap)

Ogni modulo è eseguibile da solo per testare una fase alla volta:

```bash
# Fase 1 — verifica quali fonti RSS funzionano davvero
python fetch.py

# Fase 2 — richiede che fetch.py sia già stato eseguito (usa output/articoli_grezzi.json)
python synthesize.py

# Fase 3 — richiede che synthesize.py sia già stato eseguito
python tts.py

# Fase 4 — richiede che tts.py sia già stato eseguito
python send_telegram.py

# Pipeline completa
python main.py
```

**Importante sulla Fase 1:** alcune fonti nel `config.py` sono marcate `"verified": False` — sono gli URL più probabili in base alle mie ricerche, ma non ho potuto verificarli in tempo reale (l'ambiente in cui ho scritto questo codice non ha accesso libero a internet). Alla prima esecuzione di `fetch.py` guarda il riepilogo finale in console/log: ti dirà esattamente quali fonti falliscono, così puoi:
- cercare l'URL RSS corretto sul sito della fonte (di solito in fondo alla homepage, o `sito.it/rss`),
- oppure rimuovere la fonte da `config.py` se non trovi un feed valido.

**Nota su Reuters:** Reuters ha dismesso i feed RSS pubblici ufficiali da anni. Ho impostato un workaround via Google News (filtrato su reuters.com), marcato chiaramente nei commenti di `config.py`. È meno affidabile di un feed diretto: se noti risultati scarsi, valuta di toglierlo e affidarti solo a BBC/ANSA/AGI per l'estero, o di usare un servizio "RSS generator" di terze parti.

## Scheduling (Task Scheduler di Windows)

1. Apri **Utilità di pianificazione** → Crea attività.
2. Trigger: giornaliero, orario a scelta (es. 6:30).
3. Azione: avvia un programma →
   - Programma: `C:\percorso\progetto\venv\Scripts\python.exe`
   - Argomenti: `main.py`
   - Cartella di partenza: `C:\percorso\progetto`
4. Controlla dopo qualche giorno i file in `logs/` per verificare che tutto giri liscio.

## Personalizzazione del prompt di sintesi

Le istruzioni di imparzialità sono nel `SYSTEM_PROMPT` dentro `synthesize.py`. È il punto su cui vale la pena iterare di più: ascolta i primi risultati e affina la formulazione se noti bias, ripetizioni o un tono poco naturale da leggere ad alta voce.

## Costi stimati

Solo l'API Claude ha un costo (Sonnet, uso quotidiano di sintesi su un volume moderato di articoli): resta nell'ordine di qualche euro al mese, come stimato nel documento di progetto originale. Tutto il resto (RSS, Piper, Telegram, scheduling) è gratuito.
