"""
serve_locale.py — Server locale per provare il sito, CON supporto alle
richieste Range (HTTP 206).

Perché serve: `python -m http.server` NON supporta Range. Senza Range il
browser non può saltare in un punto qualsiasi dell'MP3: cliccando su una frase
o muovendo lo slider la traccia riparte da zero. Cloudflare Pages (e ogni
hosting vero) supporta Range, quindi il problema c'è solo in locale.

Uso:
    python serve_locale.py              # porta 8000, cartella output/sito
    python serve_locale.py -p 8080

Dal telefono (stessa rete Wi-Fi) apri l'indirizzo "rete locale" che viene stampato.
"""

import argparse
import mimetypes
import os
import re
import socket
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import config


class RangeHandler(SimpleHTTPRequestHandler):
    _intervallo = None

    def send_head(self):
        self._intervallo = None
        richiesta = self.headers.get("Range")
        percorso = self.translate_path(self.path)
        if not richiesta or not os.path.isfile(percorso):
            return super().send_head()
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", richiesta.strip())
        if not m or (m.group(1) == "" and m.group(2) == ""):
            return super().send_head()

        dimensione = os.path.getsize(percorso)
        da, a = m.groups()
        if da == "":                                  # ultimi N byte
            inizio, fine = max(0, dimensione - int(a)), dimensione - 1
        else:
            inizio = int(da)
            fine = min(int(a), dimensione - 1) if a else dimensione - 1
        if inizio >= dimensione or inizio > fine:
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", f"bytes */{dimensione}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None

        f = open(percorso, "rb")
        f.seek(inizio)
        self._intervallo = (inizio, fine)
        self.send_response(HTTPStatus.PARTIAL_CONTENT)
        self.send_header("Content-Type", mimetypes.guess_type(percorso)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {inizio}-{fine}/{dimensione}")
        self.send_header("Content-Length", str(fine - inizio + 1))
        self.end_headers()
        return f

    def end_headers(self):
        if self._intervallo is None:
            self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def copyfile(self, source, outputfile):
        try:
            if self._intervallo is None:
                return super().copyfile(source, outputfile)
            restanti = self._intervallo[1] - self._intervallo[0] + 1
            while restanti > 0:
                blocco = source.read(min(64 * 1024, restanti))
                if not blocco:
                    break
                outputfile.write(blocco)
                restanti -= len(blocco)
        except (BrokenPipeError, ConnectionResetError):
            pass          # il browser ha chiuso la connessione (normale quando si salta)


def _ip_locale():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Server locale con supporto Range per provare il sito.")
    ap.add_argument("-p", "--porta", type=int, default=8000)
    ap.add_argument("-d", "--cartella", default=config.DIR_SITO)
    a = ap.parse_args()

    radice = Path(a.cartella)
    if not radice.exists():
        raise SystemExit(f"{radice} non esiste: genera prima il sito (python main.py ...).")

    server = ThreadingHTTPServer(("0.0.0.0", a.porta), partial(RangeHandler, directory=str(radice)))
    giorni = sorted((p.name for p in (radice / "t" / config.sito_token()).glob("????-??-??") if p.is_dir()), reverse=True)
    percorso = f"/t/{config.sito_token()}/" + (f"{giorni[0]}/" if giorni else "")
    print(f"Questo PC:    http://localhost:{a.porta}{percorso}")
    print(f"Rete locale:  http://{_ip_locale()}:{a.porta}{percorso}   (per il telefono)")
    print("Ctrl+C per fermare.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
