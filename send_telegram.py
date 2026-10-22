"""
send_telegram.py — Fase 4: notifica su Telegram (l'audio sta sul sito).

Variabili d'ambiente (vedi .env.example):
- TELEGRAM_BOT_TOKEN: token del bot creato con @BotFather
- TELEGRAM_CHAT_ID: canale/gruppo a cui mandare la notifica
- TELEGRAM_ADMIN_CHAT_ID: (opz.) chat per gli avvisi di errore; se manca, TELEGRAM_CHAT_ID
- TELEGRAM_INVIA_AUDIO: (opz., default spento) rimanda anche l'MP3 come file.
  Compromesso: nel browser interno di Telegram l'ascolto a schermo spento
  non è garantito, il file audio sì.

Uso da terminale (prova manuale):
    python send_telegram.py --test
"""

import os
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

import requests

import config
from logging_config import configura_logger

log = configura_logger("telegram", "telegram.log")


def _credenziali(admin=False):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = (os.environ.get("TELEGRAM_ADMIN_CHAT_ID") if admin else None) or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN e/o TELEGRAM_CHAT_ID non impostate. Vedi .env.example.")
    return token, chat_id


def _post(token, metodo, **kwargs):
    r = requests.post(f"https://api.telegram.org/bot{token}/{metodo}", timeout=60, **kwargs)
    if not r.ok:
        log.error(f"Errore Telegram {metodo}: {r.status_code} {r.text}")
        raise RuntimeError(f"Errore Telegram {metodo}: {r.text}")
    return r.json()


def notifica_episodio(data_it, durata_min, url):
    """'Rassegna del {data} pronta · {durata} min' + link, con anteprima
    attiva (grazie ai metadati Open Graph scritti dal sito)."""
    token, chat_id = _credenziali()
    testo = f"Rassegna del {data_it} pronta · {durata_min} min"
    if url:
        testo += f"\n{url}"
    risposta = _post(token, "sendMessage", data={"chat_id": chat_id, "text": testo})
    log.info("Notifica inviata.")
    return risposta


def invia_audio(percorso_audio, didascalia=None):
    """Rimanda l'MP3 come file (solo se TELEGRAM_INVIA_AUDIO è attivo)."""
    token, chat_id = _credenziali()
    didascalia = didascalia or f"Rassegna stampa audio — {datetime.now().strftime('%d/%m/%Y')}"
    with open(percorso_audio, "rb") as f:
        risposta = _post(token, "sendAudio", data={"chat_id": chat_id, "caption": didascalia}, files={"audio": f})
    log.info("Audio inviato come file.")
    return risposta


def notifica_errore(messaggio):
    """Avviso alla chat admin se la pipeline fallisce. Non solleva mai
    eccezioni: un errore di notifica non deve nascondere l'errore originale."""
    try:
        token, chat_id = _credenziali(admin=True)
        _post(token, "sendMessage", data={"chat_id": chat_id, "text": f"⚠️ Rassegna: {messaggio}"[:4000]})
    except Exception as e:
        log.error(f"Impossibile inviare la notifica di errore: {e}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Prove manuali delle notifiche Telegram.")
    ap.add_argument("--test", action="store_true", help="invia una notifica di prova con l'URL del giorno")
    a = ap.parse_args()
    if a.test:
        import sito
        notifica_episodio(sito._data_it(config.data_corrente()), 0, sito.url_episodio(config.data_corrente()))
