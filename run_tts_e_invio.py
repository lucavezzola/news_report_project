"""
run_tts_e_invio.py — Esegue solo Fase 3 (TTS) + Fase 4 (invio Telegram) sui
testi delle sezioni già generati oggi in output/testo_<Sezione>.txt.

Utile per rilanciare l'invio dopo aver corretto un testo a mano, o dopo un
fix a tts.py/config.py, senza rifare fetch + chiamata a Claude.

Uso:
    python run_tts_e_invio.py
    python run_tts_e_invio.py -s Italia Tecnologia   # solo alcune sezioni
"""

import argparse
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import config
import tts
import send_telegram

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/run_tts_e_invio.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("run_tts_e_invio")


def carica_sezioni_da_file(nomi_sezioni):
    """Legge output/testo_<Sezione>.txt per ogni nome richiesto, saltando
    quelle mancanti (es. sezioni omesse quel giorno perché senza notizie)."""
    sezioni = []
    for nome in nomi_sezioni:
        percorso = Path(config.percorso_testo_sezione(nome))
        if not percorso.exists():
            log.warning(f"File non trovato per sezione '{nome}', salto: {percorso}")
            continue
        testo = percorso.read_text(encoding="utf-8").strip()
        if not testo:
            log.warning(f"File vuoto per sezione '{nome}', salto: {percorso}")
            continue
        sezioni.append({"nome": nome, "testo": testo})
    return sezioni


def esegui(nomi_sezioni):
    sezioni = carica_sezioni_da_file(nomi_sezioni)
    if not sezioni:
        log.error("Nessuna sezione da processare (file mancanti o vuoti). Interrompo.")
        sys.exit(1)

    data_oggi_breve = datetime.now().strftime("%d/%m/%Y")
    sezioni_fallite = []
    for s in sezioni:
        nome = s["nome"]
        try:
            log.info(f"TTS sezione '{nome}'...")
            percorso_wav = config.percorso_audio_wav_sezione(nome)
            percorso_ogg = config.percorso_audio_ogg_sezione(nome)
            voce = config.voce_per_sezione(nome)
            if voce:
                log.info(f"  voce assegnata a '{nome}': {voce}")
            percorso_audio = tts.genera_audio(s["testo"], percorso_wav, percorso_ogg, speaker_name=voce)

            log.info(f"Invio sezione '{nome}' su Telegram...")
            didascalia = f"{nome} — {data_oggi_breve}"
            send_telegram.invia_audio(percorso_audio, didascalia=didascalia)
        except Exception:
            log.error(f"Sezione '{nome}' fallita:\n" + traceback.format_exc())
            sezioni_fallite.append(nome)

    if sezioni_fallite:
        log.error(f"Completato con errori nelle sezioni: {', '.join(sezioni_fallite)}")
        sys.exit(1)
    log.info("Completato con successo.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-s", "--sezioni",
        nargs="+",
        choices=config.SEZIONI,
        default=config.SEZIONI,
        help="Sezioni da processare (default: tutte quelle in config.SEZIONI, "
             "nell'ordine dato lì, non nell'ordine passato qui).",
    )
    args = parser.parse_args()

    # Rispetta sempre l'ordine di config.SEZIONI, indipendentemente dall'ordine
    # con cui sono state passate su riga di comando.
    nomi_richiesti = [n for n in config.SEZIONI if n in args.sezioni]

    esegui(nomi_richiesti)