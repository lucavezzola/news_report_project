# Rassegna Stampa Audio Giornaliera — Documento di Progettazione

**Obiettivo:** pipeline automatica che raccoglie notizie da fonti bilanciate, le sintetizza in un resoconto imparziale diviso per sezioni, lo converte in audio e lo consegna su Telegram ogni mattina.

**Costo stimato:** 1-5€/mese (solo API LLM; tutto il resto gira gratis in locale).

---

## 1. Architettura generale

```
[RSS Feeds] → [Script Python: fetch] → [File JSON grezzo]
                                            ↓
                              [Claude API: raggruppa + sintetizza]
                                            ↓
                                    [Testo per sezione]
                                            ↓
                              [Piper TTS: locale, in italiano]
                                            ↓
                                    [File audio .mp3/.ogg]
                                            ↓
                              [Telegram Bot API: invio automatico]
                                            ↓
                        [Canale/gruppo privato: tu + amici selezionati]
```

Tutto orchestrato da uno **scheduler** (Task Scheduler di Windows) che lancia lo script ogni mattina a un orario fisso.

---

## 2. Componenti in dettaglio

### 2.1 Raccolta dati (RSS ingestion)

**Libreria:** `feedparser` (Python)

**Fonti suggerite (bilanciate per costruzione):**
| Categoria | Fonte | Nota |
|---|---|---|
| Agenzia IT | ANSA | Linguaggio asciutto, poco interpretativo |
| Agenzia IT | AGI | Alternativa/complemento ad ANSA |
| Quotidiano IT (rotazione) | Corriere della Sera / Repubblica / Il Foglio / Il Giornale | Ruota settimanalmente per bilanciare il taglio editoriale nel tempo |
| Estero | BBC News | Generalmente percepita come bilanciata |
| Tech | Agenzia, taglio asciutto |
| Tech | Il Post - Tecnologia | Divulgativo, equilibrato |
| Tech | Wired Italia | Analitico, copre anche impatto sociale |
| Tech | Ars Technica | Analitico/tecnico, poco sensazionalismo |
| Tech | Agenda Digitale | Policy/normative, AI Act, PA digitale |

**Logica:**

- Ogni fonte ha un URL RSS pubblico e gratuito.
- Lo script scarica solo gli articoli delle ultime 24h (filtro su `published_parsed`).
- Salva tutto in un JSON intermedio: `{fonte, titolo, link, data, testo_estratto}`.

**Nota tecnica:** molti RSS danno solo titolo + estratto, non il testo completo. Per il corpo pieno serve un secondo step di scraping (es. `trafilatura`, libreria Python ottima per estrarre testo pulito da pagine HTML). Se vuoi restare più semplice, puoi anche lavorare solo su titolo+estratto: per un resoconto sintetico spesso basta.

### 2.2 Sintesi e analisi (il cuore del sistema)

**Motore:** Claude API (Haiku per costo, o Sonnet se vuoi qualità superiore su temi complessi — il costo resta comunque basso ai volumi di questo progetto).

**Cosa fa il prompt, concettualmente:**

1. Riceve tutti gli articoli del giorno raggruppati per fonte.
2. Li raggruppa per argomento/evento (stesso fatto raccontato da più fonti = un solo blocco).
3. Per ogni blocco:
   - Scrive i fatti condivisi in modo neutro.
   - Se le fonti divergono nel framing o nell'enfasi, lo segnala esplicitamente e nomina le fonti coinvolte.
4. Organizza l'output in sezioni fisse: **Italia, Esteri, Tecnologia**.
5. Scrive in **prosa parlata**: frasi brevi, niente elenchi puntati, niente markdown — deve suonare bene se letto ad alta voce.

**Punto critico — istruzioni esplicite di imparzialità nel prompt:**

- "Non usare aggettivi valutativi propri; riporta solo ciò che le fonti dicono."
- "Se una fonte usa un framing marcatamente diverso da un'altra sullo stesso fatto, segnalalo per nome, non appiattirlo."
- "Cita sempre da quale fonte proviene ogni affermazione specifica."
- "Se un fatto è riportato da una sola fonte, dillo esplicitamente (minore affidabilità)."

Questo prompt va scritto una volta e poi affinato nel tempo osservando gli output.

### 2.3 Sintesi vocale (TTS)

**Motore:** Piper (open source, locale, gratis)

- Gira bene sulla tua RTX 3060.
- Esistono voci italiane pre-addestrate di buona qualità pronte all'uso.
- Output: file `.wav` che poi converti in `.mp3`/`.ogg` (più leggero per l'invio) con `ffmpeg`.

**Alternativa se vuoi qualità vocale superiore:** servizi cloud (ElevenLabs) a pagamento — ma per un uso quotidiano personale, Piper è più che sufficiente e a costo zero.

### 2.4 Distribuzione

**Opzione consigliata: Telegram Bot**

- Crei un bot gratuito tramite **@BotFather** su Telegram (due minuti, nessun costo).
- Crei un canale privato o gruppo con i tuoi amici, aggiungi il bot come admin.
- Lo script, a fine pipeline, invia il file audio al canale via Telegram Bot API (libreria `python-telegram-bot`).

### 2.5 Orchestrazione

**Scheduler:** Task Scheduler di Windows, trigger giornaliero a un orario fisso (es. 6:30).

- Lo script Python principale (`main.py`) chiama in sequenza: fetch → sintesi → TTS → invio.
- Log su file per capire se qualcosa fallisce (es. una fonte RSS irraggiungibile quel giorno).

---

## 3. Stack tecnico riassuntivo

| Componente              | Strumento                 | Costo      |
| ----------------------- | ------------------------- | ---------- |
| Linguaggio              | Python 3.11+              | Gratis     |
| RSS parsing             | `feedparser`              | Gratis     |
| Estrazione testo (opz.) | `trafilatura`             | Gratis     |
| Sintesi/analisi         | Claude API (Haiku/Sonnet) | ~1-5€/mese |
| TTS                     | Piper (locale)            | Gratis     |
| Conversione audio       | `ffmpeg`                  | Gratis     |
| Distribuzione           | Telegram Bot API          | Gratis     |
| Scheduling              | Task Scheduler (Windows)  | Gratis     |

---

## 4. Roadmap di implementazione consigliata

1. **Fase 1 — Fetch:** script che scarica RSS e stampa a schermo i titoli del giorno. Verifica che le fonti funzionino.
2. **Fase 2 — Sintesi:** collega l'API Claude, scrivi e affina il prompt di sintesi imparziale, testa su output testuale (leggilo tu stesso prima di passare all'audio).
3. **Fase 3 — TTS:** installa Piper, genera il primo audio di prova dal testo della Fase 2.
4. **Fase 4 — Distribuzione:** crea il bot Telegram, automatizza l'invio.
5. **Fase 5 — Scheduling:** collega tutto a Task Scheduler, testa per una settimana osservando qualità e affidabilità.
6. **Fase 6 — Affinamento:** aggiusta fonti, sezioni, lunghezza e prompt in base a cosa funziona meglio per te nell'ascolto reale.

---

## 5. Limiti da tenere presenti

- **Nessun sistema è perfettamente imparziale.** La qualità del risultato dipende dalla qualità e varietà delle fonti scelte a monte, e dalla precisione del prompt di sintesi.
- **RSS non sempre dà il testo completo**: valuta se ti basta estratto+titolo o se serve lo scraping completo (più complesso, più fragile nel tempo se i siti cambiano struttura).
- **Piper in italiano** è buono ma non allo stesso livello delle voci commerciali più costose (ElevenLabs, ecc.) — per un uso personale quotidiano è comunque un compromesso ragionevole.
- **Manutenzione:** i feed RSS a volte cambiano URL o smettono di funzionare; va messo in conto un controllo occasionale.
