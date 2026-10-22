// Player con sottotitoli sincronizzati. Il testo è già nell'HTML (generato lato
// server con escape): qui si leggono solo attributi data-* e si cambiano classi.
// Mai innerHTML: il contenuto arriva da RSS -> Claude, quindi è non fidato.
(function () {
  "use strict";
  var audio = document.getElementById("audio");
  if (!audio) return;
  var frasi = Array.prototype.slice.call(document.querySelectorAll(".frase"));
  var inizi = frasi.map(function (f) { return parseFloat(f.getAttribute("data-inizio")); });
  var autoscroll = document.getElementById("autoscroll");
  var corrente = -1;

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
    if (i === corrente) return;
    if (corrente >= 0) frasi[corrente].classList.remove("attiva");
    corrente = i;
    if (i >= 0) {
      frasi[i].classList.add("attiva");
      if (autoscroll && autoscroll.checked && (forza || !audio.paused)) {
        frasi[i].scrollIntoView({ block: "center", behavior: forza ? "auto" : "smooth" });
      }
    }
  }

  function tick() {
    aggiorna(false);
    if (!audio.paused && !audio.ended) window.requestAnimationFrame(tick);
  }

  audio.addEventListener("play", tick);
  audio.addEventListener("timeupdate", function () { aggiorna(false); });
  audio.addEventListener("seeked", function () { aggiorna(true); });
  audio.addEventListener("ended", function () { aggiorna(false); });

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

  // Media Session: controlli a schermo bloccato (nessun autoplay).
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
})();
