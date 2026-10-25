# Policy delle immagini e delle schede "Citati ora"

Principio: **meglio nessuna immagine che quella sbagliata.** Non è consulenza legale.

1. **Chi sceglie.** Claude fornisce solo nome, tipo e descrizione dell'entità; il codice risolve su Wikidata.
   Gli ID Wikidata non sono mai generati dal modello.
2. **Quando compare una scheda.** Solo se Wikidata conferma l'entità: nome coerente (etichetta o alias),
   classe coerente (per le persone: essere umano, Q5), almeno 10 sitelinks (soglia di notorietà),
   punteggio ≥ 5 e distacco ≥ 2 dal secondo candidato. Un nome parziale (solo il cognome) vale solo
   se la descrizione lo conferma. **Una persona non risolta non compare mai, nemmeno come semplice nome.**
3. **Quale immagine.** Sempre quella predefinita di Wikidata (P18 persone; P154 logo per partiti,
   aziende, istituzioni; P41/P94 per i paesi). Nessuna scelta manuale, stesso trattamento per tutti.
4. **Licenze ammesse.** CC BY, CC BY-SA, CC0, pubblico dominio. Rifiutate: NC (non commerciale),
   ND (noi ridimensioniamo), fair use, licenze assenti o sconosciute. Se la licenza non va, la scheda
   resta senza immagine (badge con l'iniziale).
5. **Crediti.** Autore, licenza (con link) e pagina Wikimedia Commons sono salvati e mostrati in fondo alla pagina.
6. **Niente hotlinking.** Le immagini (miniatura 400 px) sono scaricate e servite dal tuo sito.
7. **Marchi.** I loghi possono essere liberi da copyright ma restare marchi registrati: uso informativo, non commerciale.
8. **Se il sito diventasse pubblico,** rivalutare licenze, privacy delle persone citate e termini di Wikimedia.

## Correzioni manuali: `data/entita_override.json`

    {
      "Mario Rossi":   {"azione": "blocca"},            // nessuna scheda, mai
      "Anna Verdi":    {"azione": "senza_immagine"},    // scheda solo testuale
      "Paolo Bianchi": {"qid": "Q12345"}                // forza l'entità giusta
    }

Le chiavi non distinguono maiuscole/accenti. Per i luoghi: `data/luoghi_override.json`:

    {
      "Crimea":   {"ignora": true},
      "Taranto":  {"lat": 40.4644, "lon": 17.2470, "paese": "IT", "tipo": "citta"}
    }

## Perché una persona o un partito non ha l'immagine? `diagnosi_entita.py`

    python diagnosi_entita.py "Giorgia Meloni" --tipo persona --descrizione "presidente del Consiglio"
    python diagnosi_entita.py "Partito Democratico" --tipo partito

Mostra i candidati di Wikidata con punteggio o motivo dello scarto, quello scelto, le immagini candidate
(persone: P18, anche più d'una; loghi: P154) e la licenza di ciascuna con l'esito ammessa/rifiutata.
Le stesse informazioni finiscono in `logs/wikidata.log` ("candidato per ...", "Immagine ... scartata: licenza non ammessa: ...").

Cause tipiche e rimedi:
- **Licenza non ammessa** (molti loghi di partito e foto istituzionali non sono CC BY/CC0/pubblico dominio):
  se dopo averla letta decidi che per te va bene, aggiungi un'espressione in `config.LICENZE_EXTRA_AMMESSE`,
  per esempio `[r"iodl"]`. Se la prima immagine non va, si prova automaticamente la successiva (fino a 3).
- **Nome abbreviato** ("Meloni", "Pd"): Claude ora scrive sempre il nome completo e ufficiale nel campo `nome`.
- **Omonimi**: il più noto vince grazie al bonus di notorietà (+1 per ogni raddoppio dei sitelinks oltre 10).
- **Nessuna immagine su Wikidata** per quell'entità: la scheda compare comunque, con un riquadro testuale.
- **Entità sbagliata o non trovata**: forza il QID giusto in `data/entita_override.json`.
