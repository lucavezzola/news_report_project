// Player con sottotitoli sincronizzati. Il testo è già nell'HTML (generato lato
// server con escape): qui si leggono solo attributi data-* e si cambiano classi.
// Mai innerHTML: il contenuto arriva da RSS -> Claude, quindi è non fidato.
// Espone window.Rassegna per i moduli opzionali (mappa.js, citati.js).
(function () {
  "use strict";
  var audio = document.getElementById("audio");
  if (!audio) return;
  var frasi = Array.prototype.slice.call(document.querySelectorAll(".frase"));
  var inizi = frasi.map(function (f) { return parseFloat(f.getAttribute("data-inizio")); });
  var autoscroll = document.getElementById("autoscroll");
  var corrente = -1;
  var ascoltatori = [], suFraseCb = [], suVisCb = [];

  window.Rassegna = {
    audio: audio,
    ascolta: function (fn) { ascoltatori.push(fn); },        // fn(t, forzato) a ogni aggiornamento
    suFrase: function (fn) { suFraseCb.push(fn); },          // fn(elementoFrase) quando cambia la frase
    suVisibilita: function (fn) { suVisCb.push(fn); },       // fn() quando il pannello visivo cambia dimensione
    mostraVisivo: function () {                              // chiamata da mappa.js / citati.js quando hanno dati
      var v = document.getElementById("visivo"), l = document.getElementById("layout");
      if (v) v.hidden = false;
      if (l) l.classList.add("con-visivo");
    }
  };

  function notifica(forzato) {
    var t = audio.currentTime;
    for (var i = 0; i < ascoltatori.length; i++) {
      try { ascoltatori[i](t, !!forzato); } catch (e) { /* un modulo rotto non ferma il player */ }
    }
  }

  // ricerca binaria: ultima frase con inizio <= t
  function indice(t) {
    var lo = 0, hi = inizi.length - 1, r = -1;
    while (lo <= hi) {
      var m = (lo + hi) >> 1;
      if (inizi[m] <= t) { r = m; lo = m + 1; } else { hi = m - 1; }
    }
    return r;
  }

  // Limite alto dell'area realmente visibile: sotto il player fisso e, sul telefono,
  // sotto la mappa fissa. Il testo evidenziato va centrato LÌ, non nello schermo intero.
  function limiteAltoUtile() {
    var player = document.getElementById("player"), visivo = document.getElementById("visivo");
    var alto = player ? player.getBoundingClientRect().bottom : 0;
    var stretto = window.matchMedia && window.matchMedia("(max-width: 899px)").matches;
    if (stretto && visivo && !visivo.hidden && getComputedStyle(visivo).display !== "none") {
      alto = Math.max(alto, visivo.getBoundingClientRect().bottom);
    }
    return Math.max(0, alto);
  }

  function scrollSuFrase(el, istantaneo) {
    var layout = document.getElementById("layout");
    if (layout && layout.classList.contains("testo-nascosto")) return;       // il testo non si vede
    var alto = limiteAltoUtile(), basso = window.innerHeight, margine = 16;
    var r = el.getBoundingClientRect();
    if (r.top >= alto + margine && r.bottom <= basso - margine) return;      // già ben visibile: non muovere
    var delta = (r.top + r.height / 2) - (alto + (basso - alto) / 2);
    window.scrollBy({ top: delta, behavior: istantaneo ? "auto" : "smooth" });
  }

  function aggiorna(forza, senzaScroll) {
    var i = indice(audio.currentTime);
    if (i !== corrente) {
      if (corrente >= 0) frasi[corrente].classList.remove("attiva");
      corrente = i;
      if (i >= 0) {
        frasi[i].classList.add("attiva");
        suFraseCb.forEach(function (fn) { try { fn(frasi[i]); } catch (e) {} });
        if (autoscroll && autoscroll.checked && !senzaScroll && (forza || !audio.paused)) {
          scrollSuFrase(frasi[i], forza);
        }
      }
    }
    notifica(forza);
  }

  function tick() {
    aggiorna(false);
    if (!audio.paused && !audio.ended) window.requestAnimationFrame(tick);
  }

  audio.addEventListener("play", tick);
  audio.addEventListener("timeupdate", function () { aggiorna(false); });
  audio.addEventListener("seeked", function () { aggiorna(true); });
  audio.addEventListener("ended", function () { aggiorna(false); });
  audio.addEventListener("loadedmetadata", function () { aggiorna(true, true); });

  function vai(t) {
    audio.currentTime = t;
    var p = audio.play();            // il clic dell'utente autorizza la riproduzione
    if (p && p.catch) p.catch(function () {});
    aggiorna(true);
  }

  frasi.forEach(function (f) {
    f.addEventListener("click", function () { vai(parseFloat(f.getAttribute("data-inizio"))); });
    f.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); vai(parseFloat(f.getAttribute("data-inizio"))); }
    });
  });
  Array.prototype.forEach.call(document.querySelectorAll("button.vai"), function (b) {
    b.addEventListener("click", function () { vai(parseFloat(b.getAttribute("data-t"))); });
  });

  var sel = document.getElementById("velocita");
  if (sel) sel.addEventListener("change", function () { audio.playbackRate = parseFloat(sel.value) || 1; });
  audio.addEventListener("play", function () { if (sel) audio.playbackRate = parseFloat(sel.value) || 1; });

  // ---- preferenze (tema, dimensione testo, pannello visivo): mai bloccanti ----
  function leggi(k) { try { return window.localStorage.getItem("rassegna:" + k); } catch (e) { return null; } }
  function scrivi(k, v) { try { window.localStorage.setItem("rassegna:" + k, v); } catch (e) {} }
  var radice = document.documentElement;

  var btnTema = document.getElementById("tema");
  var temi = ["auto", "chiaro", "scuro"];
  function applicaTema(t) {
    if (t === "chiaro" || t === "scuro") radice.setAttribute("data-tema", t); else radice.removeAttribute("data-tema");
    if (btnTema) btnTema.textContent = "Tema: " + (t === "chiaro" || t === "scuro" ? t : "auto");
    document.dispatchEvent(new CustomEvent("rassegna:tema"));
  }
  var temaAttuale = leggi("tema") || "auto";
  if (btnTema) {
    applicaTema(temaAttuale);
    btnTema.addEventListener("click", function () {
      temaAttuale = temi[(temi.indexOf(temaAttuale) + 1) % temi.length];
      scrivi("tema", temaAttuale === "auto" ? "" : temaAttuale);
      applicaTema(temaAttuale);
    });
  }

  // palette pastello: ogni palette è solo un valore dell'attributo data-palette (le formule sono nel CSS)
  var PALETTE = ["menta", "lavanda", "pesca", "cielo", "rosa", "limone", "salvia"];
  var selPalette = document.getElementById("palette");
  function applicaPalette(p) {
    if (PALETTE.indexOf(p) >= 0) radice.setAttribute("data-palette", p); else radice.removeAttribute("data-palette");
    document.dispatchEvent(new CustomEvent("rassegna:tema"));      // la mappa rilegge i colori
  }
  if (selPalette) {
    var pSalvata = leggi("palette");
    selPalette.value = PALETTE.indexOf(pSalvata) >= 0 ? pSalvata : "predefinita";
    selPalette.addEventListener("change", function () {
      scrivi("palette", selPalette.value === "predefinita" ? "" : selPalette.value);
      applicaPalette(selPalette.value);
    });
  }

  var zoom = parseFloat(leggi("zoom")) || 1;
  function applicaZoom(z) {
    zoom = Math.max(0.8, Math.min(1.6, Math.round(z * 100) / 100));
    radice.style.setProperty("--zoom", zoom);
    scrivi("zoom", zoom);
  }
  var piu = document.getElementById("testo-piu"), meno = document.getElementById("testo-meno");
  if (piu) piu.addEventListener("click", function () { applicaZoom(zoom + 0.1); });
  if (meno) meno.addEventListener("click", function () { applicaZoom(zoom - 0.1); });

  var layout = document.getElementById("layout");
  var mostra = document.getElementById("mostra-visivo"), visivo = document.getElementById("visivo");
  function ridimensionato() { suVisCb.forEach(function (fn) { try { fn(); } catch (e) {} }); }

  // "Mappa e immagini": mostra/nasconde la colonna di destra (il testo torna a tutta larghezza)
  if (mostra && visivo && layout) {
    mostra.checked = leggi("visivo") !== "0";
    var applicaVisivo = function () {
      layout.classList.toggle("senza-visivo", !mostra.checked);
      ridimensionato();
    };
    mostra.addEventListener("change", function () { scrivi("visivo", mostra.checked ? "1" : "0"); applicaVisivo(); });
    applicaVisivo();
  }

  // "Nascondi testo": la mappa prende tutta la larghezza
  var btnTesto = document.getElementById("toggle-testo");
  if (btnTesto && layout) {
    var applicaTesto = function (nascosto) {
      layout.classList.toggle("testo-nascosto", nascosto);
      btnTesto.textContent = nascosto ? "Mostra testo" : "Nascondi testo";
      btnTesto.setAttribute("aria-expanded", nascosto ? "false" : "true");
      ridimensionato();
    };
    applicaTesto(leggi("testo") === "0");
    btnTesto.addEventListener("click", function () {
      var nascondi = !layout.classList.contains("testo-nascosto");
      scrivi("testo", nascondi ? "0" : "1");
      applicaTesto(nascondi);
    });
  }

  // l'area visiva resta ferma sotto il player: serve l'altezza del player
  var player = document.getElementById("player");
  function misuraPlayer() { if (player) radice.style.setProperty("--alt-player", player.offsetHeight + "px"); }
  misuraPlayer();
  if (window.ResizeObserver) {
    if (player) new ResizeObserver(misuraPlayer).observe(player);
    if (visivo) new ResizeObserver(ridimensionato).observe(visivo);
  }

  // ---- Media Session: controlli a schermo bloccato (nessun autoplay) ----
  if ("mediaSession" in navigator) {
    var meta = {};
    try { meta = JSON.parse(document.getElementById("meta-episodio").textContent); } catch (e) {}
    try {
      navigator.mediaSession.metadata = new window.MediaMetadata({
        title: meta.titolo || document.title, artist: meta.artista || "", album: meta.album || ""
      });
    } catch (e) {}
    var azioni = {
      play: function () { audio.play(); },
      pause: function () { audio.pause(); },
      seekbackward: function () { audio.currentTime = Math.max(0, audio.currentTime - 10); },
      seekforward: function () { audio.currentTime = Math.min(audio.duration || Infinity, audio.currentTime + 10); },
      seekto: function (d) { if (d && typeof d.seekTime === "number") audio.currentTime = d.seekTime; }
    };
    Object.keys(azioni).forEach(function (k) {
      try { navigator.mediaSession.setActionHandler(k, azioni[k]); } catch (e) {}
    });
  }

  // ---- PWA: solo su https o localhost; il service worker non tocca mai l'audio ----
  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("../sw.js", { scope: "../" }).catch(function () {});
    });
  }

  aggiorna(true, true);        // stato iniziale: evidenzia la frase ma non sposta la pagina
})();
