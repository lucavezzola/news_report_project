"""
main.py — Orchestratore della pipeline completa.

Esegue in sequenza: fetch -> sintesi -> TTS -> invio Telegram.
Pensato per essere lanciato da Task Scheduler ogni mattina.

Uso:
    python main.py

Ogni fase è isolata: se una fase fallisce, l'errore viene loggato con
traceback completo in logs/main.log e lo script esce con codice diverso da 0
(utile per far vedere a Task Scheduler che qualcosa è andato storto).
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

    # --- Fase 2: sintesi ---
    log.info("Fase 2/4: sintesi con Claude...")
    testo = synthesize.sintetizza(articoli)
    synthesize.salva_testo(testo)
    if not testo.strip():
        log.error("Sintesi vuota. Interrompo la pipeline.")
        sys.exit(1)

    # --- Fase 3: TTS ---
    log.info("Fase 3/4: sintesi vocale...")
    percorso_audio = tts.genera_audio(testo)

    # --- Fase 4: invio Telegram ---
    log.info("Fase 4/4: invio su Telegram...")
    didascalia = f"Rassegna stampa audio — {datetime.now().strftime('%A %d %B %Y')}"
    send_telegram.invia_audio(percorso_audio, didascalia=didascalia)

    log.info("Pipeline completata con successo.")


if __name__ == "__main__":
    try:
        esegui_pipeline()
    except Exception:
        log.error("Pipeline interrotta da un errore:\n" + traceback.format_exc())
        sys.exit(1)
