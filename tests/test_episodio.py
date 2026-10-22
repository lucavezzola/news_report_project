import json
import numpy as np
import episodio as ep
import config

SR = ep.SAMPLE_RATE


def sezioni():
    return [
        {"nome": "Italia", "notizie": [
            {"titolo": "Uno", "fonti": ["a1", "a2"], "frasi": [{"testo": "Frase uno."}, {"testo": "Frase due."}]},
            {"titolo": "Due", "fonti": ["a3"], "frasi": [{"testo": "Frase tre."}]}]},
        {"nome": "Esteri", "notizie": [{"titolo": "Tre", "fonti": ["b1"], "frasi": [{"testo": "Frase quattro."}]}]},
    ]


SPECIALI = {"apertura": "Buongiorno.", "transizioni": {"Italia": "Iniziamo dall'Italia.", "Esteri": "Passiamo agli esteri."},
            "chiusura": "Fine."}
ART = {"a1": {"fonte": "ANSA - Politica", "titolo": "t1", "link": "https://x.it/1"},
       "a2": {"fonte": "ANSA - Cronaca", "titolo": "t2", "link": "https://x.it/2"},
       "a3": {"fonte": "Repubblica", "titolo": "t3", "link": "javascript:alert(1)"},
       "b1": {"fonte": "BBC News World", "titolo": "t4", "link": "http://x.it/4"}}


def parlato():
    return ep.costruisci_parlato(sezioni(), SPECIALI, {"Italia": "v1", "Esteri": "v2"}, dizionario=[])


def test_struttura_unita_e_pause():
    p = parlato()
    tipi = [(u["tipo"], u.get("sottotipo")) for u in p[0]["unita"]]
    assert tipi[:2] == [("speciale", "apertura"), ("speciale", "transizione")]
    assert p[1]["unita"][-1]["sottotipo"] == "chiusura"
    # una frase scritta = una unità
    assert sum(u["tipo"] == "frase" for s in p for u in s["unita"]) == 4
    # pausa: breve tra frasi, più lunga tra notizie, più lunga tra sezioni
    f = [u for u in p[0]["unita"] if u["tipo"] == "frase"]
    assert f[0]["pausa_dopo"] < f[1]["pausa_dopo"] < f[2]["pausa_dopo"]
    assert f[0]["voce"] == "v1" and p[1]["unita"][0]["voce"] == "v2"


def test_voce_speciale_configurabile(monkeypatch):
    monkeypatch.setattr(config, "XTTS_VOCE_SPECIALE", "Speciale")
    p = parlato()
    assert p[0]["unita"][0]["voce"] == "Speciale"


def test_assemblaggio_e_offset_intro():
    t1 = (np.zeros(SR * 3, np.float32), [(0.0, 2.0), (2.5, 3.0)])
    t2 = (np.zeros(SR * 2, np.float32), [(0.0, 1.5)])
    voce, tempi, offs = ep.assembla([t1, t2])
    assert len(voce) == SR * 5 and offs == [0.0, 3.0]
    assert tempi[1][0] == (3.0, 4.5)
    spostati = ep.sposta_tempi(tempi, 2.0)
    assert spostati[0][0] == (2.0, 4.0) and spostati[1][0] == (5.0, 6.5)


def test_manifest_fonti_fonte_singola_e_url():
    p = parlato()
    tempi = [[(i * 2.0, i * 2.0 + 1.5) for i in range(len(s["unita"]))] for s in p]
    m = ep.costruisci_manifest("2099-01-01", p, sezioni(), tempi, 20.0, ART)
    n1 = next(n for n in m["sezioni"][0]["notizie"] if n.get("titolo") == "Uno")
    n2 = next(n for n in m["sezioni"][0]["notizie"] if n.get("titolo") == "Due")
    assert n1["fonte_singola"] is True           # ANSA Politica + ANSA Cronaca = stessa testata
    assert n2["fonte_singola"] is True and n2["fonti"][0]["url"] is None   # javascript: scartato
    sez2 = sezioni(); sez2[0]["notizie"][0]["fonti"] = ["a1", "b1"]
    m2 = ep.costruisci_manifest("2099-01-01", p, sez2, tempi, 20.0, ART)
    assert next(n for n in m2["sezioni"][0]["notizie"] if n.get("titolo") == "Uno")["fonte_singola"] is False
    assert n1["fonti"][0]["url"] == "https://x.it/1"
    assert m["sezioni"][0]["inizio"] == 0.0 and m["durata"] == 20.0
    # inizio/fine della notizia = prima/ultima frase
    assert n1["inizio"] == n1["frasi"][0]["inizio"] and n1["fine"] == n1["frasi"][-1]["fine"]
    # nessun campo che manca di mappa/entità obbligatorio
    assert "mappa" not in m


def test_url_http():
    assert ep.url_http("https://a.it") and not ep.url_http("javascript:x") and not ep.url_http("ftp://a") and not ep.url_http(None)


def test_cache_audio_per_sezione(cartelle_tmp, monkeypatch):
    monkeypatch.setattr(config, "AUDIO_FINTO", True)
    s = parlato()[0]
    a1, t1 = ep.traccia_sezione(s, data="2099-01-01")
    import tts
    chiamate = []
    monkeypatch.setattr(tts, "genera_traccia", lambda *a, **k: chiamate.append(1) or (a1, t1))
    ep.traccia_sezione(s, data="2099-01-01")
    assert chiamate == []                                  # riuso dalla cache
    s["unita"][2]["parlato"] += " modificata"
    ep.traccia_sezione(s, data="2099-01-01")
    assert chiamate == [1]                                 # testo cambiato: rigenera


def test_voci_stabili_tra_le_esecuzioni(cartelle_tmp, monkeypatch):
    monkeypatch.setattr(config, "voce_per_sezione", lambda n: f"voce-{n}-{np.random.randint(1e9)}")
    v1 = ep.scegli_voci(["Italia"], "2099-01-01")
    v2 = ep.scegli_voci(["Italia", "Esteri"], "2099-01-01")
    assert v1["Italia"] == v2["Italia"] and "Esteri" in v2
