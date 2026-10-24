import json
from pathlib import Path

import config
import sito


def manifest_base():
    return {"data": "2099-01-01", "durata": 60.0, "audio": "episodio.mp3", "sezioni": [], "mappa": [{"t": 0}],
            "entita": {
                "e1": {"nome": "<script>x</script>", "tipo": "persona", "descrizione": "d", "immagine": "img/Q1.jpg",
                       "colore": "zzzzzz", "crediti": {"autore": "A", "licenza": "CC BY 4.0", "licenza_url": "javascript:alert(1)", "pagina": "ftp://x"}},
                "e2": {"nome": "Due", "tipo": "persona", "descrizione": "", "immagine": "../../etc/passwd", "colore": "1A73E8", "crediti": None},
                "e3": {"nome": "Tre", "tipo": "persona", "descrizione": "", "immagine": "img/Q3.jpg", "colore": None, "crediti": None}},
            "luoghi": {"l1": {"nome": "Roma", "tipo": "citta", "paese": "IT", "lat": 41.9, "lon": 12.5, "poligono": None},
                       "l2": {"nome": "Rotto", "tipo": "citta", "paese": "IT", "lat": "41.9", "lon": None, "poligono": None},
                       "l3": {"nome": "Poli", "tipo": "regione", "paese": "IT", "lat": 1.0, "lon": 2.0,
                              "poligono": {"livello": "../x", "id": "a"}}}}


def test_sanificazione():
    dati, crediti = sito.prepara_dati_visivi(manifest_base(), {"img/Q1.jpg"})
    assert dati["entita"]["e1"]["immagine"] == "img/Q1.jpg" and dati["entita"]["e1"]["colore"] is None
    assert dati["entita"]["e2"]["immagine"] is None            # percorso non in whitelist
    assert dati["entita"]["e3"]["immagine"] is None            # file non presente nel sito
    assert set(dati["luoghi"]) == {"l1", "l3"} and dati["luoghi"]["l3"]["poligono"] is None
    assert crediti[0]["licenza_url"] == "" and crediti[0]["pagina"].startswith("https://commons.wikimedia.org")


def test_nessun_contenuto_visivo():
    assert sito.prepara_dati_visivi({"sezioni": [], "durata": 1}, set()) == (None, [])


def test_immagini_orfane(cartelle_tmp):
    radice = sito.dir_token()
    (radice / "img").mkdir(parents=True)
    (radice / "img" / "Q1.jpg").write_bytes(b"x")
    (radice / "img" / "Q2.jpg").write_bytes(b"x")
    giorno = radice / "2099-01-01"
    giorno.mkdir()
    (giorno / "manifest.json").write_text(json.dumps({"entita": {"e1": {"immagine": "img/Q1.jpg"}}}), encoding="utf-8")
    assert sito.pulisci_immagini_orfane() == ["Q2.jpg"]
    assert (radice / "img" / "Q1.jpg").exists() and not (radice / "img" / "Q2.jpg").exists()
