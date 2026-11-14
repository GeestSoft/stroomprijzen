#!/usr/bin/env python3
"""Webpagina met de stroomprijzen per uur en advies voor je wasmachine.

Draait een kleine webserver op deze computer. Open daarna in je browser:
    http://127.0.0.1:8080

Gebruik:
    python3 stroomprijzen_web.py                  # alleen bereikbaar op deze computer
    python3 stroomprijzen_web.py --port 9000      # andere poort
    python3 stroomprijzen_web.py --host 0.0.0.0   # ook bereikbaar vanaf andere
                                                  # apparaten in je thuisnetwerk

Stoppen: Ctrl+C in het terminalvenster.

Dit bestand gebruikt stroomprijzen.py (zelfde map) om de prijzen op te halen.
De prijzen worden enkele minuten bewaard, zodat verversen van de pagina niet
elke keer een aanroep naar jeroen.nl kost (limiet: 60 per uur).

Voorwaarden: https://jeroen.nl/api-voorwaarden
Alleen voor persoonlijk gebruik: zet deze pagina niet open op internet.
Bron van de prijzen: jeroen.nl, https://jeroen.nl
"""

import sys

sys.dont_write_bytecode = True  # geen __pycache__ in deze map

import argparse
import html
import math
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import stroomprijzen as sp

TTL_MET_DATA = 600   # seconden dat gevonden prijzen bewaard blijven
TTL_ZONDER_DATA = 300  # eerder opnieuw proberen als er nog niets is (bv. morgen voor 13:00)

_cache = {}
_cache_lock = threading.Lock()


# ----------------------------------------------------------------- gegevens

def prijzen(dag):
    """Geeft (uren, foutmelding) voor een dag, met een korte cache."""
    nu = time.time()
    with _cache_lock:
        item = _cache.get(dag)
        if item and nu - item["tijd"] < item["ttl"]:
            return item["uren"], item["fout"]

    try:
        uren, fout = sp.haal_uurprijzen(dag), None
    except sp.ServerFout as f:
        uren, fout = [], str(f)

    with _cache_lock:
        oud = _cache.get(dag)
        if fout and oud and oud["uren"]:
            # Verversen mislukt: toon de eerder opgehaalde prijzen nog even.
            uren = oud["uren"]
        ttl = TTL_MET_DATA if uren else TTL_ZONDER_DATA
        _cache[dag] = {"tijd": nu, "uren": uren, "fout": fout, "ttl": ttl}
    return uren, fout


def bereken_advies(vandaag, uren_vandaag, uren_morgen, venster, van, tot, duur, nu):
    """Zoekt het goedkoopste toegestane moment. Geeft een dict of None."""
    einde = nu + timedelta(hours=venster)
    kandidaten = sp.maak_kandidaten(vandaag, uren_vandaag)
    kandidaten += sp.maak_kandidaten(vandaag + timedelta(days=1), uren_morgen)

    mogelijk = []
    for uur_start, prijs in kandidaten:
        if uur_start + timedelta(hours=1) <= nu or uur_start >= einde:
            continue
        wacht_min = max(0.0, (uur_start - nu).total_seconds() / 60)
        uitstel = math.ceil(wacht_min / 60)
        echte_start = nu + timedelta(hours=uitstel)
        if sp.binnen_tijdvenster(echte_start, duur, van, tot):
            mogelijk.append((uur_start, prijs, uitstel, echte_start, wacht_min))

    if not mogelijk:
        return None

    uur_start, prijs, uitstel, echte_start, wacht_min = min(
        mogelijk, key=lambda item: (item[1], item[0])
    )
    return {
        "uur_start": uur_start,
        "prijs": prijs,
        "uitstel": uitstel,
        "echte_start": echte_start,
        "klaar": echte_start + timedelta(hours=duur),
        "wacht_min": wacht_min,
    }


# ------------------------------------------------------------------- weergave

CSS = """
:root{--bg:#f4f6f9;--fg:#1c2330;--muted:#5d6879;--card:#ffffff;--line:#dfe3ea;
--accent:#2563eb;--bar:#9db9f2;--good:#15803d;--bad:#b91c1c;--mark:#fff4c2;}
@media (prefers-color-scheme: dark){
:root{--bg:#12151b;--fg:#e6e9ef;--muted:#9aa4b5;--card:#1b2029;--line:#2c3340;
--accent:#7aa2ff;--bar:#41609f;--good:#4ade80;--bad:#f87171;--mark:#3a3416;}}
*{box-sizing:border-box}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);
font:16px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1000px;margin:0 auto}
h1{font-size:1.5rem;margin:0 0 4px}
h2{font-size:1.1rem;margin:0 0 10px}
.stil{color:var(--muted);font-size:.9rem}
.kaart{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:16px;margin:14px 0}
.advies{border-left:6px solid var(--accent)}
.groot{font-size:2rem;font-weight:700;margin:4px 0}
.fout{border-left:6px solid var(--bad)}
.melding{color:var(--bad);margin:0 0 8px}
form{display:flex;flex-wrap:wrap;gap:12px;align-items:end}
label{display:flex;flex-direction:column;font-size:.85rem;color:var(--muted)}
input[type=number]{width:96px;padding:6px;font-size:1rem;border:1px solid var(--line);
border-radius:6px;background:var(--bg);color:var(--fg)}
button{padding:8px 16px;font-size:1rem;border:0;border-radius:6px;
background:var(--accent);color:#fff;cursor:pointer}
.tabellen{display:grid;grid-template-columns:1fr;gap:14px}
@media (min-width:760px){.tabellen{grid-template-columns:1fr 1fr}}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th{text-align:left;font-size:.8rem;color:var(--muted);font-weight:600;
border-bottom:1px solid var(--line);padding:4px 6px}
td{padding:3px 6px;border-bottom:1px solid var(--line);font-size:.95rem}
td.p,th.p{text-align:right}
.balk{display:block;height:12px;background:var(--bar);border-radius:3px;min-width:4px}
tr.laagste .balk{background:var(--good)}
tr.hoogste .balk{background:var(--bad)}
tr.nu td{font-weight:700}
tr.advies td{background:var(--mark)}
.badge{font-size:.7rem;padding:1px 6px;border-radius:9px;border:1px solid var(--line);
color:var(--muted);margin-left:4px;white-space:nowrap}
footer{margin:18px 0 8px;color:var(--muted);font-size:.85rem}
a{color:var(--accent)}
"""


def eur(waarde):
    return "-" if waarde is None else f"{waarde:.4f}".replace(".", ",")


def duur_tekst(minuten):
    return sp.formatteer_duur(minuten)


def tabel_html(titel, dag, uren, lo, hi, nu, advies_start):
    if not uren:
        return (f'<section class="kaart"><h2>{html.escape(titel)}</h2>'
                f'<p class="stil">Nog geen prijzen bekend.</p></section>')

    allin = [u[2] for u in uren if u[2] is not None]
    dag_lo, dag_hi = min(allin), max(allin)
    gemiddeld = sum(allin) / len(allin)

    rijen = []
    for uur, markt, prijs in uren:
        klassen, badges = [], []
        if prijs is not None and prijs == dag_lo:
            klassen.append("laagste")
            badges.append("laagste")
        elif prijs is not None and prijs == dag_hi:
            klassen.append("hoogste")
            badges.append("hoogste")
        if dag == nu.date() and uur == f"{nu.hour:02d}:00":
            klassen.append("nu")
            badges.append("nu")
        if (advies_start is not None and advies_start.date() == dag
                and advies_start.strftime("%H:%M") == uur):
            klassen.append("advies")
            badges.append("advies")

        if prijs is None:
            breedte = 0
        elif hi > lo:
            breedte = round(8 + 92 * (prijs - lo) / (hi - lo))
        else:
            breedte = 50
        badge_html = "".join(f'<span class="badge">{b}</span>' for b in badges)
        rijen.append(
            f'<tr class="{" ".join(klassen)}"><td>{html.escape(uur)}{badge_html}</td>'
            f'<td class="p">{eur(markt)}</td><td class="p">{eur(prijs)}</td>'
            f'<td style="width:28%"><span class="balk" style="width:{breedte}%"></span></td></tr>'
        )

    return (
        f'<section class="kaart"><h2>{html.escape(titel)} '
        f'<span class="stil">({dag.strftime("%d-%m-%Y")})</span></h2>'
        '<table><thead><tr><th>Uur</th><th class="p">Markt<br>excl. btw</th>'
        '<th class="p">All-in<br>incl. btw</th><th></th></tr></thead><tbody>'
        + "".join(rijen)
        + "</tbody></table>"
        f'<p class="stil">Gemiddeld all-in: {eur(gemiddeld)} &middot; '
        f'laagste: {eur(dag_lo)} &middot; hoogste: {eur(dag_hi)} (EUR per kWh)</p>'
        "</section>"
    )


def advies_html(advies, uren_vandaag, fout_vandaag, uren_morgen, vandaag, van, tot, duur):
    if not uren_vandaag:
        reden = html.escape(fout_vandaag or "geen prijzen beschikbaar")
        return f'<section class="kaart fout"><h2>Geen prijzen</h2><p>{reden}</p></section>'

    voorwaarde = (f"Starten vanaf {van:02d}:00 en klaar v&oacute;&oacute;r {tot:02d}:00 "
                  f"(programma van {duur} uur).")
    morgen_nog_niet = ""
    if not uren_morgen:
        morgen_nog_niet = ('<p class="stil">De prijzen van morgen zijn nog niet bekend '
                           "(verwacht rond 13:00); er is alleen tot middernacht gekeken.</p>")

    if advies is None:
        return ('<section class="kaart advies"><h2>Wasmachine</h2>'
                "<p>Geen geschikt moment gevonden in deze periode.</p>"
                f'<p class="stil">{voorwaarde}</p>{morgen_nog_niet}</section>')

    dagnaam = "vandaag" if advies["uur_start"].date() == vandaag else "morgen"
    if advies["uitstel"] == 0:
        kop = '<div class="groot">Start nu</div>'
        regel = f'Klaar rond {advies["klaar"].strftime("%H:%M")}.'
    else:
        kop = f'<div class="groot">Uitstel: {advies["uitstel"]} uur</div>'
        regel = (f'Wachttijd {duur_tekst(advies["wacht_min"])}. '
                 f'Start ca. {advies["echte_start"].strftime("%H:%M")}, '
                 f'klaar rond {advies["klaar"].strftime("%H:%M")}.')

    return (
        '<section class="kaart advies"><h2>Wasmachine</h2>'
        f"{kop}"
        f'<p>Goedkoopste uur: <strong>{advies["uur_start"].strftime("%H:%M")}</strong> '
        f'({dagnaam}), {eur(advies["prijs"])} EUR per kWh all-in.<br>{regel}</p>'
        f'<p class="stil">{voorwaarde}</p>{morgen_nog_niet}</section>'
    )


def lees_getal(params, naam, standaard, minimum, maximum, meldingen, label):
    try:
        waarde = int(params.get(naam, [standaard])[0])
    except ValueError:
        meldingen.append(f"{label}: ongeldige waarde, standaard {standaard} gebruikt.")
        return standaard
    if not minimum <= waarde <= maximum:
        meldingen.append(f"{label}: moet tussen {minimum} en {maximum} liggen, "
                         f"standaard {standaard} gebruikt.")
        return standaard
    return waarde


def maak_pagina(params):
    nu = datetime.now(sp.TIJDZONE)
    vandaag = nu.date()
    morgen = vandaag + timedelta(days=1)

    meldingen = []
    van = lees_getal(params, "van", sp.STANDAARD_VAN, 0, 23, meldingen, "Starten vanaf")
    tot = lees_getal(params, "tot", sp.STANDAARD_TOT, 1, 24, meldingen, "Klaar voor")
    duur = lees_getal(params, "duur", sp.STANDAARD_DUUR, 0, 24, meldingen, "Duur")
    venster = lees_getal(params, "venster", 24, 1, 48, meldingen, "Zoek vooruit")
    if van + duur > tot:
        meldingen.append("Het programma past niet tussen 'vanaf' en 'voor'; "
                         "standaardwaarden gebruikt.")
        van, tot, duur = sp.STANDAARD_VAN, sp.STANDAARD_TOT, sp.STANDAARD_DUUR

    uren_v, fout_v = prijzen(vandaag)
    uren_m, _ = prijzen(morgen)

    advies = None
    if uren_v:
        advies = bereken_advies(vandaag, uren_v, uren_m, venster, van, tot, duur, nu)

    alle = [u[2] for u in uren_v + uren_m if u[2] is not None]
    lo, hi = (min(alle), max(alle)) if alle else (0, 0)
    advies_start = advies["uur_start"] if advies else None

    meldingen_html = "".join(f'<p class="melding">{html.escape(m)}</p>' for m in meldingen)

    formulier = (
        '<section class="kaart"><form method="get" action="/">'
        f'<label>Starten vanaf (uur)<input type="number" name="van" min="0" max="23" value="{van}"></label>'
        f'<label>Klaar voor (uur)<input type="number" name="tot" min="1" max="24" value="{tot}"></label>'
        f'<label>Duur programma (uur)<input type="number" name="duur" min="0" max="24" value="{duur}"></label>'
        f'<label>Zoek vooruit (uur)<input type="number" name="venster" min="1" max="48" value="{venster}"></label>'
        '<button type="submit">Bereken</button></form></section>'
    )

    return (
        '<!doctype html><html lang="nl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta http-equiv="refresh" content="600">'
        "<title>Stroomprijzen per uur</title>"
        f"<style>{CSS}</style></head><body><main>"
        "<h1>Stroomprijzen per uur</h1>"
        f'<p class="stil">Bijgewerkt om {nu.strftime("%H:%M")} &middot; '
        "dynamische prijzen, EUR per kWh</p>"
        f"{meldingen_html}"
        + advies_html(advies, uren_v, fout_v, uren_m, vandaag, van, tot, duur)
        + formulier
        + '<div class="tabellen">'
        + tabel_html("Vandaag", vandaag, uren_v, lo, hi, nu, advies_start)
        + tabel_html("Morgen", morgen, uren_m, lo, hi, nu, advies_start)
        + "</div>"
        "<footer>All-in is indicatief: marktprijs + energiebelasting + gemiddelde "
        "leveranciersvergoeding + 21% btw; jouw leverancier kan afwijken. "
        "De berekening kijkt naar de prijs van het uur waarin de machine start.<br>"
        'Bron: <a href="https://jeroen.nl">jeroen.nl</a></footer>'
        "</main></body></html>"
    )


# ------------------------------------------------------------------- server

class Handler(BaseHTTPRequestHandler):
    server_version = "stroomprijzen-web/1.0"

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if url.path != "/":
            self.send_error(404, "Pagina niet gevonden")
            return

        body = maak_pagina(parse_qs(url.query)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description="Webpagina met stroomprijzen per uur.")
    parser.add_argument("--host", default="127.0.0.1",
                        help="adres om op te luisteren (standaard 127.0.0.1, alleen deze computer)")
    parser.add_argument("--port", type=int, default=8080, help="poort (standaard 8080)")
    args = parser.parse_args()

    if not 1024 <= args.port <= 65535:
        parser.error("--port moet tussen 1024 en 65535 liggen")

    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as fout:
        sys.exit(f"Kan niet starten op {args.host}:{args.port}: {fout}")

    adres = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    print(f"Stroomprijzen-pagina draait op http://{adres}:{args.port}")
    if args.host in ("0.0.0.0", ""):
        print("Let op: de pagina is nu bereikbaar voor iedereen in je lokale netwerk.")
    print("Stoppen met Ctrl+C.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nGestopt.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
