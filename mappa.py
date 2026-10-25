"""
mappa.py — Fase 5: keyframe della mappa sincronizzata (funzioni pure).

Dalla timeline dell'episodio e dai luoghi geocodificati produce una lista di
keyframe {t, sezione, cumula, vista, evidenzia} che il front-end applica
quando il tempo di riproduzione li supera.

Viste:  {"tipo":"mondo"} · {"tipo":"italia"} ·
        {"tipo":"punto","lat","lon","zoom"} · {"tipo":"bounds","sw":[lat,lon],"ne":[lat,lon]}

Modalità per sezione (config.MAPPA_MODALITA):
  fissa  vista sull'Italia, luoghi evidenziati e accumulati per tutta la sezione
  zoom   zoom sul luogo; lo storico si accumula dentro la notizia e si azzera col
         "torna al mondo" di fine notizia
  auto   come zoom, ma la mappa si mostra solo nelle notizie con luoghi

Storico: "citati" è ordinato dal più recente al più vecchio; il front-end sbiadisce
i luoghi in base a questa posizione (bordo tratteggiato) e disegna il corrente pieno.

`stato_a()` rispecchia esattamente quanto fa mappa_logica.js: serve a testare
che dopo un seek lo stato dipenda solo dal tempo e non dalla storia.
"""

import config

VISTA_MONDO = {"tipo": "mondo"}
VISTA_ITALIA = {"tipo": "italia"}


def tempo_menzione(testo, menzione, inizio, fine):
    """Stima proporzionale: dove cade la menzione nella durata della frase."""
    pos = testo.find(menzione) if menzione else -1
    frazione = 0.0 if pos < 0 else pos / max(1, len(testo))
    return round(inizio + frazione * (fine - inizio), 3)


def _estremi(luogo):
    """(min_lat, min_lon, max_lat, max_lon) di un luogo: bbox se c'è, altrimenti il punto."""
    b = luogo.get("bbox")
    if b:
        return tuple(b)
    return (luogo["lat"], luogo["lon"], luogo["lat"], luogo["lon"])


def vista_luogo(luogo):
    if luogo.get("bbox") and luogo.get("poligono"):
        b = luogo["bbox"]
        return {"tipo": "bounds", "sw": [b[0], b[1]], "ne": [b[2], b[3]]}
    zoom = config.MAPPA_ZOOM_CITTA if luogo.get("tipo") == "citta" else config.MAPPA_ZOOM_LUOGO
    return {"tipo": "punto", "lat": luogo["lat"], "lon": luogo["lon"], "zoom": zoom}


def vista_gruppo(luoghi, span_max):
    """Una sola vista per più luoghi vicini; None se troppo distanti (→ sequenziale)."""
    if len(luoghi) == 1:
        return vista_luogo(luoghi[0])
    e = [_estremi(l) for l in luoghi]
    sw = [min(x[0] for x in e), min(x[1] for x in e)]
    ne = [max(x[2] for x in e), max(x[3] for x in e)]
    if max(ne[0] - sw[0], ne[1] - sw[1]) > span_max:
        return None
    return {"tipo": "bounds", "sw": [round(sw[0], 3), round(sw[1], 3)], "ne": [round(ne[0], 3), round(ne[1], 3)]}


def _raggruppa(eventi, fusione):
    """eventi: [(t, lid)] -> gruppi di eventi con gap < fusione tra consecutivi."""
    gruppi = []
    for t, lid in sorted(eventi):
        if gruppi and t - gruppi[-1][-1][0] < fusione:
            gruppi[-1].append((t, lid))
        else:
            gruppi.append([(t, lid)])
    return gruppi


def calcola_keyframe(sezioni, luoghi, fusione_s=None, span_max=None):
    """sezioni: [{"id","modalita","inizio","fine","notizie":[{"id","tipo","inizio","fine","eventi":[(t,lid)]}]}]
    luoghi: {lid: {lat, lon, tipo, bbox?, poligono?}}.
    Ritorna (keyframe_ordinati, ha_mappa) con ha_mappa = {id_notizia: bool}."""
    fusione_s = config.MAPPA_FUSIONE_S if fusione_s is None else fusione_s
    span_max = config.MAPPA_SPAN_MAX_GRADI if span_max is None else span_max
    kfs, ha_mappa = [], {}
    gap = fusione_s / 2          # distanza minima tra due movimenti consecutivi (il volo dura ~1,2 s)
    ultimo_reset = None          # keyframe "torna al mondo" della notizia precedente

    def kf(t, sez, cumula, vista, evidenzia):
        k = {"t": round(t, 3), "sezione": sez, "cumula": cumula, "vista": vista, "evidenzia": list(evidenzia)}
        kfs.append(k)
        return k

    def non_scavalcare(reset, t_prossimo):
        """Un 'torna al mondo' in ritardo non deve mai cancellare il luogo che segue."""
        if reset is not None and reset["t"] >= t_prossimo:
            reset["t"] = round(t_prossimo - 0.01, 3)

    for s in sezioni:
        modalita, sid = s["modalita"], s["id"]
        validi = lambda ev: [(t, l) for t, l in ev if l in luoghi]
        non_scavalcare(ultimo_reset, s["inizio"])

        if modalita == "fissa":
            kf(s["inizio"], sid, True, VISTA_ITALIA, [])
            for n in s["notizie"]:
                ha_mappa[n["id"]] = True
                for gruppo in _raggruppa(validi(n.get("eventi", [])), fusione_s):
                    kf(gruppo[0][0], sid, True, VISTA_ITALIA, dict.fromkeys(l for _, l in gruppo))
            ultimo_reset = None
            continue

        kf(s["inizio"], sid, False, VISTA_MONDO, [])
        for n in s["notizie"]:
            eventi = validi(n.get("eventi", []))
            ha_mappa[n["id"]] = True if modalita == "zoom" else bool(eventi)
            if not eventi:
                continue
            nuovi, ultimo_t = [], n["inizio"]
            for gruppo in _raggruppa(eventi, fusione_s):
                lids = list(dict.fromkeys(l for _, l in gruppo))
                vista = vista_gruppo([luoghi[l] for l in lids], span_max)
                if vista is not None:
                    nuovi.append((gruppo[0][0], vista, lids))
                    ultimo_t = gruppo[-1][0]
                else:                                   # troppo distanti: un movimento per luogo
                    t_prec = None
                    for t, l in gruppo:
                        t_eff = t if t_prec is None else max(t, t_prec + gap)
                        t_eff = min(t_eff, max(n["fine"], t))     # mai oltre la fine della notizia
                        nuovi.append((t_eff, vista_luogo(luoghi[l]), [l]))
                        t_prec = t_eff
                    ultimo_t = t_prec
            non_scavalcare(ultimo_reset, nuovi[0][0])
            for t, vista, lids in nuovi:
                # cumula=True: i luoghi già citati in QUESTA notizia restano come storico (sbiaditi);
                # il "torna al mondo" a fine notizia (cumula=False) azzera lo storico.
                kf(t, sid, True, vista, lids)
            # fine notizia: torna al mondo, ma lascia l'ultimo luogo visibile almeno 'gap' secondi
            ultimo_reset = kf(max(n["fine"], ultimo_t + gap), sid, False, VISTA_MONDO, [])

    # ordina; a parità di tempo vince l'ultimo; elimina i duplicati consecutivi
    kfs.sort(key=lambda k: k["t"])
    unici = []
    for k in kfs:
        if unici and unici[-1]["t"] == k["t"]:
            unici[-1] = k
        else:
            unici.append(k)
    puliti = []
    for k in unici:
        if puliti and all(puliti[-1][c] == k[c] for c in ("sezione", "cumula", "vista", "evidenzia")):
            continue
        puliti.append(k)
    return puliti, ha_mappa


def stato_a(keyframes, t):
    """Stato della mappa al tempo t: {"vista", "attivi", "citati", "indice"}.
    Dipende SOLO da (keyframes, t): così un seek avanti o indietro ricostruisce
    sempre lo stesso risultato che si avrebbe ascoltando di seguito."""
    i = -1
    for j, k in enumerate(keyframes):
        if k["t"] <= t:
            i = j
        else:
            break
    if i < 0:
        return {"vista": VISTA_MONDO, "attivi": [], "citati": [], "indice": -1}
    k = keyframes[i]
    attivi = list(k["evidenzia"])
    citati = []
    if k["cumula"]:
        j = i - 1
        while j >= 0 and keyframes[j]["sezione"] == k["sezione"] and keyframes[j]["cumula"]:
            for l in keyframes[j]["evidenzia"]:
                if l not in attivi and l not in citati:
                    citati.append(l)
            j -= 1
    return {"vista": k["vista"], "attivi": attivi, "citati": citati, "indice": i}
