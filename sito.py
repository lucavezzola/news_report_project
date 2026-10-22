"""
sito.py — Fase 4: genera il sito statico (HTML, JSON, asset).

Struttura prodotta in config.DIR_SITO (contiene TUTTI i giorni; la retention
la applica deploy.py):

    robots.txt, _headers
    t/<token>/index.html              archivio dei giorni
    t/<token>/static/{style.css,app.js}
    t/<token>/AAAA-MM-GG/index.html   pagina episodio
    t/<token>/AAAA-MM-GG/episodio.mp3
    t/<token>/AAAA-MM-GG/manifest.json

Il testo e i metadati Open Graph sono scritti nell'HTML lato server (il
crawler di Telegram non esegue JavaScript); Jinja2 con autoescape.
"""

import json
import re
import shutil
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

import config
import synthesize
from logging_config import configura_logger

log = configura_logger("sito", "sito.log")

_RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _env():
    return Environment(loader=FileSystemLoader(config.DIR_SITO_TEMPLATE),
                       autoescape=select_autoescape(["html", "xml"]), trim_blocks=True, lstrip_blocks=True)


def _data_it(data_iso):
    return synthesize._data_italiana(date.fromisoformat(data_iso))


def dir_token():
    return Path(config.DIR_SITO) / "t" / config.sito_token()


def url_episodio(data):
    base = config.sito_base_url()
    return f"{base}/t/{config.sito_token()}/{data}/" if base else ""


def _descrizione(manifest, massimo=200):
    titoli = [n["titolo"] for s in manifest["sezioni"] for n in s["notizie"] if n["tipo"] == "notizia"]
    testo = "; ".join(titoli[:4])
    return (testo[:massimo - 1] + "…") if len(testo) > massimo else testo


def aggiorna_archivio():
    """Rigenera l'indice dei giorni presenti sul disco."""
    radice = dir_token()
    giorni = []
    for d in sorted((p for p in radice.iterdir() if p.is_dir() and _RE_DATA.match(p.name)), reverse=True) if radice.exists() else []:
        mf = d / "manifest.json"
        if not mf.exists():
            continue
        m = json.loads(mf.read_text(encoding="utf-8"))
        giorni.append({"data": d.name, "data_it": _data_it(d.name), "durata_min": round(m["durata"] / 60),
                       "n_notizie": sum(1 for s in m["sezioni"] for n in s["notizie"] if n["tipo"] == "notizia")})
    radice.mkdir(parents=True, exist_ok=True)
    html = _env().get_template("archivio.html").render(titolo_sito=config.TITOLO_SITO, giorni=giorni)
    (radice / "index.html").write_text(html, encoding="utf-8")
    return giorni


def costruisci_sito_giorno(data=None):
    """Genera la pagina del giorno e aggiorna archivio e asset. Ritorna la
    cartella del giorno nel sito."""
    data = data or config.data_corrente()
    manifest = json.loads(Path(config.percorso_manifest(data)).read_text(encoding="utf-8"))
    mp3 = Path(config.percorso_episodio_mp3(data))
    if not mp3.exists():
        raise RuntimeError(f"MP3 mancante: {mp3}")

    radice = dir_token()
    cartella = radice / data
    cartella.mkdir(parents=True, exist_ok=True)
    shutil.copy2(mp3, cartella / "episodio.mp3")
    (cartella / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    statici = radice / "static"
    statici.mkdir(parents=True, exist_ok=True)
    for nome in ("style.css", "app.js"):
        shutil.copy2(Path(config.DIR_SITO_TEMPLATE) / nome, statici / nome)

    titolo = f"Rassegna del {_data_it(data)}"
    url = url_episodio(data)
    og = cartella / "og.png"           # immagine OG per giorno: Fase 7 (opzionale)
    html = _env().get_template("episodio.html").render(
        manifest=manifest,
        titolo_pagina=titolo,
        titolo_sito=config.TITOLO_SITO,
        durata_min=round(manifest["durata"] / 60),
        descrizione=_descrizione(manifest),
        url_pagina=url,
        url_og_image=(url + "og.png") if (url and og.exists()) else "",
        meta_media={"titolo": titolo, "artista": config.TITOLO_SITO, "album": "Rassegna stampa"},
    )
    (cartella / "index.html").write_text(html, encoding="utf-8")

    # file a livello di sito
    sito = Path(config.DIR_SITO)
    (sito / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    (sito / "_headers").write_text("/*\n  X-Robots-Tag: noindex, nofollow\n  Referrer-Policy: no-referrer\n"
                                   "  X-Content-Type-Options: nosniff\n", encoding="utf-8")
    aggiorna_archivio()

    dim_html = (cartella / "index.html").stat().st_size + (statici / "app.js").stat().st_size + (statici / "style.css").stat().st_size
    log.info(f"Sito generato in {cartella} (pagina+asset: {dim_html / 1024:.0f} KB, audio escluso)")
    return cartella


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Genera il sito del giorno indicato.")
    ap.add_argument("--data")
    a = ap.parse_args()
    config.imposta_data(a.data)
    print(costruisci_sito_giorno())
