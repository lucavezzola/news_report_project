"""
sito.py — Fase 4 + 7: genera il sito statico (HTML, JSON, asset, PWA).

Struttura prodotta in config.DIR_SITO (contiene TUTTI i giorni; la retention
la applica deploy.py):

    robots.txt, _headers
    t/<token>/index.html                 archivio dei giorni
    t/<token>/manifest.webmanifest, sw.js   PWA (il service worker non tocca l'audio)
    t/<token>/static/                    css, js, leaflet/, geo/, icone
    t/<token>/img/                       immagini delle entità (da data/cache/img)
    t/<token>/AAAA-MM-GG/index.html      pagina episodio
    t/<token>/AAAA-MM-GG/episodio.mp3, manifest.json, og.png

Il testo e i metadati Open Graph sono scritti nell'HTML lato server (il
crawler di Telegram non esegue JavaScript); Jinja2 con autoescape. I dati che
passano al JavaScript (luoghi, entità) vengono sanificati qui: percorsi
immagine in una whitelist, URL solo http(s), coordinate solo numeri.
"""

import json
import re
import shutil
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

import config
import immagine_og
import synthesize
from logging_config import configura_logger

log = configura_logger("sito", "sito.log")

_RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RE_IMG = re.compile(r"^img/[A-Za-z0-9_.-]+$")
FILE_STATICI = ("style.css", "app.js", "mappa_logica.js", "mappa.js", "citati.js")


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


def _http(url):
    try:
        p = urlparse((url or "").strip())
    except ValueError:
        return ""
    return url.strip() if p.scheme in ("http", "https") and p.netloc else ""


def _descrizione(manifest, massimo=200):
    titoli = [n["titolo"] for s in manifest["sezioni"] for n in s["notizie"] if n["tipo"] == "notizia"]
    testo = "; ".join(titoli[:4])
    return (testo[:massimo - 1] + "…") if len(testo) > massimo else testo


# ---------------------------------------------------------------------------
# Dati per i moduli JavaScript (sanificati)
# ---------------------------------------------------------------------------
def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def prepara_dati_visivi(manifest, immagini_presenti):
    """Ritorna (dati_visivi | None, crediti). 'immagini_presenti': set di percorsi
    'img/...' realmente disponibili nel sito (le altre vengono tolte)."""
    entita, crediti = {}, []
    for eid, e in manifest.get("entita", {}).items():
        img = e.get("immagine") if e.get("immagine") in immagini_presenti and _RE_IMG.match(e.get("immagine") or "") else None
        col = e.get("colore") if re.fullmatch(r"[0-9A-Fa-f]{6}", e.get("colore") or "") else None
        entita[eid] = {"nome": str(e["nome"])[:80], "descrizione": str(e.get("descrizione") or "")[:80],
                       "immagine": img, "colore": col}
        c = e.get("crediti")
        if img and c:
            crediti.append({"nome": entita[eid]["nome"], "autore": str(c.get("autore") or "")[:120],
                            "licenza": str(c.get("licenza") or "")[:60], "licenza_url": _http(c.get("licenza_url")),
                            "pagina": _http(c.get("pagina")) or "https://commons.wikimedia.org/"})
    luoghi = {}
    for lid, l in manifest.get("luoghi", {}).items():
        lat, lon = _num(l.get("lat")), _num(l.get("lon"))
        if lat is None or lon is None:
            continue
        p = l.get("poligono")
        poligono = {"livello": p["livello"], "id": str(p["id"])} if (
            isinstance(p, dict) and p.get("livello") in ("paesi", "regioni", "province") and re.fullmatch(r"[A-Za-z0-9_-]+", str(p.get("id", "")))) else None
        luoghi[lid] = {"nome": str(l.get("nome", ""))[:80], "tipo": l.get("tipo"), "paese": str(l.get("paese") or "")[:2],
                       "lat": lat, "lon": lon, "poligono": poligono}
    if not entita and not manifest.get("mappa"):
        return None, []
    dati = {"base": "../", "entita": entita, "max_carte": config.ENTITA_MAX_CONTEMPORANEE,
            "durata_carte": config.ENTITA_DURATA_DOPO_S}
    if manifest.get("mappa") and luoghi:
        dati["mappa"] = manifest["mappa"]
        dati["luoghi"] = luoghi
    return dati, crediti


# ---------------------------------------------------------------------------
# Archivio
# ---------------------------------------------------------------------------
def aggiorna_archivio():
    """Rigenera l'indice dei giorni presenti sul disco."""
    radice = dir_token()
    giorni = []
    cartelle = sorted((p for p in radice.iterdir() if p.is_dir() and _RE_DATA.match(p.name)), reverse=True) if radice.exists() else []
    for d in cartelle:
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


def pulisci_immagini_orfane():
    """Toglie da t/<token>/img/ le immagini non più referenziate da nessun giorno rimasto."""
    radice = dir_token()
    cartella = radice / "img"
    if not cartella.exists():
        return []
    usate = set()
    for mf in radice.glob("????-??-??/manifest.json"):
        for e in json.loads(mf.read_text(encoding="utf-8")).get("entita", {}).values():
            if e.get("immagine"):
                usate.add(Path(e["immagine"]).name)
    rimosse = []
    for f in cartella.iterdir():
        if f.is_file() and f.name not in usate:
            f.unlink()
            rimosse.append(f.name)
    if rimosse:
        log.info(f"Rimosse {len(rimosse)} immagini orfane dal sito.")
    return rimosse


# ---------------------------------------------------------------------------
# Generazione
# ---------------------------------------------------------------------------
def _copia_asset(radice, ha_mappa):
    statici = radice / "static"
    statici.mkdir(parents=True, exist_ok=True)
    for nome in FILE_STATICI:
        shutil.copy2(Path(config.DIR_SITO_TEMPLATE) / nome, statici / nome)
    vendor = Path(config.DIR_SITO_TEMPLATE) / "vendor" / "leaflet"
    if vendor.exists():
        shutil.copytree(vendor, statici / "leaflet", dirs_exist_ok=True)
    if ha_mappa:
        dest = statici / "geo"
        dest.mkdir(exist_ok=True)
        for nome in ("paesi", "regioni", "province"):
            sorgente = Path(config.DIR_GEO) / f"{nome}.json"
            if sorgente.exists():
                shutil.copy2(sorgente, dest / f"{nome}.json")
            else:
                log.warning(f"{sorgente} mancante: la mappa non avrà quei confini (python scarica_geo.py).")
    for lato, nome, maskable in ((192, "icon-192.png", False), (512, "icon-512.png", False), (512, "icon-512-maskable.png", True)):
        if not (statici / nome).exists():
            immagine_og.genera_icona(lato, statici / nome, maskable=maskable)


def _pwa(radice):
    manifest = {"name": config.TITOLO_SITO, "short_name": "Rassegna", "lang": "it", "start_url": "./", "scope": "./",
                "display": "standalone", "background_color": "#fbfbf9", "theme_color": "#0b5cad",
                "icons": [{"src": "static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                          {"src": "static/icon-512.png", "sizes": "512x512", "type": "image/png"},
                          {"src": "static/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}]}
    (radice / "manifest.webmanifest").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    sw = (Path(config.DIR_SITO_TEMPLATE) / "sw.js").read_text(encoding="utf-8")
    sw = sw.replace("__VERSIONE__", time.strftime("%Y%m%d%H%M%S")).replace("__MAX_PAGINE__", str(config.PWA_PAGINE_IN_CACHE))
    (radice / "sw.js").write_text(sw, encoding="utf-8")


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

    # immagini delle entità: copiate dalla cache; se il file manca l'entità resta senza immagine
    presenti = set()
    cartella_img = radice / "img"
    for e in manifest.get("entita", {}).values():
        img = e.get("immagine")
        if not img or not _RE_IMG.match(img):
            e["immagine"] = None
            continue
        sorgente = Path(config.DIR_CACHE_IMMAGINI) / Path(img).name
        if sorgente.exists():
            cartella_img.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sorgente, cartella_img / sorgente.name)
            presenti.add(img)
        else:
            log.warning(f"Immagine {sorgente} non trovata: la scheda resterà senza immagine.")
            e["immagine"] = None
    (cartella / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    dati_visivi, crediti = prepara_dati_visivi(manifest, presenti)
    ha_mappa = bool(dati_visivi and dati_visivi.get("mappa"))
    _copia_asset(radice, ha_mappa)
    _pwa(radice)

    titolo = f"Rassegna del {_data_it(data)}"
    titoli = [n["titolo"] for s in manifest["sezioni"] for n in s["notizie"] if n["tipo"] == "notizia"]
    try:
        immagine_og.genera_og(titolo, round(manifest["durata"] / 60), titoli, cartella / "og.png", config.TITOLO_SITO)
    except Exception as e:                       # l'anteprima è un di più: mai bloccare il sito
        log.warning(f"Immagine OG non generata: {e}")
    url = url_episodio(data)
    html = _env().get_template("episodio.html").render(
        manifest=manifest,
        titolo_pagina=titolo,
        titolo_sito=config.TITOLO_SITO,
        durata_min=round(manifest["durata"] / 60),
        descrizione=_descrizione(manifest),
        url_pagina=url,
        url_og_image=(url + "og.png") if (url and (cartella / "og.png").exists()) else "",
        meta_media={"titolo": titolo, "artista": config.TITOLO_SITO, "album": "Rassegna stampa"},
        dati_visivi=dati_visivi, ha_visivo=bool(dati_visivi), ha_mappa=ha_mappa, crediti=crediti,
    )
    (cartella / "index.html").write_text(html, encoding="utf-8")

    sito = Path(config.DIR_SITO)
    (sito / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    (sito / "_headers").write_text(
        "/*\n  X-Robots-Tag: noindex, nofollow\n  Referrer-Policy: no-referrer\n  X-Content-Type-Options: nosniff\n"
        "/t/:token/sw.js\n  Cache-Control: no-cache\n", encoding="utf-8")
    aggiorna_archivio()
    pulisci_immagini_orfane()

    dim = sum(f.stat().st_size for f in (cartella / "index.html", radice / "static" / "app.js", radice / "static" / "style.css"))
    log.info(f"Sito generato in {cartella} (HTML+css+js base: {dim / 1024:.0f} KB; mappa={'sì' if ha_mappa else 'no'}, "
             f"schede={len(manifest.get('entita', {}))}, audio escluso)")
    return cartella


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Genera il sito del giorno indicato.")
    ap.add_argument("--data")
    a = ap.parse_args()
    config.imposta_data(a.data)
    print(costruisci_sito_giorno())
