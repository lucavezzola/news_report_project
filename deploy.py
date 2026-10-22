"""
deploy.py — Fase 4: pubblica il sito su Cloudflare Pages e applica la retention.

Richiede Node/npx (wrangler) e in .env:
    CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, (opz.) CF_PAGES_PROJECT
Il progetto Pages va creato una volta: npx wrangler pages project create <nome>
Limiti da ricontrollare al momento dell'uso (piano gratuito): 25 MiB per file,
20.000 file per sito. Sconsigliato il push su git con l'audio nel repository.
"""

import os
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import config
import sito
from logging_config import configura_logger

log = configura_logger("deploy", "deploy.log")

LIMITE_FILE_MIB = 25


def applica_retention(giorni=None, oggi=None):
    """Elimina dalla cartella del sito i giorni più vecchi di 'giorni'
    (config.RETENTION_GIORNI) e rigenera l'archivio. Ritorna i giorni rimossi."""
    giorni = giorni if giorni is not None else config.RETENTION_GIORNI
    if giorni <= 0:
        return []
    limite = (oggi or date.today()) - timedelta(days=giorni)
    rimossi = []
    radice = sito.dir_token()
    if radice.exists():
        for d in radice.iterdir():
            if d.is_dir() and sito._RE_DATA.match(d.name) and date.fromisoformat(d.name) < limite:
                shutil.rmtree(d)
                rimossi.append(d.name)
    if rimossi:
        log.info(f"Retention ({giorni} giorni): rimossi {', '.join(sorted(rimossi))}")
        sito.aggiorna_archivio()
    return sorted(rimossi)


def _controlla_dimensioni():
    for p in Path(config.DIR_SITO).rglob("*"):
        if p.is_file() and p.stat().st_size > LIMITE_FILE_MIB * 1024 * 1024:
            log.warning(f"{p} supera {LIMITE_FILE_MIB} MiB: Cloudflare Pages lo rifiuterebbe.")


def pubblica(data=None):
    """Applica la retention e pubblica config.DIR_SITO con wrangler.
    Ritorna l'URL pubblico dell'episodio (se SITO_BASE_URL è impostato)."""
    data = data or config.data_corrente()
    applica_retention()
    _controlla_dimensioni()

    for var in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        if not os.environ.get(var):
            raise RuntimeError(f"Variabile d'ambiente {var} non impostata (vedi .env.example).")
    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError("npx non trovato nel PATH: installa Node.js per usare wrangler.")

    progetto = os.environ.get("CF_PAGES_PROJECT") or config.SITO_NOME_PROGETTO_CF
    cmd = [npx, "wrangler", "pages", "deploy", config.DIR_SITO, "--project-name", progetto,
           "--branch", "main", "--commit-dirty=true"]
    log.info(f"Deploy su Cloudflare Pages (progetto {progetto})...")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        log.error(f"wrangler ha fallito:\n{r.stdout[-1000:]}\n{r.stderr[-1000:]}")
        raise RuntimeError("Deploy fallito: vedi logs/deploy.log")
    log.info("Deploy completato.")
    url = sito.url_episodio(data)
    if not url:
        log.warning("SITO_BASE_URL non impostato: la notifica Telegram non avrà il link.")
    return url


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Pubblica il sito già generato.")
    ap.add_argument("--data")
    a = ap.parse_args()
    config.imposta_data(a.data)
    print(pubblica())
