"""
diagnosi_entita.py — Perché una entità non ha scheda o immagine?

Interroga Wikidata e Commons per UN nome e mostra: i candidati con punteggio o
motivo dello scarto, quale viene scelto, le immagini candidate e la licenza di
ciascuna (e se sarebbe ammessa). Non scrive nulla in cache.

    python diagnosi_entita.py "Giorgia Meloni" --tipo persona --descrizione "presidente del Consiglio"
    python diagnosi_entita.py "Partito Democratico" --tipo partito

Poi, se serve: ammetti una licenza in config.LICENZE_EXTRA_AMMESSE, forza il QID giusto o blocca
la scheda in data/entita_override.json (vedi docs/policy_immagini.md).
Richiede CONTATTO_EMAIL nel .env (Wikimedia lo chiede nello user agent).
"""

import argparse

from dotenv import load_dotenv
load_dotenv()

import config
import wikidata as w


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("nome")
    ap.add_argument("--tipo", default="persona", choices=sorted(config.WIKIDATA_CLASSI))
    ap.add_argument("--descrizione", default="")
    a = ap.parse_args()
    if not config.contatto_api():
        raise SystemExit("Imposta CONTATTO_EMAIL nel .env: senza, le chiamate a Wikimedia vengono saltate.")

    wd = w.Wikidata(online=True)
    qids = wd._cerca_qid(a.nome)
    print(f"Ricerca '{a.nome}': {len(qids)} candidati ({', '.join(qids) or 'nessuno'})")
    cands = wd._carica_entita(qids)
    print("\nCandidati:")
    for riga in w.riassumi_candidati(cands, a.nome, a.tipo, a.descrizione):
        print("  ", riga)
    scelto, motivo = w.scegli_candidato(cands, a.nome, a.tipo, a.descrizione)
    print(f"\nScelto: {scelto['qid'] + ' ' + scelto['etichetta'] if scelto else 'NESSUNO'}  ({motivo})")
    if not scelto:
        print("Suggerimento: se il QID giusto è tra i candidati, forzalo in data/entita_override.json.")
        return
    print(f"Descrizione Wikidata: {scelto['descrizione']!r}; sitelinks: {scelto['sitelinks']}; "
          f"bonus notorietà: +{w.bonus_notorieta(scelto['sitelinks'])}")
    file_candidati = wd._immagini_da_claims(scelto["claims"], a.tipo, massimo=6)
    print(f"\nImmagini candidate (proprietà {config.WIKIDATA_PROPRIETA_IMMAGINE.get(a.tipo)}): {len(file_candidati)}")
    for nome_file in file_candidati:
        info = wd._info_commons(nome_file)
        if not info:
            print(f"   {nome_file}: non trovato su Commons")
            continue
        c = wd._crediti(nome_file, info)
        ok = "AMMESSA" if w.licenza_ammessa(c["licenza"]) else "RIFIUTATA"
        print(f"   {nome_file}: licenza {c['licenza']!r} -> {ok}; autore: {c['autore'] or 'n/d'}")


if __name__ == "__main__":
    main()
