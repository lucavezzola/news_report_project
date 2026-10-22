"""
run_tts_e_invio.py — scorciatoia: rilancia dalla Fase 2 (fonetica) in poi sui
testi già generati oggi, senza rifare fetch e chiamate a Claude.

Equivale a:  python main.py --da-fase 2 [opzioni]
Le opzioni (--data, --solo-sezione, --no-deploy, --no-telegram, --audio-finto,
--rigenera) sono quelle di main.py. Usa direttamente main.py per le altre fasi.
"""

import sys

import main

if __name__ == "__main__":
    main.main(["--da-fase", "2"] + sys.argv[1:])
