# Rassegna Stampa Audio Giornaliera

Implementazione della pipeline descritta in `progetto-rassegna-audio.md`:
RSS → sintesi imparziale (Claude) → audio (XTTS-v2) → invio Telegram.

## Struttura del progetto

```
config.py              configurazione: fonti RSS, sezioni, parametri
fetch.py                Fase 1 — raccolta articoli RSS
synthesize.py            Fase 2 — sintesi imparziale via Claude API
tts.py                  Fase 3 — sintesi vocale locale con XTTS-v2 (Coqui)
send_telegram.py         Fase 4 — invio audio su Telegram
main.py                 orchestratore: esegue tutte le fasi in sequenza
run_tts_e_invio.py       rilancia solo Fase 3 + Fase 4 sui testi già generati
requirements.txt         dipendenze Python
.env.example             template variabili d'ambiente (copialo in .env)
output/                 file generati (JSON grezzo, testo, audio) — non versionare
logs/                   log di ogni fase, un file per modulo
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

### 4. Setup XTTS-v2 (TTS neurale con voice cloning)

Il progetto usa **XTTS-v2** (Coqui) per la sintesi vocale: qualità e naturalezza molto superiori a un TTS "a regole" come Piper, con la possibilità di clonare una voce a scelta da un breve campione audio. Gira in locale sulla tua GPU.

1. **Installa PyTorch con supporto CUDA** — PRIMA di installare il resto. Il tuo driver (visto con `nvidia-smi`) supporta fino a CUDA 13.4, quindi il comando giusto per te è:
   ```bash
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130
   ```
   (se dovesse dare problemi di compatibilità, `cu128` è l'alternativa più "conservativa" — vedi [pytorch.org/get-started/locally](https://pytorch.org/get-started/locally/) per tutte le opzioni)
2. **Installa le altre dipendenze**, incluso `coqui-tts` (vedi `requirements.txt`):
   ```bash
   pip install -r requirements.txt
   ```
   ⚠️ Non installare mai il pacchetto `TTS` di PyPI: è il progetto originale di Coqui, abbandonato dopo la chiusura dell'azienda. Usiamo `coqui-tts`, il fork attivamente mantenuto — importa comunque con `from TTS.api import TTS`, quindi nel codice non cambia nulla.
3. **Prepara un file audio di riferimento** per il voice cloning: 6-30 secondi di voce pulita, senza rumore di fondo, in formato `.wav`. Può essere la tua voce, quella di un amico (con il suo consenso), o un campione di dominio pubblico. Mettilo in `xtts_reference/voce_riferimento.wav` (o aggiorna il percorso in `config.py` → `XTTS_SPEAKER_WAV`).
4. **Installa ffmpeg** (serve per convertire il wav generato in ogg, più leggero per Telegram) — [ffmpeg.org](https://ffmpeg.org/download.html), aggiungilo al PATH.
5. Al primo avvio di `tts.py`, il modello (~1.9GB) viene scaricato automaticamente da Hugging Face e messo in cache — la primissima esecuzione sarà quindi più lenta delle successive.

**Nota sulla VRAM:** `tts.py` è scritto per essere prudente con la memoria della GPU:
- il modello viene caricato **una sola volta** e riusato per tutte le sezioni, non ricaricato ogni volta;
- gira in **fp32** di default (`XTTS_USE_FP16 = False` in `config.py`): il sotto-modulo che analizza l'audio di riferimento per il voice cloning non gestisce in modo affidabile la mezza precisione in questa versione di `coqui-tts` (va in errore per mismatch fp16/fp32 tra pesi e input), quindi teniamo fp32 per evitare questa classe di errori — userà più VRAM (circa 8-10GB), ma è più stabile. Puoi provare a mettere `XTTS_USE_FP16 = True` per risparmiare memoria, ma preparati a debuggare eventuali errori simili;
- il testo di ogni sezione viene spezzato **una frase per blocco** (XTTS-v2 è più stabile così su testi lunghi), sotto la soglia `XTTS_MAX_CHARS_PER_CHUNK` caratteri (200 di default). Se una singola frase supera comunque la soglia, viene spezzata ulteriormente su virgole/punto e virgola e, come ultima risorsa, sulle singole parole — questo garantisce che nessun blocco superi mai il limite tecnico fisso di XTTS-v2 (213 caratteri per l'italiano), altrimenti l'audio verrebbe troncato;
- se la VRAM libera scende sotto la soglia `XTTS_MIN_VRAM_LIBERA_GB` (4GB di default), lo script passa automaticamente alla CPU invece di rischiare un crash per out-of-memory (sarà molto più lento, ma completa comunque).

**⚠️ La tua GPU ha 6GB di VRAM totali — margine stretto per XTTS-v2.** Consigli specifici per te:
- **Chiudi il browser (Brave) prima di lanciare la pipeline.** Dal tuo `nvidia-smi` risulta che Brave sta già occupando un po' di VRAM in background (comune coi browser moderni per l'accelerazione grafica) — su una scheda da 6GB ogni MB conta.
- `XTTS_MAX_CHARS_PER_CHUNK` è impostato a 200 proprio per questo: blocchi più piccoli = picchi di memoria più bassi. Non alzarlo sopra ~210 (limite fisso del modello per l'italiano).
- Se nonostante tutto vedi errori di out-of-memory, i prossimi passi sono, in ordine: chiudere altre app che usano la GPU → abbassare `XTTS_MAX_CHARS_PER_CHUNK` ulteriormente (es. 120) → provare `XTTS_USE_FP16 = True` in `config.py` (rischio di errori di compatibilità, vedi nota sopra).

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
- oppure rimuovere la fonte da `config.py` se non trovi un feed valido..

## Rilanciare solo TTS + invio (senza rifare fetch e sintesi)

Se devi correggere a mano un testo già generato (es. un nome pronunciato male) o hai aggiornato `tts.py`/`config.py` e vuoi rigenerare l'audio senza richiamare Claude, usa `run_tts_e_invio.py`: legge i file `output/testo_<Sezione>.txt` già esistenti (creati dall'ultima `python main.py` o `python synthesize.py`) e rifà solo Fase 3 (TTS) + Fase 4 (invio Telegram).

```bash
# tutte le sezioni del giorno
python run_tts_e_invio.py

# solo alcune sezioni (es. dopo aver corretto a mano Italia)
python run_tts_e_invio.py -s Italia
python run_tts_e_invio.py -s Italia Tecnologia
```

Se un file `testo_<Sezione>.txt` manca o è vuoto (es. sezione omessa quel giorno perché senza notizie), lo script la salta con un warning nel log, senza bloccare le altre.

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

Oltre all'imparzialità, il prompt include regole pensate specificamente per il sintetizzatore vocale, aggiunte dopo aver ascoltato i primi audio generati:
- **Trascrizione fonetica** di nomi e parole straniere (es. "Musk" → "Mask", "software" → "sofuer"), *e* di nomi italiani con lettere non standard come la "j" (es. "Tajani" → "Taiani"), che XTTS-v2 altrimenti pronuncia in modo scorretto leggendoli con le regole di pronuncia italiane.
- **Niente punto come separatore delle migliaia** nei numeri (es. non "1.500.000", meglio per esteso in lettere) e **niente abbreviazioni puntate** (es. non "ecc.", "dott.", "art."): XTTS-v2 a volte legge il punto alla lettera come la parola "punto" invece di riconoscerlo come fine frase o abbreviazione.
- **Frasi sotto circa 180 caratteri**: XTTS-v2 ha un limite tecnico fisso di 213 caratteri per l'italiano. Frasi via via più corte di quel limite lasciano margine al chunking in `tts.py` e riducono i casi in cui è necessario spezzare a metà frase senza una punteggiatura naturale su cui appoggiarsi.

## Problemi noti / Troubleshooting

- **Un blocco viene letto dicendo "punto" seguito da un breve rumore/artefatto**: capita quando il punto di fine frase resta come ultimo carattere della stringa passata a XTTS-v2 — l'euristica interna del modello che distingue "fine frase" da "numero decimale" fa un look-ahead sul carattere successivo, e se non c'è nulla dopo può leggerlo alla lettera. `tts.py` toglie la punteggiatura di fine frase (`.!?`) prima di passare il testo al modello, ricreando la pausa con un breve silenzio inserito a parte tra un blocco e l'altro (non con la punteggiatura letta dal modello). Se il problema si ripresenta, verifica che questa pulizia sia ancora presente nel codice.
- **Warning `"The text length exceeds the character limit of 213 for language 'it', this might cause truncated audio"`**: significa che un blocco ha superato il limite tecnico del modello nonostante il chunking. Non dovrebbe più comparire dato che ogni frase troppo lunga viene ulteriormente spezzata su virgole/punto e virgola e, come ultima risorsa, sulle singole parole — garantendo che nessun blocco superi mai la soglia. Se lo vedi ancora, controlla che questo fallback sia presente in `_spezza_frase_lunga`/`_spezza_su_parole` in `tts.py`.
- **Un nome proprio viene pronunciato male** (es. straniero, o italiano con lettere come "j", "k", "w", "x", "y"): il fix va nel `SYSTEM_PROMPT` di `synthesize.py`, non in `tts.py` — è lì che si istruisce Claude a scrivere una trascrizione fonetica approssimata invece del nome originale.

## Costi stimati

Solo l'API Claude ha un costo (Sonnet, uso quotidiano di sintesi su un volume moderato di articoli): resta nell'ordine di qualche euro al mese, come stimato nel documento di progetto originale. XTTS-v2 gira in locale sulla tua GPU (nessun costo per chiamata), così come RSS e Telegram — l'unico "costo" è il tempo di calcolo sulla tua macchina.