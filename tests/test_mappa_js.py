"""La logica JS della mappa (mappa_logica.js, eseguita da Node) deve dare esattamente
gli stessi risultati di mappa.stato_a() in Python, a qualunque tempo e dopo seek."""
import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

import mappa
from test_mappa import LUOGHI, _scenario

RADICE = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js non installato")


def test_js_e_python_coincidono():
    kfs, _ = mappa.calcola_keyframe(_scenario(), LUOGHI)
    tempi = [i * 0.5 for i in range(-2, 150)]
    random.Random(3).shuffle(tempi)
    r = subprocess.run(["node", str(RADICE / "tests" / "js" / "logica.js")], input=json.dumps({"keyframes": kfs, "tempi": tempi}),
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    for t, js in zip(tempi, json.loads(r.stdout)):
        py = mappa.stato_a(kfs, t)
        assert js == py, f"t={t}: js={js} py={py}"
