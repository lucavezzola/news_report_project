"""
tts.py — Fase 3: sintesi vocale locale con XTTS-v2 (Coqui), attento alla VRAM.

Il modello viene caricato UNA SOLA VOLTA (non ad ogni chiamata) e riutilizzato
per tutte le sezioni, per non spendere tempo/VRAM extra ricaricandolo ogni
volta. Il testo di ogni sezione viene spezzato in blocchi di frasi (XTTS-v2
degrada in stabilità su input molto lunghi in un colpo solo), sintetizzato
blocco per blocco, e i blocchi vengono poi concatenati con un breve silenzio
tra l'uno e l'altro.

Prerequisiti (vedi README.md sezione "Setup XTTS-v2"):
- pacchetto `coqui-tts` installato (il fork mantenuto, NON il vecchio `TTS`
  di PyPI — non sono compatibili tra loro)
- PyTorch con supporto CUDA installato per la tua GPU
- un file audio di riferimento per il voice cloning, percorso in
  config.XTTS_SPEAKER_WAV
- ffmpeg installato e nel PATH (per la conversione finale in .ogg)

Uso da terminale (test manuale sul testo di una sezione già generato):
    python tts.py

Uso da main.py:
    from tts import genera_audio
    percorso_ogg = genera_audio(testo, percorso_wav, percorso_ogg)
"""

import gc
import logging
import os
import re
import subprocess
from pathlib import Path

import numpy as np

import config
import musica

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/tts.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("tts")

# Le librerie sotto XTTS-v2 (TTS, numba, matplotlib, transformers) loggano
# parecchio a livello INFO (dettagli interni tipo "Text split into
# sentences.", tempi di processing per singola chiamata, ecc.) — li silenzio
# tenendo solo warning/errori, il nostro logger "tts" resta a INFO.
for _nome_logger_esterno in ("TTS", "numba", "matplotlib", "transformers"):
    logging.getLogger(_nome_logger_esterno).setLevel(logging.WARNING)

# Registra la cartella delle DLL ffmpeg PRIMA che torch/torchcodec vengano
# importati da qualunque punto del codice: dal Python 3.8 in poi, ctypes non
# cerca più le dipendenze delle DLL native nel PATH di sistema su Windows,
# va usata esplicitamente questa API.
if os.name == "nt" and getattr(config, "FFMPEG_DLL_DIR", None):
    _cartella_dll = config.FFMPEG_DLL_DIR
    if os.path.isdir(_cartella_dll):
        os.add_dll_directory(_cartella_dll)
        log.info(f"Registrata cartella DLL ffmpeg: {_cartella_dll}")
    else:
        log.warning(
            f"config.FFMPEG_DLL_DIR punta a una cartella inesistente: {_cartella_dll} "
            "— torch/torchcodec potrebbero non trovare le DLL di ffmpeg."
        )

SAMPLE_RATE = 24000  # frequenza di campionamento fissa di XTTS-v2

# Il modello viene tenuto qui una volta caricato, per essere riusato tra le
# chiamate a genera_audio() senza ricaricarlo (costoso in tempo e VRAM).
_modello_tts = None
_device_usato = None


def _verifica_prerequisiti(richiedi_speaker_wav=True):
    problemi = []

    if richiedi_speaker_wav and not Path(config.XTTS_SPEAKER_WAV).exists():
        problemi.append(
            f"Audio di riferimento per il voice cloning non trovato: "
            f"{config.XTTS_SPEAKER_WAV} (vedi README.md sezione Setup XTTS-v2)"
        )

    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=False, timeout=10)
    except FileNotFoundError:
        problemi.append("ffmpeg non trovato nel PATH (serve per convertire wav -> ogg).")

    if problemi:
        for p in problemi:
            log.error(p)
        raise RuntimeError("Prerequisiti TTS mancanti:\n" + "\n".join(problemi))


def list_speakers():
    """Restituisce la lista delle 58 voci predefinite di XTTS-v2 (nessun
    cloning, voci native del modello)."""
    modello = _carica_modello()
    return list(modello.speakers or [])


def _scegli_device():
    """Sceglie GPU o CPU controllando la VRAM libera, per evitare crash per
    out-of-memory a metà pipeline."""
    import torch

    if not torch.cuda.is_available():
        log.warning("Nessuna GPU CUDA rilevata: uso la CPU (sarà molto più lento).")
        return "cpu"

    libera_bytes, totale_bytes = torch.cuda.mem_get_info()
    libera_gb = libera_bytes / (1024 ** 3)
    totale_gb = totale_bytes / (1024 ** 3)
    log.info(f"GPU rilevata — VRAM libera: {libera_gb:.1f}GB / {totale_gb:.1f}GB totali")

    if libera_gb < config.XTTS_MIN_VRAM_LIBERA_GB:
        log.warning(
            f"VRAM libera ({libera_gb:.1f}GB) sotto la soglia minima "
            f"({config.XTTS_MIN_VRAM_LIBERA_GB}GB): passo alla CPU per sicurezza. "
            "Chiudi altri programmi che usano la GPU se vuoi provare comunque su GPU."
        )
        return "cpu"

    return "cuda"


def _carica_modello():
    """Carica il modello XTTS-v2 una sola volta (lazy loading) e lo tiene in
    memoria per le chiamate successive."""
    global _modello_tts, _device_usato

    if _modello_tts is not None:
        return _modello_tts

    import torch
    from TTS.api import TTS

    _device_usato = _scegli_device()
    log.info(f"Carico il modello XTTS-v2 su {_device_usato}... (può richiedere un minuto)")

    modello = TTS(config.XTTS_MODEL_NAME).to(_device_usato)

    if _device_usato == "cuda" and config.XTTS_USE_FP16:
        try:
            modello.synthesizer.tts_model.half()
            log.info("Modello caricato in fp16 (mezza precisione, VRAM ridotta).")
        except Exception as e:
            log.warning(f"Non sono riuscito a passare a fp16, resto in fp32: {e}")

    _modello_tts = modello
    return _modello_tts


def _spezza_frase_lunga(frase, max_caratteri):
    """Se una singola frase supera da sola il limite, la spezza ulteriormente
    sulle virgole (o punto e virgola), per restare sotto il limite interno di
    XTTS-v2 (213 caratteri per l'italiano) ed evitare troncamenti audio."""
    if len(frase) <= max_caratteri:
        return [frase]

    pezzi = re.split(r'(?<=[,;:])\s+', frase)
    blocchi = []
    corrente = ""
    for pezzo in pezzi:
        candidato = f"{corrente} {pezzo}".strip() if corrente else pezzo
        if len(candidato) <= max_caratteri:
            corrente = candidato
        else:
            if corrente:
                blocchi.append(corrente)
            corrente = pezzo
    if corrente:
        blocchi.append(corrente)

    # Se anche dopo aver spezzato sulle virgole un pezzo resta troppo lungo
    # (frase senza punteggiatura interna), non c'è altro modo pulito di
    # spezzarla: la teniamo com'è, il warning di XTTS è l'unico costo.
    return blocchi


def _spezza_in_blocchi(testo, max_caratteri=None):
    """Spezza il testo in blocchi di frasi complete, ciascuno sotto la soglia
    di caratteri, senza mai tagliare una frase a metà (tranne, come ultima
    risorsa, sulle virgole per le frasi singole troppo lunghe)."""
    max_caratteri = max_caratteri or config.XTTS_MAX_CHARS_PER_CHUNK

    frasi = re.split(r'(?<=[.!?])\s+', testo.strip())
    frasi = [f.strip() for f in frasi if f.strip()]

    blocchi = []
    corrente = ""
    for frase in frasi:
        candidato = f"{corrente} {frase}".strip() if corrente else frase
        if len(candidato) <= max_caratteri:
            corrente = candidato
        else:
            if corrente:
                blocchi.append(corrente)
            # Se anche una singola frase supera la soglia, proviamo a
            # spezzarla ulteriormente sulle virgole prima di arrenderci.
            if len(frase) > max_caratteri:
                blocchi.extend(_spezza_frase_lunga(frase, max_caratteri))
                corrente = ""
            else:
                corrente = frase
    if corrente:
        blocchi.append(corrente)

    return blocchi


def _pulisci_testo(testo):
    """Ripulisce piccole irregolarità di spaziatura/punteggiatura che possono
    confondere il normalizzatore testuale di XTTS-v2 e fargli leggere ad alta
    voce simboli come il punto invece di trattarli come fine frase."""
    t = testo.strip()
    t = re.sub(r'\s+', ' ', t)              # spazi multipli -> uno solo
    t = re.sub(r'\s+([.,!?;:])', r'\1', t)  # niente spazio prima della punteggiatura
    t = re.sub(r'([.!?]){2,}', r'\1', t)    # punti/esclamativi/interrogativi ripetuti -> uno solo
    # Spazio dopo la punteggiatura se manca, ma solo se seguita da una
    # lettera (non da una cifra: protegge i numeri decimali tipo "3.14" o "3,5").
    t = re.sub(r'(?<=[.,!?;:])(?=[A-Za-zÀ-ÖØ-öø-ÿ])', ' ', t)
    return t.strip()


def genera_audio(testo, percorso_wav=None, percorso_ogg=None, speaker_wav=None, speaker_name=None,
                  e_prima_sezione=False, e_ultima_sezione=False):
    """Genera il file audio dal testo con XTTS-v2. Ritorna il percorso del
    file .ogg finale.

    speaker_wav: percorso del file audio di riferimento per il voice cloning.
    speaker_name: nome di una delle 58 voci predefinite di XTTS-v2 (vedi
    list_speakers()), in ALTERNATIVA a speaker_wav — se lo passi, niente
    cloning, usa direttamente quella voce nativa del modello.
    Se non passi né l'uno né l'altro, usa config.XTTS_SPEAKER_WAV (comportamento di sempre).

    e_prima_sezione / e_ultima_sezione: se True, aggiunge rispettivamente la
    musica di intro (prima) o di outro (dopo) attorno all'audio — vedi
    musica.py e config.MUSICA_*. Se config.MUSICA_ABILITATA è False, questi
    due parametri non hanno effetto (nessuna musica in nessun caso)."""
    if not testo or not testo.strip():
        raise ValueError("Testo vuoto: niente da sintetizzare.")
    if not percorso_wav or not percorso_ogg:
        raise ValueError("Vanno specificati percorso_wav e percorso_ogg (uno per sezione).")

    if not speaker_name and not speaker_wav:
        speaker_wav = config.XTTS_SPEAKER_WAV
    if speaker_name and speaker_wav:
        raise ValueError("Specifica solo uno tra speaker_name e speaker_wav, non entrambi.")
    if speaker_wav and not Path(speaker_wav).exists():
        raise RuntimeError(f"Audio di riferimento non trovato: {speaker_wav}")

    testo = _pulisci_testo(testo)

    _verifica_prerequisiti(richiedi_speaker_wav=(speaker_wav is not None))
    modello = _carica_modello()

    blocchi = _spezza_in_blocchi(testo)
    voce_usata = f"voce predefinita '{speaker_name}'" if speaker_name else f"clonata da {speaker_wav}"
    log.info(f"Sintetizzo {len(blocchi)} blocchi di testo con XTTS-v2 -> {percorso_wav} ({voce_usata})")

    silenzio = np.zeros(int(SAMPLE_RATE * config.XTTS_SILENZIO_TRA_CHUNK_MS / 1000), dtype=np.float32)
    pezzi_audio = []

    kwargs_voce = {"speaker": speaker_name} if speaker_name else {"speaker_wav": speaker_wav}

    for i, blocco in enumerate(blocchi, 1):
        log.debug(f"  blocco {i}/{len(blocchi)} ({len(blocco)} caratteri)...")
        try:
            onda = modello.tts(
                text=blocco,
                language=config.XTTS_LANGUAGE,
                **kwargs_voce,
            )
        except RuntimeError as e:
            if "out of memory" in str(e).lower():
                log.error(
                    "Out-of-memory sulla GPU durante la sintesi. Prova a: "
                    "chiudere altri programmi che usano la GPU, ridurre "
                    "XTTS_MAX_CHARS_PER_CHUNK in config.py, o verificare che "
                    "XTTS_USE_FP16 sia True."
                )
            raise

        pezzi_audio.append(np.asarray(onda, dtype=np.float32))
        if i < len(blocchi):
            pezzi_audio.append(silenzio)

        # Libera la cache della GPU tra un blocco e l'altro: non riduce la
        # memoria occupata dai pesi del modello, ma evita accumulo di
        # frammentazione/allocazioni temporanee tra una chiamata e l'altra.
        if _device_usato == "cuda":
            import torch
            torch.cuda.empty_cache()

    audio_completo = np.concatenate(pezzi_audio)

    audio_completo = musica.applica_musica(
        audio_completo, SAMPLE_RATE,
        e_prima_sezione=e_prima_sezione,
        e_ultima_sezione=e_ultima_sezione,
    )

    import soundfile as sf
    sf.write(percorso_wav, audio_completo, SAMPLE_RATE)
    log.info(f"Wav salvato: {percorso_wav}")

    # Pulizia esplicita a fine sezione: aiuta a tenere sotto controllo il
    # picco di VRAM quando si generano più sezioni una dopo l'altra.
    gc.collect()
    if _device_usato == "cuda":
        import torch
        torch.cuda.empty_cache()
        libera_gb = torch.cuda.mem_get_info()[0] / (1024 ** 3)
        log.info(f"VRAM libera dopo la sezione: {libera_gb:.1f}GB")

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
    import argparse
    import glob

    parser = argparse.ArgumentParser(
        description="Genera audio con XTTS-v2 da uno o più file di testo (per sezione)."
    )
    parser.add_argument(
        "-f", "--file",
        action="append",
        help="Percorso di un file di testo da sintetizzare (puoi ripetere -f più volte "
             "per più file). Utile per test rapidi su testi più brevi, non necessariamente "
             "nel formato output/testo_<Sezione>.txt. Se omesso, processa tutti i file "
             "output/testo_*.txt trovati (comportamento di default).",
    )
    parser.add_argument(
        "-s", "--speaker-wav",
        default=None,
        help="Percorso di un file audio di riferimento per il voice cloning, in "
             "alternativa a quello impostato in config.py (XTTS_SPEAKER_WAV). "
             "Utile per confrontare voci diverse senza modificare il file di configurazione.",
    )
    parser.add_argument(
        "-n", "--speaker-name",
        default=None,
        help="Nome di una delle 58 voci predefinite di XTTS-v2 (nessun voice cloning). "
             "Usa --list-speakers per vedere i nomi disponibili. Alternativo a --speaker-wav.",
    )
    parser.add_argument(
        "--list-speakers",
        action="store_true",
        help="Stampa la lista delle voci predefinite disponibili ed esce, senza sintetizzare nulla.",
    )
    args = parser.parse_args()

    if args.list_speakers:
        for nome in list_speakers():
            print(nome)
        raise SystemExit(0)

    if args.file:
        file_testo = args.file
    else:
        file_testo = sorted(glob.glob("output/testo_*.txt"))

    if not file_testo:
        print("Nessun file di testo trovato. Lancia prima synthesize.py, oppure "
              "passa un file con: python tts.py -f percorso/al/tuo_test.txt")
    else:
        print(f"File da sintetizzare: {', '.join(file_testo)}")

        for percorso_testo in file_testo:
            percorso_testo = Path(percorso_testo)
            if not percorso_testo.exists():
                print(f"ATTENZIONE: file non trovato, salto: {percorso_testo}")
                continue

            # Il nome sezione serve solo per dare un nome ai file di output:
            # se il file non segue la convenzione testo_<Sezione>.txt, uso
            # semplicemente il nome del file senza estensione.
            stem = percorso_testo.stem
            nome_sezione = stem.replace("testo_", "") if stem.startswith("testo_") else stem

            with open(percorso_testo, encoding="utf-8") as f:
                testo = f.read()

            log.info(f"=== File '{percorso_testo.name}' (sezione '{nome_sezione}') ===")
            percorso = genera_audio(
                testo,
                config.percorso_audio_wav_sezione(nome_sezione),
                config.percorso_audio_ogg_sezione(nome_sezione),
                speaker_wav=args.speaker_wav,
                speaker_name=args.speaker_name,
            )
            print(f"Audio generato: {percorso}")

        print("\nCompletato.")
