"""
immagine_og.py — Fase 7: immagine di anteprima (Open Graph) e icone della PWA.

Generate con Pillow, nessuna rete. Il font viene cercato fra quelli di sistema
(Windows, Linux, macOS); in mancanza si usa quello incorporato in Pillow.
"""

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SFONDO, SFONDO2, TESTO, TESTO_SOFT = (11, 92, 173), (8, 58, 112), (255, 255, 255), (214, 228, 245)
_FONT_GRASSETTO = ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "Helvetica.ttc"]
_FONT_NORMALE = ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Helvetica.ttc"]


def _font(dimensione, grassetto=False):
    for nome in (_FONT_GRASSETTO if grassetto else _FONT_NORMALE):
        try:
            return ImageFont.truetype(nome, dimensione)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=dimensione)
    except TypeError:                         # Pillow < 10.1
        return ImageFont.load_default()


def _sfumatura(larghezza, altezza):
    im = Image.new("RGB", (larghezza, altezza), SFONDO)
    px = ImageDraw.Draw(im)
    for y in range(altezza):
        t = y / altezza
        px.line([(0, y), (larghezza, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(SFONDO, SFONDO2)))
    return im


def _a_capo(draw, testo, font, larghezza_max, max_righe):
    parole, righe, corrente = testo.split(), [], ""
    for p in parole:
        prova = f"{corrente} {p}".strip()
        if draw.textlength(prova, font=font) <= larghezza_max or not corrente:
            corrente = prova
        else:
            righe.append(corrente)
            corrente = p
    if corrente:
        righe.append(corrente)
    if len(righe) > max_righe:
        righe = righe[:max_righe]
        righe[-1] = righe[-1].rstrip(" ,.;:") + "…"
    return righe


def genera_og(titolo, durata_min, titoli_notizie, percorso, nome_sito="Rassegna stampa audio"):
    """1200x630: nome del sito, data/titolo, durata e fino a 3 titoli di notizie."""
    im = _sfumatura(1200, 630)
    d = ImageDraw.Draw(im)
    d.text((70, 60), nome_sito.upper(), font=_font(30, True), fill=TESTO_SOFT)
    y = 120
    for riga in _a_capo(d, titolo, _font(78, True), 1060, 2):
        d.text((70, y), riga, font=_font(78, True), fill=TESTO)
        y += 92
    d.text((70, y + 6), f"{durata_min} minuti di ascolto", font=_font(34), fill=TESTO_SOFT)
    y += 80
    for t in titoli_notizie[:3]:
        righe = _a_capo(d, t, _font(32), 1020, 1)
        d.text((70, y), "•  " + (righe[0] if righe else ""), font=_font(32), fill=TESTO)
        y += 48
    Path(percorso).parent.mkdir(parents=True, exist_ok=True)
    im.save(percorso, "PNG", optimize=True)
    return percorso


def genera_icona(lato, percorso, maskable=False):
    """Quadrato con una 'R' (maskable: simbolo più piccolo, dentro la zona sicura)."""
    im = _sfumatura(lato, lato)
    d = ImageDraw.Draw(im)
    f = _font(int(lato * (0.42 if maskable else 0.58)), True)
    d.text((lato / 2, lato / 2), "R", font=f, fill=TESTO, anchor="mm")
    Path(percorso).parent.mkdir(parents=True, exist_ok=True)
    im.save(percorso, "PNG", optimize=True)
    return percorso
