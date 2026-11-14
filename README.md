# Stroomprijzen per uur

Dynamische stroomprijzen per uur, met een advies voor het uitstel van een
wasmachine: het goedkoopste uur binnen een zelf gekozen tijdvenster
(standaard: starten vanaf 07:00, klaar vóór 22:00, programma van 2 uur).

Live pagina: https://geestsoft.github.io/stroomprijzen/

## Bestanden

| Bestand | Doel |
| --- | --- |
| `stroomprijzen.py` | Basis: haalt de uurprijzen op en toont ze met het wasmachine-advies in de terminal. |
| `maak_html.py` | Schrijft de prijzen in een zelfstandige HTML-pagina die het advies zelf in de browser uitrekent. |
| `stroomprijzen_web.py` | Kleine webserver voor lokaal gebruik (niet nodig voor GitHub Pages). |
| `.github/workflows/pages.yml` | Draait `maak_html.py` drie keer per dag en publiceert de pagina via GitHub Pages. |

`maak_html.py` en `stroomprijzen_web.py` gebruiken `stroomprijzen.py`; houd ze in dezelfde map.

## Gebruik

```
python3 stroomprijzen.py                   # vandaag + wachttijd wasmachine
python3 stroomprijzen.py --duur 3          # programma duurt 3 uur
python3 stroomprijzen.py --van 8 --tot 21  # machine mag tussen 08:00 en 21:00
python3 stroomprijzen.py --morgen          # tabel van morgen (bekend vanaf ca. 13:00)

python3 maak_html.py --uit site/index.html # zelfstandige HTML-pagina maken
python3 stroomprijzen_web.py               # lokale webserver op http://127.0.0.1:8080
```

Geen installatie nodig: alleen Python 3 (standaardbibliotheek).

## Hoe het werkt

- De prijzen komen van de publieke MCP-server van jeroen.nl (zonder inloggen).
- De all-in prijs is indicatief: marktprijs + energiebelasting + gemiddelde
  leveranciersvergoeding + 21% btw. Een eigen leverancier kan afwijken.
- Het uitstel wordt in hele uren, naar boven afgerond, gerekend vanaf het moment
  van kijken. De machine moet binnen het tijdvenster starten en klaar zijn.
- De prijs die telt is die van het uur waarin de machine start.

## Voorwaarden en bron

Alleen voor persoonlijk gebruik. Maximaal 60 aanroepen per uur per IP-adres, zie
de [voorwaarden van jeroen.nl](https://jeroen.nl/api-voorwaarden).

Bron van de prijzen: [jeroen.nl](https://jeroen.nl)
