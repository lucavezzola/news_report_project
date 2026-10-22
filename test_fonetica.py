"""
test_fonetica.py — Sintetizza una parola o frase con PIÙ GRAFIE ALTERNATIVE
(come test_voci.py fa con le voci), per scegliere quella che suona meglio e
poi metterla in fonetica.txt.

Uso:
    python test_fonetica.py Washington -a Uascington Uoscinton Washinton
    python test_fonetica.py WeChat -a Uiciat "Ui ciat" -c "Ho scaricato {} ieri."
    python test_fonetica.py ChatGPT -a "Ciat gi pi ti" --voce Claribel

Ogni grafia (compresa la parola originale, per confronto) finisce in
output/test_fonetica/ come <n>_<grafia>.wav. {} nel testo di contorno (-c) è
il segnaposto della parola; il default è una frase neutra.
"""

import argparse
import re
from pathlib import Path

import numpy as np
import soundfile as sf

import config
import fonetica
import tts

CARTELLA = Path("output/test_fonetica")
CONTORNO_DEFAULT = "Oggi parliamo di {}, come riportano le agenzie."


def _nome_file(testo):
    return re.sub(r"[^\w\-]", "", testo.strip().replace(" ", "_"))[:40] or "x"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("parola", help="parola/sigla/nome come si scrive")
    ap.add_argument("-a", "--alternative", nargs="+", default=[], help="grafie alternative da provare")
    ap.add_argument("-c", "--contorno", default=CONTORNO_DEFAULT, help="frase con {} al posto della parola")
    ap.add_argument("--voce", default=None, help="voce predefinita XTTS (default: prima di config.XTTS_VOCI_PREFERITE o cloning)")
    a = ap.parse_args()

    if "{}" not in a.contorno:
        ap.error("il testo di contorno deve contenere {}")
    CARTELLA.mkdir(parents=True, exist_ok=True)
    voce = a.voce or (config.XTTS_VOCI_PREFERITE[0] if config.XTTS_VOCI_PREFERITE else None)

    print(f"Voce: {voce or 'voice cloning (config.XTTS_SPEAKER_WAV)'}")
    for i, grafia in enumerate([a.parola] + a.alternative):
        frase = a.contorno.format(grafia)
        parlato = fonetica.normalizza_per_tts(frase, dizionario=[])   # solo regole, niente dizionario
        onda = tts.sintetizza_testo(parlato, speaker_name=voce)
        percorso = CARTELLA / f"{i}_{_nome_file(grafia)}.wav"
        sf.write(str(percorso), np.asarray(onda, dtype=np.float32), tts.SAMPLE_RATE)
        print(f"[{i}] {grafia!r:25} -> {percorso}")
    print("\nAscoltale e aggiungi la migliore a fonetica.txt come:  parola = grafia")
