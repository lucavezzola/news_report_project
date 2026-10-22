import json
from datetime import date, timedelta
from pathlib import Path

import config
import deploy
import sito


def manifest_xss():
    fr = {"testo": "<script>alert(1)</script> & \"virgolette\"", "inizio": 1.0, "fine": 2.0}
    return {"data": "2099-01-01", "durata": 120.0, "audio": "episodio.mp3", "sezioni": [{
        "id": "italia", "nome": "Italia", "inizio": 1.0, "fine": 2.0, "notizie": [{
            "id": "italia-1", "tipo": "notizia", "titolo": "<b>Titolo</b>", "fonte_singola": True,
            "fonti": [{"titolo": "Art", "testata": "ANSA", "url": "javascript:alert(1)"},
                      {"titolo": "Ok", "testata": "BBC", "url": "https://example.org/a?x=1&y=2"}],
            "inizio": 1.0, "fine": 2.0, "frasi": [fr]}]}]}


def prepara(cartelle_tmp, giorno="2099-01-01"):
    config.imposta_data(giorno)
    Path(config.percorso_manifest()).write_text(json.dumps(manifest_xss()), encoding="utf-8")
    Path(config.percorso_episodio_mp3()).write_bytes(b"ID3fake")


def test_html_escape_e_link_sicuri(cartelle_tmp):
    prepara(cartelle_tmp)
    cartella = sito.costruisci_sito_giorno()
    h = (cartella / "index.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in h and "&lt;script&gt;" in h
    assert "<b>Titolo</b>" not in h
    assert "javascript:" not in h
    assert 'rel="noopener noreferrer"' in h and "fonte singola" in h
    assert 'property="og:title"' in h and "noindex" in h
    assert 'og:url" content="https://esempio.test/t/tokentest/2099-01-01/"' in h


def test_js_senza_innerhtml():
    js = (Path(config.DIR_SITO_TEMPLATE) / "app.js").read_text(encoding="utf-8")
    codice = "\n".join(r for r in js.splitlines() if not r.strip().startswith("//"))
    assert "innerHTML" not in codice and "document.write" not in codice and "eval(" not in codice


def test_struttura_sito_e_archivio(cartelle_tmp):
    prepara(cartelle_tmp)
    sito.costruisci_sito_giorno()
    radice = Path(config.DIR_SITO)
    assert (radice / "robots.txt").read_text().startswith("User-agent: *")
    t = radice / "t" / "tokentest"
    for p in ("index.html", "static/app.js", "static/style.css", "2099-01-01/episodio.mp3", "2099-01-01/manifest.json"):
        assert (t / p).exists(), p
    assert "2099-01-01" in (t / "index.html").read_text(encoding="utf-8")


def test_retention(cartelle_tmp):
    oggi = date(2099, 3, 1)
    for d in (oggi - timedelta(days=40), oggi - timedelta(days=5)):
        prepara(cartelle_tmp, d.isoformat())
        sito.costruisci_sito_giorno()
    rimossi = deploy.applica_retention(giorni=30, oggi=oggi)
    assert rimossi == [(oggi - timedelta(days=40)).isoformat()]
    assert (Path(config.DIR_SITO) / "t" / "tokentest" / (oggi - timedelta(days=5)).isoformat()).exists()
