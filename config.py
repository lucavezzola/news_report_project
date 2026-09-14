"""
config.py — Configurazione centrale della Rassegna Stampa Audio.

Modifica questo file per:
- aggiungere/rimuovere fonti RSS
- cambiare le sezioni del resoconto
- regolare parametri (finestra oraria, orario invio, ecc.)
"""

from datetime import timedelta

# ---------------------------------------------------------------------------
# FONTI RSS
# ---------------------------------------------------------------------------
# Ogni fonte ha: nome, categoria (usata per raggruppare nel prompt di sintesi),
# url del feed, e un flag "verified" che indica se l'URL è stato verificato
# funzionante durante la stesura di questo progetto (settembre 2026).
#
# In fase 1 lo script segnala chiaramente quali fonti falliscono, così puoi
# decidere se tenerle, sostituirle o rimuoverle.

FONTI = [
    # --- Italia / Agenzie ---
    {"nome": "ANSA - Politica", "categoria": "Italia",
     "url": "https://www.ansa.it/sito/notizie/politica/politica_rss.xml", "verified": True},
    {"nome": "ANSA - Cronaca", "categoria": "Italia",
     "url": "https://www.ansa.it/sito/notizie/cronaca/cronaca_rss.xml", "verified": True},
    {"nome": "AGI", "categoria": "Italia",
     "url": "https://www.agi.it/rss", "verified": False},

    # --- Italia / Quotidiani (rotazione settimanale — vedi ROTAZIONE_QUOTIDIANI sotto) ---
    {"nome": "Corriere della Sera", "categoria": "Italia",
     "url": "https://xml2.corriereobjects.it/rss/homepage.xml", "verified": False},
    {"nome": "Repubblica", "categoria": "Italia",
     "url": "https://www.repubblica.it/rss/homepage/rss2.0.xml", "verified": False},
    {"nome": "Il Foglio", "categoria": "Italia",
     "url": "https://naxos.ilfoglio.it/api/v5/rss/stories/latest", "verified": False},
    {"nome": "Il Giornale", "categoria": "Italia",
     "url": "https://www.ilgiornale.it/feed", "verified": False},

    # --- Estero ---
    {"nome": "BBC News World", "categoria": "Esteri",
     "url": "http://feeds.bbci.co.uk/news/world/rss.xml", "verified": True},

    # --- Economia ---
    {"nome": "Il Sole 24 Ore - Italia", "categoria": "Economia",
     "url": "https://www.ilsole24ore.com/rss/italia.xml", "verified": False},
    {"nome": "Il Sole 24 Ore - Finanza", "categoria": "Economia",
     "url": "https://www.ilsole24ore.com/rss/finanza.xml", "verified": False},

    # --- Tecnologia ---
    {"nome": "Il Post - Tecnologia", "categoria": "Tecnologia",
     "url": "https://www.ilpost.it/tecnologia/feed/", "verified": False},
    {"nome": "Wired Italia", "categoria": "Tecnologia",
     "url": "https://www.wired.it/feed/rss", "verified": False},
    {"nome": "Ars Technica", "categoria": "Tecnologia",
     "url": "http://feeds.arstechnica.com/arstechnica/index", "verified": False},
    {"nome": "Agenda Digitale", "categoria": "Tecnologia",
     "url": "https://www.agendadigitale.eu/feed/", "verified": False},
]

# Rotazione settimanale dei quotidiani generalisti italiani (per bilanciare
# il taglio editoriale nel tempo, come indicato nel documento di progetto).
# 0 = lunedì ... 6 = domenica
ROTAZIONE_QUOTIDIANI = {
    0: "Corriere della Sera",
    1: "Repubblica",
    2: "Il Foglio",
    3: "Il Giornale",
    4: "Corriere della Sera",
    5: "Repubblica",
    6: "Il Foglio",
}

# Nomi delle fonti "sempre incluse" (agenzie, non soggette a rotazione)
FONTI_SEMPRE_INCLUSE = {
    "ANSA - Politica", "ANSA - Cronaca", "AGI",
    "BBC News World", "Il Sole 24 Ore - Italia", "Il Sole 24 Ore - Finanza",
    "Il Post - Tecnologia", "Wired Italia", "Ars Technica", "Agenda Digitale",
}

# ---------------------------------------------------------------------------
# SEZIONI DEL RESOCONTO (in ordine di lettura)
# ---------------------------------------------------------------------------
SEZIONI = ["Italia", "Esteri", "Economia", "Tecnologia"]

# ---------------------------------------------------------------------------
# PARAMETRI GENERALI
# ---------------------------------------------------------------------------
FINESTRA_ARTICOLI = timedelta(hours=24)   # solo articoli delle ultime 24h
MAX_ARTICOLI_PER_FONTE = 25               # tetto per fonte, evita prompt enormi

# Modello Claude da usare per la sintesi (vedi synthesize.py)
CLAUDE_MODEL = "claude-sonnet-4-6"

# Percorsi file
DIR_OUTPUT = "output"
FILE_JSON_GREZZO = "output/articoli_grezzi.json"


def percorso_testo_sezione(nome_sezione):
    return f"output/testo_{nome_sezione}.txt"


def percorso_audio_wav_sezione(nome_sezione):
    return f"output/audio_{nome_sezione}.wav"


def percorso_audio_ogg_sezione(nome_sezione):
    return f"output/audio_{nome_sezione}.ogg"

# Piper TTS — percorso del modello vocale italiano (scaricalo separatamente,
# vedi README.md sezione "Setup Piper")
PIPER_MODEL_PATH = "piper/piper_models/it_IT-serena-high.onnx"
PIPER_EXECUTABLE = "piper/piper.exe"  # se non è nel PATH, mettere il percorso assoluto

# Parametri di sintesi vocale, calibrati per la voce it_IT-serena-medium
# (i default di Piper, noise_scale 0.667 / noise_w 0.8, tendono a "mangiarsi"
# alcuni foni con questa voce, es. la /r/ in "portato" — vedi scheda del
# modello su Hugging Face). Se cambi voce, controlla se ha impostazioni
# consigliate diverse e aggiornale qui.
PIPER_NOISE_SCALE = 0.6      # variazione acustica: più basso = voce più stabile/pulita — NON TOCCARE senza motivo
PIPER_LENGTH_SCALE = 1.3    # velocità del parlato: >1 rallenta, <1 accelera — sicuro da regolare
PIPER_NOISE_W = 0.4          # variazione nella durata dei foni — NON TOCCARE senza motivo
PIPER_SENTENCE_SILENCE = 0.45  # secondi di silenzio tra una frase e l'altra — sicuro da regolare

# Telegram — valori letti da variabili d'ambiente, vedi .env.example
