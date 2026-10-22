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

FONTI = [
    # --- Italia / Agenzie ---
    {"nome": "ANSA - Politica", "categoria": "Italia",
     "url": "https://www.ansa.it/sito/notizie/politica/politica_rss.xml", "verified": True},
    {"nome": "ANSA - Cronaca", "categoria": "Italia",
     "url": "https://www.ansa.it/sito/notizie/cronaca/cronaca_rss.xml", "verified": True},
    {"nome": "AGI", "categoria": "Italia",
     "url": "https://www.agi.it/rss", "verified": True},

    # --- Italia / Quotidiani (rotazione settimanale — vedi ROTAZIONE_QUOTIDIANI sotto) ---
    {"nome": "Corriere della Sera", "categoria": "Italia",
     "url": "https://xml2.corriereobjects.it/rss/homepage.xml", "verified": True},
    {"nome": "Repubblica", "categoria": "Italia",
     "url": "https://www.repubblica.it/rss/homepage/rss2.0.xml", "verified": True},
    {"nome": "Il Foglio", "categoria": "Italia",
     "url": "https://naxos.ilfoglio.it/api/v5/rss/stories/latest", "verified": True},
    {"nome": "Il Giornale", "categoria": "Italia",
     "url": "https://www.ilgiornale.it/feed", "verified": False},

    # --- Estero ---
    {"nome": "BBC News World", "categoria": "Esteri",
     "url": "http://feeds.bbci.co.uk/news/world/rss.xml", "verified": True},

    # --- Economia (URL da verificare con fetch.py: i feed non sono stati testati) ---
    {"nome": "ANSA - Economia", "categoria": "Economia",
     "url": "https://www.ansa.it/sito/notizie/economia/economia_rss.xml", "verified": False},
    {"nome": "BBC News Business", "categoria": "Economia",
     "url": "http://feeds.bbci.co.uk/news/business/rss.xml", "verified": False},
    {"nome": "Il Post - Economia", "categoria": "Economia",
     "url": "https://www.ilpost.it/economia/feed/", "verified": False},

    # --- Tecnologia ---
    {"nome": "Il Post - Tecnologia", "categoria": "Tecnologia",
     "url": "https://www.ilpost.it/tecnologia/feed/", "verified": True},
    {"nome": "Wired Italia", "categoria": "Tecnologia",
     "url": "https://www.wired.it/feed/rss", "verified": True},
    {"nome": "Ars Technica", "categoria": "Tecnologia",
     "url": "http://feeds.arstechnica.com/arstechnica/index", "verified": True},
    {"nome": "Agenda Digitale", "categoria": "Tecnologia",
     "url": "https://www.agendadigitale.eu/feed/", "verified": True},
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
    "BBC News World", "Il Post - Tecnologia",
    "ANSA - Economia", "BBC News Business", "Il Post - Economia",
    "Wired Italia", "Ars Technica", "Agenda Digitale",
}

# ---------------------------------------------------------------------------
# SEZIONI DEL RESOCONTO (in ordine di lettura)
# ---------------------------------------------------------------------------
SEZIONI = ["Italia", "Esteri", "Economia", "Tecnologia"]

# Slug usato in id, nomi di file e URL (niente accenti/spazi)
def slug_sezione(nome_sezione):
    return nome_sezione.strip().lower().replace(" ", "-")

# ---------------------------------------------------------------------------
# VOCI PREFERITE PER SEZIONE
# ---------------------------------------------------------------------------
# Lista di voci predefinite di XTTS-v2 (vedi "python tts.py --list-speakers")
# lette da voci_preferite.txt, una per riga. A ogni sezione viene scelta
# casualmente una voce dalla lista. Se il file manca o è vuoto, si torna al
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


def voce_per_sezione(nome_sezione):
    """Sceglie casualmente la voce per questa sezione, o ritorna None se non
    è stata configurata nessuna lista di voci preferite."""
    if not XTTS_VOCI_PREFERITE:
        return None
    return random.choice(XTTS_VOCI_PREFERITE)

# ---------------------------------------------------------------------------
# PARAMETRI GENERALI
# ---------------------------------------------------------------------------
FINESTRA_ARTICOLI = timedelta(hours=24)   # solo articoli delle ultime 24h
MAX_ARTICOLI_PER_FONTE = 28               # tetto per fonte, evita prompt enormi
LOG_DIMENSIONE_MASSIMA_MB = 10             # avviso all'avvio se un log supera questa dimensione

# Modello Claude da usare per la sintesi (vedi synthesize.py)
CLAUDE_MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# PERCORSI PER DATA (output/AAAA-MM-GG/)
# ---------------------------------------------------------------------------
# Ogni fase scrive i suoi file nella cartella del giorno e può essere
# rilanciata da sola (main.py --da-fase N). La data corrente si cambia con
# imposta_data() (main.py --data AAAA-MM-GG); di default è oggi.
from datetime import date as _date

DIR_OUTPUT = "output"
FILE_ULTIMA_CHIAMATA = "output/ultima_chiamata.txt"   # globale, non per giorno
FILE_VOCI_GIORNO = "voci.json"

_data_corrente = None


def imposta_data(data_str=None):
    """Imposta il giorno di lavoro (stringa AAAA-MM-GG). None = oggi."""
    global _data_corrente
    if data_str:
        _date.fromisoformat(data_str)          # valida il formato
    _data_corrente = data_str or None


def data_corrente():
    return _data_corrente or _date.today().isoformat()


def dir_giorno(data=None):
    p = Path(DIR_OUTPUT) / (data or data_corrente())
    p.mkdir(parents=True, exist_ok=True)
    return p


def percorso_articoli_grezzi(data=None):
    return str(dir_giorno(data) / "articoli_grezzi.json")


def percorso_notizie_sezione(nome_sezione, data=None):
    return str(dir_giorno(data) / f"notizie_{slug_sezione(nome_sezione)}.json")


def percorso_parlato(data=None):
    """Testi 'parlati' (dopo la fonetica) di tutte le sezioni, input della fase 3."""
    return str(dir_giorno(data) / "parlato.json")


def percorso_voce_wav_sezione(nome_sezione, data=None):
    return str(dir_giorno(data) / f"voce_{slug_sezione(nome_sezione)}.wav")


def percorso_voce_meta_sezione(nome_sezione, data=None):
    return str(dir_giorno(data) / f"voce_{slug_sezione(nome_sezione)}.json")


def percorso_episodio_wav(data=None):
    return str(dir_giorno(data) / "episodio.wav")


def percorso_episodio_mp3(data=None):
    return str(dir_giorno(data) / "episodio.mp3")


def percorso_manifest(data=None):
    return str(dir_giorno(data) / "manifest.json")


def percorso_voci_giorno(data=None):
    return str(dir_giorno(data) / FILE_VOCI_GIORNO)


# --- Compatibilità con test_voci.py / tts.py (CLI legacy, un audio per sezione) ---
def percorso_testo_sezione(nome_sezione):
    return str(dir_giorno() / f"testo_{nome_sezione}.txt")


def percorso_audio_wav_sezione(nome_sezione):
    return str(dir_giorno() / f"audio_{nome_sezione}.wav")


def percorso_audio_ogg_sezione(nome_sezione):
    return str(dir_giorno() / f"audio_{nome_sezione}.ogg")


# ---------------------------------------------------------------------------
# SINTESI PER SEZIONE (Fase 1)
# ---------------------------------------------------------------------------
MAX_NOTIZIE_PER_SEZIONE = 6
MAX_FRASI_PER_NOTIZIA = 8
MAX_CHARS_FRASE = 200            # limite XTTS per l'italiano: 213
SINTESI_MAX_TOKENS = 16000       # primo tentativo; il retry raddoppia
SINTESI_PARALLELA = True         # una chiamata per sezione, in parallelo
SINTESI_PROMPT_CACHING = True

# Saluto, transizioni e commiato li genera il codice (Claude, con una
# chiamata per sezione, non sa se la sua è la prima o l'ultima del giorno).
# Segnaposto: {data}, {periodo}. Si sceglie una variante in modo
# deterministico per data (stesso giorno = stesso testo = cache audio valida).
TESTI_APERTURA = [
    "Buongiorno, questa è la rassegna stampa di {data}.",
    "Buongiorno e benvenuti alla rassegna stampa di {data}.",
]
TESTO_PERIODO = "Le notizie di questa edizione coprono il periodo {periodo}."
ARGOMENTO_DA = {"Italia": "dall'Italia", "Esteri": "dagli esteri",
                "Economia": "dall'economia", "Tecnologia": "dalla tecnologia"}
ARGOMENTO_A = {"Italia": "all'Italia", "Esteri": "agli esteri",
               "Economia": "all'economia", "Tecnologia": "alla tecnologia"}
TRANSIZIONE_PRIMA = ["Iniziamo {argomento}.", "Cominciamo {argomento}."]
TRANSIZIONE_ALTRE = ["Passiamo {argomento}.", "Spostiamoci {argomento}."]
TESTI_CHIUSURA = [
    "Per oggi è tutto. Buon proseguimento.",
    "Questo è tutto per oggi. Grazie dell'ascolto e a domani.",
]

# ---------------------------------------------------------------------------
# FONETICA (Fase 2)
# ---------------------------------------------------------------------------
FILE_FONETICA = "fonetica.txt"                       # dizionario scritto -> parlato
FILE_FONETICA_CANDIDATI = "logs/fonetica_candidati.txt"

# ---------------------------------------------------------------------------
# AUDIO ED EPISODIO (Fase 3)
# ---------------------------------------------------------------------------
PAUSA_FRASE_MS = 350      # tra frasi della stessa notizia
PAUSA_NOTIZIA_MS = 900    # tra notizie
PAUSA_SEZIONE_MS = 1500   # tra sezioni (e dopo apertura/transizioni)
XTTS_VOCE_SPECIALE = None  # voce per saluto/transizioni/commiato; None = voce della sezione
MP3_BITRATE = "64k"
TOLLERANZA_DURATA_S = 0.5  # controllo coerenza durata file vs timeline
AUDIO_FINTO = False        # True (main.py --audio-finto): toni al posto di XTTS, per sviluppo

# ---------------------------------------------------------------------------
# SITO, DEPLOY, NOTIFICA (Fase 4) — i segreti stanno in .env, vedi .env.example
# ---------------------------------------------------------------------------
import os as _os

DIR_SITO = "output/sito"            # contiene tutti i giorni (retention inclusa)
DIR_SITO_TEMPLATE = "sito_template"
RETENTION_GIORNI = 30
SITO_NOME_PROGETTO_CF = "rassegna-audio"   # nome progetto Cloudflare Pages (o env CF_PAGES_PROJECT)
FILE_TOKEN_SITO = "data/sito_token.txt"
TITOLO_SITO = "Rassegna stampa audio"
# Hook per la Fase 5 (mappa): auto = mappa solo se la notizia ha luoghi.
MAPPA_MODALITA = {"Italia": "fissa", "Esteri": "zoom",
                  "Economia": "auto", "Tecnologia": "auto"}


def sito_token():
    """Token casuale nel percorso del sito (/t/<token>/...). Da env SITO_TOKEN,
    altrimenti generato una volta e salvato in data/sito_token.txt."""
    t = _os.environ.get("SITO_TOKEN", "").strip()
    if t:
        return t
    p = Path(FILE_TOKEN_SITO)
    if p.exists() and p.read_text(encoding="utf-8").strip():
        return p.read_text(encoding="utf-8").strip()
    import secrets
    t = secrets.token_urlsafe(16)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(t, encoding="utf-8")
    return t


def sito_base_url():
    return _os.environ.get("SITO_BASE_URL", "").rstrip("/")


def telegram_invia_audio():
    return _os.environ.get("TELEGRAM_INVIA_AUDIO", "").strip().lower() in {"1", "true", "si", "sì", "yes"}


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

# Velocità di lettura: 1.0 = normale, >1 più veloce, <1 più lento (es. 1.15
# = 15% più veloce, 0.9 = 10% più lento). Applicata SOLO alla voce, PRIMA di
# aggiungere la musica di sottofondo (musica.py) — così la musica resta al
# suo tempo naturale, non viene accelerata/rallentata insieme al parlato.
# Time-stretch puro via librosa: non cambia il pitch della voce.
# Range utile: 0.5-2.0 (oltre questi valori l'audio inizia a suonare innaturale).
XTTS_VELOCITA = 1.0

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

# ---------------------------------------------------------------------------
# MUSICA DI SOTTOFONDO (stile telegiornale)
# ---------------------------------------------------------------------------
# Tre file separati (qualunque formato legga ffmpeg: mp3, wav, ecc.):
# - MUSICA_INTRO: suonata da sola prima della prima sezione della rassegna
# - MUSICA_CORPO: in loop come sottofondo sotto la voce, in ogni sezione
# - MUSICA_OUTRO: suonata da sola dopo l'ultima sezione della rassegna
# Metti MUSICA_ABILITATA = False per disattivare del tutto (nessuna musica,
# solo voce, come prima di questa funzionalità).
MUSICA_ABILITATA = True
MUSICA_INTRO = "musica/intro.wav"
MUSICA_CORPO = "musica/corpo.wav"
MUSICA_OUTRO = "musica/outro.wav"

# Volume del sottofondo mentre la voce parla (0 = silenzio, 1 = stesso
# volume della voce). Tenerlo basso: deve "sentirsi" senza sovrastare il parlato.
MUSICA_VOLUME_SOTTOFONDO = 0.18
# Volume di intro/outro quando suonano da sole (senza voce sopra), può stare
# più alto del sottofondo.
MUSICA_VOLUME_INTRO_OUTRO = 0.7
# Dissolvenza (fade in/out, in millisecondi) applicata a inizio/fine di ogni
# pezzo musicale, per evitare "click" uditi ai punti di attacco/stacco.
MUSICA_DISSOLVENZA_MS = 500

# Telegram — valori letti da variabili d'ambiente, vedi .env.example
