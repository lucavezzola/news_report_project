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

    percorso_wav = str(percorso_wav or config.FILE_AUDIO_WAV)
    percorso_ogg = str(percorso_ogg or config.FILE_AUDIO_OGG)

    _verifica_prerequisiti()

    log.info(f"Genero audio con Piper -> {percorso_wav}")
    comando_piper = [
        config.PIPER_EXECUTABLE,
        "--model", config.PIPER_MODEL_PATH,
        "--output_file", percorso_wav,
        "--noise-scale", str(config.PIPER_NOISE_SCALE),
        "--length-scale", str(config.PIPER_LENGTH_SCALE),
        "--noise-w", str(config.PIPER_NOISE_W),
        "--sentence-silence", str(config.PIPER_SENTENCE_SILENCE),
    ]
    try:
        risultato = subprocess.run(
            comando_piper,
            input=testo,
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Piper ha impiegato troppo tempo per sintetizzare l'audio.") from exc
    if risultato.returncode != 0:
        log.error(f"Piper ha restituito errore: {risultato.stderr}")
        raise RuntimeError(f"Errore Piper: {risultato.stderr}")

    log.info(f"Converto in ogg (bitrate leggero) -> {percorso_ogg}")
    comando_ffmpeg = [
        "ffmpeg", "-y", "-nostdin",
        "-hide_banner",
        "-loglevel", "error",
        "-i", percorso_wav,
        "-c:a", "libopus", "-b:a", "32k",
        percorso_ogg,
    ]
    try:
        risultato = subprocess.run(
            comando_ffmpeg,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("ffmpeg ha impiegato troppo tempo per convertire l'audio.") from exc
    if risultato.returncode != 0:
        log.error(f"ffmpeg ha restituito errore: {risultato.stderr}")
        raise RuntimeError(f"Errore ffmpeg: {risultato.stderr}")

    log.info(f"Audio pronto: {percorso_ogg}")
    return percorso_ogg


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Sintetizza l'audio di una o più sezioni della rassegna.")
    parser.add_argument(
        "--sezione",
        default="all",
        help="Nome della sezione da sintetizzare (Italia, Esteri, Economia, Tecnologia) oppure 'all' per tutte."
    )
    parser.add_argument("--testo", help="Percorso opzionale a un file di testo alternativo da usare invece delle sezioni standard.")
    parser.add_argument("--wav", help="Percorso del file WAV di output. Usato solo con una singola sezione.")
    parser.add_argument("--ogg", help="Percorso del file OGG di output. Usato solo con una singola sezione.")
    args = parser.parse_args()

    if args.testo:
        with open(args.testo, encoding="utf-8") as f:
            testo = f.read()
        percorso_wav = args.wav or config.FILE_AUDIO_WAV
        percorso_ogg = args.ogg or config.FILE_AUDIO_OGG
        percorso = genera_audio(testo, percorso_wav, percorso_ogg)
        print(f"Audio generato da file personalizzato: {percorso}")
        raise SystemExit(0)

    sezioni = config.SEZIONI if args.sezione == "all" else [args.sezione]
    if len(sezioni) > 1 and (args.wav or args.ogg):
        raise ValueError("--wav e --ogg possono essere usati solo con una singola sezione. In modalità 'all' il percorso viene generato automaticamente per ogni sezione.")

    for nome_sezione in sezioni:
        percorso_testo = config.percorso_testo_sezione(nome_sezione)
        if not Path(percorso_testo).exists():
            log.warning(
                "File testo non trovato per la sezione '%s': %s. Salto la sezione.",
                nome_sezione,
                percorso_testo,
            )
            continue

        with open(percorso_testo, encoding="utf-8") as f:
            testo = f.read()

        percorso_wav = args.wav or config.percorso_audio_wav_sezione(nome_sezione)
        percorso_ogg = args.ogg or config.percorso_audio_ogg_sezione(nome_sezione)
        percorso = genera_audio(testo, percorso_wav, percorso_ogg)
        print(f"Audio generato per sezione '{nome_sezione}': {percorso}")
