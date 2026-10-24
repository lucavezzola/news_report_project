// Legge da stdin {"keyframes": [...], "tempi": [...]} e stampa lo stato calcolato
// da sito_template/mappa_logica.js a ciascun tempo.
const path = require("path");
const { calcolaStato } = require(path.join(__dirname, "../../sito_template/mappa_logica.js"));
let dati = "";
process.stdin.on("data", (c) => (dati += c));
process.stdin.on("end", () => {
  const { keyframes, tempi } = JSON.parse(dati);
  console.log(JSON.stringify(tempi.map((t) => calcolaStato(keyframes, t))));
});
