import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

import tempfile

import logging_config
# I test simulano errori (risposte troncate, JSON invalido...): i loro log
# NON devono finire in logs/ del progetto vero. Va fatto prima di importare
# i moduli che creano i logger.
logging_config.LOG_DIR = Path(tempfile.mkdtemp(prefix="log_test_"))

import pytest
import config


@pytest.fixture
def cartelle_tmp(tmp_path, monkeypatch):
    """Isola output, sito e token in una cartella temporanea."""
    monkeypatch.setattr(config, "DIR_OUTPUT", str(tmp_path / "output"))
    monkeypatch.setattr(config, "DIR_SITO", str(tmp_path / "sito"))
    monkeypatch.setattr(config, "FILE_TOKEN_SITO", str(tmp_path / "token.txt"))
    monkeypatch.setattr(config, "DIR_SITO_TEMPLATE", str(RADICE / "sito_template"))
    monkeypatch.setattr(config, "FILE_FONETICA_CANDIDATI", str(tmp_path / "cand.txt"))
    monkeypatch.setattr(config, "DIR_GEO", str(RADICE / "data" / "geo"))
    monkeypatch.setattr(config, "DIR_CACHE_IMMAGINI", str(tmp_path / "cache" / "img"))
    monkeypatch.setattr(config, "FILE_CACHE_LUOGHI", str(tmp_path / "cache" / "luoghi.json"))
    monkeypatch.setattr(config, "FILE_CACHE_ENTITA", str(tmp_path / "cache" / "entita.json"))
    monkeypatch.setattr(config, "MUSICA_ABILITATA", False)
    monkeypatch.setenv("SITO_TOKEN", "tokentest")
    monkeypatch.setenv("SITO_BASE_URL", "https://esempio.test")
    config.imposta_data("2099-01-01")
    yield tmp_path
    config.imposta_data(None)
