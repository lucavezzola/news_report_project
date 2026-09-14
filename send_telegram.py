"""
send_telegram.py — Fase 4: invio dell'audio su Telegram.

Richiede due variabili d'ambiente (vedi README.md e .env.example):
- TELEGRAM_BOT_TOKEN: token del bot creato con @BotFather
- TELEGRAM_CHAT_ID: id del canale/gruppo privato a cui inviare

Uso da terminale (test manuale sull'audio già generato):
    python send_telegram.py

Uso da main.py:
    from send_telegram import invia_audio
    invia_audio(percorso_ogg, didascalia="Rassegna del 13 settembre 2026")
"""

import logging
import os
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()  # legge TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID dal file .env, se presente

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/telegram.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("telegram")


def invia_audio(percorso_audio, didascalia=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN e/o TELEGRAM_CHAT_ID non impostate. "
            "Vedi README.md sezione Setup Telegram."
        )

    didascalia = didascalia or f"Rassegna stampa audio — {datetime.now().strftime('%d/%m/%Y')}"

    url = f"https://api.telegram.org/bot{token}/sendAudio"
    log.info(f"Invio {percorso_audio} al chat_id {chat_id}...")

    with open(percorso_audio, "rb") as audio_file:
        risposta = requests.post(
            url,
            data={"chat_id": chat_id, "caption": didascalia},
            files={"audio": audio_file},
            timeout=60,
        )

    if not risposta.ok:
        log.error(f"Errore invio Telegram: {risposta.status_code} {risposta.text}")
        raise RuntimeError(f"Errore invio Telegram: {risposta.text}")

    log.info("Audio inviato con successo.")
    return risposta.json()


if __name__ == "__main__":
    import argparse
    from pathlib import Path
    import config

    parser = argparse.ArgumentParser(description="Invia un audio o tutte le sezioni della rassegna su Telegram.")
    parser.add_argument(
        "--sezione",
        default="all",
        help="Sezione da inviare (Italia, Esteri, Economia, Tecnologia) oppure 'all' per tutte."
    )
    args = parser.parse_args()

    sezioni = config.SEZIONI if args.sezione == "all" else [args.sezione]
    for nome_sezione in sezioni:
        percorso = config.percorso_audio_ogg_sezione(nome_sezione)
        if not Path(percorso).exists():
            log.warning(
                "Audio non trovato per la sezione '%s': %s. Salto la sezione.",
                nome_sezione,
                percorso,
            )
            continue

        invia_audio(percorso, didascalia=f"{nome_sezione} — {datetime.now().strftime('%d/%m/%Y')}")
