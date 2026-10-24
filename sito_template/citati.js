// Pannello "Citati ora": carte (immagine, nome, ruolo) per le entità della frase
// corrente, che restano ~4 s dopo la fine della frase; al massimo 3 insieme.
// Tutto con createElement/textContent: i dati arrivano da RSS -> Claude -> Wikidata.
(function () {
  "use strict";
  var R = window.Rassegna;
  var cont = document.getElementById("citati"), visivo = document.getElementById("visivo");
  var datiEl = document.getElementById("dati-visivi");
  if (!R || !cont || !visivo || !datiEl) { return; }
  var dati;
  try { dati = JSON.parse(datiEl.textContent); } catch (e) { return; }
  var entita = dati.entita || {};
  if (!Object.keys(entita).length) { return; }

  var MAX = dati.max_carte || 3, DOPO = dati.durata_carte || 4, BASE = dati.base || "";
  var eventi = [];
  Array.prototype.forEach.call(document.querySelectorAll(".frase[data-entita]"), function (sp) {
    var inizio = parseFloat(sp.getAttribute("data-inizio")), fine = parseFloat(sp.getAttribute("data-fine"));
    sp.getAttribute("data-entita").split(" ").forEach(function (id) {
      if (entita[id]) { eventi.push({ id: id, inizio: inizio, fine: fine + DOPO }); }
    });
  });
  if (!eventi.length) { return; }
  eventi.sort(function (a, b) { return a.inizio - b.inizio; });
  R.mostraVisivo();

  var mostrate = {};   // id -> elemento

  function carta(id) {
    var e = entita[id];
    var fig = document.createElement("figure");
    fig.className = "carta";
    if (e.immagine && /^img\/[A-Za-z0-9_.-]+$/.test(e.immagine)) {
      var img = document.createElement("img");
      img.src = BASE + e.immagine; img.alt = ""; img.loading = "lazy"; img.decoding = "async";
      fig.appendChild(img);
    } else {
      var badge = document.createElement("div");
      badge.className = "carta-badge";
      badge.textContent = (e.nome || "?").trim().charAt(0).toUpperCase();
      if (e.colore && /^[0-9A-Fa-f]{6}$/.test(e.colore)) { badge.style.background = "#" + e.colore; }
      fig.appendChild(badge);
    }
    var cap = document.createElement("figcaption");
    var nome = document.createElement("strong"); nome.textContent = e.nome;
    cap.appendChild(nome);
    if (e.descrizione) { var ruolo = document.createElement("span"); ruolo.textContent = e.descrizione; cap.appendChild(ruolo); }
    fig.appendChild(cap);
    return fig;
  }

  function attive(t) {
    var ids = [];
    for (var i = eventi.length - 1; i >= 0 && ids.length < MAX; i--) {
      var ev = eventi[i];
      if (ev.inizio <= t && t <= ev.fine && ids.indexOf(ev.id) < 0) { ids.push(ev.id); }
    }
    return ids.reverse();      // la più recente a destra
  }

  var ultimaChiave = null;
  R.ascolta(function (t, forzato) {
    var chiave = Math.floor(t * 4);                 // 4 aggiornamenti al secondo bastano
    if (!forzato && chiave === ultimaChiave) { return; }
    ultimaChiave = chiave;
    var ids = attive(t);
    Object.keys(mostrate).forEach(function (id) {
      if (ids.indexOf(id) < 0) { cont.removeChild(mostrate[id]); delete mostrate[id]; }
    });
    ids.forEach(function (id) {
      if (!mostrate[id]) { mostrate[id] = carta(id); }
      cont.appendChild(mostrate[id]);               // riordina: appendChild sposta l'elemento esistente
    });
  });
})();
