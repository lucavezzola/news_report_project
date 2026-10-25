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

// telefono (schermo stretto) e scroll osservabile
w.matchMedia = (q) => ({ matches: /max-width: 899px/.test(q), addEventListener() {} });
const scrolli = [];
w.scrollBy = (o) => scrolli.push(o);

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
  // scroll sul telefono: la frase evidenziata NON deve finire dietro player + mappa fissi
  const rect = (top, bottom) => ({ top, bottom, height: bottom - top, left: 0, right: 0, width: 0 });
  doc.getElementById("player").getBoundingClientRect = () => rect(0, 90);
  doc.getElementById("visivo").getBoundingClientRect = () => rect(90, 300);       // mappa fissa: copre fino a y=300
  const f8 = doc.querySelectorAll(".frase")[8];
  f8.getBoundingClientRect = () => rect(120, 160);                                  // frase nascosta dietro la mappa
  scrolli.length = 0;
  vai(parseFloat(f8.getAttribute("data-inizio")) + 0.05);
  const areaUtile = 300 + (w.innerHeight - 300) / 2;                                // centro della zona visibile
  out.scroll_nascosta = scrolli.length === 1 ? scrolli[0].top : null;
  out.scroll_atteso = (120 + 20) - areaUtile;
  f8.getBoundingClientRect = () => rect(400, 440);                                  // già visibile sotto la mappa
  scrolli.length = 0;
  vai(parseFloat(f8.getAttribute("data-inizio")) + 0.06);
  out.scroll_se_visibile = scrolli.length;

  // layout: colonna visiva attiva; "Nascondi testo" e "Mappa e immagini" commutano le classi
  const layout = doc.getElementById("layout");
  out.layout_con_visivo = layout.classList.contains("con-visivo");
  out.visivo_dentro_layout = layout.contains(doc.getElementById("visivo"));
  doc.getElementById("toggle-testo").click();
  out.testo_nascosto = layout.classList.contains("testo-nascosto");
  out.etichetta_toggle = doc.getElementById("toggle-testo").textContent;
  doc.getElementById("toggle-testo").click();
  out.testo_ripristinato = !layout.classList.contains("testo-nascosto");
  const mv = doc.getElementById("mostra-visivo"); mv.checked = false; mv.dispatchEvent(new w.Event("change"));
  out.senza_visivo = layout.classList.contains("senza-visivo");
  mv.checked = true; mv.dispatchEvent(new w.Event("change"));
  // ---- mappa: etichette, storico tratteggiato e sbiadito, punto corrente pieno ----
  const dati = JSON.parse(doc.getElementById("dati-visivi").textContent);
  // ultimo istante della sezione Italia in cui il luogo corrente è un PUNTO (una città), con storico alle spalle
  const kfIt = dati.mappa.filter((k) => k.sezione === "italia" && k.evidenzia.some((l) => !dati.luoghi[l].poligono));
  vai(kfIt[kfIt.length - 1].t + 0.05);
  const tracciati = [...doc.querySelectorAll("#mappa .leaflet-luoghi-pane path")];
  const visibili = tracciati.filter((p) => parseFloat(p.getAttribute("stroke-opacity")) > 0);
  const tratteggiati = visibili.filter((p) => p.getAttribute("stroke-dasharray"));
  const pieni = visibili.filter((p) => !p.getAttribute("stroke-dasharray"));
  out.mappa_pieni = pieni.length;                                       // il corrente: bordo solido
  out.mappa_tratteggiati = tratteggiati.length;                         // lo storico: bordo tratteggiato
  out.mappa_opacita_storico = tratteggiati.map((p) => parseFloat(p.getAttribute("stroke-opacity")));
  out.etichette = [...doc.querySelectorAll("#mappa .etichetta-luogo")].map((e) => e.textContent);

  // ---- carte: logo intero per i non-persona, descrizione completa espandibile e trattenuta ----
  const frAnna = [...doc.querySelectorAll(".frase[data-entita]")][0];
  vai(parseFloat(frAnna.getAttribute("data-inizio")) + 0.1);
  let cartaAnna = doc.querySelector("#citati .carta");
  out.carta_persona_logo = cartaAnna.classList.contains("logo");
  out.carta_titolo_completo = cartaAnna.title.length > 90;              // la descrizione intera sta nel title
  cartaAnna.click();
  out.carta_espansa = cartaAnna.classList.contains("espansa") && cartaAnna.getAttribute("aria-expanded") === "true";
  vai(0.0);                                                              // la frase è lontana: la carta fissata resta
  out.carta_resta_se_fissata = doc.querySelectorAll("#citati .carta").length === 1;
  doc.querySelector("#citati .carta").click();                           // si richiude: non più attuale, sparisce
  out.carta_sparisce_dopo_chiusura = doc.querySelectorAll("#citati .carta").length === 0;
  const frBanca = [...doc.querySelectorAll(".frase[data-entita]")].find((f) => f.textContent.includes("Banca Centrale"));
  vai(parseFloat(frBanca.getAttribute("data-inizio")) + 0.1);
  out.carta_istituzione_logo = doc.querySelector("#citati .carta").classList.contains("logo");

  // ---- riproduzione in corso: il salto fra luoghi lontani non deve dare errori e deve concludersi ----
  inPausa = false;
  const kfEs = dati.mappa.filter((k) => k.sezione === "esteri" && k.evidenzia.length);
  tempo = kfEs[0].t + 0.05; audio.dispatchEvent(new w.Event("timeupdate"));
  await attendi(700);
  tempo = kfEs[kfEs.length - 1].t + 0.05; audio.dispatchEvent(new w.Event("timeupdate"));
  await attendi(700);
  out.dissolvenza_conclusa = !doc.getElementById("mappa").classList.contains("dissolvenza");
  inPausa = true;

  // ---- palette ----
  const sp = doc.getElementById("palette");
  out.palette_opzioni = [...sp.options].map((o) => o.value);
  sp.value = "menta"; sp.dispatchEvent(new w.Event("change"));
  out.palette_menta = doc.documentElement.getAttribute("data-palette");
  sp.value = "predefinita"; sp.dispatchEvent(new w.Event("change"));
  out.palette_tolta = doc.documentElement.getAttribute("data-palette");

  // tema e dimensione testo
  const bt = doc.getElementById("tema"); bt.click();
  out.tema_dopo_clic = doc.documentElement.getAttribute("data-tema");
  doc.getElementById("testo-piu").click();
  out.zoom = doc.documentElement.style.getPropertyValue("--zoom");
  console.log(JSON.stringify(out));
  process.exit(0);
})();
