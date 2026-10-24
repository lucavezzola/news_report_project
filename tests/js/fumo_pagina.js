// Test di fumo del front-end in jsdom: carica la pagina generata, esegue app.js,
// leaflet, mappa e citati, simula riproduzione/seek/clic e verifica lo stato del DOM.
// Uso: node fumo_pagina.js <cartella t/<token>> <AAAA-MM-GG>
// NON sostituisce una prova su browser vero (layout, animazioni, touch).
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

const [radice, giorno] = process.argv.slice(2);
const html = fs.readFileSync(path.join(radice, giorno, "index.html"), "utf8");
const errori = [];
const vc = new VirtualConsole();
vc.on("jsdomError", (e) => { if (!/Not implemented/.test(String(e.message))) errori.push("jsdomError: " + e.message); });
vc.on("error", (m) => errori.push("console.error: " + m));

const dom = new JSDOM(html, { url: `http://localhost/t/TOKEN/${giorno}/`, runScripts: "outside-only", pretendToBeVisual: true, virtualConsole: vc });
const w = dom.window;
w.addEventListener("error", (e) => errori.push("window.onerror: " + e.message));

// ambiente minimo: SVG per Leaflet, dimensioni, audio finto, fetch dei confini da disco
w.SVGElement.prototype.createSVGRect = () => ({});
Object.defineProperty(w.HTMLElement.prototype, "clientWidth", { get() { return 360; } });
Object.defineProperty(w.HTMLElement.prototype, "clientHeight", { get() { return 200; } });
w.HTMLElement.prototype.scrollIntoView = function () {};
const audio = w.document.getElementById("audio");
let tempo = 0, inPausa = true;
Object.defineProperty(audio, "currentTime", { get: () => tempo, set: (v) => { tempo = v; } });
Object.defineProperty(audio, "paused", { get: () => inPausa });
audio.play = () => { inPausa = false; return Promise.resolve(); };
w.fetch = (url) => {
  const rel = new URL(url, `http://localhost/t/TOKEN/${giorno}/`).pathname.replace("/t/TOKEN/", "");
  const f = path.join(radice, rel);
  return fs.existsSync(f) ? Promise.resolve({ ok: true, json: () => Promise.resolve(JSON.parse(fs.readFileSync(f, "utf8"))) })
                          : Promise.reject(new Error("404 " + rel));
};

// esegue gli script nell'ordine del documento
for (const s of w.document.querySelectorAll("script[src]")) {
  const file = path.join(radice, giorno, s.getAttribute("src"));
  try { w.eval(fs.readFileSync(path.normalize(file), "utf8")); } catch (e) { errori.push(`script ${s.getAttribute("src")}: ${e.message}`); }
}

const attendi = (ms) => new Promise((r) => setTimeout(r, ms));
const vai = (t) => { tempo = t; audio.dispatchEvent(new w.Event("seeked")); };
const out = { errori };

(async () => {
  await attendi(300);                         // caricamento dei confini
  const doc = w.document;
  out.ha_Rassegna = !!w.Rassegna;
  out.frasi = doc.querySelectorAll(".frase").length;
  out.visivo_visibile = doc.getElementById("visivo") ? !doc.getElementById("visivo").hidden : null;
  out.percorsi_mappa = doc.querySelectorAll("#mappa path").length;

  // clic su una frase -> il tempo salta al suo inizio
  const frase = doc.querySelectorAll(".frase")[5];
  frase.click();
  out.clic_ok = Math.abs(tempo - parseFloat(frase.getAttribute("data-inizio"))) < 1e-6;
  out.attive_dopo_clic = doc.querySelectorAll(".frase.attiva").length;

  // seek a tempi sparsi (avanti e indietro): una sola frase attiva, al massimo 3 carte
  const tot = parseFloat(doc.querySelectorAll(".frase")[out.frasi - 1].getAttribute("data-fine"));
  out.seek = [];
  for (const f of [0.1, 0.5, 0.9, 0.2, 0.75, 0.0, 1.0]) {
    vai(tot * f);
    out.seek.push({ t: +(tot * f).toFixed(1), attive: doc.querySelectorAll(".frase.attiva").length,
                    carte: doc.querySelectorAll("#citati .carta").length,
                    nomi: [...doc.querySelectorAll("#citati .carta strong")].map((n) => n.textContent) });
  }
  // tempo in cui compare Anna Verdi (seek diretto sulla sua frase)
  const conEntita = [...doc.querySelectorAll(".frase[data-entita]")][0];
  if (conEntita) {
    vai(parseFloat(conEntita.getAttribute("data-inizio")) + 0.1);
    out.carta_prima_entita = [...doc.querySelectorAll("#citati .carta strong")].map((n) => n.textContent);
    out.immagini_carte = [...doc.querySelectorAll("#citati img")].map((i) => i.getAttribute("src"));
  }
  // niente HTML iniettato né script inattesi
  out.script_nel_citati = doc.querySelectorAll("#citati script").length;
  // tema e dimensione testo
  const bt = doc.getElementById("tema"); bt.click();
  out.tema_dopo_clic = doc.documentElement.getAttribute("data-tema");
  doc.getElementById("testo-piu").click();
  out.zoom = doc.documentElement.style.getPropertyValue("--zoom");
  console.log(JSON.stringify(out));
  process.exit(0);
})();
