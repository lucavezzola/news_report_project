import pytest
import synthesize as s

ART = {"a1": {"id": "a1"}, "a2": {"id": "a2"}}


def notizia(**kw):
    base = {"titolo": "T", "fonti": ["a1"], "frasi": [{"testo": "Roma è la capitale."}]}
    base.update(kw)
    return {"notizie": [base]}


def test_caso_valido_e_metriche():
    d = notizia(frasi=[{"testo": "Mario Rossi è a Roma.",
                        "entita": [{"nome": "Mario Rossi", "tipo": "persona", "menzione": "Mario Rossi"}],
                        "luoghi": [{"nome": "Roma", "tipo": "citta", "paese": "it", "menzione": "Roma"}]}])
    nz, m = s.valida_notizie(d, ART)
    assert nz[0]["frasi"][0]["luoghi"][0]["paese"] == "IT"
    assert s.percentuale_menzioni(m) == 100


def test_menzione_non_nella_frase_scartata():
    d = notizia(frasi=[{"testo": "Si parla di Roma.",
                        "luoghi": [{"nome": "Parigi", "tipo": "citta", "menzione": "Parigi"}]}])
    nz, m = s.valida_notizie(d, ART)
    assert nz[0]["frasi"][0]["luoghi"] == [] and s.percentuale_menzioni(m) == 0


def test_menzione_recuperata_dal_nome():
    d = notizia(frasi=[{"testo": "Si parla di Roma.",
                        "luoghi": [{"nome": "Roma", "tipo": "citta", "menzione": "roma capitale"}]}])
    nz, _ = s.valida_notizie(d, ART)
    assert nz[0]["frasi"][0]["luoghi"][0]["menzione"] == "Roma"


def test_id_fonti_inesistenti_scartati_e_notizia_senza_fonti_eliminata():
    nz, m = s.valida_notizie(notizia(fonti=["a1", "zzz", "a1"]), ART)
    assert nz[0]["fonti"] == ["a1"] and m["id_fonti_scartati"] == 1
    nz, m = s.valida_notizie(notizia(fonti=["zzz"]), ART)
    assert nz == [] and m["notizie_scartate"] == 1


def test_frasi_vuote_scartate_lunghe_spezzate_non_scartate():
    lunga = "Parola, " * 60 + "fine."
    nz, m = s.valida_notizie(notizia(frasi=[{"testo": "  "}, {"testo": lunga}]), ART, max_chars=200)
    assert m["frasi_scartate"] == 1 and m["frasi_spezzate"] == 1
    assert all(len(f["testo"]) <= 200 for f in nz[0]["frasi"])
    assert " ".join(f["testo"] for f in nz[0]["frasi"]).replace(" ", "") == lunga.replace(" ", "")


def test_metadati_seguono_il_pezzo_giusto():
    testo = ("Prima parte molto lunga " * 6).strip() + ". " + ("Seconda parte con Roma " * 5).strip() + "."
    d = notizia(frasi=[{"testo": testo, "luoghi": [{"nome": "Roma", "tipo": "citta", "menzione": "Roma"}]}])
    nz, _ = s.valida_notizie(d, ART, max_chars=120)
    con = [f for f in nz[0]["frasi"] if f["luoghi"]]
    assert con and all("Roma" in f["testo"] for f in con)


def test_tipi_invalidi_normalizzati_e_limiti():
    d = notizia(frasi=[{"testo": "Roma e Fiat.",
                        "entita": [{"nome": "Fiat", "tipo": "boh", "menzione": "Fiat"}],
                        "luoghi": [{"nome": "Roma", "tipo": "xx", "menzione": "Roma"}]}])
    nz, _ = s.valida_notizie(d, ART)
    f = nz[0]["frasi"][0]
    assert f["entita"][0]["tipo"] == "altro" and f["luoghi"][0]["tipo"] == "luogo"
    many = {"notizie": [notizia()["notizie"][0] for _ in range(10)]}
    assert len(s.valida_notizie(many, ART, max_notizie=3)[0]) == 3


def test_schema_errato():
    with pytest.raises(ValueError):
        s.valida_notizie({"altro": 1}, ART)
    with pytest.raises(ValueError):
        s.valida_notizie([], ART)


def test_notizie_serializzate_come_stringa():
    import json
    nz, _ = s.valida_notizie({"notizie": json.dumps(notizia()["notizie"])}, ART)
    assert len(nz) == 1


def test_testi_speciali_deterministici():
    from datetime import datetime, timezone
    t = datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc)
    a = s.testi_speciali(["Italia", "Esteri"], t)
    assert a == s.testi_speciali(["Italia", "Esteri"], t)
    assert "21 ottobre 2026" in a["apertura"]
    assert "Italia" in a["transizioni"]["Italia"] or "Italia" in a["transizioni"]["Italia"].title()
    assert a["transizioni"]["Esteri"].startswith(("Passiamo", "Spostiamoci"))
