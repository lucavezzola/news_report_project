"""
geo.py — Fase 5: da luogo nominato da Claude a coordinate e poligono.

Ordine di risoluzione (il più affidabile per primo):
  1. override manuale        data/luoghi_override.json
  2. cache                   data/cache/luoghi.json
  3. paese                   Natural Earth (data/geo/paesi.json), per codice ISO
  4. regione/provincia IT    ISTAT (data/geo/regioni.json, province.json)
  5. città e altri luoghi    Nominatim (1 richiesta/s, user agent identificabile)

Validazione: il risultato deve essere coerente col `paese` indicato da Claude;
nella sezione Italia il punto deve cadere in Italia. Se è ambiguo o incoerente
si ritorna None: la mappa non si muove (resta sulla vista precedente).

Scelta editoriale: i territori contestati NON diventano mai il poligono di un
paese. Un "luogo" non italiano di tipo regione/città è sempre solo un punto
(marker); solo il tipo "paese" evidenzia un poligono. Vedi docs/confini_contesi.md.
"""

import json
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import config
from logging_config import configura_logger
from scarica_geo import normalizza

log = configura_logger("geo", "geo.log")

# alias comuni (chiavi già normalizzate) -> ISO alpha-2
ALIAS_PAESI = {"usa": "US", "statiuniti": "US", "uk": "GB", "granbretagna": "GB", "regnounito": "GB"}
PREFISSI_PROVINCIA = ("cittametropolitanadi", "provinciaautonomadi", "provinciadi", "provdi")


def http_json(url, params=None, headers=None, timeout=15):
    import requests
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _nome_provincia(chiave):
    for p in PREFISSI_PROVINCIA:
        if chiave.startswith(p):
            chiave = chiave[len(p):]
    return chiave[:-len("capitale")] if chiave.endswith("capitale") else chiave


class Geo:
    def __init__(self, http_get=None, dir_geo=None, file_cache=None, file_override=None,
                 online=None, pausa=None, sleep=time.sleep, oggi=None):
        self.http_get = http_get or http_json
        self.dir_geo = Path(dir_geo or config.DIR_GEO)
        self.file_cache = Path(file_cache or config.FILE_CACHE_LUOGHI)
        self.pausa = config.PAUSA_API_S if pausa is None else pausa
        self.sleep = sleep
        self.oggi = oggi or date.today()
        self.online = bool(config.contatto_api()) if online is None else online
        self._ultima_richiesta = 0.0
        self.stats = Counter()

        self.paesi, self.nomi_paesi = {}, dict(ALIAS_PAESI)
        self.regioni, self.province = {}, {}
        self._carica_poligoni()
        self.cache = self._leggi_json(self.file_cache)
        self.override = {normalizza(k): v for k, v in self._leggi_json(Path(file_override or config.FILE_OVERRIDE_LUOGHI)).items()}
        self._cache_modificata = False

    # ------------------------------------------------------------------ dati
    @staticmethod
    def _leggi_json(percorso):
        p = Path(percorso)
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log.warning(f"{p} illeggibile, lo ignoro: {e}")
            return {}

    def _carica_poligoni(self):
        for nome, dest in (("paesi", self.paesi), ("regioni", self.regioni), ("province", self.province)):
            p = self.dir_geo / f"{nome}.json"
            if not p.exists():
                log.warning(f"{p} mancante: esegui 'python scarica_geo.py'. Quella parte della mappa sarà disattivata.")
                continue
            for f in json.loads(p.read_text(encoding="utf-8"))["features"]:
                pr = f["properties"]
                chiave = pr["iso"] if nome == "paesi" else pr["id"]
                if chiave:
                    dest[chiave] = pr
                if nome == "paesi" and pr["iso"]:
                    for n in (pr.get("nome"), pr.get("nome_en")):
                        if n:
                            self.nomi_paesi.setdefault(normalizza(n), pr["iso"])

    def salva_cache(self):
        if self._cache_modificata:
            self.file_cache.parent.mkdir(parents=True, exist_ok=True)
            self.file_cache.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), encoding="utf-8")
            self._cache_modificata = False

    def pota_cache(self, giorni=None):
        """Toglie dalla cache le voci non usate da più di 'giorni' giorni."""
        limite = (self.oggi - timedelta(days=giorni or config.CACHE_MAX_INUTILIZZO_GIORNI)).isoformat()
        vecchie = [k for k, v in self.cache.items() if v.get("ultimo_uso", "9999") < limite]
        for k in vecchie:
            del self.cache[k]
        if vecchie:
            self._cache_modificata = True
            log.info(f"Cache luoghi: potate {len(vecchie)} voci inutilizzate.")
        return len(vecchie)

    # ------------------------------------------------------------- risultati
    @staticmethod
    def _esito(nome, tipo, paese, lat, lon, poligono=None, bbox=None, fonte=""):
        return {"nome": nome, "tipo": tipo, "paese": paese, "lat": round(float(lat), 4), "lon": round(float(lon), 4),
                "poligono": poligono, "bbox": bbox, "fonte": fonte}

    def _da_paese(self, nome, paese_claude):
        iso_nome = self.nomi_paesi.get(normalizza(nome))
        if paese_claude and iso_nome and paese_claude != iso_nome:
            log.warning(f"Paese incoerente per {nome!r}: Claude dice {paese_claude}, il nome indica {iso_nome}. Ignoro.")
            return None
        iso = paese_claude or iso_nome
        pr = self.paesi.get(iso)
        if not pr:
            return None
        lat, lon = pr["centro"]
        return self._esito(pr["nome"], "paese", iso, lat, lon, {"livello": "paesi", "id": iso}, pr["bbox"], "natural-earth")

    def _da_italia(self, nome, tipo):
        chiave = normalizza(nome)
        if tipo == "regione" and chiave in self.regioni:
            livello, pr = "regioni", self.regioni[chiave]
        elif tipo == "provincia" and _nome_provincia(chiave) in self.province:
            chiave = _nome_provincia(chiave)
            livello, pr = "province", self.province[chiave]
        else:
            return None
        b = pr["bbox"]
        return self._esito(pr["nome"], tipo, "IT", (b[0] + b[2]) / 2, (b[1] + b[3]) / 2,
                           {"livello": livello, "id": chiave}, b, "istat")

    def _attendi(self):
        da_attendere = self.pausa - (time.monotonic() - self._ultima_richiesta)
        if da_attendere > 0:
            self.sleep(da_attendere)
        self._ultima_richiesta = time.monotonic()

    def _da_nominatim(self, nome, tipo, paese):
        if not self.online:
            self.stats["offline"] += 1
            return None
        params = {"q": nome, "format": "jsonv2", "limit": 1, "addressdetails": 1}
        if paese:
            params["countrycodes"] = paese.lower()
        self._attendi()
        try:
            risultati = self.http_get(config.NOMINATIM_URL, params, {"User-Agent": config.user_agent_api()})
        except Exception as e:
            log.warning(f"Nominatim ha fallito per {nome!r}: {e}")
            self.stats["errori_rete"] += 1
            return "ERRORE"
        if not risultati:
            return None
        r = risultati[0]
        cc = str(r.get("address", {}).get("country_code", "")).upper()
        if paese and cc and cc != paese:
            log.warning(f"Nominatim: {nome!r} cade in {cc}, Claude indicava {paese}. Scarto.")
            return None
        return self._esito(nome, tipo, cc or paese, r["lat"], r["lon"], None, None, "nominatim")

    # ------------------------------------------------------------- interfaccia
    def risolvi(self, luogo, sezione=None):
        """luogo: {"nome","tipo","paese"}. Ritorna un dict (vedi _esito) o None."""
        nome, tipo = luogo["nome"], luogo.get("tipo", "luogo")
        paese = (luogo.get("paese") or "").upper()
        chiave_n = normalizza(nome)

        ov = self.override.get(chiave_n)
        if ov is not None:
            if ov.get("ignora"):
                return None
            self.stats["override"] += 1
            return self._esito(nome, ov.get("tipo", tipo), ov.get("paese", paese), ov["lat"], ov["lon"],
                               ov.get("poligono"), ov.get("bbox"), "override")

        chiave = f"{chiave_n}|{tipo}|{paese}"
        voce = self.cache.get(chiave)
        if voce:
            voce["ultimo_uso"] = self.oggi.isoformat()
            self._cache_modificata = True
            if not voce.get("nonrisolto"):
                self.stats["da_cache"] += 1
                return self._valida(voce["esito"], sezione)
            if date.fromisoformat(voce["data"]) + timedelta(days=config.CACHE_NEGATIVA_GIORNI) > self.oggi:
                self.stats["da_cache_negativa"] += 1
                return None

        esito = None
        if tipo == "paese":
            esito = self._da_paese(nome, paese)
        elif paese in ("IT", "") and tipo in ("regione", "provincia"):
            esito = self._da_italia(nome, tipo)
        if esito is None:
            esito = self._da_nominatim(nome, tipo, paese)
            if esito == "ERRORE":                # errore di rete: non memorizzare nulla
                return None

        if esito is None:
            if self.online:          # senza rete non c'è stato un vero tentativo: niente cache negativa
                self.cache[chiave] = {"nonrisolto": True, "data": self.oggi.isoformat(), "ultimo_uso": self.oggi.isoformat()}
                self._cache_modificata = True
            self.stats["non_risolti"] += 1
            return None

        self.cache[chiave] = {"esito": esito, "data": self.oggi.isoformat(), "ultimo_uso": self.oggi.isoformat()}
        self._cache_modificata = True
        self.stats["risolti_locale" if esito["fonte"] in ("natural-earth", "istat") else "risolti_nominatim"] += 1
        return self._valida(esito, sezione)

    @staticmethod
    def _valida(esito, sezione):
        """Nella sezione Italia ogni luogo deve cadere in Italia."""
        if esito is None:
            return None
        if sezione == "Italia" and esito.get("paese") != "IT":
            log.warning(f"Luogo {esito['nome']!r} fuori dall'Italia nella sezione Italia: scartato.")
            return None
        return esito
