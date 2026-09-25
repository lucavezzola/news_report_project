"""Configurazione condivisa dei logger della pipeline."""

import logging
from pathlib import Path


LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DIR = Path("logs")


def configura_logger(nome, nome_file):
    """Configura un logger indipendente, evitando handler duplicati."""
    LOG_DIR.mkdir(exist_ok=True)
    logger = logging.getLogger(nome)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    percorso_log = (LOG_DIR / nome_file).resolve()
    handler_file_gia_presente = any(
        isinstance(handler, logging.FileHandler)
        and Path(handler.baseFilename).resolve() == percorso_log
        for handler in logger.handlers
    )
    if not handler_file_gia_presente:
        handler_file = logging.FileHandler(percorso_log, encoding="utf-8")
        handler_file.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler_file)

    if not any(isinstance(handler, logging.StreamHandler)
               and not isinstance(handler, logging.FileHandler)
               for handler in logger.handlers):
        handler_console = logging.StreamHandler()
        handler_console.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler_console)

    return logger


def avvisa_log_grandi(soglia_bytes):
    """Emette un warning per ogni log che ha superato la soglia indicata."""
    if soglia_bytes <= 0 or not LOG_DIR.exists():
        return

    for percorso in sorted(LOG_DIR.glob("*.log")):
        dimensione = percorso.stat().st_size
        if dimensione >= soglia_bytes:
            dimensione_mb = dimensione / (1024 * 1024)
            soglia_mb = soglia_bytes / (1024 * 1024)
            logging.getLogger("main").warning(
                "Il log %s e' grande %.1f MB (soglia %.1f MB): "
                "valuta di eliminarlo o archiviarlo.",
                percorso.name,
                dimensione_mb,
                soglia_mb,
            )