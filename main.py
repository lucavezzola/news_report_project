"""
main.py — Orchestratore della pipeline completa.

Esegue in sequenza: fetch -> sintesi -> TTS -> invio Telegram.
Genera e invia UN AUDIO SEPARATO PER OGNI SEZIONE (Italia, Esteri, Tecnologia),
inviati come messaggi distinti in sequenza sul canale Telegram.
La prima sezione generata quel giorno riceve la musica di intro, l'ultima
quella di outro (vedi musica.py e config.MUSICA_*).

Pensato per essere lanciato da Task Scheduler ogni mattina.

Uso:
    python main.py
"""

import argparse
import logging
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # carica ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, ecc. da .env se presente

import config
import fetch
import synthesize
import tts
import send_telegram
from logging_config import avvisa_log_grandi, configura_logger

log = configura_logger("main", "main.log")


def esegui_pipeline(giorni=1, ora_inizio=None):
    if giorni < 1:
        raise ValueError("Il numero di giorni deve essere almeno 1.")

    ora_fine = datetime.now(timezone.utc)
    periodo = synthesize.formatta_intervallo(ora_fine, giorni, ora_inizio=ora_inizio)
    avvisa_log_grandi(config.LOG_DIMENSIONE_MASSIMA_MB * 1024 * 1024)
    log.info("=" * 70)
    log.info(f"Avvio pipeline rassegna stampa — {ora_fine.isoformat()}")
    log.info(f"Periodo delle notizie: {periodo}")

    # --- Fase 1: fetch ---
    log.info("Fase 1/4: raccolta articoli...")
    articoli = fetch.raccogli_articoli(
        giorni=giorni, ora_fine=ora_fine, ora_inizio=ora_inizio
    )
    fetch.salva_json(articoli)
    if not articoli:
        log.error("Nessun articolo raccolto. Interrompo la pipeline.")
        sys.exit(1)

    # --- Fase 2: sintesi (una voce di testo per sezione) ---
    log.info("Fase 2/4: sintesi con Claude...")
    sezioni = synthesize.sintetizza(
        articoli, giorni=giorni, ora_fine=ora_fine, ora_inizio=ora_inizio
    )
    synthesize.salva_sezioni(sezioni)
    if not sezioni:
        log.error("Nessuna sezione generata. Interrompo la pipeline.")
        sys.exit(1)

    # --- Fase 3 + 4: per ogni sezione, genera l'audio e invialo subito ---
    # (invio sezione per sezione, non tutto insieme alla fine, così se una
    # sezione fallisce le precedenti sono già state consegnate)
    # e_prima/e_ultima si basano sulla posizione REALE nella lista di sezioni
    # generate oggi (non su config.SEZIONI), perché una sezione può mancare
    # se non ci sono notizie rilevanti quel giorno.
    data_oggi_breve = ora_fine.astimezone().strftime("%d/%m/%Y")
    sezioni_fallite = []
    for indice, s in enumerate(sezioni):
        nome = s["nome"]
        e_prima = (indice == 0)
        e_ultima = (indice == len(sezioni) - 1)
        try:
            log.info(f"Fase 3/4: sintesi vocale sezione '{nome}'...")
            percorso_wav = config.percorso_audio_wav_sezione(nome)
            percorso_ogg = config.percorso_audio_ogg_sezione(nome)
            voce = config.voce_per_sezione(nome)
            if voce:
                log.info(f"  voce assegnata a '{nome}': {voce}")
            percorso_audio = tts.genera_audio(
                s["testo"], percorso_wav, percorso_ogg,
                speaker_name=voce,
                e_prima_sezione=e_prima,
                e_ultima_sezione=e_ultima,
            )

            log.info(f"Fase 4/4: invio sezione '{nome}' su Telegram...")
            didascalia = (
                f"{nome} — {periodo}" if giorni > 1 or ora_inizio is not None
                else f"{nome} — {data_oggi_breve}"
            )
            send_telegram.invia_audio(percorso_audio, didascalia=didascalia)
        except Exception:
            log.error(f"Sezione '{nome}' fallita, salto e continuo con le altre:\n" + traceback.format_exc())
            sezioni_fallite.append(nome)

    if sezioni_fallite:
        log.error(f"Pipeline completata con errori nelle sezioni: {', '.join(sezioni_fallite)}")
        sys.exit(1)  # exit code diverso da 0 per far notare il problema a Task Scheduler
    log.info("Pipeline completata con successo.")


if __name__ == "__main__":
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

    parser = argparse.ArgumentParser(description="Genera e invia la rassegna stampa audio.")
    parser.add_argument(
        "giorni",
        nargs="?",
        type=int,
        default=1,
        metavar="GIORNI",
        help="giorni di notizie da includere (1 = ultime 24 ore; default: 1)",
    )
    parser.add_argument(
        "--da-ultima-chiamata",
        action="store_true",
        help="raccoglie le notizie dall'ultima esecuzione di main.py, dopo conferma",
    )
    args = parser.parse_args()
    if args.giorni < 1:
        parser.error("GIORNI deve essere almeno 1")

    try:
        ora_chiamata = datetime.now(timezone.utc)
        ora_inizio = None
        if args.da_ultima_chiamata:
            ora_inizio = leggi_ultima_chiamata()
            if ora_inizio is None:
                parser.error(
                    "nessuna chiamata precedente registrata; esegui prima python main.py"
                )
            durata = ora_chiamata - ora_inizio
            if durata.total_seconds() < 0:
                parser.error("l'ultima chiamata risulta nel futuro; controlla l'orologio di sistema")
            giorni_trascorsi, resto = divmod(int(durata.total_seconds()), 24 * 60 * 60)
            ore_trascorse = resto // (60 * 60)
            testo_giorni = "giorno" if giorni_trascorsi == 1 else "giorni"
            testo_ore = "ora" if ore_trascorse == 1 else "ore"
            print(
                f"Dall'ultima chiamata: {giorni_trascorsi} {testo_giorni} e "
                f"{ore_trascorse} {testo_ore}. Vuoi procedere? [s/N]",
                end=" ",
                flush=True,
            )
            if input().strip().lower() not in {"s", "si", "sì", "y", "yes"}:
                print("Operazione annullata.")
                sys.exit(0)
            giorni_pipeline = max(1, (int(durata.total_seconds()) + 86399) // 86400)
        else:
            giorni_pipeline = args.giorni

        salva_ultima_chiamata(ora_chiamata)
        esegui_pipeline(giorni=giorni_pipeline, ora_inizio=ora_inizio)
    except Exception:
        log.error("Pipeline interrotta da un errore:\n" + traceback.format_exc())
        sys.exit(1)
