"""
fetch.py — Fase 1: raccolta articoli dai feed RSS.

Scarica ogni fonte configurata in config.py, tiene solo gli articoli
nell'intervallo selezionato e salva tutto in un JSON intermedio.

Uso da terminale (per test manuale, indipendente dalla pipeline completa):
    python fetch.py

Uso da main.py:
    from fetch import raccogli_articoli
    articoli = raccogli_articoli()
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from calendar import timegm

import feedparser

import config
from logging_config import configura_logger

log = configura_logger("fetch", "fetch.log")


USER_AGENT = "Mozilla/5.0 (compatible; RassegnaAudio/1.0; lettore RSS personale)"


def _scarica_feed(url):
    """Scarica il feed con requests (User-Agent esplicito, timeout) e lo passa
    a feedparser. Molti siti rifiutano o ridirigono lo user agent predefinito di
    feedparser restituendo una pagina HTML: in quel caso l'errore riporta
    status, Content-Type e l'inizio della risposta, per capire al volo cosa è successo."""
    import requests
    r = requests.get(url, timeout=20, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
    })
    if r.status_code >= 400:
        raise ValueError(f"HTTP {r.status_code}")
    feed = feedparser.parse(r.content)
    if not feed.entries:
        inizio = r.text[:120].replace("\n", " ").strip()
        raise ValueError(
            f"nessun articolo nel feed (bozo_exception: {feed.bozo_exception if feed.bozo else 'nessuna'}; "
            f"Content-Type: {r.headers.get('Content-Type', '?')}; inizio risposta: {inizio!r})"
        )
    return feed


def _fonti_di_oggi(ora_fine=None, giorni=1, ora_inizio=None):
    """Restituisce le fonti attive nei giorni di calendario coperti."""
    ora_fine = ora_fine or datetime.now().astimezone()
    oggi = ora_fine.astimezone().date()
    if ora_inizio is not None:
        data = ora_inizio.astimezone().date()
        giorni_coperti = set()
        while data <= oggi:
            giorni_coperti.add(data.weekday())
            data += timedelta(days=1)
    elif giorni == 1:
        giorni_coperti = {oggi.weekday()}
    else:
        data = (ora_fine - timedelta(days=giorni)).astimezone().date()
        giorni_coperti = set()
        while data <= oggi:
            giorni_coperti.add(data.weekday())
            data += timedelta(days=1)
    quotidiani_di_turno = {
        config.ROTAZIONE_QUOTIDIANI[giorno]
        for giorno in giorni_coperti
        if giorno in config.ROTAZIONE_QUOTIDIANI
    }

    fonti_attive = []
    for fonte in config.FONTI:
        if fonte["nome"] in config.FONTI_SEMPRE_INCLUSE:
            fonti_attive.append(fonte)
        elif fonte["nome"] in quotidiani_di_turno:
            fonti_attive.append(fonte)
        # le altre fonti in rotazione ma non di turno oggi vengono saltate
    return fonti_attive


def id_articolo(link, fonte="", titolo=""):
    """ID stabile: primi 10 caratteri dello sha1 dell'URL (se manca l'URL,
    fonte+titolo). Claude cita le fonti solo con questi ID: non scrive mai URL."""
    base = (link or "").strip() or f"{fonte}|{titolo}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]


def _entry_e_recente(entry, ora_limite):
    """Ritorna True se l'entry RSS ha una data di pubblicazione dentro la
    finestra temporale. Se il feed non fornisce una data valida, l'entry
    viene comunque inclusa (meglio un falso positivo che perdere notizie)."""
    struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if not struct:
        return True
    dt = datetime.fromtimestamp(timegm(struct), tz=timezone.utc)
    return dt >= ora_limite


def raccogli_articoli(giorni=1, ora_fine=None, ora_inizio=None):
    """Interroga tutte le fonti attive di oggi e restituisce una lista di
    dizionari: {fonte, categoria, titolo, link, data, estratto} nel periodo
    delle ultime 24 * giorni ore oppure dall'ora_inizio indicata."""
    if giorni < 1:
        raise ValueError("Il numero di giorni deve essere almeno 1.")
    ora_fine = ora_fine or datetime.now(timezone.utc)
    ora_limite = (
        ora_inizio.astimezone(timezone.utc)
        if ora_inizio is not None
        else ora_fine.astimezone(timezone.utc) - config.FINESTRA_ARTICOLI * giorni
    )
    limite_articoli = config.MAX_ARTICOLI_PER_FONTE * giorni
    fonti_attive = _fonti_di_oggi(ora_fine, giorni, ora_inizio=ora_inizio)
    log.info(f"Fonti attive: {len(fonti_attive)}/{len(config.FONTI)}")
    log.info(
        f"Raccolta da {ora_limite.isoformat()}; massimo {limite_articoli} articoli per fonte"
    )

    tutti_articoli = []
    ids_visti = set()
    fonti_ok, fonti_ko = [], []

    for fonte in fonti_attive:
        nome, categoria, url = fonte["nome"], fonte["categoria"], fonte["url"]
        try:
            feed = _scarica_feed(url)

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
            recenti = recenti[:limite_articoli]

            for entry in recenti:
                titolo = entry.get("title", "").strip()
                link = entry.get("link", "")
                id_art = id_articolo(link, nome, titolo)
                if id_art in ids_visti:      # stesso URL da due feed: tienilo una volta
                    continue
                ids_visti.add(id_art)
                tutti_articoli.append({
                    "id": id_art,
                    "fonte": nome,
                    "categoria": categoria,
                    "titolo": titolo,
                    "link": link,
                    "data": entry.get("published", entry.get("updated", "")),
                    "estratto": entry.get("summary", "").strip(),
                })

            fonti_ok.append(f"{nome} ({len(recenti)} articoli)")
            log.info(f"OK  {nome}: {len(recenti)} articoli dal {ora_limite.isoformat()}")

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
    percorso = percorso or config.percorso_articoli_grezzi()
    with open(percorso, "w", encoding="utf-8") as f:
        json.dump(articoli, f, ensure_ascii=False, indent=2)
    log.info(f"Salvato JSON grezzo in {percorso}")


if __name__ == "__main__":
    articoli = raccogli_articoli()
    salva_json(articoli)

    print("\n--- Anteprima titoli raccolti ---")
    for a in articoli[:30]:
        print(f"[{a['categoria']:10}] {a['id']} {a['fonte']:25} — {a['titolo']}")
    if len(articoli) > 30:
        print(f"... e altri {len(articoli) - 30} articoli (vedi {config.percorso_articoli_grezzi()})")
