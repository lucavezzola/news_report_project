"""
fetch.py — Fase 1: raccolta articoli dai feed RSS.

Scarica ogni fonte configurata in config.py, tiene solo gli articoli delle
ultime 24h (o FINESTRA_ARTICOLI), e salva tutto in un JSON intermedio.

Uso da terminale (per test manuale, indipendente dalla pipeline completa):
    python fetch.py

Uso da main.py:
    from fetch import raccogli_articoli
    articoli = raccogli_articoli()
"""

import json
import logging
from datetime import datetime, timezone
from time import mktime

import feedparser

import config
from logging_config import configura_logger

log = configura_logger("fetch", "fetch.log")


def _fonti_di_oggi():
    """Applica la rotazione settimanale dei quotidiani generalisti e
    restituisce l'elenco effettivo di fonti da interrogare oggi."""
    oggi = datetime.now().weekday()  # 0=lunedì
    quotidiano_di_turno = config.ROTAZIONE_QUOTIDIANI.get(oggi)

    fonti_attive = []
    for fonte in config.FONTI:
        if fonte["nome"] in config.FONTI_SEMPRE_INCLUSE:
            fonti_attive.append(fonte)
        elif fonte["nome"] == quotidiano_di_turno:
            fonti_attive.append(fonte)
        # le altre fonti in rotazione ma non di turno oggi vengono saltate
    return fonti_attive


def _entry_e_recente(entry, ora_limite):
    """Ritorna True se l'entry RSS ha una data di pubblicazione dentro la
    finestra temporale. Se il feed non fornisce una data valida, l'entry
    viene comunque inclusa (meglio un falso positivo che perdere notizie)."""
    struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if not struct:
        return True
    dt = datetime.fromtimestamp(mktime(struct), tz=timezone.utc)
    return dt >= ora_limite


def raccogli_articoli():
    """Interroga tutte le fonti attive di oggi e restituisce una lista di
    dizionari: {fonte, categoria, titolo, link, data, estratto}."""
    ora_limite = datetime.now(timezone.utc) - config.FINESTRA_ARTICOLI
    fonti_attive = _fonti_di_oggi()
    log.info(f"Fonti attive oggi: {len(fonti_attive)}/{len(config.FONTI)}")

    tutti_articoli = []
    fonti_ok, fonti_ko = [], []

    for fonte in fonti_attive:
        nome, categoria, url = fonte["nome"], fonte["categoria"], fonte["url"]
        try:
            feed = feedparser.parse(url)

            # feedparser non lancia eccezioni sugli errori HTTP: bisogna
            # controllare bozo/status esplicitamente.
            status = getattr(feed, "status", None)
            if feed.bozo and not feed.entries:
                raise ValueError(f"feed non valido (bozo_exception: {feed.bozo_exception})")
            if status and status >= 400:
                raise ValueError(f"HTTP {status}")
            if not feed.entries:
                raise ValueError("nessun articolo restituito dal feed")

            recenti = [e for e in feed.entries if _entry_e_recente(e, ora_limite)]
            recenti = recenti[: config.MAX_ARTICOLI_PER_FONTE]

            for entry in recenti:
                tutti_articoli.append({
                    "fonte": nome,
                    "categoria": categoria,
                    "titolo": entry.get("title", "").strip(),
                    "link": entry.get("link", ""),
                    "data": entry.get("published", entry.get("updated", "")),
                    "estratto": entry.get("summary", "").strip(),
                })

            fonti_ok.append(f"{nome} ({len(recenti)} articoli)")
            log.info(f"OK  {nome}: {len(recenti)} articoli nelle ultime 24h")

        except Exception as e:
            fonti_ko.append(f"{nome}: {e}")
            log.warning(f"KO  {nome}: {e}")

    # Riepilogo finale — utile per capire subito quali fonti vanno sistemate
    log.info("=" * 60)
    log.info(f"Riepilogo: {len(fonti_ok)} fonti OK, {len(fonti_ko)} fonti KO")
    if fonti_ko:
        log.info("Fonti da controllare/sostituire:")
        for f in fonti_ko:
            log.info(f"  - {f}")
    log.info(f"Totale articoli raccolti: {len(tutti_articoli)}")

    return tutti_articoli


def salva_json(articoli, percorso=None):
    percorso = percorso or config.FILE_JSON_GREZZO
    with open(percorso, "w", encoding="utf-8") as f:
        json.dump(articoli, f, ensure_ascii=False, indent=2)
    log.info(f"Salvato JSON grezzo in {percorso}")


if __name__ == "__main__":
    articoli = raccogli_articoli()
    salva_json(articoli)

    print("\n--- Anteprima titoli raccolti ---")
    for a in articoli[:30]:
        print(f"[{a['categoria']:10}] {a['fonte']:25} — {a['titolo']}")
    if len(articoli) > 30:
        print(f"... e altri {len(articoli) - 30} articoli (vedi {config.FILE_JSON_GREZZO})")
