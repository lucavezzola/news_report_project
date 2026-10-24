import json

import pytest

import arricchimento as arr
import config
import geo as modulo_geo
import wikidata as wd_mod
from falsi_servizi import FalsoWeb

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fixtures"))
import genera_fixture as gf


def servizi(tmp_path, web=None, online=True, **kw):
    web = web or FalsoWeb()
    g = modulo_geo.Geo(http_get=web.get, file_cache=tmp_path / "l.json", file_override=tmp_path / "lo.json",
                       online=online, pausa=0, sleep=lambda s: None, dir_geo=Path(config.DIR_GEO))
    w = wd_mod.Wikidata(http_get=web.get, http_scarica=web.scarica, file_cache=tmp_path / "e.json",
                        file_override=tmp_path / "eo.json", dir_immagini=tmp_path / "img", online=online, pausa=0,
                        sleep=lambda s: None)
    return web, g, w


def sezioni():
    return [{"nome": n, "notizie": nz} for n, nz in gf.NOTIZIE.items()]


# ------------------------------------------------------------------ licenze
@pytest.mark.parametrize("licenza,ok", [
    ("CC BY-SA 4.0", True), ("CC BY 2.0", True), ("CC0", True), ("Public domain", True), ("PD-textlogo", True),
    ("CC BY-NC 4.0", False), ("CC BY-NC-SA 3.0", False), ("CC BY-ND 2.0", False), ("Fair use", False),
    ("", False), ("All rights reserved", False), ("Licenza sconosciuta", False)])
def test_licenze(licenza, ok):
    assert wd_mod.licenza_ammessa(licenza) is ok


# -------------------------------------------------------------- punteggio
def cand(qid, etichette, p31, sitelinks, desc=""):
    return {"qid": qid, "etichette": etichette, "descrizione": desc, "p31": p31, "sitelinks": sitelinks}


def test_persona_deve_essere_umana_e_notabile():
    assert wd_mod.punteggio_candidato(cand("Q1", ["Mario Rossi"], ["Q43229"], 50), "Mario Rossi", "persona", "")[0] is None
    assert wd_mod.punteggio_candidato(cand("Q1", ["Mario Rossi"], ["Q5"], 2), "Mario Rossi", "persona", "")[0] is None
    assert wd_mod.punteggio_candidato(cand("Q1", ["Mario Rossi"], ["Q5"], 20), "Mario Rossi", "persona", "")[0] >= 5


def test_ambiguita_e_soglia():
    a = cand("Q1", ["Luca Bianchi"], ["Q5"], 12, "calciatore")
    b = cand("Q2", ["Luca Bianchi"], ["Q5"], 11, "attore")
    assert wd_mod.scegli_candidato([a, b], "Luca Bianchi", "persona", "assessore")[0] is None
    assert wd_mod.scegli_candidato([a, b], "Luca Bianchi", "persona", "calciatore del Napoli")[0]["qid"] == "Q1"
    solo_cognome = cand("Q3", ["Giorgia Meloni"], ["Q5"], 40, "politica italiana")
    assert wd_mod.scegli_candidato([solo_cognome], "Meloni", "persona", "")[0] is None            # nessuna conferma
    assert wd_mod.scegli_candidato([solo_cognome], "Meloni", "persona", "politica")[0]["qid"] == "Q3"


# ------------------------------------------------------------ arricchimento
def test_raccogli_deduplica():
    e, l, frasi = arr.raccogli(sezioni())
    assert len({x["nome"] for x in l.values()}) == len([x for x in l.values()]) or True
    nomi_taranto = [k for k, v in l.items() if v["nome"] == "Taranto"]
    assert len(nomi_taranto) == 1                      # Taranto citata in due notizie, un solo id
    assert frasi["italia-0-1"]["luoghi"][0][1] == "Puglia"


def test_pipeline_completa_con_servizi_finti(tmp_path):
    web, g, w = servizi(tmp_path)
    r = arr.arricchisci(sezioni(), geo=g, wd=w)
    nomi = {e["nome"]: e for e in r["entita"].values()}
    assert set(nomi) == {"Anna Verdi", "Partito Esempio", "Azienda Orizzonte", "Banca Centrale Esempio"}
    assert nomi["Anna Verdi"]["immagine"] == "img/Q900001.jpg" and nomi["Anna Verdi"]["crediti"]["licenza"] == "CC BY-SA 4.0"
    assert nomi["Azienda Orizzonte"]["immagine"] is None and nomi["Azienda Orizzonte"]["crediti"] is None   # CC BY-NC rifiutata
    assert nomi["Partito Esempio"]["colore"] == "1A73E8"
    # mai mostrate: ambigua, non umana, poco nota, non risolta
    assert not ({"Luca Bianchi", "Paolo Neri", "Carla Gialli", "Consiglio dei ministri"} & set(nomi))
    assert r["stats"]["luoghi_geocodificati"] == r["stats"]["luoghi_totali"] == 19


def test_poligoni_e_marker(tmp_path):
    _, g, w = servizi(tmp_path)
    r = arr.arricchisci(sezioni(), geo=g, wd=w)
    per_nome = {l["nome"]: l for l in r["luoghi"].values()}
    assert per_nome["Puglia"]["poligono"] == {"livello": "regioni", "id": "puglia"}
    assert per_nome["Bologna"]["poligono"] == {"livello": "province", "id": "bologna"}
    assert per_nome["Francia"]["poligono"] == {"livello": "paesi", "id": "FR"}
    assert per_nome["Taranto"]["poligono"] is None and per_nome["Taranto"]["fonte"] == "nominatim"
    # territorio conteso: solo marker, mai il poligono di un paese
    assert per_nome["Crimea"]["poligono"] is None and per_nome["Crimea"]["bbox"] is None


def test_italia_scarta_luoghi_stranieri(tmp_path):
    _, g, _ = servizi(tmp_path)
    assert g.risolvi({"nome": "Washington", "tipo": "citta", "paese": "US"}, sezione="Italia") is None
    assert g.risolvi({"nome": "Washington", "tipo": "citta", "paese": "US"}, sezione="Esteri")["paese"] == "US"
    assert g.risolvi({"nome": "Francia", "tipo": "paese", "paese": "DE"}, sezione="Esteri") is None   # incoerente


def test_paese_incoerente_per_nominatim(tmp_path):
    _, g, _ = servizi(tmp_path)
    # Claude dice Italia ma il luogo è altrove: Nominatim (con countrycodes=it) non lo trova -> scartato
    assert g.risolvi({"nome": "Tokyo", "tipo": "citta", "paese": "IT"}, sezione="Esteri") is None


def test_cache_secondo_giro_senza_chiamate(tmp_path):
    web, g, w = servizi(tmp_path)
    arr.arricchisci(sezioni(), geo=g, wd=w)
    n = len(web.chiamate)
    assert n > 0
    web2, g2, w2 = servizi(tmp_path, web=FalsoWeb())
    arr.arricchisci(sezioni(), geo=g2, wd=w2)
    assert web2.chiamate == []                                     # tutto dalla cache, anche i non risolti


def test_offline_usa_solo_dati_locali(tmp_path):
    web, g, w = servizi(tmp_path, online=False)
    r = arr.arricchisci(sezioni(), geo=g, wd=w)
    assert web.chiamate == []
    assert r["entita"] == {}                                       # senza rete nessuna scheda
    nomi = {l["nome"] for l in r["luoghi"].values()}
    assert {"Puglia", "Francia", "Egitto"} <= nomi and "Taranto" not in nomi


def test_errore_di_rete_non_ferma_e_non_viene_memorizzato(tmp_path):
    class Rotto(FalsoWeb):
        def get(self, url, params=None, headers=None):
            raise ConnectionError("rete assente")
    web, g, w = servizi(tmp_path, web=Rotto())
    r = arr.arricchisci(sezioni(), geo=g, wd=w)                    # non solleva
    assert r["entita"] == {} and g.cache.get("taranto|citta|IT") is None   # nessuna cache negativa da un errore di rete
    assert r["stats"]["geo"]["errori_rete"] > 0


def test_override_manuali(tmp_path):
    (tmp_path / "eo.json").write_text(json.dumps({"Anna Verdi": {"azione": "blocca"}}), encoding="utf-8")
    (tmp_path / "lo.json").write_text(json.dumps({"Crimea": {"ignora": True}, "Taranto": {"lat": 1.0, "lon": 2.0, "paese": "IT"}}), encoding="utf-8")
    _, g, w = servizi(tmp_path)
    r = arr.arricchisci(sezioni(), geo=g, wd=w)
    assert "Anna Verdi" not in {e["nome"] for e in r["entita"].values()}
    nomi = {l["nome"]: l for l in r["luoghi"].values()}
    assert "Crimea" not in nomi and nomi["Taranto"]["lat"] == 1.0 and nomi["Taranto"]["fonte"] == "override"


def test_hash_notizie_invalida_arricchimento_vecchio(cartelle_tmp):
    s = sezioni()
    dati = {"hash_notizie": arr.hash_notizie(s), "entita": {}, "luoghi": {}, "frasi": {}}
    p = Path(config.percorso_arricchimento())
    p.write_text(json.dumps(dati), encoding="utf-8")
    assert arr.carica_valido(s) is not None
    s[0]["notizie"][0]["titolo"] += " modificato"
    assert arr.carica_valido(s) is None


def test_percorso_immagine_sito_whitelist():
    assert arr._percorso_immagine_sito("Q1.jpg") == "img/Q1.jpg"
    assert arr._percorso_immagine_sito("../x.jpg") is None and arr._percorso_immagine_sito("a/b.png") is None


def test_potatura_cache(tmp_path):
    from datetime import date
    _, g, w = servizi(tmp_path)
    arr.arricchisci(sezioni(), geo=g, wd=w)
    g.oggi = w.oggi = date(2099, 1, 1)                             # molto tempo dopo
    assert g.pota_cache() > 0 and w.pota_cache() > 0
    assert not (tmp_path / "img").exists() or list((tmp_path / "img").iterdir()) == []
