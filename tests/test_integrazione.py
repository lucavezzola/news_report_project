"""Pipeline completa sulle fixture (audio finto, nessuna rete): controlla il sito generato."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import config
import main
import sito

RADICE = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg non installato")


@pytest.fixture(scope="module")
def giorno(tmp_path_factory):
    """Esegue main.py --usa-fixture in cartelle temporanee e ritorna (cartella giorno, radice token)."""
    mp = pytest.MonkeyPatch()
    tmp = tmp_path_factory.mktemp("integ")
    for nome, val in (("DIR_OUTPUT", str(tmp / "output")), ("DIR_SITO", str(tmp / "sito")), ("FILE_TOKEN_SITO", str(tmp / "t.txt")),
                      ("DIR_SITO_TEMPLATE", str(RADICE / "sito_template")), ("DIR_GEO", str(RADICE / "data" / "geo")),
                      ("DIR_CACHE_IMMAGINI", str(tmp / "cache" / "img")), ("MUSICA_ABILITATA", False)):
        mp.setattr(config, nome, val)
    mp.setenv("SITO_TOKEN", "tokentest")
    mp.setenv("SITO_BASE_URL", "https://esempio.test")
    mp.chdir(RADICE)
    codice = main.main(["--usa-fixture", "--data", "2099-01-01", "--audio-finto", "--no-deploy", "--no-telegram"])
    assert codice == 0
    radice = tmp / "sito" / "t" / "tokentest"
    yield radice / "2099-01-01", radice
    config.imposta_data(None)
    mp.undo()


def test_manifest_con_mappa_ed_entita(giorno):
    cartella, _ = giorno
    m = json.loads((cartella / "manifest.json").read_text(encoding="utf-8"))
    assert len(m["luoghi"]) >= 10 and m["mappa"]
    assert {e["nome"] for e in m["entita"].values()} == {"Anna Verdi", "Partito Esempio", "Azienda Orizzonte", "Banca Centrale Esempio"}
    # tempi coerenti: ogni keyframe cade dentro la durata
    assert all(0 <= k["t"] <= m["durata"] for k in m["mappa"])
    # ogni luogo/entità referenziata dalle frasi esiste nelle tabelle
    for s in m["sezioni"]:
        for n in s["notizie"]:
            for f in n["frasi"]:
                assert set(f.get("luoghi", [])) <= set(m["luoghi"]) and set(f.get("entita", [])) <= set(m["entita"])


def test_file_del_sito(giorno):
    cartella, radice = giorno
    for p in ("index.html", "episodio.mp3", "manifest.json", "og.png"):
        assert (cartella / p).exists(), p
    for p in ("manifest.webmanifest", "sw.js", "static/app.js", "static/mappa.js", "static/mappa_logica.js", "static/citati.js",
              "static/leaflet/leaflet.js", "static/leaflet/LICENSE", "static/geo/paesi.json", "static/geo/regioni.json",
              "static/geo/province.json", "static/icon-192.png", "static/icon-512.png", "img/Q900001.jpg", "img/Q900010.png"):
        assert (radice / p).exists(), p


def test_html_pagina(giorno):
    cartella, _ = giorno
    h = (cartella / "index.html").read_text(encoding="utf-8")
    assert 'id="dati-visivi"' in h and "data-entita=" in h and 'data-mappa="1"' in h and 'data-mappa="0"' in h
    # layout a due colonne: testo a sinistra, colonna visiva a destra, entrambi dentro .layout
    assert h.index('class="layout"') < h.index('id="contenuto"') < h.index('id="visivo"') < h.index("</div>", h.index('id="visivo"'))
    assert 'id="toggle-testo"' in h and 'aria-expanded="true"' in h and 'id="citati"' in h
    assert "javascript:" not in h and "Crediti delle immagini" in h
    assert "CC BY-SA 4.0" in h and "CC BY-NC" not in h
    assert "Natural Earth" in h and "ISTAT" in h                          # attribuzioni
    assert 'og:image" content="https://esempio.test/t/tokentest/2099-01-01/og.png"' in h
    assert len(h.encode()) < 1_000_000


def test_dati_visivi_sanificati(giorno):
    cartella, _ = giorno
    h = (cartella / "index.html").read_text(encoding="utf-8")
    dati = json.loads(re.search(r'id="dati-visivi">(.*?)</script>', h, re.S).group(1))
    assert dati["base"] == "../"
    for e in dati["entita"].values():
        assert e["immagine"] is None or re.fullmatch(r"img/[A-Za-z0-9_.-]+", e["immagine"])
    assert all(isinstance(l["lat"], float) and isinstance(l["lon"], float) for l in dati["luoghi"].values())


def test_pwa(giorno):
    _, radice = giorno
    wm = json.loads((radice / "manifest.webmanifest").read_text(encoding="utf-8"))
    for icona in wm["icons"]:
        assert (radice / icona["src"]).exists()
    sw = (radice / "sw.js").read_text(encoding="utf-8")
    assert "__VERSIONE__" not in sw and "__MAX_PAGINE__" not in sw
    assert 'req.headers.has("range")' in sw and "mp3" in sw             # l'audio non viene mai intercettato
    assert 'url.origin !== self.location.origin' in sw


def test_pagina_leggera_e_asset_condivisi(giorno):
    cartella, radice = giorno
    base = sum(f.stat().st_size for f in (cartella / "index.html", radice / "static" / "app.js", radice / "static" / "style.css"))
    assert base < 100_000                                                # il grosso (mappa, leaflet) si scarica una volta


def test_fumo_in_jsdom(giorno):
    node_path = os.environ.get("NODE_PATH", "")
    locale = RADICE / "tests" / "js" / "node_modules" / "jsdom"
    if shutil.which("node") is None or not (locale.exists() or any((Path(p) / "jsdom").exists() for p in node_path.split(os.pathsep) if p)):
        pytest.skip("jsdom non installato (opzionale: npm install --prefix tests/js jsdom)")
    cartella, radice = giorno
    r = subprocess.run(["node", str(RADICE / "tests" / "js" / "fumo_pagina.js"), str(radice), "2099-01-01"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["errori"] == []
    assert out["ha_Rassegna"] and out["visivo_visibile"] and out["clic_ok"] and out["percorsi_mappa"] > 50
    assert all(s["attive"] == 1 and s["carte"] <= 3 for s in out["seek"])
    assert out["carta_prima_entita"] == ["Anna Verdi"] and out["immagini_carte"] == ["../img/Q900001.jpg"]
    assert out["scroll_nascosta"] is not None and abs(out["scroll_nascosta"] - out["scroll_atteso"]) < 1e-6 and out["scroll_nascosta"] < 0
    assert out["scroll_se_visibile"] == 0                                # frase già visibile: nessun movimento
    assert out["layout_con_visivo"] and out["visivo_dentro_layout"]
    assert out["testo_nascosto"] and out["etichetta_toggle"] == "Mostra testo" and out["testo_ripristinato"] and out["senza_visivo"]
    assert out["script_nel_citati"] == 0 and out["tema_dopo_clic"] == "chiaro" and out["zoom"] == "1.1"
