"""
episodio.py — Fasi 2 e 3: dal testo delle notizie all'episodio (MP3 + manifest).

Due passi, ciascuno rilanciabile da solo (main.py --da-fase N):

  prepara_parlato_giorno()  (Fase 2)  notizie_*.json -> parlato.json
      saluto/transizioni/commiato dai template, fonetica su ogni frase,
      pause, voce per sezione (scelta una volta e salvata in voci.json).

  costruisci_episodio()     (Fase 3)  parlato.json -> episodio.mp3 + manifest.json
      TTS per frase (con cache per sezione: voce_<slug>.wav/.json), tempi,
      musica UNA volta sull'episodio, MP3 mono ~64 kbps, manifest (3.2 del piano).

Le funzioni che calcolano tempi e manifest sono pure (testabili senza GPU).
"""

import hashlib
import json
import random
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import soundfile as sf

import config
import fonetica
import mappa
import musica
import synthesize
from logging_config import configura_logger

log = configura_logger("episodio", "episodio.log")

SAMPLE_RATE = 24000  # come XTTS-v2 (tts.SAMPLE_RATE); duplicato per non importare torch qui


# ---------------------------------------------------------------------------
# Utilità
# ---------------------------------------------------------------------------
def testata(fonte):
    """'ANSA - Politica' e 'ANSA - Cronaca' sono la stessa testata."""
    return (fonte or "").split(" - ")[0].strip()


def url_http(url):
    """Solo link http(s) provenienti dagli articoli reali; altro -> None."""
    try:
        p = urlparse((url or "").strip())
    except ValueError:
        return None
    return url.strip() if p.scheme in ("http", "https") and p.netloc else None


def scegli_voci(nomi_sezioni, data=None):
    """Una voce per sezione, scelta una volta e salvata in voci.json: così
    rilanciare le fasi non cambia le voci (e la cache audio resta valida)."""
    percorso = Path(config.percorso_voci_giorno(data))
    voci = json.loads(percorso.read_text(encoding="utf-8")) if percorso.exists() else {}
    cambiato = False
    for nome in nomi_sezioni:
        if nome not in voci:
            voci[nome] = config.voce_per_sezione(nome)   # None = voice cloning
            cambiato = True
    if cambiato:
        percorso.write_text(json.dumps(voci, ensure_ascii=False, indent=2), encoding="utf-8")
    return voci


# ---------------------------------------------------------------------------
# Fase 2 — parlato
# ---------------------------------------------------------------------------
def costruisci_parlato(sezioni, speciali, voci, dizionario=None, candidati=None):
    """Funzione pura. sezioni: [{"nome","notizie"}]. Ritorna la lista di
    sezioni con le 'unita' da sintetizzare, nell'ordine di lettura.

    Ogni unità: {"tipo": "speciale"|"frase", "sottotipo"?, "notizia"?, "frase"?,
    "testo" (scritto, per i sottotitoli), "parlato" (per XTTS), "voce", "pausa_dopo"}.
    Invariante: una frase scritta = una unità = una frase parlata."""
    p_frase = config.PAUSA_FRASE_MS / 1000
    p_notizia = config.PAUSA_NOTIZIA_MS / 1000
    p_sezione = config.PAUSA_SEZIONE_MS / 1000

    def norm(t):
        return fonetica.normalizza_per_tts(t, dizionario=dizionario, candidati=candidati)

    risultato = []
    for i, s in enumerate(sezioni):
        nome = s["nome"]
        voce_sezione = voci.get(nome)
        voce_speciale = config.XTTS_VOCE_SPECIALE or voce_sezione
        e_prima, e_ultima = i == 0, i == len(sezioni) - 1
        unita = []

        def speciale(sottotipo, testo, pausa):
            unita.append({"tipo": "speciale", "sottotipo": sottotipo, "testo": testo,
                          "parlato": norm(testo), "voce": voce_speciale, "pausa_dopo": pausa})

        if e_prima:
            speciale("apertura", speciali["apertura"], p_notizia)
        speciale("transizione", speciali["transizioni"][nome], p_notizia)

        n_notizie = len(s["notizie"])
        for ni, notizia in enumerate(s["notizie"]):
            n_frasi = len(notizia["frasi"])
            for fi, frase in enumerate(notizia["frasi"]):
                if fi < n_frasi - 1:
                    pausa = p_frase
                elif ni < n_notizie - 1:
                    pausa = p_notizia
                else:
                    pausa = p_notizia if e_ultima else p_sezione
                unita.append({"tipo": "frase", "notizia": ni, "frase": fi, "testo": frase["testo"],
                              "parlato": norm(frase["testo"]), "voce": voce_sezione, "pausa_dopo": pausa})
        if e_ultima:
            speciale("chiusura", speciali["chiusura"], p_notizia)

        risultato.append({"nome": nome, "slug": config.slug_sezione(nome), "voce": voce_sezione, "unita": unita})
    return risultato


def prepara_parlato_giorno(data=None):
    """Fase 2: legge notizie_*.json + meta.json e scrive parlato.json."""
    sezioni = synthesize.carica_sezioni(data)
    if not sezioni:
        raise RuntimeError("Nessuna sezione con notizie: esegui prima la Fase 1.")
    meta = synthesize.carica_meta(data)
    from datetime import datetime
    if meta:
        ora_fine = datetime.fromisoformat(meta["ora_fine"])
        giorni = meta["giorni"]
        ora_inizio = datetime.fromisoformat(meta["ora_inizio"]) if meta.get("ora_inizio") else None
    else:
        log.warning("meta.json mancante: uso la data odierna e 1 giorno.")
        ora_fine, giorni, ora_inizio = datetime.now().astimezone(), 1, None

    nomi = [s["nome"] for s in sezioni]
    speciali = synthesize.testi_speciali(nomi, ora_fine, giorni=giorni, ora_inizio=ora_inizio,
                                         seme=data or config.data_corrente())
    voci = scegli_voci(nomi, data)
    candidati = fonetica.Counter()
    dizionario = fonetica.carica_dizionario()
    parlato = costruisci_parlato(sezioni, speciali, voci, dizionario=dizionario, candidati=candidati)
    fonetica.salva_candidati(candidati)

    out = {"data": data or config.data_corrente(), "sezioni": parlato}
    Path(config.percorso_parlato(data)).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    n = sum(len(s["unita"]) for s in parlato)
    log.info(f"Parlato pronto: {len(parlato)} sezioni, {n} frasi; {len(candidati)} parole candidate per il dizionario.")
    return out


# ---------------------------------------------------------------------------
# Fase 3 — audio
# ---------------------------------------------------------------------------
def _hash_sezione(sezione):
    base = {
        "unita": [(u["parlato"], round(u["pausa_dopo"], 3), u.get("voce")) for u in sezione["unita"]],
        "voce": sezione["voce"],
        "velocita": config.XTTS_VELOCITA,
        "finto": bool(config.AUDIO_FINTO),
        "modello": config.XTTS_MODEL_NAME,
    }
    return hashlib.sha1(json.dumps(base, sort_keys=True).encode("utf-8")).hexdigest()


def traccia_sezione(sezione, data=None, rigenera=False):
    """Ritorna (audio, tempi) della sola voce di una sezione. Riusa
    voce_<slug>.wav se il contenuto (testi, voce, velocità) non è cambiato."""
    nome = sezione["nome"]
    wav = Path(config.percorso_voce_wav_sezione(nome, data))
    meta_p = Path(config.percorso_voce_meta_sezione(nome, data))
    h = _hash_sezione(sezione)

    if not rigenera and wav.exists() and meta_p.exists():
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        if meta.get("hash") == h:
            audio, sr = sf.read(str(wav), dtype="float32")
            if sr == SAMPLE_RATE:
                log.info(f"[{nome}] audio in cache, riuso {wav.name}")
                return audio, [tuple(t) for t in meta["tempi"]]

    import tts  # import tardivo: carica torch/XTTS solo se serve davvero
    log.info(f"[{nome}] sintesi di {len(sezione['unita'])} frasi...")
    unita_tts = [{"testo": u["parlato"], "pausa_dopo": u["pausa_dopo"], "voce": u.get("voce")} for u in sezione["unita"]]
    audio, tempi = tts.genera_traccia(unita_tts, voce_default=sezione["voce"])
    sf.write(str(wav), audio, SAMPLE_RATE)
    meta_p.write_text(json.dumps({"hash": h, "tempi": tempi, "durata": len(audio) / SAMPLE_RATE}), encoding="utf-8")
    return audio, tempi


def assembla(tracce):
    """Funzione pura. tracce: lista di (audio, tempi) per sezione, nell'ordine.
    Ritorna (voce_totale, tempi_globali, offset_sezioni): i tempi sono quelli
    della sola voce (senza intro), uno per sezione e per unità."""
    pezzi, tempi_globali, offsets, cursore = [], [], [], 0
    for audio, tempi in tracce:
        offset = cursore / SAMPLE_RATE
        offsets.append(offset)
        tempi_globali.append([(round(offset + i, 3), round(offset + f, 3)) for i, f in tempi])
        pezzi.append(audio)
        cursore += len(audio)
    voce = np.concatenate(pezzi).astype(np.float32) if pezzi else np.zeros(0, dtype=np.float32)
    return voce, tempi_globali, offsets


def sposta_tempi(tempi_globali, offset):
    """Sposta tutti i tempi della durata dell'intro."""
    return [[(round(i + offset, 3), round(f + offset, 3)) for i, f in sez] for sez in tempi_globali]


# ---------------------------------------------------------------------------
# Manifest (modello dati 3.2 del piano)
# ---------------------------------------------------------------------------
def costruisci_manifest(data, parlato, sezioni, tempi, durata, articoli_per_id, audio="episodio.mp3", arricchimento=None):
    """Funzione pura. parlato: lista di sezioni con 'unita'; sezioni: notizie
    originali (stesso ordine); tempi[s][u] = (inizio, fine) con offset intro
    già applicato. 'arricchimento' (opzionale, vedi arricchimento.py) aggiunge
    entità, luoghi e keyframe della mappa; senza, il manifest è quello base."""
    arr = arricchimento or {}
    frasi_arr = arr.get("frasi", {})
    manifest_sezioni, sezioni_mappa = [], []
    entita_usate, luoghi_usati = set(), set()

    for si, (sez_p, sez_n) in enumerate(zip(parlato, sezioni)):
        slug = sez_p["slug"]
        elementi, correnti, eventi = [], {}, {}
        n_speciali = 0

        for ui, u in enumerate(sez_p["unita"]):
            inizio, fine = tempi[si][ui]
            fr = {"testo": u["testo"], "inizio": inizio, "fine": fine}
            if u["tipo"] == "speciale":
                n_speciali += 1
                el = {"id": f"{slug}-s{n_speciali}", "tipo": "speciale", "sottotipo": u["sottotipo"], "frasi": [fr]}
                elementi.append(el)
                continue
            ni = u["notizia"]
            if ni not in correnti:
                n = sez_n["notizie"][ni]
                fonti, testate = [], set()
                for id_fonte in n["fonti"]:
                    a = articoli_per_id.get(id_fonte)
                    if not a:
                        continue
                    testate.add(testata(a["fonte"]))
                    fonti.append({"titolo": a["titolo"], "testata": testata(a["fonte"]), "url": url_http(a.get("link"))})
                correnti[ni] = {"id": f"{slug}-{ni + 1}", "tipo": "notizia", "titolo": n["titolo"],
                                "fonte_singola": len(testate) < 2, "fonti": fonti, "frasi": []}
                elementi.append(correnti[ni])
                eventi[ni] = []
            ref = frasi_arr.get(f"{slug}-{ni}-{u['frase']}")
            if ref:
                if ref["entita"]:
                    fr["entita"] = list(ref["entita"])
                    entita_usate.update(ref["entita"])
                if ref["luoghi"]:
                    fr["luoghi"] = [lid for lid, _ in ref["luoghi"]]
                    luoghi_usati.update(fr["luoghi"])
                    for lid, menzione in ref["luoghi"]:
                        eventi[ni].append((mappa.tempo_menzione(u["testo"], menzione, inizio, fine), lid))
            correnti[ni]["frasi"].append(fr)

        for el in elementi:
            el["inizio"], el["fine"] = el["frasi"][0]["inizio"], el["frasi"][-1]["fine"]
        manifest_sezioni.append({"id": slug, "nome": sez_p["nome"], "inizio": elementi[0]["inizio"],
                                 "fine": elementi[-1]["fine"], "notizie": elementi})
        sezioni_mappa.append({
            "id": slug, "modalita": config.MAPPA_MODALITA.get(sez_p["nome"], "auto"),
            "inizio": elementi[0]["inizio"], "fine": elementi[-1]["fine"],
            "notizie": [{"id": el["id"], "tipo": el["tipo"], "inizio": el["inizio"], "fine": el["fine"],
                         "eventi": eventi.get(int(el["id"].rsplit("-", 1)[1]) - 1, []) if el["tipo"] == "notizia" else []}
                        for el in elementi]})

    manifest = {"data": data, "durata": round(durata, 2), "audio": audio, "sezioni": manifest_sezioni}

    luoghi_tab = {lid: l for lid, l in arr.get("luoghi", {}).items() if lid in luoghi_usati}
    keyframe, ha_mappa = mappa.calcola_keyframe(sezioni_mappa, luoghi_tab) if luoghi_tab else ([], {})
    if keyframe:
        manifest["luoghi"] = {lid: {k: v for k, v in l.items() if k != "fonte"} for lid, l in luoghi_tab.items()}
        manifest["mappa"] = keyframe
        for sez_m, sez_s in zip(manifest_sezioni, sezioni_mappa):
            sez_m["mappa"] = sez_s["modalita"]
            for el in sez_m["notizie"]:
                el["ha_mappa"] = ha_mappa.get(el["id"], sez_s["modalita"] != "auto")
    if entita_usate:
        manifest["entita"] = {eid: arr["entita"][eid] for eid in sorted(entita_usate, key=lambda x: int(x[1:]))}
    return manifest


# ---------------------------------------------------------------------------
# Export e controlli
# ---------------------------------------------------------------------------
def esporta_mp3(wav, mp3):
    cmd = ["ffmpeg", "-y", "-i", str(wav), "-ac", "1", "-c:a", "libmp3lame", "-b:a", config.MP3_BITRATE, str(mp3)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg ha fallito nell'export MP3: {r.stderr[-500:]}")


def durata_file(percorso):
    """Durata in secondi via ffprobe, o None se non disponibile."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", str(percorso)], capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def costruisci_episodio(data=None, rigenera=False):
    """Fase 3: parlato.json -> episodio.mp3 + manifest.json. Ritorna il manifest."""
    p_parlato = Path(config.percorso_parlato(data))
    if not p_parlato.exists():
        raise RuntimeError("parlato.json mancante: esegui prima la Fase 2.")
    parlato = json.loads(p_parlato.read_text(encoding="utf-8"))["sezioni"]
    sezioni = {s["nome"]: s for s in synthesize.carica_sezioni(data)}
    sezioni = [sezioni[s["nome"]] for s in parlato]          # stesso ordine del parlato
    articoli = json.loads(Path(config.percorso_articoli_grezzi(data)).read_text(encoding="utf-8"))
    articoli_per_id = {a["id"]: a for a in articoli if "id" in a}

    tracce = [traccia_sezione(s, data=data, rigenera=rigenera) for s in parlato]
    voce, tempi, _ = assembla(tracce)
    audio, offset_intro = musica.applica_musica_episodio(voce, SAMPLE_RATE)
    tempi = sposta_tempi(tempi, offset_intro)
    durata = len(audio) / SAMPLE_RATE

    wav, mp3 = config.percorso_episodio_wav(data), config.percorso_episodio_mp3(data)
    sf.write(wav, audio, SAMPLE_RATE)
    esporta_mp3(wav, mp3)
    Path(wav).unlink(missing_ok=True)

    d_file = durata_file(mp3)
    scarto = None if d_file is None else abs(d_file - durata)
    if scarto is not None and scarto > config.TOLLERANZA_DURATA_S:
        log.warning(f"Durata del file ({d_file:.2f}s) diversa dalla timeline ({durata:.2f}s): "
                    f"scarto {scarto:.2f}s > {config.TOLLERANZA_DURATA_S}s. La sincronia potrebbe derivare.")
    else:
        log.info(f"Coerenza durata ok (timeline {durata:.2f}s, file {d_file if d_file is None else round(d_file, 2)}s)")

    import arricchimento as modulo_arr
    arr = modulo_arr.carica_valido([{"nome": s["nome"], "notizie": s["notizie"]} for s in sezioni], data)
    if arr is None:
        log.info("Nessun arricchimento valido: il manifest esce senza mappa né immagini.")
    manifest = costruisci_manifest(data or config.data_corrente(), parlato, sezioni, tempi, durata, articoli_per_id,
                                   arricchimento=arr)
    Path(config.percorso_manifest(data)).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Episodio pronto: {mp3} ({durata / 60:.1f} min), manifest: {config.percorso_manifest(data)}")
    return manifest


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Fasi 2 e 3 sul giorno indicato (default: oggi).")
    ap.add_argument("--data")
    ap.add_argument("--rigenera", action="store_true", help="ignora la cache audio per sezione")
    ap.add_argument("--audio-finto", action="store_true")
    a = ap.parse_args()
    config.imposta_data(a.data)
    config.AUDIO_FINTO = a.audio_finto
    prepara_parlato_giorno()
    costruisci_episodio(rigenera=a.rigenera)
