import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

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
    monkeypatch.setenv("SITO_TOKEN", "tokentest")
    monkeypatch.setenv("SITO_BASE_URL", "https://esempio.test")
    config.imposta_data("2099-01-01")
    yield tmp_path
    config.imposta_data(None)
