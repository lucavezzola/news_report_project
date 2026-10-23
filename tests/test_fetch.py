from types import SimpleNamespace as NS

import pytest
import fetch

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Uno</title><link>https://x.it/1</link></item></channel></rss>"""


def finto(contenuto, status=200, tipo="application/xml"):
    return lambda url, **kw: NS(status_code=status, content=contenuto, text=contenuto.decode("utf-8", "replace"),
                                headers={"Content-Type": tipo})


def test_feed_valido(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", finto(RSS))
    assert len(fetch._scarica_feed("https://x.it/feed").entries) == 1


def test_html_al_posto_del_feed_da_errore_diagnostico(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", finto(b"<html><body>Accesso negato</body></html>", tipo="text/html"))
    with pytest.raises(ValueError) as e:
        fetch._scarica_feed("https://x.it/feed")
    assert "text/html" in str(e.value) and "Accesso negato" in str(e.value)


def test_http_errore(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", finto(b"", status=403))
    with pytest.raises(ValueError, match="HTTP 403"):
        fetch._scarica_feed("https://x.it/feed")


def test_user_agent_inviato(monkeypatch):
    import requests
    visti = {}
    def get(url, **kw):
        visti.update(kw)
        return finto(RSS)(url)
    monkeypatch.setattr(requests, "get", get)
    fetch._scarica_feed("https://x.it/feed")
    assert "Mozilla" in visti["headers"]["User-Agent"] and visti["timeout"] == 20
