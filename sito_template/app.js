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
    suVisibilita: function (fn) { suVisCb.push(fn); }        // fn() quando il pannello visivo cambia dimensione
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

  function aggiorna(forza) {
    var i = indice(audio.currentTime);
    if (i !== corrente) {
      if (corrente >= 0) frasi[corrente].classList.remove("attiva");
      corrente = i;
      if (i >= 0) {
        frasi[i].classList.add("attiva");
        suFraseCb.forEach(function (fn) { try { fn(frasi[i]); } catch (e) {} });
        if (autoscroll && autoscroll.checked && (forza || !audio.paused)) {
          frasi[i].scrollIntoView({ block: "center", behavior: forza ? "auto" : "smooth" });
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
  audio.addEventListener("loadedmetadata", function () { aggiorna(true); });

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

  var zoom = parseFloat(leggi("zoom")) || 1;
  function applicaZoom(z) {
    zoom = Math.max(0.8, Math.min(1.6, Math.round(z * 100) / 100));
    radice.style.setProperty("--zoom", zoom);
    scrivi("zoom", zoom);
  }
  var piu = document.getElementById("testo-piu"), meno = document.getElementById("testo-meno");
  if (piu) piu.addEventListener("click", function () { applicaZoom(zoom + 0.1); });
  if (meno) meno.addEventListener("click", function () { applicaZoom(zoom - 0.1); });

  var mostra = document.getElementById("mostra-visivo"), visivo = document.getElementById("visivo");
  if (mostra && visivo) {
    mostra.checked = leggi("visivo") !== "0";
    var applicaVisivo = function () {
      visivo.classList.toggle("nascosto", !mostra.checked);
      suVisCb.forEach(function (fn) { try { fn(); } catch (e) {} });
    };
    mostra.addEventListener("change", function () { scrivi("visivo", mostra.checked ? "1" : "0"); applicaVisivo(); });
    applicaVisivo();
  }
  if (window.ResizeObserver && visivo) {
    new ResizeObserver(function () { suVisCb.forEach(function (fn) { try { fn(); } catch (e) {} }); }).observe(visivo);
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

  aggiorna(true);
})();
