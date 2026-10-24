"""
arricchimento.py — Fasi 5-6: entità, luoghi, immagini e crediti.

Legge le notizie (notizie_<sezione>.json), risolve entità (Wikidata) e luoghi
(geo.py) e scrive output/AAAA-MM-GG/arricchimento.json, che episodio.py unisce
ai tempi per costruire manifest e keyframe della mappa.

Degradazione elegante: ogni singola risoluzione è protetta; se la rete manca o
CONTATTO_EMAIL non è impostata si usano solo cache, override e poligoni locali.
Se tutto fallisce l'episodio esce comunque, senza mappa e senza immagini.

Politica: una scheda entità compare SOLO se Wikidata conferma l'entità e supera
la soglia di notorietà. Una persona non risolta non viene mai mostrata, nemmeno
come semplice nome (potrebbe essere un privato cittadino).
"""

import hashlib
import json
import re
from pathlib import Path

import config
import geo as modulo_geo
import synthesize
import wikidata as modulo_wikidata
from logging_config import configura_logger
from scarica_geo import normalizza

log = configura_logger("arricchimento", "arricchimento.log")


def hash_notizie(sezioni):
    """Impronta del contenuto: se le notizie cambiano, l'arricchimento vecchio non vale più."""
    base = json.dumps([(s["nome"], s["notizie"]) for s in sezioni], sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def chiave_frase(slug, ni, fi):
    return f"{slug}-{ni}-{fi}"


def raccogli(sezioni):
    """Deduplica entità e luoghi del giorno. Ritorna (entita, luoghi, frasi):
    entita {eid: {nome,tipo,descrizione}}, luoghi {lid: {nome,tipo,paese,sezioni}},
    frasi {chiave: {"entita":[eid], "luoghi":[[lid, menzione]]}}."""
    entita, luoghi, frasi = {}, {}, {}
    idx_e, idx_l = {}, {}
    for s in sezioni:
        slug = config.slug_sezione(s["nome"])
        for ni, n in enumerate(s["notizie"]):
            for fi, f in enumerate(n["frasi"]):
                rif = {"entita": [], "luoghi": []}
                for e in f.get("entita", []):
                    k = (normalizza(e["nome"]), e.get("tipo", "altro"))
                    if k not in idx_e:
                        idx_e[k] = f"e{len(idx_e) + 1}"
                        entita[idx_e[k]] = {"nome": e["nome"], "tipo": k[1], "descrizione": e.get("descrizione", "")}
                    if idx_e[k] not in rif["entita"]:
                        rif["entita"].append(idx_e[k])
                for l in f.get("luoghi", []):
                    k = (normalizza(l["nome"]), l.get("tipo", "luogo"), l.get("paese", ""), s["nome"] == "Italia")
                    if k not in idx_l:
                        idx_l[k] = f"l{len(idx_l) + 1}"
                        luoghi[idx_l[k]] = {"nome": l["nome"], "tipo": k[1], "paese": k[2], "sezione": s["nome"]}
                    rif["luoghi"].append([idx_l[k], l["menzione"]])
                if rif["entita"] or rif["luoghi"]:
                    frasi[chiave_frase(slug, ni, fi)] = rif
    return entita, luoghi, frasi


def _percorso_immagine_sito(nome_file):
    return f"img/{nome_file}" if nome_file and re.fullmatch(r"[A-Za-z0-9_.-]+", nome_file) else None


def arricchisci(sezioni, geo=None, wd=None):
    """Ritorna il dict da salvare in arricchimento.json."""
    geo = geo or modulo_geo.Geo()
    wd = wd or modulo_wikidata.Wikidata()
    entita_grezze, luoghi_grezzi, frasi = raccogli(sezioni)

    entita_ok, scartate_e = {}, set()
    for eid, e in entita_grezze.items():
        try:
            scheda = wd.risolvi(e)
        except Exception as ex:                      # una singola entità non deve mai fermare tutto
            log.warning(f"Errore sull'entità {e['nome']!r}: {ex}")
            scheda = None
        if scheda is None:
            scartate_e.add(eid)
            continue
        entita_ok[eid] = {"nome": e["nome"], "tipo": e["tipo"], "descrizione": e["descrizione"] or scheda["descrizione_wd"],
                          "qid": scheda["qid"], "immagine": _percorso_immagine_sito(scheda["immagine"]),
                          "crediti": scheda["crediti"] if scheda["immagine"] else None, "colore": scheda["colore"]}

    luoghi_ok, scartati_l = {}, set()
    for lid, l in luoghi_grezzi.items():
        try:
            r = geo.risolvi(l, sezione=l["sezione"])
        except Exception as ex:
            log.warning(f"Errore sul luogo {l['nome']!r}: {ex}")
            r = None
        if r is None:
            scartati_l.add(lid)
        else:
            luoghi_ok[lid] = r

    frasi_ok = {}
    for k, rif in frasi.items():
        e = [x for x in rif["entita"] if x in entita_ok]
        l = [x for x in rif["luoghi"] if x[0] in luoghi_ok]
        if e or l:
            frasi_ok[k] = {"entita": e, "luoghi": l}

    geo.salva_cache()
    wd.salva_cache()
    stats = {
        "entita_totali": len(entita_grezze), "entita_risolte": len(entita_ok),
        "entita_con_immagine": sum(1 for e in entita_ok.values() if e["immagine"]),
        "luoghi_totali": len(luoghi_grezzi), "luoghi_geocodificati": len(luoghi_ok),
        "geo": dict(geo.stats), "wikidata": dict(wd.stats),
    }
    log.info(f"Arricchimento: entità {stats['entita_risolte']}/{stats['entita_totali']} "
             f"({stats['entita_con_immagine']} con immagine); luoghi {stats['luoghi_geocodificati']}/{stats['luoghi_totali']}; "
             f"geo {stats['geo']}; wikidata {stats['wikidata']}")
    return {"versione": 1, "hash_notizie": hash_notizie(sezioni), "entita": entita_ok, "luoghi": luoghi_ok,
            "frasi": frasi_ok, "stats": stats}


def arricchisci_giorno(data=None, online=None):
    sezioni = synthesize.carica_sezioni(data)
    if not sezioni:
        raise RuntimeError("Nessuna sezione con notizie: esegui prima la Fase 1.")
    geo = modulo_geo.Geo(online=online)
    wd = modulo_wikidata.Wikidata(online=online)
    if not geo.online:
        log.warning("CONTATTO_EMAIL non impostata (o --offline): salto Nominatim e Wikidata, uso solo cache, override e poligoni locali.")
    risultato = arricchisci(sezioni, geo=geo, wd=wd)
    geo.pota_cache(); wd.pota_cache()
    geo.salva_cache(); wd.salva_cache()
    Path(config.percorso_arricchimento(data)).write_text(json.dumps(risultato, ensure_ascii=False, indent=2), encoding="utf-8")
    return risultato


def carica_valido(sezioni, data=None):
    """Legge arricchimento.json se esiste ed è coerente con le notizie correnti, altrimenti None."""
    p = Path(config.percorso_arricchimento(data))
    if not p.exists():
        return None
    try:
        dati = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("arricchimento.json illeggibile: lo ignoro.")
        return None
    if dati.get("hash_notizie") != hash_notizie(sezioni):
        log.warning("arricchimento.json non corrisponde alle notizie attuali (le notizie sono cambiate): lo ignoro. "
                    "Rilancia da --da-fase 2.")
        return None
    return dati


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Entità, luoghi e immagini per il giorno indicato.")
    ap.add_argument("--data")
    ap.add_argument("--offline", action="store_true", help="niente rete: solo cache, override e poligoni locali")
    a = ap.parse_args()
    config.imposta_data(a.data)
    r = arricchisci_giorno(online=False if a.offline else None)
    print(json.dumps(r["stats"], ensure_ascii=False, indent=2))
