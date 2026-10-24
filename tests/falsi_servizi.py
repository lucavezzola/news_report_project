"""Servizi finti (Nominatim, Wikidata, Commons) per test e fixture: nessuna rete.
Nomi di persone, partiti e aziende sono INVENTATI; i QID (Q9000xx) non esistono."""

import io

# --- Nominatim: query -> (lat, lon, codice paese)
LUOGHI = {
    "Taranto": (40.4644, 17.2470, "it"), "Roma": (41.8933, 12.4829, "it"), "Milano": (45.4642, 9.1900, "it"),
    "Napoli": (40.8518, 14.2681, "it"), "Palermo": (38.1157, 13.3615, "it"),
    "Parigi": (48.8566, 2.3522, "fr"), "Tokyo": (35.6762, 139.6503, "jp"), "Il Cairo": (30.0444, 31.2357, "eg"),
    "Washington": (38.9072, -77.0369, "us"), "Francoforte": (50.1109, 8.6821, "de"),
    "Crimea": (45.3, 34.4, "ua"),
}


def _claim(valore, rango="normal"):
    return {"mainsnak": {"datavalue": {"value": valore}}, "rank": rango}


def _entita(etichetta, desc, p31, sitelinks, **claims):
    c = {"P31": [_claim({"id": q}) for q in p31]}
    c.update({k: [_claim(v)] for k, v in claims.items()})
    return {"labels": {"it": {"value": etichetta}}, "aliases": {}, "descriptions": {"it": {"value": desc}},
            "claims": c, "sitelinks": {f"site{i}": {} for i in range(sitelinks)}}


ENTITA = {
    "Q900001": _entita("Anna Verdi", "politica italiana", ["Q5"], 40, P18="Anna Verdi.jpg"),
    "Q900002": _entita("Luca Bianchi", "calciatore", ["Q5"], 30),
    "Q900003": _entita("Luca Bianchi", "attore", ["Q5"], 25),
    "Q900004": _entita("Paolo Neri", "associazione", ["Q43229"], 50),          # non è una persona
    "Q900005": _entita("Carla Gialli", "scrittrice", ["Q5"], 3),               # poco nota
    "Q900010": _entita("Partito Esempio", "partito politico", ["Q7278"], 20, P154="Logo Partito Esempio.svg", P465="1A73E8"),
    "Q900011": _entita("Azienda Orizzonte", "azienda", ["Q4830453"], 15, P154="Orizzonte logo.png"),
    "Q900012": _entita("Banca Centrale Esempio", "istituzione finanziaria", ["Q327333"], 25),
}
RICERCA = {"Anna Verdi": ["Q900001"], "Luca Bianchi": ["Q900002", "Q900003"], "Paolo Neri": ["Q900004"],
           "Carla Gialli": ["Q900005"], "Partito Esempio": ["Q900010"], "Azienda Orizzonte": ["Q900011"],
           "Banca Centrale Esempio": ["Q900012"]}

FILE_COMMONS = {   # nome file -> (estensione miniatura, licenza, autore)
    "Anna Verdi.jpg": ("jpg", "CC BY-SA 4.0", "<a href='https://x.example'>Fotografa Esempio</a>"),
    "Logo Partito Esempio.svg": ("png", "Public domain", "Autore Esempio"),
    "Orizzonte logo.png": ("png", "CC BY-NC 4.0", "Autore Non Commerciale"),
}


def immagine_finta(testo="?", ext="png", colore=(60, 90, 160)):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (400, 400), colore)
    ImageDraw.Draw(im).text((170, 180), testo, fill="white")
    buf = io.BytesIO()
    im.save(buf, format="JPEG" if ext == "jpg" else "PNG")
    return buf.getvalue()


class FalsoWeb:
    def __init__(self):
        self.chiamate = []

    def get(self, url, params=None, headers=None):
        self.chiamate.append((url, dict(params or {})))
        if "nominatim" in url:
            q = params["q"]
            if q not in LUOGHI:
                return []
            lat, lon, cc = LUOGHI[q]
            if "countrycodes" in params and params["countrycodes"] != cc:
                return []                       # il vero Nominatim restringe al paese richiesto
            return [{"lat": str(lat), "lon": str(lon), "address": {"country_code": cc}}]
        azione = (params or {}).get("action")
        if azione == "wbsearchentities":
            return {"search": [{"id": q} for q in RICERCA.get(params["search"], [])]}
        if azione == "wbgetentities":
            return {"entities": {q: ENTITA[q] for q in params["ids"].split("|") if q in ENTITA}}
        if azione == "query":
            nome = params["titles"].replace("File:", "")
            if nome not in FILE_COMMONS:
                return {"query": {"pages": {"-1": {"missing": ""}}}}
            ext, lic, autore = FILE_COMMONS[nome]
            return {"query": {"pages": {"1": {"imageinfo": [{
                "thumburl": f"https://upload.wikimedia.org/fake/400px-{nome.replace(' ', '_')}.{ext}",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:" + nome.replace(" ", "_"),
                "extmetadata": {"Artist": {"value": autore}, "LicenseShortName": {"value": lic},
                                "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"}}}]}}}}
        raise AssertionError(f"chiamata inattesa: {url} {params}")

    def scarica(self, url, headers=None):
        self.chiamate.append((url, {}))
        ext = url.rsplit(".", 1)[-1]
        return immagine_finta("IMG", ext)
