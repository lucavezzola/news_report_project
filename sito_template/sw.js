// Service worker leggero: shell (CSS/JS/Leaflet) e ultime pagine, per aprire il sito
// anche con rete debole. NON intercetta mai l'audio: cache.match() ignora gli header
// Range e restituirebbe il file intero, rompendo il salto nella traccia.
// La versione viene sostituita da sito.py a ogni generazione.
var VERSIONE = "__VERSIONE__";
var CACHE_SHELL = "shell-" + VERSIONE;
var CACHE_PAGINE = "pagine";
var CACHE_DATI = "dati";
var MAX_PAGINE = __MAX_PAGINE__;
var SHELL = ["./", "static/style.css", "static/app.js", "static/mappa_logica.js", "static/mappa.js",
             "static/citati.js", "static/leaflet/leaflet.js", "static/leaflet/leaflet.css", "manifest.webmanifest"];

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE_SHELL).then(function (c) {
    // add() singoli: un file mancante non deve far fallire l'installazione
    return Promise.all(SHELL.map(function (u) { return c.add(u).catch(function () {}); }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (nomi) {
    return Promise.all(nomi.filter(function (n) { return n.indexOf("shell-") === 0 && n !== CACHE_SHELL; })
      .map(function (n) { return caches.delete(n); }));
  }).then(function () { return self.clients.claim(); }));
});

function taglia(nomeCache, max) {
  return caches.open(nomeCache).then(function (c) {
    return c.keys().then(function (chiavi) {
      return Promise.all(chiavi.slice(0, Math.max(0, chiavi.length - max)).map(function (k) { return c.delete(k); }));
    });
  });
}

self.addEventListener("fetch", function (e) {
  var req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (req.headers.has("range") || /\.(mp3|m4a|ogg|wav)$/i.test(url.pathname)) return;   // audio: mai

  if (req.mode === "navigate") {                                  // pagine: prima la rete
    e.respondWith(fetch(req).then(function (r) {
      var copia = r.clone();
      caches.open(CACHE_PAGINE).then(function (c) { return c.put(req, copia); }).then(function () { return taglia(CACHE_PAGINE, MAX_PAGINE); });
      return r;
    }).catch(function () {
      return caches.match(req).then(function (r) { return r || caches.match("./"); });
    }));
    return;
  }
  var nome = /\/(static|img)\//.test(url.pathname) ? (/\/geo\//.test(url.pathname) ? CACHE_DATI : CACHE_SHELL) : null;
  if (!nome) return;
  e.respondWith(caches.open(nome).then(function (c) {            // asset: dalla cache, aggiornati in background
    return c.match(req).then(function (r) {
      var rete = fetch(req).then(function (nuova) { if (nuova.ok) c.put(req, nuova.clone()); return nuova; }).catch(function () { return r; });
      return r || rete;
    });
  }));
});
