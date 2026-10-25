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
  var ZOOM_MAX = typeof dati.zoom_max === "number" ? dati.zoom_max : 5.5;   // oltre, senza tile, resta un puntino su sfondo grigio (config.MAPPA_ZOOM_MAX)
  var ZOOM_MONDO_MAX = 3;
  var DURATA_VOLO = 2.8;       // s: volo lento, solo per spostamenti brevi
  var DISSOLVENZA_MS = 260;    // spostamenti lunghi: dissolvenza, salto, dissolvenza (niente riquadri vuoti)
  var ETICHETTE_MAX_STORICO = 5;
  var luoghi = dati.luoghi || {};

  R.mostraVisivo();
  elMappa.hidden = false;
  visivo.classList.add("con-mappa");

  // Il renderer vettoriale disegna solo l'area visibile + un bordo (di default 10%): durante gli
  // spostamenti compaiono riquadri vuoti. Con un bordo largo l'area intorno è già disegnata.
  var mappa = L.map(elMappa, {
    zoomControl: false, attributionControl: false, dragging: false, touchZoom: false, scrollWheelZoom: false,
    doubleClickZoom: false, boxZoom: false, keyboard: false, zoomSnap: 0.25, tap: false,
    renderer: L.svg({ padding: 1 })
  });
  ["paesi", "regioni", "province", "luoghi"].forEach(function (nome, i) {
    mappa.createPane(nome).style.zIndex = 380 + i * 10;
  });

  // Colori dal tema/palette in uso. Si legge il colore RISOLTO di un elemento sonda: funziona
  // anche quando la variabile CSS contiene hsl(var(--h) ...) o calc().
  function colore(variabile, def) {
    var sonda = document.createElement("span");
    sonda.style.cssText = "position:absolute;visibility:hidden;color:var(" + variabile + ")";
    document.body.appendChild(sonda);
    var c = getComputedStyle(sonda).color;
    document.body.removeChild(sonda);
    return c && c !== "" ? c : def;
  }
  var C = {};
  function leggiColori() {
    C = { terra: colore("--map-land", "#e8ecef"), linea: colore("--map-line", "#9aa5b1"), acc: colore("--map-accent", "#0b5cad") };
  }
  leggiColori();

  // Storico: rango 0 = il luogo citato subito prima del corrente, 1 = quello prima ancora, ...
  // ogni nuovo punto aggiunto fa sbiadire di più i precedenti.
  function dissolvenza(rango) { return Math.max(0.18, 0.7 - 0.12 * rango); }

  function stilePoligono(livello, stato, rango) {
    var base = livello === "paesi"
      ? { fillColor: C.terra, fillOpacity: 1, color: C.linea, weight: 0.5, dashArray: null }
      : { fillColor: C.acc, fillOpacity: 0, color: C.linea, weight: livello === "regioni" ? 0.6 : 0, dashArray: null };
    if (stato === "attivo") {                                  // corrente: pieno, bordo solido
      base.fillColor = C.acc; base.fillOpacity = 0.85; base.color = C.acc; base.weight = 1.6; base.dashArray = null;
    } else if (stato === "citato") {                           // storico: sbiadito, bordo tratteggiato
      base.fillColor = C.acc; base.fillOpacity = Math.max(0.08, 0.5 * dissolvenza(rango));
      base.color = C.acc; base.weight = 1.3; base.dashArray = "4 3";
    }
    return base;
  }
  function stileMarker(stato, rango) {
    if (stato === "attivo") {
      return { radius: 7, weight: 3, color: C.acc, fillColor: C.acc, opacity: 1, fillOpacity: 0.9, dashArray: null };
    }
    if (stato === "citato") {
      var o = dissolvenza(rango);
      return { radius: 6, weight: 1.6, color: C.acc, fillColor: C.acc, opacity: o, fillOpacity: o * 0.45, dashArray: "4 3" };
    }
    return { radius: 6, weight: 2, color: C.acc, fillColor: C.acc, opacity: 0, fillOpacity: 0, dashArray: null };
  }

  var strati = { paesi: {}, regioni: {}, province: {} };
  var marker = {};
  var stati = {};          // lid -> {stato, rango}
  var ultimoStato = null, ultimoIndice = -2;

  // un marker per ogni luogo senza poligono, con il nome sopra (visibile solo quando il punto lo è)
  Object.keys(luoghi).forEach(function (lid) {
    var l = luoghi[lid];
    if (!l.poligono && typeof l.lat === "number" && typeof l.lon === "number") {
      var m = L.circleMarker([l.lat, l.lon], Object.assign({ pane: "luoghi", interactive: false }, stileMarker("nessuno", 0))).addTo(mappa);
      m.bindTooltip(String(l.nome || ""), { permanent: true, direction: "top", offset: [0, -7], className: "etichetta-luogo",
                                           opacity: 0, interactive: false });
      m.closeTooltip();
      marker[lid] = m;
    }
  });

  function applicaStileLuogo(lid, stato, rango) {
    var l = luoghi[lid];
    if (!l) { return; }
    var m = marker[lid];
    if (m) {
      m.setStyle(stileMarker(stato, rango));
      var visibileEtichetta = stato === "attivo" || (stato === "citato" && rango < ETICHETTE_MAX_STORICO);
      if (visibileEtichetta) {
        m.openTooltip();
        var t = m.getTooltip();
        if (t) { t.setOpacity(stato === "attivo" ? 1 : Math.min(1, dissolvenza(rango) + 0.2)); }
      } else {
        m.closeTooltip();
      }
      return;
    }
    var p = l.poligono;
    var strato = p && strati[p.livello] && strati[p.livello][p.id];
    if (strato) { strato.setStyle(stilePoligono(p.livello, stato, rango)); }
  }

  function carica(nome, chiave) {
    return fetch(BASE + "static/geo/" + nome + ".json").then(function (r) { return r.json(); }).then(function (geo) {
      L.geoJSON(geo, {
        pane: nome,
        style: function () { return stilePoligono(nome, "nessuno", 0); },
        interactive: false,
        onEachFeature: function (f, layer) { strati[nome][f.properties[chiave]] = layer; }
      }).addTo(mappa);
      if (ultimoStato) { evidenzia(ultimoStato); }
    }).catch(function () { /* senza confini la mappa resta vuota ma l'episodio funziona */ });
  }
  var livelli = {};
  Object.keys(luoghi).forEach(function (lid) { if (luoghi[lid].poligono) { livelli[luoghi[lid].poligono.livello] = true; } });
  carica("paesi", "iso");                                   // sfondo: sempre
  if (livelli.regioni || Object.keys(luoghi).some(function (k) { return luoghi[k].paese === "IT"; })) { carica("regioni", "id"); }
  if (livelli.province) { carica("province", "id"); }

  function evidenzia(st) {
    var nuovi = {};
    st.citati.forEach(function (l, i) { nuovi[l] = { stato: "citato", rango: i }; });   // citati: dal più recente
    st.attivi.forEach(function (l) { nuovi[l] = { stato: "attivo", rango: 0 }; });
    Object.keys(stati).forEach(function (l) { if (!nuovi[l]) { applicaStileLuogo(l, "nessuno", 0); } });
    Object.keys(nuovi).forEach(function (l) { applicaStileLuogo(l, nuovi[l].stato, nuovi[l].rango); });
    stati = nuovi;
  }

  function visibile() { return elMappa.clientWidth > 0 && elMappa.clientHeight > 0; }

  // vista -> {c: centro, z: zoom}; i punti e i riquadri hanno un tetto di zoom
  function bersaglio(v) {
    if (v.tipo === "punto" && isFinite(v.lat) && isFinite(v.lon)) {
      return { c: L.latLng(v.lat, v.lon), z: Math.min(v.zoom || 4.5, ZOOM_MAX) };
    }
    var lim = v.tipo === "bounds" ? [v.sw, v.ne] : LIMITI[v.tipo];
    if (!lim) { return null; }
    var b = L.latLngBounds(lim);
    var z = mappa.getBoundsZoom(b, false, L.point(12, 12));
    z = Math.min(z, v.tipo === "mondo" ? ZOOM_MONDO_MAX : ZOOM_MAX);
    return { c: b.getCenter(), z: z };
  }

  var timerSalto = null;
  function vaiA(t, anima) {
    mappa.stop();
    if (timerSalto) { clearTimeout(timerSalto); timerSalto = null; elMappa.classList.remove("dissolvenza"); }
    if (!anima) { mappa.setView(t.c, t.z, { animate: false }); return; }
    var dimensione = mappa.getSize();
    var distanza = mappa.latLngToContainerPoint(t.c).distanceTo(dimensione.divideBy(2));
    var vicino = distanza <= 1.2 * Math.max(dimensione.x, dimensione.y) && Math.abs(t.z - mappa.getZoom()) <= 2;
    if (vicino) {                                          // spostamento breve: volo lento
      mappa.flyTo(t.c, t.z, { duration: DURATA_VOLO, easeLinearity: 0.15 });
      return;
    }
    // spostamento lungo: dissolvenza -> salto -> dissolvenza. Il volo su lunghe distanze sarebbe
    // veloce e pieno di riquadri non ancora disegnati; così la mappa è completa prima di riapparire.
    elMappa.classList.add("dissolvenza");
    timerSalto = setTimeout(function () {
      mappa.setView(t.c, t.z, { animate: false });
      window.requestAnimationFrame(function () {
        window.requestAnimationFrame(function () { elMappa.classList.remove("dissolvenza"); timerSalto = null; });
      });
    }, DISSOLVENZA_MS);
  }

  function vista(v, anima) {
    if (!visibile()) { return; }
    mappa.invalidateSize(false);
    var t = bersaglio(v);
    if (t) { vaiA(t, anima); }
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
      Object.keys(strati[liv]).forEach(function (k) { strati[liv][k].setStyle(stilePoligono(liv, "nessuno", 0)); });
    });
    Object.keys(marker).forEach(function (k) { marker[k].setStyle(stileMarker("nessuno", 0)); });
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
