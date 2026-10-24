// Mappa sincronizzata (Leaflet, servito in locale, solo poligoni: nessun tile esterno).
// Applica i keyframe del manifest al tempo di riproduzione. Dati non fidati:
// si leggono solo numeri e chiavi note, nessun HTML viene costruito da stringhe.
(function () {
  "use strict";
  var R = window.Rassegna, Logica = window.RassegnaMappaLogica, L = window.L;
  var elMappa = document.getElementById("mappa"), visivo = document.getElementById("visivo");
  var datiEl = document.getElementById("dati-visivi");
  if (!R || !Logica || !L || !elMappa || !visivo || !datiEl) { return; }
  var dati;
  try { dati = JSON.parse(datiEl.textContent); } catch (e) { return; }
  if (!dati.mappa || !dati.mappa.length) { return; }

  var BASE = dati.base || "";
  var LIMITI = { mondo: [[-56, -170], [78, 180]], italia: [[36.3, 6.5], [47.3, 18.9]] };
  var luoghi = dati.luoghi || {};

  elMappa.hidden = false;
  visivo.hidden = false;
  visivo.classList.add("con-mappa");

  var mappa = L.map(elMappa, {
    zoomControl: false, attributionControl: false, dragging: false, touchZoom: false, scrollWheelZoom: false,
    doubleClickZoom: false, boxZoom: false, keyboard: false, zoomSnap: 0.25, tap: false
  });
  ["paesi", "regioni", "province", "luoghi"].forEach(function (nome, i) {
    mappa.createPane(nome).style.zIndex = 380 + i * 10;
  });

  function colore(v, def) {
    var c = getComputedStyle(document.documentElement).getPropertyValue(v).trim();
    return c || def;
  }
  var C = {};
  function leggiColori() {
    C = { terra: colore("--map-land", "#e8ecef"), linea: colore("--map-line", "#9aa5b1"), acc: colore("--map-accent", "#0b5cad") };
  }
  leggiColori();

  // stile per livello e stato: nessuno | citato | attivo
  function stile(livello, stato) {
    var base = livello === "paesi"
      ? { fillColor: C.terra, fillOpacity: 1, color: C.linea, weight: 0.5 }
      : { fillColor: C.acc, fillOpacity: 0, color: C.linea, weight: livello === "regioni" ? 0.6 : 0 };
    if (stato === "attivo") { base.fillColor = C.acc; base.fillOpacity = 0.85; if (livello !== "paesi") { base.weight = 1; base.color = C.acc; } }
    if (stato === "citato") { base.fillColor = C.acc; base.fillOpacity = 0.35; }
    return base;
  }
  function stileMarker(stato) {
    return { radius: 6, weight: 2, color: C.acc, fillColor: C.acc,
             opacity: stato === "nessuno" ? 0 : 1, fillOpacity: stato === "attivo" ? 0.9 : (stato === "citato" ? 0.3 : 0) };
  }

  var strati = { paesi: {}, regioni: {}, province: {} };
  var marker = {};
  var stati = {};          // lid -> stato corrente
  var ultimoStato = null, ultimoIndice = -2;

  Object.keys(luoghi).forEach(function (lid) {
    var l = luoghi[lid];
    if (!l.poligono && typeof l.lat === "number" && typeof l.lon === "number") {
      marker[lid] = L.circleMarker([l.lat, l.lon], Object.assign({ pane: "luoghi", interactive: false }, stileMarker("nessuno"))).addTo(mappa);
    }
  });

  function applicaStileLuogo(lid, stato) {
    var l = luoghi[lid];
    if (!l) { return; }
    if (marker[lid]) { marker[lid].setStyle(stileMarker(stato)); return; }
    var p = l.poligono;
    var strato = p && strati[p.livello] && strati[p.livello][p.id];
    if (strato) { strato.setStyle(stile(p.livello, stato)); }
  }

  function carica(nome, chiave) {
    return fetch(BASE + "static/geo/" + nome + ".json").then(function (r) { return r.json(); }).then(function (geo) {
      L.geoJSON(geo, {
        pane: nome,
        style: function () { return stile(nome, "nessuno"); },
        interactive: false,
        onEachFeature: function (f, layer) { strati[nome][f.properties[chiave]] = layer; }
      }).addTo(mappa);
      if (ultimoStato) { evidenzia(ultimoStato); }
    }).catch(function () { /* senza confini la mappa resta vuota ma l'episodio funziona */ });
  }
  var livelli = {};
  Object.keys(luoghi).forEach(function (lid) { if (luoghi[lid].poligono) { livelli[luoghi[lid].poligono.livello] = true; } });
  carica("paesi", "iso");                                   // sfondo: sempre
  if (livelli.regioni || luoghi && Object.keys(luoghi).some(function (k) { return luoghi[k].paese === "IT"; })) { carica("regioni", "id"); }
  if (livelli.province) { carica("province", "id"); }

  function evidenzia(st) {
    var nuovi = {};
    st.citati.forEach(function (l) { nuovi[l] = "citato"; });
    st.attivi.forEach(function (l) { nuovi[l] = "attivo"; });
    Object.keys(stati).forEach(function (l) { if (!nuovi[l]) { applicaStileLuogo(l, "nessuno"); } });
    Object.keys(nuovi).forEach(function (l) { applicaStileLuogo(l, nuovi[l]); });
    stati = nuovi;
  }

  function visibile() { return elMappa.clientWidth > 0 && elMappa.clientHeight > 0; }

  function vista(v, anima) {
    if (!visibile()) { return; }
    mappa.invalidateSize(false);
    var opz = { animate: !!anima, duration: 1.2, padding: [12, 12], maxZoom: 9 };
    if (v.tipo === "punto" && isFinite(v.lat) && isFinite(v.lon)) {
      if (anima) { mappa.flyTo([v.lat, v.lon], v.zoom || 8, { duration: 1.2 }); }
      else { mappa.setView([v.lat, v.lon], v.zoom || 8, { animate: false }); }
      return;
    }
    var limiti = null;
    if (v.tipo === "bounds") { limiti = [v.sw, v.ne]; }
    else if (LIMITI[v.tipo]) { limiti = LIMITI[v.tipo]; if (v.tipo === "mondo") { opz.maxZoom = 3; } }
    if (!limiti) { return; }
    if (anima) { mappa.flyToBounds(limiti, opz); } else { mappa.fitBounds(limiti, opz); }
  }

  function applica(st, anima) { ultimoStato = st; evidenzia(st); vista(st.vista, anima); }

  R.ascolta(function (t, forzato) {
    var st = Logica.calcolaStato(dati.mappa, t);
    if (!forzato && st.indice === ultimoIndice) { return; }
    ultimoIndice = st.indice;
    applica(st, !forzato && !R.audio.paused);
  });

  // la mappa si mostra solo dove ha senso (data-mappa="0": sezione 'auto' senza luoghi)
  R.suFrase(function (el) { visivo.classList.toggle("senza-mappa", el.getAttribute("data-mappa") === "0"); });
  R.suVisibilita(function () { mappa.invalidateSize(false); if (ultimoStato) { vista(ultimoStato.vista, false); } });

  function ristila() {
    leggiColori();
    Object.keys(strati).forEach(function (liv) {
      Object.keys(strati[liv]).forEach(function (k) { strati[liv][k].setStyle(stile(liv, "nessuno")); });
    });
    Object.keys(marker).forEach(function (k) { marker[k].setStyle(stileMarker("nessuno")); });
    if (ultimoStato) { evidenzia(ultimoStato); }
  }
  document.addEventListener("rassegna:tema", ristila);
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    if (mq.addEventListener) { mq.addEventListener("change", ristila); }
  }

  applica(Logica.calcolaStato(dati.mappa, 0), false);
  setTimeout(function () { applica(Logica.calcolaStato(dati.mappa, R.audio.currentTime || 0), false); }, 50);
})();
