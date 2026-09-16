"""
main.py — Orchestratore della pipeline completa.

Esegue in sequenza: fetch -> sintesi -> TTS -> invio Telegram.
Genera e invia UN AUDIO SEPARATO PER OGNI SEZIONE (Italia, Esteri, Tecnologia),
inviati come messaggi distinti in sequenza sul canale Telegram.
La prima sezione generata quel giorno riceve la musica di intro, l'ultima
quella di outro (vedi musica.py e config.MUSICA_*).

Pensato per essere lanciato da Task Scheduler ogni mattina.

Uso:
    python main.py
"""

import logging
import sys
import traceback
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()  # carica ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, ecc. da .env se presente

import config
import fetch
import synthesize
import tts
import send_telegram

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/main.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("main")


def esegui_pipeline():
    log.info("=" * 70)
    log.info(f"Avvio pipeline rassegna stampa — {datetime.now().isoformat()}")

    # --- Fase 1: fetch ---
    log.info("Fase 1/4: raccolta articoli...")
    articoli = fetch.raccogli_articoli()
    fetch.salva_json(articoli)
    if not articoli:
        log.error("Nessun articolo raccolto. Interrompo la pipeline.")
        sys.exit(1)

    # --- Fase 2: sintesi (una voce di testo per sezione) ---
    log.info("Fase 2/4: sintesi con Claude...")
    sezioni = synthesize.sintetizza(articoli)
    synthesize.salva_sezioni(sezioni)
    if not sezioni:
        log.error("Nessuna sezione generata. Interrompo la pipeline.")
        sys.exit(1)

    # --- Fase 3 + 4: per ogni sezione, genera l'audio e invialo subito ---
    # (invio sezione per sezione, non tutto insieme alla fine, così se una
    # sezione fallisce le precedenti sono già state consegnate)
    # e_prima/e_ultima si basano sulla posizione REALE nella lista di sezioni
    # generate oggi (non su config.SEZIONI), perché una sezione può mancare
    # se non ci sono notizie rilevanti quel giorno.
    data_oggi_breve = datetime.now().strftime("%d/%m/%Y")
    sezioni_fallite = []
    for indice, s in enumerate(sezioni):
        nome = s["nome"]
        e_prima = (indice == 0)
        e_ultima = (indice == len(sezioni) - 1)
        try:
            log.info(f"Fase 3/4: sintesi vocale sezione '{nome}'...")
            percorso_wav = config.percorso_audio_wav_sezione(nome)
            percorso_ogg = config.percorso_audio_ogg_sezione(nome)
            voce = config.voce_per_sezione(nome)
            if voce:
                log.info(f"  voce assegnata a '{nome}': {voce}")
            percorso_audio = tts.genera_audio(
                s["testo"], percorso_wav, percorso_ogg,
                speaker_name=voce,
                e_prima_sezione=e_prima,
                e_ultima_sezione=e_ultima,
            )

            log.info(f"Fase 4/4: invio sezione '{nome}' su Telegram...")
            didascalia = f"{nome} — {data_oggi_breve}"
            send_telegram.invia_audio(percorso_audio, didascalia=didascalia)
        except Exception:
            log.error(f"Sezione '{nome}' fallita, salto e continuo con le altre:\n" + traceback.format_exc())
            sezioni_fallite.append(nome)

    if sezioni_fallite:
        log.error(f"Pipeline completata con errori nelle sezioni: {', '.join(sezioni_fallite)}")
        sys.exit(1)  # exit code diverso da 0 per far notare il problema a Task Scheduler
    log.info("Pipeline completata con successo.")


if __name__ == "__main__":
    try:
        esegui_pipeline()
    except Exception:
        log.error("Pipeline interrotta da un errore:\n" + traceback.format_exc())
        sys.exit(1)
