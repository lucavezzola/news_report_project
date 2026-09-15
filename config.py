"""
config.py — Configurazione centrale della Rassegna Stampa Audio.

Modifica questo file per:
- aggiungere/rimuovere fonti RSS
- cambiare le sezioni del resoconto
- regolare parametri (finestra oraria, orario invio, ecc.)
"""

from datetime import timedelta
from pathlib import Path
import random

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
     "url": "https://naxos.ilfoglio.it/api/v5/rss/stories/latest", "verified": False},
    {"nome": "Il Giornale", "categoria": "Italia",
     "url": "https://www.ilgiornale.it/feed", "verified": False},

    # --- Estero ---
    {"nome": "BBC News World", "categoria": "Esteri",
     "url": "http://feeds.bbci.co.uk/news/world/rss.xml", "verified": True},
    {"nome": "Reuters World (workaround Google News)", "categoria": "Esteri",
     "url": "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com+world&hl=en-US&gl=US&ceid=US:en",
     "verified": False},

    # --- Economia ---
    {"nome": "Il Sole 24 Ore - Italia", "categoria": "Economia",
     "url": "https://www.ilsole24ore.com/rss/italia.xml", "verified": False},
    {"nome": "Il Sole 24 Ore - Finanza", "categoria": "Economia",
     "url": "https://www.ilsole24ore.com/rss/finanza.xml", "verified": False},
    {"nome": "Reuters Business (workaround Google News)", "categoria": "Economia",
     "url": "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com+business&hl=en-US&gl=US&ceid=US:en",
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
     "url": "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com+technology&hl=en-US&gl=US&ceid=US:en",
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
    "Il Sole 24 Ore - Italia", "Il Sole 24 Ore - Finanza", "Reuters Business (workaround Google News)",
    "Il Post - Tecnologia", "Wired Italia", "Ars Technica", "Agenda Digitale",
    "Reuters Technology (workaround Google News)",
}

# ---------------------------------------------------------------------------
# SEZIONI DEL RESOCONTO (in ordine di lettura)
# ---------------------------------------------------------------------------
SEZIONI = ["Italia", "Esteri", "Economia", "Tecnologia"]

# ---------------------------------------------------------------------------
# VOCI PREFERITE PER SEZIONE
# ---------------------------------------------------------------------------
# Lista di voci predefinite di XTTS-v2 (vedi "python tts.py --list-speakers")
# lette da voci_preferite.txt, una per riga. main.py assegna automaticamente
# una voce diversa a ciascuna sezione (Italia, Esteri, Economia, Tecnologia),
# seguendo l'ordine di SEZIONI sopra. Se il file manca o è vuoto, si torna al
# comportamento precedente (voice cloning da XTTS_SPEAKER_WAV per tutte le
# sezioni, nessuna voce predefinita).

def _carica_voci_preferite(percorso="voci_preferite.txt"):
    p = Path(percorso)
    if not p.exists():
        return []
    voci = []
    for riga in p.read_text(encoding="utf-8").splitlines():
        riga = riga.strip()
        if riga and not riga.startswith("#"):
            voci.append(riga)
    return voci


XTTS_VOCI_PREFERITE = _carica_voci_preferite()
_XTTS_VOCI_ASSEGNATE = None


def voce_per_sezione(nome_sezione):
    """Ritorna il nome della voce predefinita da usare per questa sezione, o
    None se non è stata configurata nessuna lista di voci preferite (in quel
    caso tts.py userà il voice cloning di default da XTTS_SPEAKER_WAV)."""
    global _XTTS_VOCI_ASSEGNATE

    if not XTTS_VOCI_PREFERITE:
        return None
    if _XTTS_VOCI_ASSEGNATE is None:
        voci_scelte = []
        while len(voci_scelte) < len(SEZIONI):
            voci_scelte.extend(random.sample(XTTS_VOCI_PREFERITE, k=len(XTTS_VOCI_PREFERITE)))
        voci_scelte = voci_scelte[:len(SEZIONI)]
        _XTTS_VOCI_ASSEGNATE = dict(zip(SEZIONI, voci_scelte))
    return _XTTS_VOCI_ASSEGNATE[nome_sezione]

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

# XTTS-v2 (Coqui) — sintesi vocale neurale con voice cloning.
# Il modello gira in locale sulla tua GPU (richiede circa 4-6GB di VRAM in
# fp16, il default qui sotto). Se hai poca VRAM libera, vedi i commenti su
# XTTS_USE_FP16 e XTTS_MAX_CHARS_PER_CHUNK più sotto.

XTTS_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
XTTS_LANGUAGE = "it"

# Percorso di un file audio di riferimento (6-30 secondi, voce pulita, senza
# rumore di fondo) usato per clonare la voce. Deve esistere prima di lanciare
# tts.py — vedi README.md sezione "Setup XTTS-v2".
XTTS_SPEAKER_WAV = "xtts_reference/voce_riferimento.wav"

# Mezza precisione (fp16): in teoria dimezza l'uso di VRAM rispetto a fp32,
# ma XTTS-v2 (in questa versione di coqui-tts) ha un sotto-modulo — l'encoder
# che analizza l'audio di riferimento per il voice cloning — che non gestisce
# .half() in modo pulito e va in errore (mismatch fp16/fp32 tra pesi e
# input). Per affidabilità teniamo fp32 di default: userà più VRAM, ma evita
# questa classe di errori. Riattiva fp16 solo se hai davvero bisogno di
# risparmiare VRAM e sei disposto a debuggare eventuali altri errori simili.
XTTS_USE_FP16 = False

# XTTS-v2 degrada in stabilità su testi molto lunghi in una singola chiamata,
# e ha un limite FISSO interno di 213 caratteri per l'italiano (oltre quella
# soglia tronca l'audio, indipendentemente da questo parametro) — quindi non
# alzare questo valore sopra ~210. Il testo di ogni sezione viene spezzato in
# blocchi di frasi sotto questa soglia, sintetizzati separatamente e poi
# concatenati.
XTTS_MAX_CHARS_PER_CHUNK = 200

# Silenzio (millisecondi) inserito tra un blocco e l'altro all'interno della
# stessa sezione, per una lettura più naturale.
XTTS_SILENZIO_TRA_CHUNK_MS = 300

# Su Windows, ctypes (usato internamente da torch per caricare le DLL native)
# dal Python 3.8 in poi NON cerca più le dipendenze delle DLL nelle cartelle
# elencate nel PATH di sistema (cambiamento di sicurezza contro il DLL
# hijacking). Va quindi registrata esplicitamente qui la cartella "bin" della
# tua installazione ffmpeg "shared" (quella con avcodec-*.dll, avformat-*.dll,
# ecc.) — altrimenti torch/torchcodec non trovano le DLL anche se il PATH è
# configurato correttamente.
FFMPEG_DLL_DIR = r"C:\ffmpeg8-shared\bin"  # aggiorna se hai usato un percorso diverso

# Se la VRAM libera sulla GPU è sotto questa soglia (GB) all'avvio, lo script
# avvisa e passa automaticamente alla CPU (molto più lento, ma non va in crash).
# Su una scheda da 6GB totali, 4GB liberi è già un buon segno che non ci sono
# altri programmi pesanti in esecuzione sulla GPU.
XTTS_MIN_VRAM_LIBERA_GB = 4.0

# Telegram — valori letti da variabili d'ambiente, vedi .env.example
