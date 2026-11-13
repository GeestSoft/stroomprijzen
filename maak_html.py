#!/usr/bin/env python3
"""Maakt een zelfstandige HTML-pagina met de stroomprijzen per uur.

De pagina (stroomprijzen.html) bevat de prijzen van vandaag en morgen en
rekent zelf, in je browser, uit hoe lang je moet wachten tot het goedkoopste
moment voor de wasmachine. Er is geen webserver en geen internet nodig om de
pagina te openen: dubbelklik op het bestand of open het in Firefox.

Alleen de prijzen zelf worden opgehaald door dit script. Draai het opnieuw
voor verse prijzen (bijvoorbeeld 's ochtends en na 13:00, dan komen de
prijzen van morgen binnen):

    python3 maak_html.py
    python3 maak_html.py --uit /pad/naar/andere-naam.html

Gebruikt stroomprijzen.py (zelfde map) om de prijzen op te halen.
Elke keer dat je dit script draait zijn dat 2 aanroepen naar jeroen.nl
(limiet: 60 per uur).

Voorwaarden: https://jeroen.nl/api-voorwaarden
Alleen voor persoonlijk gebruik. Bron van de prijzen: jeroen.nl, https://jeroen.nl
"""

import sys

sys.dont_write_bytecode = True  # geen __pycache__ in deze map

import argparse
import json
import os
import tempfile
from datetime import datetime, timedelta

import stroomprijzen as sp

STANDAARD_UIT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "stroomprijzen.html"
)

SJABLOON = r"""<!doctype html>
<html lang="nl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>Stroomprijzen per uur</title>
<style>
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
.formulier{display:flex;flex-wrap:wrap;gap:12px;align-items:end}
label{display:flex;flex-direction:column;font-size:.85rem;color:var(--muted)}
input[type=number]{width:96px;padding:6px;font-size:1rem;border:1px solid var(--line);
border-radius:6px;background:var(--bg);color:var(--fg)}
.tabellen{display:grid;grid-template-columns:1fr;gap:14px}
.tabellen .kaart{margin:0}
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
</style>
</head>
<body>
<main>
<h1>Stroomprijzen per uur</h1>
<p class="stil" id="bijgewerkt"></p>
<div id="meldingen"></div>
<section class="kaart advies" id="advies"></section>
<section class="kaart">
<div class="formulier">
<label>Starten vanaf (uur)<input type="number" id="van" min="0" max="23" value="__VAN__"></label>
<label>Klaar voor (uur)<input type="number" id="tot" min="1" max="24" value="__TOT__"></label>
<label>Duur programma (uur)<input type="number" id="duur" min="0" max="24" value="__DUUR__"></label>
<label>Zoek vooruit (uur)<input type="number" id="venster" min="1" max="48" value="24"></label>
</div>
</section>
<div class="tabellen">
<section class="kaart" id="t-vandaag"></section>
<section class="kaart" id="t-morgen"></section>
</div>
<footer>
All-in is indicatief: marktprijs + energiebelasting + gemiddelde leveranciersvergoeding
+ 21% btw; jouw leverancier kan afwijken. De berekening kijkt naar de prijs van het uur
waarin de machine start. De prijzen staan in dit bestand; draai <code>maak_html.py</code>
opnieuw voor verse prijzen.<br>
Bron: <a href="https://jeroen.nl">jeroen.nl</a>
</footer>
</main>
<script>
'use strict';
const DATA = __DATA__;
const STANDAARD = {van: __VAN__, tot: __TOT__, duur: __DUUR__, venster: 24};
const UUR_MS = 3600000;

function esc(t) {
  return String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function pad(n) { return String(n).padStart(2, '0'); }
function dagSleutel(d) {
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
}
function datumTekst(d) {
  return pad(d.getDate()) + '-' + pad(d.getMonth() + 1) + '-' + d.getFullYear();
}
function tijdTekst(d) { return pad(d.getHours()) + ':' + pad(d.getMinutes()); }
function eur(x) {
  return (x === null || x === undefined) ? '-' : x.toFixed(4).replace('.', ',');
}
function duurTekst(minuten) {
  const m = Math.round(minuten);
  const u = Math.floor(m / 60), r = m % 60;
  if (u && r) return u + ' uur en ' + r + ' min';
  if (u) return u + ' uur';
  return r + ' min';
}

function slots(sleutel) {
  const rijen = DATA.dagen[sleutel] || [];
  const delen = sleutel.split('-').map(Number);
  return rijen.map(function (r) {
    return {
      uur: r[0], markt: r[1], prijs: r[2],
      start: new Date(delen[0], delen[1] - 1, delen[2],
        parseInt(r[0].slice(0, 2), 10), parseInt(r[0].slice(3, 5), 10))
    };
  });
}

function leesGetal(id, min, max, standaard, label, meldingen) {
  const w = parseInt(document.getElementById(id).value, 10);
  if (Number.isNaN(w) || w < min || w > max) {
    meldingen.push(label + ': moet tussen ' + min + ' en ' + max +
      ' liggen, standaard ' + standaard + ' gebruikt.');
    return standaard;
  }
  return w;
}

function bereken(kandidaten, nu, venster, van, tot, duur) {
  const einde = new Date(nu.getTime() + venster * UUR_MS);
  let beste = null;
  kandidaten.forEach(function (s) {
    if (s.prijs === null) return;
    if (s.start.getTime() + UUR_MS <= nu.getTime() || s.start >= einde) return;
    const wachtMin = Math.max(0, (s.start - nu) / 60000);
    const uitstel = Math.ceil(wachtMin / 60);
    const echte = new Date(nu.getTime() + uitstel * UUR_MS);
    const middernacht = new Date(echte.getFullYear(), echte.getMonth(), echte.getDate());
    const begin = new Date(middernacht.getTime() + van * UUR_MS);
    const eind = new Date(middernacht.getTime() + tot * UUR_MS);
    const klaar = new Date(echte.getTime() + duur * UUR_MS);
    if (echte < begin || klaar > eind) return;
    if (!beste || s.prijs < beste.prijs ||
        (s.prijs === beste.prijs && s.start < beste.uurStart)) {
      beste = {uurStart: s.start, prijs: s.prijs, uitstel: uitstel,
        echteStart: echte, klaar: klaar, wachtMin: wachtMin};
    }
  });
  return beste;
}

function tekenAdvies(doel, a, heeftToekomst, morgenBekend, vandaag, van, tot, duur) {
  if (!heeftToekomst) {
    doel.className = 'kaart fout';
    doel.innerHTML = '<h2>Geen actuele prijzen</h2><p>Dit bestand bevat geen prijzen ' +
      'meer voor de komende uren. Draai <code>maak_html.py</code> opnieuw.</p>';
    return;
  }
  doel.className = 'kaart advies';
  const voorwaarde = 'Starten vanaf ' + pad(van) + ':00 en klaar vóór ' + pad(tot) +
    ':00 (programma van ' + duur + ' uur).';
  const morgenNiet = morgenBekend ? '' :
    '<p class="stil">Dit bestand bevat geen prijzen voor morgen (die zijn pas rond ' +
    '13:00 bekend). Er is gekeken tot het einde van de bekende prijzen; draai ' +
    '<code>maak_html.py</code> opnieuw voor de nieuwste prijzen.</p>';

  if (!a) {
    doel.innerHTML = '<h2>Wasmachine</h2><p>Geen geschikt moment gevonden in deze ' +
      'periode.</p><p class="stil">' + esc(voorwaarde) + '</p>' + morgenNiet;
    return;
  }
  const dagnaam = dagSleutel(a.uurStart) === dagSleutel(vandaag) ? 'vandaag' : 'morgen';
  let kop, regel;
  if (a.uitstel === 0) {
    kop = '<div class="groot">Start nu</div>';
    regel = 'Klaar rond ' + tijdTekst(a.klaar) + '.';
  } else {
    kop = '<div class="groot">Uitstel: ' + a.uitstel + ' uur</div>';
    regel = 'Wachttijd ' + duurTekst(a.wachtMin) + '. Start ca. ' +
      tijdTekst(a.echteStart) + ', klaar rond ' + tijdTekst(a.klaar) + '.';
  }
  doel.innerHTML = '<h2>Wasmachine</h2>' + kop +
    '<p>Goedkoopste uur: <strong>' + tijdTekst(a.uurStart) + '</strong> (' + dagnaam +
    '), ' + eur(a.prijs) + ' EUR per kWh all-in.<br>' + esc(regel) + '</p>' +
    '<p class="stil">' + esc(voorwaarde) + '</p>' + morgenNiet;
}

function tekenTabel(doel, titel, datum, lijst, leegTekst, lo, hi, nu, adviesStart) {
  const kop = '<h2>' + esc(titel) + ' <span class="stil">(' + datumTekst(datum) +
    ')</span></h2>';
  if (!lijst.length) {
    doel.innerHTML = kop + '<p class="stil">' + esc(leegTekst) + '</p>';
    return;
  }
  const prijzen = lijst.map(function (s) { return s.prijs; })
    .filter(function (p) { return p !== null; });
  const dagLo = Math.min.apply(null, prijzen);
  const dagHi = Math.max.apply(null, prijzen);
  const gemiddeld = prijzen.reduce(function (a, b) { return a + b; }, 0) / prijzen.length;

  const rijen = lijst.map(function (s) {
    const klassen = [], badges = [];
    if (s.prijs !== null && s.prijs === dagLo) { klassen.push('laagste'); badges.push('laagste'); }
    else if (s.prijs !== null && s.prijs === dagHi) { klassen.push('hoogste'); badges.push('hoogste'); }
    if (s.start.getTime() <= nu.getTime() && nu.getTime() < s.start.getTime() + UUR_MS) {
      klassen.push('nu'); badges.push('nu');
    }
    if (adviesStart && s.start.getTime() === adviesStart.getTime()) {
      klassen.push('advies'); badges.push('advies');
    }
    let breedte = 0;
    if (s.prijs !== null) breedte = hi > lo ? Math.round(8 + 92 * (s.prijs - lo) / (hi - lo)) : 50;
    const badgeHtml = badges.map(function (b) {
      return '<span class="badge">' + b + '</span>';
    }).join('');
    return '<tr class="' + klassen.join(' ') + '"><td>' + esc(s.uur) + badgeHtml + '</td>' +
      '<td class="p">' + eur(s.markt) + '</td><td class="p">' + eur(s.prijs) + '</td>' +
      '<td style="width:28%"><span class="balk" style="width:' + breedte + '%"></span></td></tr>';
  }).join('');

  doel.innerHTML = kop + '<table><thead><tr><th>Uur</th><th class="p">Markt<br>excl. btw</th>' +
    '<th class="p">All-in<br>incl. btw</th><th></th></tr></thead><tbody>' + rijen +
    '</tbody></table><p class="stil">Gemiddeld all-in: ' + eur(gemiddeld) +
    ' &middot; laagste: ' + eur(dagLo) + ' &middot; hoogste: ' + eur(dagHi) +
    ' (EUR per kWh)</p>';
}

function teken() {
  const nu = new Date();
  const meldingen = [];
  let van = leesGetal('van', 0, 23, STANDAARD.van, 'Starten vanaf', meldingen);
  let tot = leesGetal('tot', 1, 24, STANDAARD.tot, 'Klaar voor', meldingen);
  let duur = leesGetal('duur', 0, 24, STANDAARD.duur, 'Duur', meldingen);
  const venster = leesGetal('venster', 1, 48, STANDAARD.venster, 'Zoek vooruit', meldingen);
  if (van + duur > tot) {
    meldingen.push("Het programma past niet tussen 'vanaf' en 'voor'; standaardwaarden gebruikt.");
    van = STANDAARD.van; tot = STANDAARD.tot; duur = STANDAARD.duur;
  }

  const vandaag = new Date(nu.getFullYear(), nu.getMonth(), nu.getDate());
  const morgen = new Date(nu.getFullYear(), nu.getMonth(), nu.getDate() + 1);
  const lv = slots(dagSleutel(vandaag));
  const lm = slots(dagSleutel(morgen));
  const alle = lv.concat(lm).map(function (s) { return s.prijs; })
    .filter(function (p) { return p !== null; });
  const lo = alle.length ? Math.min.apply(null, alle) : 0;
  const hi = alle.length ? Math.max.apply(null, alle) : 0;

  const heeftToekomst = lv.concat(lm).some(function (s) {
    return s.start.getTime() + UUR_MS > nu.getTime();
  });
  const advies = bereken(lv.concat(lm), nu, venster, van, tot, duur);

  const leeftijdMin = (nu.getTime() - DATA.gegenereerd_ts) / 60000;
  document.getElementById('bijgewerkt').textContent =
    'Prijzen opgehaald op ' + DATA.gegenereerd + ' (' + duurTekst(leeftijdMin) +
    ' geleden) · pagina bijgewerkt om ' + tijdTekst(nu) + ' · EUR per kWh';
  if (!lv.length) {
    meldingen.push('Dit bestand bevat geen prijzen voor vandaag. ' +
      'Draai maak_html.py opnieuw.');
  }
  document.getElementById('meldingen').innerHTML = meldingen.map(function (m) {
    return '<p class="melding">' + esc(m) + '</p>';
  }).join('');

  tekenAdvies(document.getElementById('advies'), advies, heeftToekomst,
    lm.length > 0, vandaag, van, tot, duur);
  const adviesStart = advies ? advies.uurStart : null;
  tekenTabel(document.getElementById('t-vandaag'), 'Vandaag', vandaag, lv,
    'Geen prijzen voor vandaag in dit bestand.', lo, hi, nu, adviesStart);
  tekenTabel(document.getElementById('t-morgen'), 'Morgen', morgen, lm,
    'Nog geen prijzen bekend (verwacht rond 13:00).', lo, hi, nu, adviesStart);
}

['van', 'tot', 'duur', 'venster'].forEach(function (id) {
  document.getElementById(id).addEventListener('input', teken);
});
teken();
setInterval(teken, 60000);
</script>
</body>
</html>
"""


def bouw_pagina(data):
    # '</' escapen zodat de JSON nooit het script-blok kan afsluiten.
    json_tekst = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return (
        SJABLOON.replace("__DATA__", json_tekst)
        .replace("__VAN__", str(sp.STANDAARD_VAN))
        .replace("__TOT__", str(sp.STANDAARD_TOT))
        .replace("__DUUR__", str(sp.STANDAARD_DUUR))
    )


def schrijf_bestand(pad, inhoud):
    """Schrijft in één keer, zodat een half bestand nooit zichtbaar is."""
    map_ = os.path.dirname(os.path.abspath(pad))
    fd, tijdelijk = tempfile.mkstemp(dir=map_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as bestand:
            bestand.write(inhoud)
        os.chmod(tijdelijk, 0o644)
        os.replace(tijdelijk, pad)
    except Exception:
        if os.path.exists(tijdelijk):
            os.remove(tijdelijk)
        raise


def main():
    parser = argparse.ArgumentParser(description="Maakt stroomprijzen.html.")
    parser.add_argument("--uit", default=STANDAARD_UIT,
                        help=f"pad van het HTML-bestand (standaard {STANDAARD_UIT})")
    args = parser.parse_args()

    nu = datetime.now(sp.TIJDZONE)
    vandaag = nu.date()
    morgen = vandaag + timedelta(days=1)

    try:
        uren_vandaag = sp.haal_uurprijzen(vandaag)
    except sp.ServerFout as fout:
        sys.exit(f"Prijzen ophalen mislukt: {fout}\nHet bestaande bestand is niet gewijzigd.")
    if not uren_vandaag:
        sys.exit("Geen prijzen voor vandaag ontvangen. Het bestaande bestand is niet gewijzigd.")

    try:
        uren_morgen = sp.haal_uurprijzen(morgen)
    except sp.ServerFout:
        uren_morgen = []

    data = {
        "gegenereerd": nu.strftime("%d-%m-%Y %H:%M"),
        "gegenereerd_ts": int(nu.timestamp() * 1000),
        "dagen": {vandaag.isoformat(): uren_vandaag},
    }
    if uren_morgen:
        data["dagen"][morgen.isoformat()] = uren_morgen

    schrijf_bestand(args.uit, bouw_pagina(data))

    print(f"Geschreven: {args.uit}")
    print(f"  vandaag: {len(uren_vandaag)} uren, "
          f"morgen: {len(uren_morgen) if uren_morgen else 'nog niet bekend'}")
    print(f"Open in je browser: file://{os.path.abspath(args.uit)}")


if __name__ == "__main__":
    main()
