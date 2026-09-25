"""
musica.py — Aggiunge una base musicale in stile telegiornale attorno e sotto
l'audio vocale di ciascuna sezione.

Tre pezzi musicali separati (percorsi in config.py):
- MUSICA_INTRO: suonata DA SOLA prima della prima sezione della rassegna
- MUSICA_CORPO: in LOOP come sottofondo SOTTO la voce, in ogni sezione
- MUSICA_OUTRO: suonata DA SOLA dopo l'ultima sezione della rassegna

Il missaggio avviene in memoria su array numpy float32, alla sample rate di
XTTS-v2 (24000Hz), prima che tts.py scriva il file wav finale — non serve
nessun editing audio manuale, solo i 3 file musicali grezzi.

I file musicali possono essere in qualunque formato che ffmpeg sa leggere
(mp3, wav, ecc.): vengono convertiti automaticamente in mono alla sample
rate giusta la prima volta che servono, e tenuti in cache in memoria.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

import config
from logging_config import configura_logger

log = configura_logger("musica", "musica.log")

_cache_tracce = {}


def _carica_traccia(percorso, sample_rate_target):
    """Carica un file musicale convertendolo (via ffmpeg) in mono alla sample
    rate richiesta. Tenuto in cache: i 3 file musicali sono piccoli e vengono
    riusati per ogni sezione della rassegna."""
    percorso = str(percorso)
    chiave = (percorso, sample_rate_target)
    if chiave in _cache_tracce:
        return _cache_tracce[chiave]

    if not Path(percorso).exists():
        raise FileNotFoundError(f"File musicale non trovato: {percorso}")

    fd, percorso_temp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        comando = [
            "ffmpeg", "-y", "-i", percorso,
            "-ac", "1", "-ar", str(sample_rate_target),
            percorso_temp,
        ]
        risultato = subprocess.run(comando, capture_output=True, text=True)
        if risultato.returncode != 0:
            raise RuntimeError(f"ffmpeg non è riuscito a convertire {percorso}: {risultato.stderr}")
        dati, _ = sf.read(percorso_temp, dtype="float32", always_2d=False)
    finally:
        try:
            os.remove(percorso_temp)
        except OSError:
            pass

    _cache_tracce[chiave] = dati
    return dati


def _applica_dissolvenza(audio, sample_rate, ms=None):
    """Fade-in e fade-out brevi, per evitare click agli attacchi/stacchi tra
    un pezzo musicale e l'altro."""
    ms = ms if ms is not None else config.MUSICA_DISSOLVENZA_MS
    n = int(sample_rate * ms / 1000)
    n = min(n, len(audio) // 2)
    if n <= 0:
        return audio
    audio = audio.copy()
    audio[:n] *= np.linspace(0, 1, n, dtype=np.float32)
    audio[-n:] *= np.linspace(1, 0, n, dtype=np.float32)
    return audio


def _loop_a_lunghezza(traccia, lunghezza):
    """Ripete la traccia in loop finché non copre almeno 'lunghezza'
    campioni, poi taglia esattamente a quella lunghezza."""
    if len(traccia) == 0:
        return np.zeros(lunghezza, dtype=np.float32)
    n_ripetizioni = lunghezza // len(traccia) + 1
    return np.tile(traccia, n_ripetizioni)[:lunghezza]


def _mixa(voce, sottofondo, volume_sottofondo):
    """Mixa voce (volume pieno) e sottofondo (abbassato), normalizzando solo
    se il mix supera il livello di clipping."""
    mix = voce + sottofondo * volume_sottofondo
    picco = np.abs(mix).max()
    if picco > 1.0:
        mix = mix / picco * 0.99
    return mix.astype(np.float32)


def applica_musica(audio_voce, sample_rate, e_prima_sezione=False, e_ultima_sezione=False):
    """Aggiunge intro/corpo/outro musicale attorno all'audio vocale di una
    sezione, secondo la sua posizione nella rassegna del giorno:
    - prima sezione: [intro da sola] + [voce con corpo in loop come sottofondo]
    - sezioni centrali: [voce con corpo in loop come sottofondo]
    - ultima sezione: [voce con corpo in loop come sottofondo] + [outro da sola]
    (una sezione che è sia prima che ultima, es. un solo giorno con una sola
    sezione di notizie, include sia intro che outro)

    Se config.MUSICA_ABILITATA è False, o un file musicale manca/è illeggibile,
    va avanti comunque senza quella parte (non blocca mai la pipeline per un
    problema di musica di sottofondo)."""
    if not getattr(config, "MUSICA_ABILITATA", False):
        return audio_voce

    pezzi = []

    if e_prima_sezione:
        try:
            intro = _carica_traccia(config.MUSICA_INTRO, sample_rate)
            intro = _applica_dissolvenza(intro, sample_rate) * config.MUSICA_VOLUME_INTRO_OUTRO
            pezzi.append(intro.astype(np.float32))
        except Exception as e:
            log.warning(f"Musica di intro non disponibile, la salto: {e}")

    try:
        corpo = _carica_traccia(config.MUSICA_CORPO, sample_rate)
        sottofondo = _loop_a_lunghezza(corpo, len(audio_voce))
        sottofondo = _applica_dissolvenza(sottofondo, sample_rate)
        corpo_mixato = _mixa(audio_voce, sottofondo, config.MUSICA_VOLUME_SOTTOFONDO)
    except Exception as e:
        log.warning(f"Musica di sottofondo non disponibile, procedo con la sola voce: {e}")
        corpo_mixato = audio_voce
    pezzi.append(corpo_mixato)

    if e_ultima_sezione:
        try:
            outro = _carica_traccia(config.MUSICA_OUTRO, sample_rate)
            outro = _applica_dissolvenza(outro, sample_rate) * config.MUSICA_VOLUME_INTRO_OUTRO
            pezzi.append(outro.astype(np.float32))
        except Exception as e:
            log.warning(f"Musica di outro non disponibile, la salto: {e}")

    return np.concatenate(pezzi).astype(np.float32)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Testa il missaggio musicale (intro/corpo/outro) senza rifare la sintesi vocale."
    )
    parser.add_argument(
        "-v", "--voce",
        default=None,
        help="File audio (qualunque formato letto da ffmpeg) da usare come 'voce' per il test, "
             "es. un output/audio_<Sezione>.wav già generato. Se omesso, genera un placeholder "
             "silenzioso di --durata secondi.",
    )
    parser.add_argument(
        "--durata", type=float, default=5.0,
        help="Durata in secondi del placeholder silenzioso, usato solo se --voce non è passato "
             "(default: 5).",
    )
    parser.add_argument(
        "--prima", action="store_true",
        help="Simula la prima sezione della rassegna (aggiunge la musica di intro).",
    )
    parser.add_argument(
        "--ultima", action="store_true",
        help="Simula l'ultima sezione della rassegna (aggiunge la musica di outro).",
    )
    parser.add_argument(
        "-o", "--output", default="output/test_musica.wav",
        help="Percorso del file wav di output (default: output/test_musica.wav).",
    )
    args = parser.parse_args()

    SAMPLE_RATE_TEST = 24000  # stessa sample rate usata da XTTS-v2 in tts.py

    if args.voce:
        if not Path(args.voce).exists():
            print(f"File non trovato: {args.voce}")
            raise SystemExit(1)
        print(f"Carico come voce: {args.voce}")
        voce = _carica_traccia(args.voce, SAMPLE_RATE_TEST)  # ffmpeg gestisce mono+resample
        print(f"  durata: {len(voce) / SAMPLE_RATE_TEST:.2f}s")
    else:
        voce = np.zeros(int(SAMPLE_RATE_TEST * args.durata), dtype=np.float32)
        print(f"Nessun file --voce passato: uso {args.durata}s di silenzio come placeholder "
              f"(utile solo per verificare durate/timing, non per sentire davvero la voce).")

    print(f"Posizione simulata: prima_sezione={args.prima}, ultima_sezione={args.ultima}\n")

    risultato = applica_musica(voce, SAMPLE_RATE_TEST, e_prima_sezione=args.prima, e_ultima_sezione=args.ultima)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    sf.write(args.output, risultato, SAMPLE_RATE_TEST)
    print(f"\nFile generato: {args.output}")
    print(f"Durata totale: {len(risultato) / SAMPLE_RATE_TEST:.2f}s "
          f"(voce: {len(voce) / SAMPLE_RATE_TEST:.2f}s)")
