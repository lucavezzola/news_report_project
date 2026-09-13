"""
synthesize.py — Fase 2: sintesi imparziale degli articoli via Claude API.

Prende la lista di articoli grezzi (da fetch.py) e produce un testo unico,
in prosa parlata, diviso per sezioni, pensato per essere letto ad alta voce
da un TTS.

Richiede la variabile d'ambiente ANTHROPIC_API_KEY.

Uso da terminale (test manuale su un JSON già salvato):
    python synthesize.py

Uso da main.py:
    from synthesize import sintetizza
    testo = sintetizza(articoli)
"""

import json
import logging
import os

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


SYSTEM_PROMPT = """Sei un redattore che prepara una rassegna stampa audio giornaliera, imparziale e bilanciata, per un piccolo gruppo di ascoltatori italiani.

REGOLE DI IMPARZIALITÀ (fondamentali, da rispettare sempre):
1. Non usare aggettivi valutativi tuoi; riporta solo ciò che le fonti dicono.
2. Se una fonte usa un framing marcatamente diverso da un'altra sullo stesso fatto, segnalalo per nome (es. "Il Foglio inquadra la vicenda come..., mentre Repubblica la presenta come...") — non appiattire le differenze.
3. Quando riporti un'affermazione specifica o un dato, cita da quale fonte proviene.
4. Se un fatto è riportato da una sola fonte, dillo esplicitamente (es. "secondo una sola fonte, ANSA, ...") perché ha minore affidabilità rispetto a una notizia confermata da più fonti indipendenti.
5. Raggruppa gli articoli per argomento/evento: se più fonti raccontano lo stesso fatto, trattale come un unico blocco narrativo, non ripetere la stessa notizia più volte.

FORMATO DI OUTPUT (fondamentale, perché il testo verrà letto da un sintetizzatore vocale):
- Scrivi in prosa parlata: frasi brevi e scorrevoli, come se un giornalista radiofonico stesse leggendo in diretta.
- NIENTE markdown, NIENTE elenchi puntati, NIENTE asterischi o simboli. Solo testo continuo.
- Organizza il contenuto nelle sezioni, in quest'ordine: Italia, Esteri, Economia, Tecnologia.
- Apri ogni sezione con una breve frase di transizione naturale (es. "Passiamo all'economia.").
- Se una sezione non ha notizie rilevanti quel giorno, salta la sezione senza commentarlo (non dire "oggi non ci sono notizie").
- Apri il resoconto con un brevissimo saluto e la data, chiudi con un breve commiato.
- Non inventare fatti non presenti negli articoli forniti. Se le informazioni sono scarse su un argomento, sii sintetico piuttosto che aggiungere dettagli non verificati.
"""


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


def sintetizza(articoli, model=None):
    """Chiama Claude API e restituisce il testo della rassegna pronto per il TTS."""
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
        return ""

    log.info(f"Invio {len(articoli)} articoli a Claude ({model}) per la sintesi...")

    response = client.messages.create(
        model=model,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Ecco gli articoli raccolti oggi, raggruppati per sezione. "
                    "Scrivi il resoconto seguendo tutte le regole del system prompt.\n"
                    + input_utente
                ),
            }
        ],
    )

    testo = "".join(
        block.text for block in response.content if block.type == "text"
    )
    log.info(f"Sintesi completata: {len(testo)} caratteri.")
    return testo


def salva_testo(testo, percorso=None):
    percorso = percorso or config.FILE_TESTO_SINTESI
    with open(percorso, "w", encoding="utf-8") as f:
        f.write(testo)
    log.info(f"Salvato testo di sintesi in {percorso}")


if __name__ == "__main__":
    with open(config.FILE_JSON_GREZZO, encoding="utf-8") as f:
        articoli = json.load(f)

    testo = sintetizza(articoli)
    salva_testo(testo)

    print("\n--- Testo generato ---\n")
    print(testo)
