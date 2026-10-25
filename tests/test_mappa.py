import random

import config
import mappa

P = lambda lat, lon, tipo="citta", **kw: dict({"lat": lat, "lon": lon, "tipo": tipo}, **kw)
LUOGHI = {"roma": P(41.9, 12.5), "milano": P(45.5, 9.2), "napoli": P(40.9, 14.3), "parigi": P(48.9, 2.4),
          "tokyo": P(35.7, 139.7), "egitto": P(26, 30, "paese", bbox=[22, 24.7, 31.6, 36.9], poligono={"livello": "paesi", "id": "EG"})}


def sez(sid, modalita, notizie, inizio=0.0):
    return {"id": sid, "modalita": modalita, "inizio": inizio, "fine": notizie[-1]["fine"], "notizie": notizie}


def notizia(nid, inizio, fine, eventi, tipo="notizia"):
    return {"id": nid, "tipo": tipo, "inizio": inizio, "fine": fine, "eventi": eventi}


def test_tempo_menzione_proporzionale():
    assert mappa.tempo_menzione("Vado a Roma subito.", "Roma", 10.0, 20.0) == round(10 + 10 * 7 / 19, 3)
    assert mappa.tempo_menzione("Nessuna.", "Roma", 10.0, 20.0) == 10.0


def test_fissa_accumula_e_parte_dal_vuoto():
    s = sez("italia", "fissa", [notizia("italia-1", 0, 30, [(5, "roma"), (12, "milano"), (13, "napoli")])])
    kfs, ha = mappa.calcola_keyframe([s], LUOGHI)
    assert kfs[0]["t"] == 0 and kfs[0]["evidenzia"] == [] and kfs[0]["vista"]["tipo"] == "italia"
    st = mappa.stato_a(kfs, 12.5)
    assert st["attivi"] == ["milano", "napoli"] and st["citati"] == ["roma"]
    assert ha["italia-1"] is True


def test_fusione_entro_due_secondi_una_sola_vista_bounds():
    s = sez("esteri", "zoom", [notizia("esteri-1", 0, 20, [(5.0, "roma"), (6.5, "napoli")])])
    kfs, _ = mappa.calcola_keyframe([s], LUOGHI)
    luogo_kf = [k for k in kfs if k["evidenzia"]]
    assert len(luogo_kf) == 1 and luogo_kf[0]["vista"]["tipo"] == "bounds"
    assert set(luogo_kf[0]["evidenzia"]) == {"roma", "napoli"}


def test_luoghi_lontani_movimenti_sequenziali_dentro_la_notizia():
    s = sez("esteri", "zoom", [notizia("esteri-1", 0, 12, [(5.0, "parigi"), (5.4, "tokyo")])])
    kfs, _ = mappa.calcola_keyframe([s], LUOGHI)
    mov = [k for k in kfs if k["evidenzia"]]
    assert [k["evidenzia"] for k in mov] == [["parigi"], ["tokyo"]]
    assert mov[1]["t"] - mov[0]["t"] >= config.MAPPA_FUSIONE_S / 2 - 1e-6
    assert all(k["t"] <= 12 + 1e-6 for k in mov)


def test_il_ritorno_al_mondo_non_cancella_il_luogo_successivo():
    s = sez("esteri", "zoom", [notizia("esteri-1", 0, 10, [(9.5, "parigi")]),
                               notizia("esteri-2", 10, 20, [(10.3, "tokyo")])])
    kfs, _ = mappa.calcola_keyframe([s], LUOGHI)
    assert mappa.stato_a(kfs, 10.5)["attivi"] == ["tokyo"]          # a 10,5 s si deve vedere Tokyo
    assert mappa.stato_a(kfs, 9.7)["attivi"] == ["parigi"]


def test_auto_mostra_la_mappa_solo_con_luoghi():
    s = sez("economia", "auto", [notizia("economia-s1", 0, 3, [], "speciale"), notizia("economia-1", 3, 9, []),
                                 notizia("economia-2", 9, 15, [(10, "milano")])])
    _, ha = mappa.calcola_keyframe([s], LUOGHI)
    assert ha == {"economia-s1": False, "economia-1": False, "economia-2": True}


def test_luoghi_sconosciuti_ignorati():
    s = sez("esteri", "zoom", [notizia("esteri-1", 0, 10, [(3, "inesistente")])])
    kfs, _ = mappa.calcola_keyframe([s], LUOGHI)
    assert all(not k["evidenzia"] for k in kfs)


def _scenario():
    return [sez("italia", "fissa", [notizia("italia-1", 0, 30, [(4, "roma"), (9, "milano"), (20, "napoli"), (21.5, "roma")])]),
            sez("esteri", "zoom", [notizia("esteri-1", 30, 50, [(33, "parigi"), (34, "tokyo"), (41, "egitto")]),
                                    notizia("esteri-2", 50, 70, [(52, "roma")])], inizio=30.0)]


def test_invarianti_dei_keyframe():
    kfs, _ = mappa.calcola_keyframe(_scenario(), LUOGHI)
    assert [k["t"] for k in kfs] == sorted(k["t"] for k in kfs)
    assert len({k["t"] for k in kfs}) == len(kfs)                  # mai due keyframe allo stesso istante
    for a, b in zip(kfs, kfs[1:]):
        assert any(a[c] != b[c] for c in ("sezione", "cumula", "vista", "evidenzia"))   # niente duplicati consecutivi


def test_stato_dipende_solo_dal_tempo_e_il_cumulo_e_corretto():
    kfs, _ = mappa.calcola_keyframe(_scenario(), LUOGHI)
    tempi = [random.Random(7).uniform(0, 70) for _ in range(1)] + [i * 0.37 for i in range(190)]
    random.Random(1).shuffle(tempi)                                  # seek in ordine casuale
    for t in tempi:
        st = mappa.stato_a(kfs, t)
        if st["indice"] < 0:
            continue
        k = kfs[st["indice"]]
        if k["cumula"]:
            # storico = keyframe consecutivi cumulativi della stessa sezione, fermandosi al primo che non cumula (reset)
            atteso, j = [], st["indice"] - 1
            while j >= 0 and kfs[j]["sezione"] == k["sezione"] and kfs[j]["cumula"]:
                atteso += [l for l in kfs[j]["evidenzia"] if l not in atteso]
                j -= 1
            assert st["citati"] == [l for l in atteso if l not in st["attivi"]]      # stesso ordine: dal più recente
        else:
            assert st["citati"] == []


def test_zoom_accumula_lo_storico_dentro_la_notizia_e_lo_azzera_a_fine_notizia():
    s = sez("esteri", "zoom", [notizia("esteri-1", 0, 20, [(3, "parigi"), (8, "tokyo"), (13, "roma")]),
                               notizia("esteri-2", 20, 40, [(25, "milano")])])
    kfs, _ = mappa.calcola_keyframe([s], LUOGHI)
    st = mappa.stato_a(kfs, 13.5)
    assert st["attivi"] == ["roma"] and st["citati"] == ["tokyo", "parigi"]      # dal più recente al più vecchio
    assert mappa.stato_a(kfs, 8.5)["citati"] == ["parigi"]
    dopo = mappa.stato_a(kfs, 25.5)                                              # nuova notizia: storico azzerato
    assert dopo["attivi"] == ["milano"] and dopo["citati"] == []


def test_un_luogo_citato_di_nuovo_torna_corrente_e_esce_dallo_storico():
    s = sez("italia", "fissa", [notizia("italia-1", 0, 30, [(3, "roma"), (9, "milano"), (15, "roma")])])
    kfs, _ = mappa.calcola_keyframe([s], LUOGHI)
    st = mappa.stato_a(kfs, 15.5)
    assert st["attivi"] == ["roma"] and st["citati"] == ["milano"]


def test_zoom_citta_non_troppo_alto():
    assert config.MAPPA_ZOOM_CITTA <= 5 and config.MAPPA_ZOOM_MAX <= 6 and mappa.vista_luogo(LUOGHI["parigi"])["zoom"] == config.MAPPA_ZOOM_CITTA
