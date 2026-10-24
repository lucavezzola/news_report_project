"""
scarica_geo.py — Scarica e semplifica i confini per la mappa (Fase 5).

Fonti:
- Paesi: Natural Earth 1:50m, "admin 0 countries" (pubblico dominio).
  https://www.naturalearthdata.com/  (mirror GitHub: nvkelso/natural-earth-vector)
- Regioni e province italiane: ISTAT, nel mirror
  openpolis/geojson-italy (CC-BY: serve l'attribuzione "ISTAT / Openpolis",
  già presente nel sito).

Scrive in data/geo/: paesi.json, regioni.json, province.json (GeoJSON
compatti: coordinate arrotondate e semplificate con Douglas-Peucker).
I file prodotti sono nel progetto: lo script serve solo per rigenerarli o
aggiornarli. Uso:  python scarica_geo.py

ATTENZIONE, scelta editoriale: Natural Earth ritrae i confini de facto e non
tutte le attribuzioni sono neutre (es. Crimea e Sahara Occidentale).
Vedi docs/confini_contesi.md.
"""

import json
import re
import unicodedata
from pathlib import Path

import requests

URL_PAESI = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"
URL_REGIONI = "https://raw.githubusercontent.com/openpolis/geojson-italy/master/geojson/limits_IT_regions.geojson"
URL_PROVINCE = "https://raw.githubusercontent.com/openpolis/geojson-italy/master/geojson/limits_IT_provinces.geojson"
DIR = Path("data/geo")


def normalizza(nome):
    """'Valle d'Aosta/Vallée d'Aoste' -> 'valledaosta'. Chiave di confronto per i nomi italiani."""
    nome = (nome or "").split("/")[0]
    nome = unicodedata.normalize("NFKD", nome)
    nome = "".join(c for c in nome if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", nome.lower())


def semplifica_anello(punti, tolleranza):
    """Douglas-Peucker iterativo. Mantiene sempre primo e ultimo punto."""
    n = len(punti)
    if n <= 4 or tolleranza <= 0:
        return punti
    tieni = [False] * n
    tieni[0] = tieni[-1] = True
    pila = [(0, n - 1)]
    while pila:
        a, b = pila.pop()
        (x1, y1), (x2, y2) = punti[a], punti[b]
        dx, dy = x2 - x1, y2 - y1
        norma = (dx * dx + dy * dy) ** 0.5
        dmax, imax = 0.0, -1
        for i in range(a + 1, b):
            x, y = punti[i]
            d = (abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norma) if norma else ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
            if d > dmax:
                dmax, imax = d, i
        if dmax > tolleranza and imax != -1:
            tieni[imax] = True
            pila.extend([(a, imax), (imax, b)])
    return [p for p, t in zip(punti, tieni) if t]


def _anello(anello, tol, decimali):
    s = semplifica_anello([(x, y) for x, y in anello], tol)
    if len(s) < 4:                      # anello degenere: lo scarto
        return None
    return [[round(x, decimali), round(y, decimali)] for x, y in s]


def _area_bbox(poligono):
    xs = [p[0] for p in poligono[0]]
    ys = [p[1] for p in poligono[0]]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def poligoni(geometria):
    return [geometria["coordinates"]] if geometria["type"] == "Polygon" else geometria["coordinates"]


def semplifica_geometria(geometria, tol, decimali=3, area_minima=0.0):
    """Ritorna una geometria semplificata. Scarta i poligoni più piccoli di
    'area_minima' (gradi quadrati) tranne il più grande."""
    polis = sorted(poligoni(geometria), key=_area_bbox, reverse=True)
    risultato = []
    for i, poli in enumerate(polis):
        if i > 0 and _area_bbox(poli) < area_minima:
            continue
        anelli = [_anello(a, tol, decimali) for a in poli]
        if anelli[0] is None:
            continue
        risultato.append([a for a in anelli if a is not None])
    if len(risultato) == 1:
        return {"type": "Polygon", "coordinates": risultato[0]}
    return {"type": "MultiPolygon", "coordinates": risultato}


def bbox_poligono_maggiore(geometria):
    """[min_lat, min_lon, max_lat, max_lon] del poligono più grande: evita che
    Russia, Stati Uniti o la Francia d'oltremare producano riquadri enormi
    (antimeridiano, territori lontani)."""
    maggiore = max(poligoni(geometria), key=_area_bbox)
    xs = [p[0] for p in maggiore[0]]
    ys = [p[1] for p in maggiore[0]]
    return [round(min(ys), 2), round(min(xs), 2), round(max(ys), 2), round(max(xs), 2)]


def processa_paesi(dati):
    feats = []
    for f in dati["features"]:
        p = f["properties"]
        iso = p.get("ISO_A2_EH") if p.get("ISO_A2_EH") not in (None, "-99") else p.get("ISO_A2")
        iso = iso if iso and re.fullmatch(r"[A-Z]{2}", iso) else ""
        if iso == "AQ":                      # Antartide: inutile e appesantisce
            continue
        feats.append({"type": "Feature", "properties": {
            "iso": iso, "nome": p.get("NAME_IT") or p.get("NAME"), "nome_en": p.get("NAME"),
            "bbox": bbox_poligono_maggiore(f["geometry"]),
            "centro": [round(p.get("LABEL_Y", 0), 3), round(p.get("LABEL_X", 0), 3)],
        }, "geometry": semplifica_geometria(f["geometry"], tol=0.04, decimali=2, area_minima=0.02)})
    return {"type": "FeatureCollection", "features": feats}


def processa_regioni(dati):
    feats = []
    for f in dati["features"]:
        p = f["properties"]
        feats.append({"type": "Feature", "properties": {
            "id": normalizza(p["reg_name"]), "nome": p["reg_name"], "iso": p.get("reg_iso_3166_2", ""),
            "bbox": bbox_poligono_maggiore(f["geometry"]),
        }, "geometry": semplifica_geometria(f["geometry"], tol=0.02, decimali=3, area_minima=0.003)})
    return {"type": "FeatureCollection", "features": feats}


def processa_province(dati):
    feats = []
    for f in dati["features"]:
        p = f["properties"]
        feats.append({"type": "Feature", "properties": {
            "id": normalizza(p["prov_name"]), "nome": p["prov_name"], "sigla": p.get("prov_acr", ""),
            "regione": p.get("reg_name", ""),
            "bbox": bbox_poligono_maggiore(f["geometry"]),
        }, "geometry": semplifica_geometria(f["geometry"], tol=0.015, decimali=3, area_minima=0.002)})
    return {"type": "FeatureCollection", "features": feats}


def _scarica(url):
    r = requests.get(url, timeout=120, headers={"User-Agent": "RassegnaAudio/1.0 (scarica_geo)"})
    r.raise_for_status()
    return r.json()


if __name__ == "__main__":
    DIR.mkdir(parents=True, exist_ok=True)
    for nome, url, fn in (("paesi", URL_PAESI, processa_paesi), ("regioni", URL_REGIONI, processa_regioni),
                          ("province", URL_PROVINCE, processa_province)):
        print(f"Scarico {nome}...")
        out = fn(_scarica(url))
        percorso = DIR / f"{nome}.json"
        percorso.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"  {len(out['features'])} elementi, {percorso.stat().st_size / 1024:.0f} KB -> {percorso}")
