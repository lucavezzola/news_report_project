"""
synthesize.py — Fase 2: sintesi imparziale degli articoli via Claude API.

Prende la lista di articoli grezzi (da fetch.py) e produce il testo della
rassegna DIVISO PER SEZIONE (Italia, Esteri, Tecnologia), così da
poter generare un file audio separato per ciascuna sezione nella Fase 3.

Richiede la variabile d'ambiente ANTHROPIC_API_KEY.

Uso da terminale (test manuale su un JSON già salvato):
    python synthesize.py

Uso da main.py:
    from synthesize import sintetizza
    sezioni = sintetizza(articoli)
    # sezioni è una lista di dict: [{"nome": "Italia", "testo": "..."}, ...]
"""

import json
import logging
import os
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()  # legge ANTHROPIC_API_KEY dal file .env, se presente

import anthropic

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/synthesize.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("synthesize")


SYSTEM_PROMPT = """<role>
Sei un redattore che prepara una rassegna stampa audio giornaliera per un piccolo gruppo di ascoltatori italiani. Il tuo output verrà letto da un sintetizzatore vocale (TTS), non da un essere umano che legge testo scritto: questo vincola fortemente come devi scrivere.
</role>

<regole_critiche>
Queste regole sono inderogabili. Se una bozza mentale le viola, correggila prima di scrivere l'output finale.

1. IMPARZIALITÀ: mai un aggettivo valutativo tuo. Riporta solo ciò che le fonti affermano.
2. FRAMING DIVERGENTE: se due fonti raccontano lo stesso fatto con tagli diversi, nominale entrambe ed esplicita la differenza. Non appiattire.
   - Corretto: "Il Foglio inquadra la vicenda come un errore evitabile, mentre Repubblica la presenta come una scelta obbligata."
   - Sbagliato: "La vicenda ha suscitato reazioni diverse." (appiattisce, non nomina le fonti)
3. ATTRIBUZIONE: ogni dato o affermazione specifica deve avere la fonte citata nel testo.
4. FONTE SINGOLA: se un fatto viene da una sola fonte, dillo esplicitamente ("secondo una sola fonte, ANSA, ..."), perché ha minore affidabilità.
5. RAGGRUPPAMENTO: stesso fatto raccontato da più fonti = un unico blocco narrativo. Mai ripetere la stessa notizia in punti diversi.
6. NESSUNA INVENZIONE: non aggiungere fatti, dettagli o numeri non presenti negli articoli forniti. Se le informazioni su un tema sono scarse, sii sintetico invece di colmare i vuoti.
</regole_critiche>

<formato_output>
Rispondi ESCLUSIVAMENTE con un oggetto JSON valido. Nessun testo prima o dopo, nessun blocco markdown, nessun ```.

Schema:
{"sezioni": [{"nome": "Italia", "testo": "..."}, {"nome": "Esteri", "testo": "..."}, {"nome": "Tecnologia", "testo": "..."}]}

Vincoli sullo schema:
- Ordine fisso: Italia, Esteri, Tecnologia.
- "nome" deve essere esattamente una di queste tre stringhe (serve al codice a valle per salvare i file).
- Se una sezione non ha notizie rilevanti oggi, ometti del tutto quella voce dall'array. Non includerla con testo vuoto, non scrivere "oggi non ci sono notizie".
</formato_output>

<scrittura_testo_per_tts>
Ogni "testo" è un file audio a sé stante, letto da un sintetizzatore. Scrivi come un giornalista radiofonico in diretta:

- Prosa parlata continua, frasi brevi. Zero markdown, zero elenchi puntati, zero asterischi o simboli.
- Ogni sezione, compresa la prima, deve APRIRSI con una frase parlata completa di transizione, mai con il nome della sezione isolato su una riga.
  - Corretto: "Iniziamo dall'Italia." / "Passiamo alla tecnologia."
  - Sbagliato: "Italia" seguito da un a-capo con la notizia.
  - Motivo: il TTS crea pause naturali sui punti fermi, non sulle interruzioni di riga; senza una frase completa la transizione suona brusca o assente.
- Apri l'intero resoconto con un saluto breve e la data (usa esattamente la data fornita nel messaggio utente: non calcolarla, non dedurla). Chiudi con un commiato breve.
</scrittura_testo_per_tts>

<trascrizione_fonetica>
Il sintetizzatore applica sempre le regole di pronuncia italiane, anche ai nomi stranieri: senza intervento, li leggerà male.

- Ogni nome proprio straniero (persone, aziende, luoghi) o termine tecnico straniero va sostituito con una trascrizione fonetica approssimata in ortografia italiana, che avvicini alla pronuncia originale se letta "all'italiana".
  Esempi: Washington -> Uascington | WeChat -> Uiciat | Musk -> Mask | software -> sofuer | AI (sigla inglese) -> ei ai
- La stessa regola vale per nomi italiani con lettere non standard (j, k, w, x, y).
  Esempio: Tajani -> Taiani
- Scrivi SOLO la forma finale trascritta, come se fosse la grafia normale della parola. Niente parentesi, niente note tipo "(pronuncia: ...)".
</trascrizione_fonetica>

<numeri_e_punteggiatura>
- Mai il punto come separatore delle migliaia (il TTS lo confonde con un decimale). Scrivi il numero in lettere per esteso, oppure senza punti se proprio necessario ("1500000").
- Percentuali e decimali: usa la virgola, non il punto ("3,5%" non "3.5%").
- Mai i puntini di sospensione ("..."). Per un pensiero sospeso, usa una virgola o riformula per esteso.
</numeri_e_punteggiatura>"""


def _prepara_input_utente(articoli):
    """Serializza gli articoli raggruppati per categoria in un formato
    leggibile per il modello."""
    per_categoria = {}
    for a in articoli:
        per_categoria.setdefault(a["categoria"], []).append(a)

    blocchi = []
    for categoria in config.SEZIONI:
        articoli_cat = per_categoria.get(categoria, [])
        if not articoli_cat:
            continue
        blocchi.append(f"\n=== SEZIONE: {categoria} ===")
        for a in articoli_cat:
            blocchi.append(
                f"- Fonte: {a['fonte']} | Titolo: {a['titolo']} | "
                f"Estratto: {a['estratto'][:500]}"
            )

    return "\n".join(blocchi)


GIORNI_IT = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI_IT = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
           "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def _data_italiana_oggi():
    """Restituisce la data odierna formattata in italiano (es. 'domenica 13 settembre 2026'),
    senza dipendere da locale di sistema (spesso non configurato in italiano su Windows)."""
    oggi = datetime.now()
    return f"{GIORNI_IT[oggi.weekday()]} {oggi.day} {MESI_IT[oggi.month - 1]} {oggi.year}"


def _estrai_json(testo_grezzo):
    """Il modello a volte avvolge il JSON in un blocco ```json ... ``` anche
    quando gli viene chiesto di non farlo: qui lo togliamo se presente prima
    di fare il parsing."""
    t = testo_grezzo.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t.rsplit("```", 1)[0]
        t = t.strip()
        if t.lower().startswith("json"):
            t = t[4:].strip()
    return t


def sintetizza(articoli, model=None):
    """Chiama Claude API e restituisce una lista di dict {"nome": ..., "testo": ...},
    una voce per sezione con notizie rilevanti oggi."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "Variabile d'ambiente ANTHROPIC_API_KEY non impostata. "
            "Vedi README.md sezione Setup."
        )

    model = model or config.CLAUDE_MODEL
    client = anthropic.Anthropic()

    input_utente = _prepara_input_utente(articoli)
    if not input_utente.strip():
        log.warning("Nessun articolo da sintetizzare (input vuoto).")
        return []

    numero_articoli = len(articoli)

    log.info(f"Invio {numero_articoli} articoli a Claude ({model}) per la sintesi...")

    data_oggi = _data_italiana_oggi()

    contenuto_utente = (
        f"Oggi è {data_oggi}. Usa questa data esatta nel saluto di apertura "
        "(non calcolarla o dedurla in altro modo).\n\n"
        f"Numero di articoli raccolti: {numero_articoli}.\n\n"
        "Ecco gli articoli raccolti oggi, raggruppati per sezione. "
        "Ogni articolo riporta fonte e testo: usa la fonte per le attribuzioni richieste.\n\n"
        "Rispondi SOLO con il JSON richiesto nel system prompt.\n\n"
        + input_utente
    )

    with client.messages.stream(
        model=model,
        max_tokens=32000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": contenuto_utente}],
    ) as stream:
        response = stream.get_final_message()
    

    log.info(
        "Risposta Claude: stop_reason=%s, input_tokens=%s, output_tokens=%s",
        response.stop_reason,
        getattr(response.usage, "input_tokens", "n/d"),
        getattr(response.usage, "output_tokens", "n/d"),
    )

    testo_grezzo = "".join(
        block.text for block in response.content if block.type == "text"
    )

    if response.stop_reason == "max_tokens":
        log.error("Claude ha esaurito il limite di token prima di chiudere il JSON.")
        log.error(f"Risposta grezza ricevuta (troncata):\n{testo_grezzo}")
        raise RuntimeError(
            "Claude ha troncato la risposta per il limite di token. "
            "Riduci gli articoli o aumenta max_tokens in synthesize.py."
        )

    try:
        dati = json.loads(_estrai_json(testo_grezzo))
        sezioni = dati.get("sezioni", [])
    except (json.JSONDecodeError, AttributeError) as e:
        log.error(f"Risposta del modello non è JSON valido: {e}")
        log.error(f"Risposta grezza ricevuta:\n{testo_grezzo}")
        raise RuntimeError(
            "Claude non ha restituito un JSON valido. Guarda logs/synthesize.log "
            "per il testo grezzo ricevuto."
        )

    # Validazione minima: nomi sezione devono essere tra quelli attesi
    sezioni_valide = []
    for s in sezioni:
        nome = s.get("nome", "")
        testo = s.get("testo", "")
        if nome not in config.SEZIONI:
            log.warning(f"Sezione con nome inatteso ignorata: '{nome}'")
            continue
        if not testo.strip():
            log.warning(f"Sezione '{nome}' ha testo vuoto, ignorata.")
            continue
        sezioni_valide.append({"nome": nome, "testo": testo.strip()})

    log.info(f"Sintesi completata: {len(sezioni_valide)} sezioni generate "
              f"({', '.join(s['nome'] for s in sezioni_valide)}).")
    return sezioni_valide


def salva_sezioni(sezioni):
    """Salva ogni sezione nel proprio file di testo (output/testo_<Sezione>.txt)."""
    for s in sezioni:
        percorso = config.percorso_testo_sezione(s["nome"])
        with open(percorso, "w", encoding="utf-8") as f:
            f.write(s["testo"])
        log.info(f"Salvato testo sezione '{s['nome']}' in {percorso}")


if __name__ == "__main__":
    with open(config.FILE_JSON_GREZZO, encoding="utf-8") as f:
        articoli = json.load(f)

    sezioni = sintetizza(articoli)
    salva_sezioni(sezioni)

    print("\n--- Sezioni generate ---\n")
    for s in sezioni:
        print(f"=== {s['nome']} ===")
        print(s["testo"])
        print()
