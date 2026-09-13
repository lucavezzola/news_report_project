"""
tts.py — Fase 3: sintesi vocale locale con Piper.

Converte il testo della rassegna in un file audio .wav con Piper, poi lo
comprime in .ogg (formato leggero, ideale per Telegram) con ffmpeg.

Prerequisiti (vedi README.md sezione "Setup Piper"):
- binario `piper` installato e raggiungibile (nel PATH o percorso assoluto
  in config.PIPER_EXECUTABLE)
- un modello vocale italiano scaricato (.onnx + .onnx.json), percorso in
  config.PIPER_MODEL_PATH
- ffmpeg installato e nel PATH

Uso da terminale (test manuale sul testo già generato):
    python tts.py

Uso da main.py:
    from tts import genera_audio
    percorso_ogg = genera_audio(testo)
"""

import logging
import subprocess
from pathlib import Path

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/tts.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("tts")


def _verifica_prerequisiti():
    problemi = []

    if not Path(config.PIPER_MODEL_PATH).exists():
        problemi.append(
            f"Modello Piper non trovato: {config.PIPER_MODEL_PATH} "
            "(scaricalo, vedi README.md)"
        )

    try:
        subprocess.run(
            [config.PIPER_EXECUTABLE, "--help"],
            capture_output=True, check=False, timeout=10,
        )
    except FileNotFoundError:
        problemi.append(
            f"Eseguibile Piper '{config.PIPER_EXECUTABLE}' non trovato nel PATH."
        )

    try:
        subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, check=False, timeout=10
        )
    except FileNotFoundError:
        problemi.append("ffmpeg non trovato nel PATH (serve per convertire wav -> ogg).")

    if problemi:
        for p in problemi:
            log.error(p)
        raise RuntimeError("Prerequisiti TTS mancanti:\n" + "\n".join(problemi))


def genera_audio(testo, percorso_wav=None, percorso_ogg=None):
    """Genera il file audio dal testo. Ritorna il percorso del file .ogg finale."""
    if not testo or not testo.strip():
        raise ValueError("Testo vuoto: niente da sintetizzare.")

    percorso_wav = percorso_wav or config.FILE_AUDIO_WAV
    percorso_ogg = percorso_ogg or config.FILE_AUDIO_OGG

    _verifica_prerequisiti()

    log.info(f"Genero audio con Piper -> {percorso_wav}")
    comando_piper = [
        config.PIPER_EXECUTABLE,
        "--model", config.PIPER_MODEL_PATH,
        "--output_file", percorso_wav,
    ]
    risultato = subprocess.run(
        comando_piper, input=testo, text=True, capture_output=True
    )
    if risultato.returncode != 0:
        log.error(f"Piper ha restituito errore: {risultato.stderr}")
        raise RuntimeError(f"Errore Piper: {risultato.stderr}")

    log.info(f"Converto in ogg (bitrate leggero) -> {percorso_ogg}")
    comando_ffmpeg = [
        "ffmpeg", "-y",
        "-i", percorso_wav,
        "-c:a", "libopus", "-b:a", "32k",
        percorso_ogg,
    ]
    risultato = subprocess.run(comando_ffmpeg, capture_output=True, text=True)
    if risultato.returncode != 0:
        log.error(f"ffmpeg ha restituito errore: {risultato.stderr}")
        raise RuntimeError(f"Errore ffmpeg: {risultato.stderr}")

    log.info(f"Audio pronto: {percorso_ogg}")
    return percorso_ogg


if __name__ == "__main__":
    with open(config.FILE_TESTO_SINTESI, encoding="utf-8") as f:
        testo = f.read()

    percorso = genera_audio(testo)
    print(f"Audio generato: {percorso}")
