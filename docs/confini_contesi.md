# Confini contestati: scelta editoriale da fare

La mappa disegna i paesi con **Natural Earth 1:50m** (`ne_50m_admin_0_countries`, pubblico dominio),
che rappresenta i confini *de facto* e in alcuni casi non coincide con la posizione di altri
organismi. Il sito ha una rassegna "imparziale": questa è una decisione tua, non tecnica.

## Cosa dicono i dati scaricati (verificato con punti campione, non a memoria)

| Punto | Poligono in cui cade |
|---|---|
| Simferopoli (Crimea) | Russia |
| Donetsk | Ucraina |
| Srinagar (Kashmir) | India |
| Taipei | Taiwan (poligono separato, codice TW) |
| Gerusalemme Est (coordinate approssimate) | Palestina |
| Laayoune (Sahara Occidentale) | Marocco |

## Cosa fa già il codice per non prendere posizione

- Solo un luogo di tipo **"paese"** evidenzia il poligono di un paese.
- Un luogo non italiano di tipo regione, città o altro (es. "Crimea", "Donbass") diventa **solo un marker
  puntiforme**: non colora mai né la Russia né l'Ucraina.
- Se Claude indica un paese incoerente col nome del luogo, il luogo viene scartato.

## Cosa NON risolve

I confini restano disegnati come nei dati: con "Ucraina" evidenziata, la Crimea appare fuori dal poligono
ucraino. Se vuoi una linea diversa (es. confini riconosciuti dall'ONU), dimmelo: va sostituito il dataset
in `scarica_geo.py`; il resto del sistema non cambia.

## Correzioni puntuali

`data/luoghi_override.json` permette di forzare un singolo luogo (vedi `docs/README_v2.md`).
