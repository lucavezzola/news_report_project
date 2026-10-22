from types import SimpleNamespace as NS

import pytest
import synthesize as s

ART = [{"id": "a1", "fonte": "ANSA", "titolo": "t", "estratto": "<p>x</p>", "categoria": "Italia"}]
OK = {"notizie": [{"titolo": "T", "fonti": ["a1"], "frasi": [{"testo": "Frase."}]}]}


class FakeClient:
    def __init__(self, risposte):
        self.risposte, self.chiamate = list(risposte), []
        self.messages = self

    def stream(self, **kw):
        self.chiamate.append(kw)
        stop, dati = self.risposte.pop(0)
        blocchi = [NS(type="tool_use", name=s.NOME_TOOL, input=dati)] if dati is not None else []
        risposta = NS(content=blocchi, stop_reason=stop, usage=NS(input_tokens=10, output_tokens=5))

        class Ctx:
            def __enter__(self_): return NS(get_final_message=lambda: risposta)
            def __exit__(self_, *a): return False
        return Ctx()


def test_ok_al_primo_tentativo():
    c = FakeClient([("tool_use", OK)])
    nz, info = s.sintetizza_sezione("Italia", ART, "ultime 24 ore", client=c)
    assert len(nz) == 1 and len(c.chiamate) == 1
    assert c.chiamate[0]["tool_choice"]["name"] == s.NOME_TOOL


def test_troncato_poi_budget_doppio_poi_meno_notizie():
    c = FakeClient([("max_tokens", {"notizie": []}), ("max_tokens", {"notizie": []}), ("tool_use", OK)])
    nz, info = s.sintetizza_sezione("Italia", ART, "p", client=c)
    mt = [k["max_tokens"] for k in c.chiamate]
    assert mt[1] == 2 * mt[0] and mt[2] == mt[1]
    assert "al massimo 3 notizie" in c.chiamate[2]["messages"][0]["content"]
    assert info["output_tokens"] == 15


def test_fallimento_dopo_tre_tentativi():
    c = FakeClient([("tool_use", None)] * 3)
    with pytest.raises(RuntimeError):
        s.sintetizza_sezione("Italia", ART, "p", client=c)


def test_output_invalido_ritenta():
    c = FakeClient([("tool_use", {"altro": 1}), ("tool_use", OK)])
    nz, _ = s.sintetizza_sezione("Italia", ART, "p", client=c)
    assert len(nz) == 1 and len(c.chiamate) == 2
