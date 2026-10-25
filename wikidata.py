"""
wikidata.py — Fase 6: da entità nominata da Claude a scheda con immagine.

Principi (policy editoriale, vedi docs/policy_immagini.md):
- Claude fornisce nome, tipo e descrizione; il CODICE risolve su Wikidata.
  Mai fidarsi di ID Wikidata generati dal modello.
- Meglio nessuna immagine che quella sbagliata: il candidato deve superare
  soglie di punteggio, di notorietà (sitelinks) e di distacco dal secondo.
- Sempre l'immagine predefinita di Wikidata (P18/P154/P41/P94), nessuna scelta
  manuale; stesso trattamento per tutti.
- Solo licenze libere o pubblico dominio; crediti salvati e mostrati.
- Immagini scaricate e servite dal proprio sito (nessun hotlinking).
Non è consulenza legale: se il sito diventasse pubblico, rivalutare le licenze.
"""

import html
import json
import math
import re
import time
import unicodedata
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

import config
from logging_config import configura_logger

log = configura_logger("wikidata", "wikidata.log")

_STOP = {"della", "dello", "delle", "degli", "dell", "dei", "del", "che", "per", "con", "una", "uno", "nel", "nella",
         "the", "and", "for", "con", "ministro", "presidente"}  # parole troppo generiche per il confronto descrizioni


def norm(testo):
    t = unicodedata.normalize("NFKD", testo or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t.lower())).strip()


def _token(testo):
    return {w for w in norm(testo).split() if len(w) > 3 and w not in _STOP}


# ---------------------------------------------------------------------------
# Scelta del candidato (funzioni pure)
# ---------------------------------------------------------------------------
def bonus_notorieta(sitelinks, soglia=None):
    """0 sotto la soglia, poi +1 per ogni raddoppio (10→0, 20→1, 40→2, 80→3, 160 o più→4):
    fra due omonimi, quello molto più noto vince nettamente."""
    soglia = config.SOGLIA_NOTORIETA_SITELINKS if soglia is None else soglia
    if sitelinks < soglia or soglia <= 0:
        return 0
    return min(4, int(math.log2(sitelinks / soglia)))


def punteggio_candidato(cand, nome, tipo, descrizione, soglia_sitelinks=None):
    """Ritorna (punteggio, motivo_scarto). punteggio None = candidato scartato.
    cand: {"qid","etichette":[str],"descrizione":str,"p31":[qid],"sitelinks":int}"""
    soglia = config.SOGLIA_NOTORIETA_SITELINKS if soglia_sitelinks is None else soglia_sitelinks
    classi = config.WIKIDATA_CLASSI.get(tipo, set())

    if tipo == "persona" and "Q5" not in cand["p31"]:
        return None, "non è un essere umano (P31 senza Q5)"
    if cand["sitelinks"] < soglia:
        return None, f"notorietà insufficiente ({cand['sitelinks']} sitelinks < {soglia})"

    n = norm(nome)
    etichette = [norm(e) for e in cand["etichette"] if e]
    in_comune = len(_token(descrizione) & _token(cand["descrizione"]))
    if n in etichette:
        punti = 4
    elif n and any(set(n.split()) <= set(e.split()) for e in etichette):
        # nome parziale (es. solo il cognome): mai senza conferma dalla descrizione
        if in_comune == 0:
            return None, "nome parziale senza conferma dalla descrizione"
        punti = 2
    else:
        return None, "nessuna corrispondenza di nome/alias"

    if classi & set(cand["p31"]):
        punti += 2
    punti += min(4, 2 * in_comune)
    punti += bonus_notorieta(cand["sitelinks"], soglia)
    return punti, None


def scegli_candidato(candidati, nome, tipo, descrizione):
    """Il migliore, solo se supera la soglia e distacca nettamente il secondo.
    Ritorna (candidato | None, motivo)."""
    valutati, scarti = [], []
    for c in candidati:
        p, motivo = punteggio_candidato(c, nome, tipo, descrizione)
        (valutati if p is not None else scarti).append((p, c) if p is not None else (motivo, c))
    if not valutati:
        return None, scarti[0][0] if scarti else "nessun candidato"
    valutati.sort(key=lambda x: -x[0])
    migliore_p, migliore = valutati[0]
    if migliore_p < config.SOGLIA_PUNTEGGIO_ENTITA:
        return None, f"punteggio troppo basso ({migliore_p} < {config.SOGLIA_PUNTEGGIO_ENTITA})"
    if len(valutati) > 1 and migliore_p - valutati[1][0] < config.MARGINE_PUNTEGGIO_ENTITA:
        return None, f"ambiguo: {migliore['qid']} ({migliore_p}) contro {valutati[1][1]['qid']} ({valutati[1][0]})"
    return migliore, "ok"


def riassumi_candidati(candidati, nome, tipo, descrizione):
    """Una riga per candidato: QID, etichetta, sitelinks, punteggio o motivo dello scarto.
    Serve ai log e a diagnosi_entita.py per capire perché una entità non è stata risolta."""
    righe = []
    for c in candidati:
        p, motivo = punteggio_candidato(c, nome, tipo, descrizione)
        esito = f"punteggio {p}" if p is not None else f"scartato: {motivo}"
        righe.append(f"{c['qid']} {c.get('etichetta') or c['etichette'][:1]} ({c['sitelinks']} sitelinks) -> {esito}")
    return righe


def licenza_ammessa(licenza):
    """Solo CC BY / CC BY-SA, CC0, pubblico dominio. Niente NC (non commerciale),
    ND (nessuna derivazione: noi ridimensioniamo), fair use o licenze ignote."""
    l = (licenza or "").strip().lower()
    if not l:
        return False
    if re.search(r"\b(nc|nd)\b|non-?commercial|no-?deriv|fair use|copyrighted|all rights", l):
        return False
    if re.match(r"(cc[ -]?by|cc0|cc[ -]?zero|public domain|pd[ -]|pd$|no known copyright|attribution)", l):
        return True
    return any(re.search(extra, l) for extra in config.LICENZE_EXTRA_AMMESSE)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
def http_json(url, params=None, headers=None, timeout=20):
    import requests
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def http_bytes(url, headers=None, timeout=30):
    import requests
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.content


class Wikidata:
    def __init__(self, http_get=None, http_scarica=None, file_cache=None, file_override=None, dir_immagini=None,
                 online=None, pausa=None, sleep=time.sleep, oggi=None):
        self.http_get = http_get or http_json
        self.http_scarica = http_scarica or http_bytes
        self.file_cache = Path(file_cache or config.FILE_CACHE_ENTITA)
        self.dir_immagini = Path(dir_immagini or config.DIR_CACHE_IMMAGINI)
        self.online = bool(config.contatto_api()) if online is None else online
        self.pausa = config.PAUSA_API_S if pausa is None else pausa
        self.sleep = sleep
        self.oggi = oggi or date.today()
        self._ultima = 0.0
        self.stats = Counter()
        self.cache = self._leggi(self.file_cache)
        self.override = {norm(k): v for k, v in self._leggi(Path(file_override or config.FILE_OVERRIDE_ENTITA)).items()}
        self._modificata = False

    @staticmethod
    def _leggi(p):
        p = Path(p)
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log.warning(f"{p} illeggibile, lo ignoro: {e}")
            return {}

    def salva_cache(self):
        if self._modificata:
            self.file_cache.parent.mkdir(parents=True, exist_ok=True)
            self.file_cache.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), encoding="utf-8")
            self._modificata = False

    def pota_cache(self, giorni=None):
        limite = (self.oggi - timedelta(days=giorni or config.CACHE_MAX_INUTILIZZO_GIORNI)).isoformat()
        vecchie = {k: v for k, v in self.cache.items() if v.get("ultimo_uso", "9999") < limite}
        for k, v in vecchie.items():
            del self.cache[k]
            if v.get("immagine"):
                (self.dir_immagini / Path(v["immagine"]).name).unlink(missing_ok=True)
        if vecchie:
            self._modificata = True
            log.info(f"Cache entità: potate {len(vecchie)} voci inutilizzate.")
        return len(vecchie)

    # ------------------------------------------------------------------ rete
    def _api(self, url, params):
        da_attendere = self.pausa - (time.monotonic() - self._ultima)
        if da_attendere > 0:
            self.sleep(da_attendere)
        self._ultima = time.monotonic()
        return self.http_get(url, params, {"User-Agent": config.user_agent_api()})

    def _cerca_qid(self, nome):
        qids = []
        for lingua in ("it", "en"):
            r = self._api(config.WIKIDATA_API, {"action": "wbsearchentities", "search": nome, "language": lingua,
                                                "uselang": lingua, "type": "item", "limit": 5, "format": "json"})
            for x in r.get("search", []):
                if x["id"] not in qids:
                    qids.append(x["id"])
        return qids

    def _carica_entita(self, qids):
        if not qids:
            return []
        r = self._api(config.WIKIDATA_API, {"action": "wbgetentities", "ids": "|".join(qids[:50]), "format": "json",
                                            "props": "labels|aliases|descriptions|claims|sitelinks",
                                            "languages": "it|en"})
        return [self._interpreta(qid, e) for qid, e in r.get("entities", {}).items() if "missing" not in e]

    @staticmethod
    def _valore_claim(claims, prop):
        """Primo valore (preferito se c'è) della proprietà, o None."""
        voci = claims.get(prop, [])
        voci = sorted(voci, key=lambda v: 0 if v.get("rank") == "preferred" else 1)
        for v in voci:
            if v.get("rank") == "deprecated":
                continue
            dv = v.get("mainsnak", {}).get("datavalue")
            if dv:
                return dv["value"]
        return None

    def _interpreta(self, qid, e):
        etichette = [x["value"] for x in e.get("labels", {}).values()]
        for lista in e.get("aliases", {}).values():
            etichette += [a["value"] for a in lista]
        desc = e.get("descriptions", {})
        claims = e.get("claims", {})
        p31 = [v.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
               for v in claims.get("P31", [])]
        colore = self._valore_claim(claims, "P465")
        return {"qid": qid, "etichette": etichette,
                "etichetta": (e.get("labels", {}).get("it") or e.get("labels", {}).get("en") or {}).get("value", ""),
                "descrizione": (desc.get("it") or desc.get("en") or {}).get("value", ""),
                "p31": [x for x in p31 if x], "sitelinks": len(e.get("sitelinks", {})),
                "claims": claims,
                "colore": colore if isinstance(colore, str) and re.fullmatch(r"[0-9A-Fa-f]{6}", colore) else None}

    # --------------------------------------------------------------- immagini
    def _immagini_da_claims(self, claims, tipo, massimo=3):
        """Nomi file candidati, nell'ordine: per proprietà (come da config) e, dentro
        ciascuna, prima il valore 'preferito'. Se la prima ha una licenza non ammessa si prova la successiva."""
        trovati = []
        for prop in config.WIKIDATA_PROPRIETA_IMMAGINE.get(tipo, ["P18"]):
            voci = sorted(claims.get(prop, []), key=lambda v: 0 if v.get("rank") == "preferred" else 1)
            for v in voci:
                valore = (v.get("mainsnak", {}).get("datavalue") or {}).get("value")
                if v.get("rank") != "deprecated" and isinstance(valore, str) and valore not in trovati:
                    trovati.append(valore)
        return trovati[:massimo]

    def _info_commons(self, nome_file):
        r = self._api(config.COMMONS_API, {
            "action": "query", "titles": "File:" + nome_file, "prop": "imageinfo", "format": "json",
            "iiprop": "url|mime|extmetadata", "iiurlwidth": config.IMMAGINE_LARGHEZZA_PX})
        for pagina in r.get("query", {}).get("pages", {}).values():
            info = (pagina.get("imageinfo") or [None])[0]
            if info:
                return info
        return None

    @staticmethod
    def _crediti(nome_file, info):
        m = info.get("extmetadata", {})
        val = lambda k: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.get(k, {}).get("value", "")))).strip()
        pagina = info.get("descriptionurl") or ("https://commons.wikimedia.org/wiki/File:" + nome_file.replace(" ", "_"))
        return {"autore": val("Artist")[:120], "licenza": val("LicenseShortName")[:60] or val("UsageTerms")[:60],
                "licenza_url": val("LicenseUrl"), "pagina": pagina, "file": nome_file}

    def scarica_immagine(self, qid, nome_file):
        """Scarica la miniatura in data/cache/img/<QID>.<ext>. Ritorna (nome_file_locale, crediti)
        oppure (None, motivo) se la licenza non è ammessa o il download fallisce."""
        info = self._info_commons(nome_file)
        if not info:
            return None, "file non trovato su Commons"
        crediti = self._crediti(nome_file, info)
        if not licenza_ammessa(crediti["licenza"]):
            self.stats["immagini_licenza_rifiutata"] += 1
            return None, f"licenza non ammessa: {crediti['licenza']!r}"
        url = info.get("thumburl") or info.get("url")
        if not url or urlparse(url).scheme != "https":
            return None, "URL immagine non valido"
        ext = Path(urlparse(url).path).suffix.lower().lstrip(".")
        ext = "jpg" if ext == "jpeg" else ext
        if ext not in ("jpg", "png", "gif", "webp"):
            ext = "png"
        self.dir_immagini.mkdir(parents=True, exist_ok=True)
        locale = f"{qid}.{ext}"
        self.sleep(self.pausa)
        dati = self.http_scarica(url, {"User-Agent": config.user_agent_api()})
        (self.dir_immagini / locale).write_bytes(dati)
        self.stats["immagini_scaricate"] += 1
        return locale, crediti

    # ------------------------------------------------------------- interfaccia
    def risolvi(self, entita):
        """entita: {"nome","tipo","descrizione"}. Ritorna una scheda
        {"qid","etichetta","descrizione_wd","immagine","crediti","colore"} oppure None
        (entità bloccata, non risolta, non notabile o ambigua).
        'immagine' è il nome file in cache (None se manca o la licenza non va)."""
        nome, tipo, desc = entita["nome"], entita.get("tipo", "altro"), entita.get("descrizione", "")
        chiave = f"{norm(nome)}|{tipo}"

        ov = self.override.get(norm(nome), {})
        if ov.get("azione") == "blocca":
            self.stats["bloccate"] += 1
            return None

        voce = self.cache.get(chiave)
        if voce and not ov.get("qid"):
            voce["ultimo_uso"] = self.oggi.isoformat()
            self._modificata = True
            if not voce.get("nonrisolto"):
                self.stats["da_cache"] += 1
                return self._senza_immagine(voce) if ov.get("azione") == "senza_immagine" else voce["scheda"]
            if date.fromisoformat(voce["data"]) + timedelta(days=config.CACHE_NEGATIVA_GIORNI) > self.oggi:
                return None
        if not self.online:
            self.stats["offline"] += 1
            return None

        try:
            if ov.get("qid"):
                cands = self._carica_entita([ov["qid"]])
                scelto, motivo = (cands[0], "override") if cands else (None, "QID da override inesistente")
            else:
                cands = self._carica_entita(self._cerca_qid(nome))
                scelto, motivo = scegli_candidato(cands, nome, tipo, desc)
                if scelto is None:
                    for riga in riassumi_candidati(cands, nome, tipo, desc)[:5]:
                        log.info(f"   candidato per {nome!r}: {riga}")
        except Exception as e:
            log.warning(f"Wikidata ha fallito per {nome!r}: {e}")
            self.stats["errori_rete"] += 1
            return None            # errore di rete: non memorizzo nulla, si riprova al prossimo run

        if scelto is None:
            log.info(f"Entità non risolta: {nome!r} ({tipo}): {motivo}")
            self.cache[chiave] = {"nonrisolto": True, "data": self.oggi.isoformat(), "ultimo_uso": self.oggi.isoformat(),
                                  "motivo": motivo}
            self._modificata = True
            self.stats["non_risolte"] += 1
            return None

        immagine, crediti = None, None
        nomi_file = [] if ov.get("azione") == "senza_immagine" else self._immagini_da_claims(scelto["claims"], tipo)
        for nome_file in nomi_file:                  # la prima con licenza ammessa vince
            try:
                immagine, esito = self.scarica_immagine(scelto["qid"], nome_file)
            except Exception as e:
                log.warning(f"Immagine {nome_file!r} di {nome!r} non scaricata: {e}")
                self.stats["errori_rete"] += 1
                continue
            if immagine:
                crediti = esito
                break
            log.info(f"Immagine {nome_file!r} di {nome!r} scartata: {esito}")
        if not immagine and nomi_file:
            log.info(f"Nessuna immagine utilizzabile per {nome!r} ({len(nomi_file)} candidate): scheda senza immagine")
        elif not nomi_file and ov.get("azione") != "senza_immagine":
            log.info(f"{nome!r} ({scelto['qid']}) non ha un'immagine su Wikidata per il tipo {tipo!r}")
        scheda = {"qid": scelto["qid"], "etichetta": scelto["etichetta"] or nome, "descrizione_wd": scelto["descrizione"],
                  "immagine": immagine, "crediti": crediti, "colore": scelto["colore"]}
        self.cache[chiave] = {"scheda": scheda, "data": self.oggi.isoformat(), "ultimo_uso": self.oggi.isoformat(),
                              "immagine": immagine}
        self._modificata = True
        self.stats["risolte"] += 1
        return scheda

    @staticmethod
    def _senza_immagine(voce):
        return dict(voce["scheda"], immagine=None, crediti=None)
