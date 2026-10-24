"""
main.py — Orchestratore della pipeline.

Fasi (ognuna salva i suoi file in output/AAAA-MM-GG/ e si può rilanciare da sola):
  1  fetch + sintesi per sezione (Claude)       -> articoli_grezzi.json, notizie_<sezione>.json
  2  entità/luoghi/immagini (Wikidata, geo) + fonetica -> arricchimento.json, parlato.json
  3  TTS per frase + episodio (musica, MP3)     -> episodio.mp3, manifest.json
  4  sito + deploy + notifica Telegram

Esempi:
    python main.py                       # tutto, ultime 24 ore
    python main.py 3                     # ultimi 3 giorni
    python main.py --da-ultima-chiamata
    python main.py --da-fase 3           # riusa notizie e parlato già su disco
    python main.py --da-fase 1 --solo-sezione Esteri   # rifà solo Esteri (articoli già raccolti)
    python main.py --no-deploy --no-telegram
    python main.py --no-arricchimento    # niente mappa/immagini (es. senza rete)
    python main.py --usa-fixture --data 2099-01-01 --audio-finto --no-deploy --no-telegram
"""

import argparse
import json
import logging
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import config
from logging_config import avvisa_log_grandi, configura_logger

log = configura_logger("main", "main.log")


def _carica_articoli():
    return json.loads(Path(config.percorso_articoli_grezzi()).read_text(encoding="utf-8"))


def fase1(giorni, ora_inizio, solo_sezione, riepilogo):
    import fetch
    import synthesize

    ora_fine = datetime.now(timezone.utc)
    riusa_articoli = bool(solo_sezione) and Path(config.percorso_articoli_grezzi()).exists()
    if riusa_articoli:
        log.info("Fase 1: --solo-sezione, riuso gli articoli già raccolti oggi.")
        articoli = _carica_articoli()
        meta = synthesize.carica_meta()
        if meta:
            ora_fine = datetime.fromisoformat(meta["ora_fine"])
    else:
        log.info("Fase 1/4: raccolta articoli...")
        articoli = fetch.raccogli_articoli(giorni=giorni, ora_fine=ora_fine, ora_inizio=ora_inizio)
        fetch.salva_json(articoli)
        synthesize.salva_meta(ora_fine, giorni, ora_inizio)
    if not articoli:
        raise RuntimeError("Nessun articolo raccolto.")

    log.info("Fase 1/4: sintesi con Claude (una chiamata per sezione)...")
    sezioni = [solo_sezione] if solo_sezione else config.SEZIONI
    risultati, errori, info = synthesize.sintetizza(
        articoli, sezioni=sezioni, giorni=giorni, ora_fine=ora_fine, ora_inizio=ora_inizio)
    for nome in sezioni:
        if nome in risultati:
            synthesize.salva_sezione(nome, risultati[nome])
        elif nome not in errori:
            synthesize.rimuovi_sezione(nome)      # oggi senza notizie: niente file vecchi
    # Se una sezione fallisce, se esiste un file precedente dello stesso giorno resta quello.
    riepilogo["token"] = (info["input_tokens"], info["output_tokens"])
    riepilogo["sezioni_fallite"] = errori
    if not synthesize.carica_sezioni():
        raise RuntimeError("Nessuna sezione generata.")


def fase2(riepilogo, arricchisci=True):
    import episodio
    if arricchisci:
        log.info("Fase 2/4: entità, luoghi e immagini...")
        try:
            import arricchimento
            riepilogo["arricchimento"] = arricchimento.arricchisci_giorno()["stats"]
        except Exception:
            # mai bloccare l'episodio per mappa e immagini: si prosegue senza
            log.error("Arricchimento fallito, l'episodio uscirà senza mappa e immagini:\n" + traceback.format_exc())
            riepilogo["arricchimento_fallito"] = True
            Path(config.percorso_arricchimento()).unlink(missing_ok=True)
    log.info("Fase 2/4: fonetica...")
    parlato = episodio.prepara_parlato_giorno()
    riepilogo["frasi"] = sum(len(s["unita"]) for s in parlato["sezioni"])


def fase3(rigenera, riepilogo):
    import episodio
    log.info("Fase 3/4: sintesi vocale ed episodio...")
    manifest = episodio.costruisci_episodio(rigenera=rigenera)
    riepilogo["durata_s"] = manifest["durata"]


def fase4(no_deploy, no_telegram, riepilogo):
    import sito
    log.info("Fase 4/4: sito, deploy, notifica...")
    sito.costruisci_sito_giorno()
    manifest = json.loads(Path(config.percorso_manifest()).read_text(encoding="utf-8"))
    url = sito.url_episodio(config.data_corrente())
    if not no_deploy:
        import deploy
        url = deploy.pubblica() or url
    else:
        log.info("--no-deploy: sito generato in locale, nessuna pubblicazione.")
    if no_telegram:
        log.info("--no-telegram: nessuna notifica.")
        return
    if no_deploy:
        log.info("Nessun deploy: non invio la notifica (il link non sarebbe raggiungibile).")
        return
    import send_telegram
    send_telegram.notifica_episodio(sito._data_it(config.data_corrente()), round(manifest["durata"] / 60), url)
    if config.telegram_invia_audio():
        send_telegram.invia_audio(config.percorso_episodio_mp3(), didascalia=f"Rassegna del {sito._data_it(config.data_corrente())}")


def esegui_pipeline(args, giorni, ora_inizio):
    t0 = time.time()
    riepilogo = {}
    avvisa_log_grandi(config.LOG_DIMENSIONE_MASSIMA_MB * 1024 * 1024)
    log.info("=" * 70)
    log.info(f"Avvio pipeline — giorno di lavoro {config.data_corrente()}, dalla fase {args.da_fase}")

    if args.usa_fixture:
        sorgente = Path("fixtures/giorno_esempio")
        for f in sorgente.glob("*.json"):
            shutil.copy2(f, config.dir_giorno() / f.name)
        if (sorgente / "img").exists():                      # immagini di esempio -> cache immagini
            Path(config.DIR_CACHE_IMMAGINI).mkdir(parents=True, exist_ok=True)
            for f in (sorgente / "img").iterdir():
                shutil.copy2(f, Path(config.DIR_CACHE_IMMAGINI) / f.name)
        log.info(f"Fixture copiate in {config.dir_giorno()}")

    if args.da_fase <= 1 and not args.usa_fixture:
        fase1(giorni, ora_inizio, args.solo_sezione, riepilogo)
    if args.da_fase <= 2:
        fase2(riepilogo, arricchisci=not (args.no_arricchimento or args.usa_fixture))
    if args.da_fase <= 3:
        fase3(args.rigenera, riepilogo)
    fase4(args.no_deploy, args.no_telegram, riepilogo)

    log.info("-" * 70)
    arr = riepilogo.get("arricchimento")
    log.info(f"Riepilogo run: durata {time.time() - t0:.0f}s; token in/out {riepilogo.get('token', 'n/d')}; "
             f"frasi {riepilogo.get('frasi', 'n/d')}; episodio {riepilogo.get('durata_s', 'n/d')}s; "
             f"entità {arr['entita_risolte'] if arr else 'n/d'}/{arr['entita_totali'] if arr else 'n/d'}, "
             f"luoghi {arr['luoghi_geocodificati'] if arr else 'n/d'}/{arr['luoghi_totali'] if arr else 'n/d'}; "
             f"sezioni fallite: {riepilogo.get('sezioni_fallite') or 'nessuna'}")
    avvisi = []
    if riepilogo.get("sezioni_fallite"):
        avvisi.append(f"sezioni mancanti: {', '.join(riepilogo['sezioni_fallite'])}")
    if riepilogo.get("arricchimento_fallito"):
        avvisi.append("arricchimento fallito (episodio senza mappa e immagini)")
    if avvisi:
        log.error("Completato con problemi: " + "; ".join(avvisi))
        if not args.no_telegram:
            try:
                import send_telegram
                send_telegram.notifica_errore("episodio pubblicato con problemi: " + "; ".join(avvisi))
            except Exception:
                pass
        return 1 if riepilogo.get("sezioni_fallite") else 0
    log.info("Pipeline completata con successo.")
    return 0


def leggi_ultima_chiamata():
    percorso = Path(config.FILE_ULTIMA_CHIAMATA)
    if not percorso.exists():
        return None
    try:
        ora = datetime.fromisoformat(percorso.read_text(encoding="utf-8").strip())
        if ora.tzinfo is None:
            raise ValueError("timestamp senza fuso orario")
        return ora.astimezone(timezone.utc)
    except (OSError, ValueError) as errore:
        raise ValueError(f"Timestamp dell'ultima chiamata non valido: {errore}")


def salva_ultima_chiamata(ora):
    percorso = Path(config.FILE_ULTIMA_CHIAMATA)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(ora.isoformat(), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Genera e pubblica la rassegna stampa audio.")
    parser.add_argument("giorni", nargs="?", type=int, default=1, metavar="GIORNI",
                        help="giorni di notizie da includere (1 = ultime 24 ore; default: 1)")
    parser.add_argument("--da-ultima-chiamata", action="store_true",
                        help="raccoglie le notizie dall'ultima esecuzione di main.py, dopo conferma")
    parser.add_argument("--data", help="giorno di lavoro AAAA-MM-GG (cartella output; default: oggi). "
                                        "Il fetch raccoglie comunque le notizie fino ad ora.")
    parser.add_argument("--da-fase", type=int, choices=[1, 2, 3, 4], default=1,
                        help="riparte da questa fase usando i file già su disco")
    parser.add_argument("--solo-sezione", choices=config.SEZIONI,
                        help="Fase 1: rifà solo questa sezione (le altre restano quelle su disco)")
    parser.add_argument("--rigenera", action="store_true", help="Fase 3: ignora la cache audio per sezione")
    parser.add_argument("--no-deploy", action="store_true", help="genera il sito ma non lo pubblica")
    parser.add_argument("--no-telegram", action="store_true", help="non invia notifiche Telegram")
    parser.add_argument("--no-arricchimento", action="store_true", help="salta entità, luoghi e immagini (niente mappa)")
    parser.add_argument("--audio-finto", action="store_true", help="toni al posto di XTTS (sviluppo senza GPU)")
    parser.add_argument("--usa-fixture", action="store_true",
                        help="copia fixtures/giorno_esempio nella cartella del giorno e parte dalla fase 2")
    args = parser.parse_args(argv)
    if args.giorni < 1:
        parser.error("GIORNI deve essere almeno 1")

    try:
        config.imposta_data(args.data)
    except ValueError:
        parser.error("--data deve essere nel formato AAAA-MM-GG")
    config.AUDIO_FINTO = args.audio_finto
    if args.usa_fixture:
        args.da_fase = max(args.da_fase, 2)

    try:
        ora_chiamata = datetime.now(timezone.utc)
        ora_inizio = None
        if args.da_ultima_chiamata:
            ora_inizio = leggi_ultima_chiamata()
            if ora_inizio is None:
                parser.error("nessuna chiamata precedente registrata; esegui prima python main.py")
            durata = ora_chiamata - ora_inizio
            if durata.total_seconds() < 0:
                parser.error("l'ultima chiamata risulta nel futuro; controlla l'orologio di sistema")
            giorni_trascorsi, resto = divmod(int(durata.total_seconds()), 24 * 60 * 60)
            ore_trascorse = resto // (60 * 60)
            print(f"Dall'ultima chiamata: {giorni_trascorsi} {'giorno' if giorni_trascorsi == 1 else 'giorni'} e "
                  f"{ore_trascorse} {'ora' if ore_trascorse == 1 else 'ore'}. Vuoi procedere? [s/N]", end=" ", flush=True)
            if input().strip().lower() not in {"s", "si", "sì", "y", "yes"}:
                print("Operazione annullata.")
                return 0
            giorni_pipeline = max(1, (int(durata.total_seconds()) + 86399) // 86400)
        else:
            giorni_pipeline = args.giorni

        if args.da_fase == 1 and not args.usa_fixture:
            salva_ultima_chiamata(ora_chiamata)
        return esegui_pipeline(args, giorni_pipeline, ora_inizio)
    except Exception:
        errore = traceback.format_exc()
        log.error("Pipeline interrotta da un errore:\n" + errore)
        if not args.no_telegram:
            try:
                import send_telegram
                send_telegram.notifica_errore(f"pipeline interrotta: {errore.strip().splitlines()[-1]}")
            except Exception:
                pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
