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
# NOTA IMPORTANTE SU REUTERS: Reuters ha dismesso da anni i feed RSS pubblici
# ufficiali (feeds.reuters.com non risponde più). Le uniche vie sono:
#   1) un servizio "RSS generator" di terze parti (es. rss.app, feedspot) che
#      fa scraping della pagina — meno stabile, dipende da un servizio esterno;
#      2) un feed di Google News filtrato su reuters.com (incluso sotto come
#      soluzione di ripiego, marcato "workaround").
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
     "url": "https://www.ilfoglio.it/rss.xml", "verified": False},
    {"nome": "Il Giornale", "categoria": "Italia",
     "url": "https://www.ilgiornale.it/feed", "verified": False},

    # --- Estero ---
    {"nome": "BBC News World", "categoria": "Esteri",
     "url": "http://feeds.bbci.co.uk/news/world/rss.xml", "verified": True},
    {"nome": "Reuters World (workaround Google News)", "categoria": "Esteri",
     "url": "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com/world&hl=it&gl=IT&ceid=IT:it",
     "verified": False},

    # --- Economia ---
    {"nome": "Il Sole 24 Ore - Italia", "categoria": "Economia",
     "url": "https://www.ilsole24ore.com/rss/italia.xml", "verified": False},
    {"nome": "Milano Finanza", "categoria": "Economia",
     "url": "https://www.milanofinanza.it/rss", "verified": False},
    {"nome": "Reuters Business (workaround Google News)", "categoria": "Economia",
     "url": "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com/business&hl=it&gl=IT&ceid=IT:it",
     "verified": False},

    # --- Tecnologia ---
    {"nome": "Il Post - Tecnologia", "categoria": "Tecnologia",
     "url": "https://www.ilpost.it/tecnologia/feed/", "verified": False},
    {"nome": "Wired Italia", "categoria": "Tecnologia",
     "url": "https://www.wired.it/feed/rss", "verified": False},
    {"nome": "Ars Technica", "categoria": "Tecnologia",
     "url": "http://feeds.arstechnica.com/arstechnica/index", "verified": False},
    {"nome": "Agenda Digitale", "categoria": "Tecnologia",
     "url": "https://www.agendadigitale.eu/feed/", "verified": False},
    {"nome": "Reuters Technology (workaround Google News)", "categoria": "Tecnologia",
     "url": "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com/technology&hl=it&gl=IT&ceid=IT:it",
     "verified": False},
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
    "BBC News World", "Reuters World (workaround Google News)",
    "Il Sole 24 Ore - Italia", "Milano Finanza", "Reuters Business (workaround Google News)",
    "Il Post - Tecnologia", "Wired Italia", "Ars Technica", "Agenda Digitale",
    "Reuters Technology (workaround Google News)",
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
FILE_TESTO_SINTESI = "output/rassegna_testo.txt"
FILE_AUDIO_WAV = "output/rassegna.wav"
FILE_AUDIO_OGG = "output/rassegna.ogg"

# Piper TTS — percorso del modello vocale italiano (scaricalo separatamente,
# vedi README.md sezione "Setup Piper")
PIPER_MODEL_PATH = "piper_models/it_IT-riccardo-x_low.onnx"
PIPER_EXECUTABLE = "piper"  # se non è nel PATH, mettere il percorso assoluto

# Telegram — valori letti da variabili d'ambiente, vedi .env.example
