"""
fonetica.py — Fase 2: da testo scritto a testo parlato.

normalizza_per_tts(frase) trasforma UNA frase scritta (quella che finisce nei
sottotitoli) in UNA frase da dare a XTTS. Due strati:
  (a) regole: numeri in lettere (num2words, lang='it'), migliaia, decimali,
      percentuali, valute, orari, anni, ordinali, abbreviazioni, simboli;
  (b) dizionario fonetica.txt: pronunce di nomi e sigle, a parola intera.

INVARIANTE: una frase in, una frase out. Mai fondere o spezzare frasi:
l'allineamento con i sottotitoli dipende da questo.

Le parole sospette (j, k, w, x, y, sigle) incontrate vengono contate in
logs/fonetica_candidati.txt, per decidere cosa aggiungere al dizionario.
"""

import re
from collections import Counter
from pathlib import Path

from num2words import num2words

import config

MESI = "gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre"

ABBREVIAZIONI = [
    (r"\becc\.", "eccetera"),
    (r"\bes\.", "ad esempio"),
    (r"\bsig\.ra\b", "signora"),
    (r"\bsig\.", "signor"),
    (r"\bdott\.ssa\b", "dottoressa"),
    (r"\bdott\.", "dottor"),
    (r"\bprof\.ssa\b", "professoressa"),
    (r"\bprof\.", "professor"),
    (r"\bon\.", "onorevole"),
    (r"\bavv\.", "avvocato"),
    (r"\bing\.", "ingegner"),
    (r"\bart\.", "articolo"),
    (r"\bn\.\s?(?=\d)", "numero "),
    (r"\bmln\b\.?", "milioni"),
    (r"\bmld\b\.?", "miliardi"),
    (r"\bkm\b", "chilometri"),
    (r"\bkg\b", "chili"),
    (r"\bcm\b", "centimetri"),
    (r"\bmq\b", "metri quadrati"),
    (r"\bvs\.?", "contro"),
]

_cache_dizionario = None


def carica_dizionario(percorso=None):
    """Legge fonetica.txt. Ritorna lista di (chiave_minuscola, sostituzione),
    ordinata per lunghezza decrescente (vince la voce più specifica)."""
    voci = []
    p = Path(percorso or config.FILE_FONETICA)
    if p.exists():
        for riga in p.read_text(encoding="utf-8").splitlines():
            riga = riga.strip()
            if not riga or riga.startswith("#") or "=" not in riga:
                continue
            chiave, valore = riga.split("=", 1)
            chiave, valore = chiave.strip(), valore.strip()
            if chiave and valore:
                voci.append((chiave, valore))
    voci.sort(key=lambda v: len(v[0]), reverse=True)
    return voci


def _applica_dizionario(testo, voci):
    for chiave, valore in voci:
        modello = re.compile(r"(?<![\w])" + re.escape(chiave) + r"(?![\w])", re.IGNORECASE)
        testo = modello.sub(lambda _m, v=valore: v, testo)
    return testo


# ---------------------------------------------------------------------------
# Numeri
# ---------------------------------------------------------------------------
def _parole(n):
    return num2words(int(n), lang="it")


def _decimale(parte_intera, parte_dec):
    """'3', '25' -> 'tre virgola venticinque'; zeri iniziali letti uno a uno."""
    zeri = len(parte_dec) - len(parte_dec.lstrip("0"))
    resto = parte_dec.lstrip("0")
    dec = " ".join(["zero"] * zeri + ([_parole(resto)] if resto else []))
    return f"{_parole(parte_intera)} virgola {dec}"


def _numero_it(testo_num):
    """Converte '1500000' o '3,5' (già senza punti di migliaia) in lettere."""
    if "," in testo_num:
        i, d = testo_num.split(",", 1)
        return _decimale(i, d)
    return _parole(testo_num)


def _numeri_a_parole(t):
    # migliaia con punto: 1.500.000 -> 1500000 (ma non 3.5 né date 13.09.2026)
    t = re.sub(r"(?<=\d)\.(?=\d{3}(?!\d))", "", t)
    # spazio come separatore di migliaia: 1 500 000
    t = re.sub(r"\b(\d{1,3})(?: (\d{3}))+\b", lambda m: m.group(0).replace(" ", ""), t)

    # orari 08:30 / 8.30 dopo "alle"/"ore"
    def _ora(m):
        h, mi = int(m.group(2)), int(m.group(3))
        s = _parole(h) + ("" if mi == 0 else " e " + _parole(mi))
        return f"{m.group(1)}{s}"
    t = re.sub(r"(\b(?:alle|ore|le)\s+)(\d{1,2})[:.](\d{2})\b", _ora, t, flags=re.IGNORECASE)
    t = re.sub(r"\b(\d{1,2}):(\d{2})\b", lambda m: _parole(m.group(1)) + ("" if m.group(2) == "00" else " e " + _parole(m.group(2))), t)

    # "1 ottobre" -> "primo ottobre"
    t = re.sub(rf"\b1(?:º|°)?\s+({MESI})\b", r"primo \1", t, flags=re.IGNORECASE)

    # ordinali: 2º, 3°, 1ª
    def _ord(m):
        w = num2words(int(m.group(1)), to="ordinal", lang="it")
        if m.group(2) == "ª" and w.endswith("o"):
            w = w[:-1] + "a"
        return w
    t = re.sub(r"\b(\d+)\s?(º|°|ª)", _ord, t)

    # percentuali: 3,5% / 12 %
    t = re.sub(r"(\d+(?:,\d+)?)\s?%", lambda m: _numero_it(m.group(1)) + " per cento", t)

    # valute: €5, 5€, 5 euro, $5 ; con milioni/miliardi
    scala = r"(?:\s+(milioni|miliardi|mila))?"
    t = re.sub(rf"(\d+(?:,\d+)?){scala}\s?(?:€|euro\b)",
               lambda m: _numero_it(m.group(1)) + (f" {m.group(2)}" if m.group(2) else "") + " euro", t, flags=re.IGNORECASE)
    t = re.sub(rf"€\s?(\d+(?:,\d+)?){scala}",
               lambda m: _numero_it(m.group(1)) + (f" {m.group(2)}" if m.group(2) else "") + " euro", t)
    t = re.sub(rf"\$\s?(\d+(?:,\d+)?){scala}",
               lambda m: _numero_it(m.group(1)) + (f" {m.group(2)}" if m.group(2) else "") + " dollari", t)
    t = re.sub(r"(\d+(?:,\d+)?)\s?\$", lambda m: _numero_it(m.group(1)) + " dollari", t)

    t = t.replace("€", " euro ").replace("$", " dollari ")
    t = re.sub(r"(?<=[A-Za-z])-(?=\d)", " ", t)   # F-35 -> F 35
    # decimali e interi rimasti (anche attaccati a lettere: 5G -> cinque G)
    t = re.sub(r"\d+,\d+", lambda m: _numero_it(m.group(0)), t)
    t = re.sub(r"\d+", lambda m: " " + _parole(m.group(0)) + " ", t)
    return t


# ---------------------------------------------------------------------------
# Candidati per il dizionario
# ---------------------------------------------------------------------------
_RE_SOSPETTA = re.compile(r"\b(?=\w*[jJkKwWxXyY])[\w'-]{2,}\b")
_RE_SIGLA = re.compile(r"\b[A-Z][A-Z0-9]{1,5}\b")
_RE_CIFRA_LETTERA = re.compile(r"\b(?=\w*\d)(?=\w*[A-Za-z])\w+\b")


def trova_candidati(frase, voci_dizionario=()):
    gia = {k.lower() for k, _ in voci_dizionario}
    trovati = Counter()
    for rx in (_RE_SOSPETTA, _RE_SIGLA, _RE_CIFRA_LETTERA):
        for m in rx.finditer(frase):
            parola = m.group(0)
            if parola.lower() not in gia:
                trovati[parola] += 1
    return trovati


def salva_candidati(contatore, percorso=None):
    """Unisce i conteggi di questo run a quelli già nel file (parola<TAB>n)."""
    if not contatore:
        return
    p = Path(percorso or config.FILE_FONETICA_CANDIDATI)
    p.parent.mkdir(parents=True, exist_ok=True)
    totale = Counter()
    if p.exists():
        for riga in p.read_text(encoding="utf-8").splitlines():
            if "\t" in riga:
                parola, n = riga.rsplit("\t", 1)
                if n.strip().isdigit():
                    totale[parola] += int(n)
    totale.update(contatore)
    righe = [f"{parola}\t{n}" for parola, n in sorted(totale.items(), key=lambda x: (-x[1], x[0].lower()))]
    p.write_text("\n".join(righe) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# API principale
# ---------------------------------------------------------------------------
def normalizza_per_tts(frase, dizionario=None, candidati=None):
    """Una frase scritta -> una frase parlata.
    dizionario: lista (chiave, valore); se None viene letto da fonetica.txt.
    candidati: Counter opzionale a cui aggiungere le parole sospette."""
    voci = carica_dizionario() if dizionario is None else dizionario
    t = frase

    if candidati is not None:
        candidati.update(trova_candidati(t, voci))

    # pulizia simboli che il TTS legge male (puntini, caporali, trattini lunghi)
    t = t.replace("…", ",").replace("...", ",")
    t = re.sub(r"[«»“”\"]", "", t)
    t = re.sub(r"\s*[—–]\s*", ", ", t)

    t = _applica_dizionario(t, voci)
    for rx, sost in ABBREVIAZIONI:
        t = re.sub(rx, sost, t, flags=re.IGNORECASE)
    t = _numeri_a_parole(t)

    t = t.replace("&", " e ").replace("+", " più ")
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t).strip()
    return t
