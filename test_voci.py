"""
test_voci.py — Genera un audio di prova per OGNI voce disponibile, così puoi
ascoltarle e confrontarle in un colpo solo, senza lanciare tts.py a mano una
voce alla volta.

Copre due categorie:
- Le 58 voci predefinite di XTTS-v2 (nessun voice cloning)
- Voice cloning su ogni file .wav trovato nella cartella di riferimento
  (di default xtts_reference/, o quella che passi con --cartella-clone)

Ogni audio finisce in output/test_voci/, con un nome che identifica la voce
usata, così puoi ascoltarli tutti e confrontare.

ATTENZIONE AI TEMPI: con 58 voci predefinite + N campioni di cloning, il test
completo può richiedere diversi minuti (circa 3-8 secondi per voce sulla tua
GPU, in base alla lunghezza del testo di prova). Usa --limite o
--solo-predefinite / --solo-clone per test più rapidi e mirati.

Uso:
    python test_voci.py                          # tutto: predefinite + clone
    python test_voci.py --solo-predefinite        # solo le 58 voci native
    python test_voci.py --solo-clone              # solo i tuoi campioni wav
    python test_voci.py --limite 10               # solo le prime 10 voci predefinite
    python test_voci.py -t "Testo di prova mio"   # testo personalizzato
"""

import argparse
import glob
import logging
import re
from pathlib import Path
import config

import tts  # riusa modello, funzioni e logging già configurati in tts.py

log = logging.getLogger("test_voci")

TESTO_DI_PROVA_DEFAULT = (
    "Buongiorno, questo è un test per confrontare voci diverse nella rassegna "
    "stampa. Oggi parliamo di politica, esteri e tecnologia, con qualche "
    "nome straniero come Uascington e Uiciat per verificare la pronuncia."
)

CARTELLA_OUTPUT = Path("output/test_voci")


def _nome_file_sicuro(testo):
    """Trasforma un nome voce/file in un nome file sicuro per il filesystem
    (via underscore, senza accenti/spazi problematici)."""
    t = testo.strip().replace(" ", "_")
    t = re.sub(r'[^\w\-.]', '', t)
    return t


def prova_voci_predefinite(testo, limite=None):
    nomi = tts.list_speakers()
    if limite:
        nomi = nomi[:limite]

    log.info(f"Provo {len(nomi)} voci predefinite...")
    for i, nome in enumerate(nomi, 1):
        nome_file = _nome_file_sicuro(nome)
        percorso_wav = CARTELLA_OUTPUT / f"predefinita_{nome_file}.wav"
        percorso_ogg = CARTELLA_OUTPUT / f"predefinita_{nome_file}.ogg"
        print(f"[{i}/{len(nomi)}] Voce predefinita: {nome}")
        try:
            tts.genera_audio(testo, str(percorso_wav), str(percorso_ogg), speaker_name=nome)
        except Exception as e:
            print(f"  ERRORE su '{nome}', salto: {e}")
            log.error(f"Errore su voce predefinita '{nome}': {e}")

def prova_voci_preferite(testo, limite=None):
    nomi = config.XTTS_VOCI_PREFERITE
    if limite:
        nomi = nomi[:limite]

    log.info(f"Provo {len(nomi)} voci preferite...")
    for i, nome in enumerate(nomi, 1):
        nome_file = _nome_file_sicuro(nome)
        percorso_wav = CARTELLA_OUTPUT / f"preferita_{nome_file}.wav"
        percorso_ogg = CARTELLA_OUTPUT / f"preferita_{nome_file}.ogg"
        print(f"[{i}/{len(nomi)}] Voce preferita: {nome}")
        try:
            tts.genera_audio(testo, str(percorso_wav), str(percorso_ogg), speaker_name=nome)
        except Exception as e:
            print(f"  ERRORE su '{nome}', salto: {e}")
            log.error(f"Errore su voce preferita '{nome}': {e}")


def prova_voice_cloning(testo, cartella_clone):
    campioni = sorted(glob.glob(str(Path(cartella_clone) / "*.wav")))
    if not campioni:
        print(f"Nessun file .wav trovato in {cartella_clone}, salto i test di voice cloning.")
        return

    log.info(f"Provo {len(campioni)} campioni di voice cloning da {cartella_clone}...")
    for i, campione in enumerate(campioni, 1):
        nome_file = _nome_file_sicuro(Path(campione).stem)
        percorso_wav = CARTELLA_OUTPUT / f"clone_{nome_file}.wav"
        percorso_ogg = CARTELLA_OUTPUT / f"clone_{nome_file}.ogg"
        print(f"[{i}/{len(campioni)}] Voice cloning da: {campione}")
        try:
            tts.genera_audio(testo, str(percorso_wav), str(percorso_ogg), speaker_wav=campione)
        except Exception as e:
            print(f"  ERRORE su '{campione}', salto: {e}")
            log.error(f"Errore su campione '{campione}': {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Genera un audio di prova per ogni voce disponibile (predefinite + cloning)."
    )
    parser.add_argument(
        "-t", "--testo",
        default=TESTO_DI_PROVA_DEFAULT,
        help="Testo di prova da usare per tutte le voci (di default una frase breve fissa).",
    )
    parser.add_argument(
        "--solo-predefinite", action="store_true",
        help="Testa solo le 58 voci predefinite, salta il voice cloning.",
    )
    parser.add_argument(
        "--solo-clone", action="store_true",
        help="Testa solo i campioni di voice cloning, salta le voci predefinite.",
    )
    parser.add_argument(
        "--solo-preferite", action="store_true",
        help="Testa solo le voci preferite nel file letto da config.py.",
    )
    parser.add_argument(
        "--limite", type=int, default=None,
        help="Testa solo le prime N voci (utile per un giro rapido).",
    )
    parser.add_argument(
        "--cartella-clone", default="xtts_reference",
        help="Cartella con i file .wav da usare per il voice cloning (default: xtts_reference/).",
    )

    args = parser.parse_args()

    CARTELLA_OUTPUT.mkdir(parents=True, exist_ok=True)

    print(f"Testo di prova: {args.testo}\n")

    if args.solo_preferite:
        prova_voci_preferite(args.testo, limite=args.limite)
    else:
        if not args.solo_clone:
            prova_voci_predefinite(args.testo, limite=args.limite)

        if not args.solo_predefinite:
            prova_voice_cloning(args.testo, args.cartella_clone)

    print(f"\nCompletato. File generati in: {CARTELLA_OUTPUT}/")
