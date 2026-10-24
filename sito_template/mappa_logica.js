// Logica pura della mappa (nessun DOM, nessuna libreria): dato l'elenco dei
// keyframe e un tempo, calcola vista e luoghi evidenziati. Rispecchia
// mappa.stato_a() di mappa.py ed è testata con Node (tests/test_mappa_js.py).
(function (radice, fabbrica) {
  if (typeof module === "object" && module.exports) { module.exports = fabbrica(); }
  else { radice.RassegnaMappaLogica = fabbrica(); }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  var MONDO = { tipo: "mondo" };

  // Lo stato dipende SOLO da (keyframe, t): dopo un seek, avanti o indietro,
  // si ricostruisce esattamente quello che si sarebbe visto ascoltando di seguito.
  function calcolaStato(kfs, t) {
    var i = -1, lo = 0, hi = kfs.length - 1;
    while (lo <= hi) {
      var m = (lo + hi) >> 1;
      if (kfs[m].t <= t) { i = m; lo = m + 1; } else { hi = m - 1; }
    }
    if (i < 0) { return { vista: MONDO, attivi: [], citati: [], indice: -1 }; }
    var k = kfs[i], attivi = k.evidenzia.slice(), citati = [];
    if (k.cumula) {
      for (var j = i - 1; j >= 0 && kfs[j].sezione === k.sezione && kfs[j].cumula; j--) {
        kfs[j].evidenzia.forEach(function (l) {
          if (attivi.indexOf(l) < 0 && citati.indexOf(l) < 0) { citati.push(l); }
        });
      }
    }
    return { vista: k.vista, attivi: attivi, citati: citati, indice: i };
  }

  return { calcolaStato: calcolaStato };
});
