#!/usr/bin/env python3
"""Toont de dynamische stroomprijs per uur in een tabel en berekent hoeveel
uur je nog moet wachten tot het goedkoopste uur waarop je wasmachine mag
draaien (standaard: starten vanaf 07:00 en klaar vóór 22:00).

Gegevens komen van de publieke MCP-server van jeroen.nl (zonder inloggen).
Gebruik:
    python3 stroomprijzen.py                   # vandaag + wachttijd wasmachine
    python3 stroomprijzen.py --duur 3          # programma duurt 3 uur
    python3 stroomprijzen.py --van 8 --tot 21  # machine mag tussen 08:00 en 21:00
    python3 stroomprijzen.py --venster 12      # alleen de komende 12 uur bekijken
    python3 stroomprijzen.py --morgen          # tabel van morgen (bekend vanaf ca. 13:00)
    python3 stroomprijzen.py 2026-11-10        # tabel van een specifieke datum

De wachttijd wordt alleen berekend als je de prijzen van vandaag bekijkt.

Voorwaarden: https://jeroen.nl/api-voorwaarden
(persoonlijk gebruik toegestaan, max. 60 aanroepen per uur per IP-adres;
 elke start van dit programma is 1 of 2 aanroepen)
Bron: jeroen.nl, https://jeroen.nl
"""

import argparse
import json
import math
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

MCP_URL = "https://jeroen.nl/mcp"
USER_AGENT = "stroomprijzen-script/1.0 (persoonlijk gebruik)"
TIJDZONE = ZoneInfo("Europe/Amsterdam")
BALK_BREEDTE = 20

STANDAARD_VAN = 7      # machine mag starten vanaf dit uur
STANDAARD_TOT = 22     # machine moet klaar zijn vóór dit uur
STANDAARD_DUUR = 2     # aangenomen duur van het wasprogramma in uren


class ServerFout(Exception):
    """Fout bij het ophalen van gegevens van de server."""


def mcp_aanroep(tool, argumenten, timeout=20):
    """Roept een tool van de MCP-server aan en geeft de gegevens terug."""
    verzoek = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": argumenten},
    }
    req = urllib.request.Request(
        MCP_URL,
        data=json.dumps(verzoek).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as antwoord:
            body = json.load(antwoord)
    except urllib.error.HTTPError as fout:
        if fout.code == 429:
            raise ServerFout("Te veel aanroepen (limiet bereikt). Probeer het later opnieuw.")
        raise ServerFout(f"De server gaf HTTP-fout {fout.code}.")
    except urllib.error.URLError as fout:
        raise ServerFout(f"Kan de server niet bereiken: {fout.reason}")

    if "error" in body:
        raise ServerFout(f"Fout van de server: {body['error'].get('message', body['error'])}")

    resultaat = body["result"]
    if resultaat.get("isError"):
        tekst = resultaat.get("content", [{}])[0].get("text", "onbekende fout")
        raise ServerFout(f"De server meldt een fout: {tekst}")

    if "structuredContent" in resultaat:
        return resultaat["structuredContent"]
    return json.loads(resultaat["content"][0]["text"])


def haal_uurprijzen(dag):
    """Geeft een lijst (uur, marktprijs excl. btw, all-in incl. btw) voor een dag."""
    data = mcp_aanroep(
        "get_electricity_prices",
        {
            "date_from": dag.isoformat(),
            "date_to": dag.isoformat(),
            "resolution": "hour",
            "include_all_in": True,
        },
    )
    kolommen = data["columns"]
    i_tijd = kolommen.index("time_local")
    i_markt = kolommen.index("market_eur_kwh_excl_vat")
    i_allin = kolommen.index("all_in_eur_kwh_incl_vat")

    uren = []
    for rij in data["rows"]:
        uren.append((rij[i_tijd][-5:], rij[i_markt], rij[i_allin]))
    return uren


def maak_balk(waarde, laagste, hoogste):
    """Eenvoudige balk waarvan de lengte de prijs aangeeft."""
    if waarde is None or hoogste == laagste:
        return ""
    lengte = 1 + round((waarde - laagste) / (hoogste - laagste) * (BALK_BREEDTE - 1))
    return "#" * lengte


def toon_tabel(dag, uren):
    allin = [u[2] for u in uren if u[2] is not None]
    if not allin:
        print(f"Geen prijzen beschikbaar voor {dag.isoformat()}.")
        return

    laagste, hoogste = min(allin), max(allin)
    gemiddeld = sum(allin) / len(allin)
    nu = datetime.now(TIJDZONE)
    huidig_uur = f"{nu.hour:02d}:00" if dag == nu.date() else None

    print()
    print(f"Stroomprijzen per uur op {dag.strftime('%d-%m-%Y')} (EUR per kWh)")
    print()
    kop = f"{'Uur':<6}{'Marktprijs':>12}{'All-in':>10}   {'':<{BALK_BREEDTE}}  "
    print(kop)
    print(f"{'':<6}{'excl. btw':>12}{'incl. btw':>10}")
    print("-" * (len(kop) + 8))

    for uur, markt, prijs in uren:
        markt_tekst = f"{markt:.4f}" if markt is not None else "-"
        prijs_tekst = f"{prijs:.4f}" if prijs is not None else "-"
        balk = maak_balk(prijs, laagste, hoogste)
        markering = ""
        if prijs == laagste:
            markering = "  <- laagste"
        elif prijs == hoogste:
            markering = "  <- hoogste"
        if uur == huidig_uur:
            markering += "  <- nu"
        print(f"{uur:<6}{markt_tekst:>12}{prijs_tekst:>10}   {balk:<{BALK_BREEDTE}}{markering}")

    print("-" * (len(kop) + 8))
    print(f"Gemiddeld all-in: {gemiddeld:.4f}   Laagste: {laagste:.4f}   Hoogste: {hoogste:.4f}")


def maak_kandidaten(dag, uren):
    """Zet uurprijzen om naar (starttijd van het uur, all-in prijs)."""
    kandidaten = []
    for uur, _markt, prijs in uren:
        if prijs is None:
            continue
        u, m = int(uur[:2]), int(uur[3:5])
        start = datetime(dag.year, dag.month, dag.day, u, m, tzinfo=TIJDZONE)
        kandidaten.append((start, prijs))
    return kandidaten


def formatteer_duur(minuten):
    uren, rest = divmod(int(round(minuten)), 60)
    if uren and rest:
        return f"{uren} uur en {rest} min"
    if uren:
        return f"{uren} uur"
    return f"{rest} min"


def binnen_tijdvenster(start, duur_uren, van, tot):
    """Controleert of een wasbeurt die op 'start' begint binnen het toegestane
    tijdvenster valt: niet eerder dan 'van' uur en klaar uiterlijk om 'tot' uur."""
    middernacht = start.replace(hour=0, minute=0, second=0, microsecond=0)
    venster_begin = middernacht + timedelta(hours=van)
    venster_einde = middernacht + timedelta(hours=tot)
    return start >= venster_begin and start + timedelta(hours=duur_uren) <= venster_einde


def toon_wachttijd(vandaag, uren_vandaag, uren_morgen, venster_uren, van, tot, duur):
    """Berekent hoeveel uur je moet wachten tot het goedkoopste toegestane uur."""
    nu = datetime.now(TIJDZONE)
    einde = nu + timedelta(hours=venster_uren)
    morgen = vandaag + timedelta(days=1)

    kandidaten = maak_kandidaten(vandaag, uren_vandaag)
    kandidaten += maak_kandidaten(morgen, uren_morgen)

    # Per prijsuur bepalen we wanneer de machine echt zou starten: je stelt een
    # uitstel in op hele uren (naar boven afgerond), gerekend vanaf nu.
    mogelijk = []
    for uur_start, prijs in kandidaten:
        if uur_start + timedelta(hours=1) <= nu or uur_start >= einde:
            continue
        wacht_min = max(0.0, (uur_start - nu).total_seconds() / 60)
        uitstel = math.ceil(wacht_min / 60)
        echte_start = nu + timedelta(hours=uitstel)
        if binnen_tijdvenster(echte_start, duur, van, tot):
            mogelijk.append((uur_start, prijs, uitstel, echte_start, wacht_min))

    print()
    print(f"Goedkoopste moment voor de wasmachine (komende {venster_uren} uur)")
    print("-" * 52)
    print(f"Voorwaarde: starten vanaf {van:02d}:00 en klaar vóór {tot:02d}:00")
    print(f"(uitgaand van een programma van {duur} uur; aanpassen met --duur)")
    print()

    if not mogelijk:
        print("Geen geschikt moment gevonden in deze periode.")
        if not uren_morgen:
            print("De prijzen van morgen zijn nog niet bekend (verwacht rond 13:00).")
        return

    # Laagste prijs; bij gelijke prijs het vroegste moment.
    uur_start, prijs, uitstel, echte_start, wacht_min = min(
        mogelijk, key=lambda item: (item[1], item[0])
    )
    klaar = echte_start + timedelta(hours=duur)
    dagnaam = "vandaag" if uur_start.date() == vandaag else "morgen"

    print(f"Goedkoopste uur:  {uur_start.strftime('%H:%M')} ({dagnaam}), "
          f"{prijs:.4f} EUR per kWh all-in")

    if uitstel == 0:
        print("Wachttijd:        geen, start de wasmachine nu.")
        print(f"                  (klaar rond {klaar.strftime('%H:%M')})")
    else:
        print(f"Wachttijd:        {formatteer_duur(wacht_min)}")
        print(f"Wasmachine:       stel het uitstel in op {uitstel} uur")
        print(f"                  (start ca. {echte_start.strftime('%H:%M')}, "
              f"klaar rond {klaar.strftime('%H:%M')})")

    if not uren_morgen:
        print()
        print("Let op: de prijzen van morgen zijn nog niet bekend (verwacht rond 13:00).")
        print("Er is alleen gekeken tot middernacht.")


def toon_voettekst():
    print()
    print("All-in is indicatief: marktprijs + energiebelasting + gemiddelde")
    print("leveranciersvergoeding + 21% btw. Jouw eigen leverancier kan afwijken.")
    print("De wachttijd kijkt naar de prijs van het uur waarin de machine start;")
    print("de volgende uren van het programma kunnen een andere prijs hebben.")
    print("Bron: jeroen.nl (https://jeroen.nl)")
    print()


def lees_argumenten():
    parser = argparse.ArgumentParser(description="Stroomprijs per uur in een tabel.")
    parser.add_argument(
        "datum",
        nargs="?",
        help="datum als JJJJ-MM-DD (standaard: vandaag)",
    )
    parser.add_argument(
        "--morgen",
        action="store_true",
        help="toon de prijzen van morgen (bekend vanaf ca. 13:00)",
    )
    parser.add_argument(
        "--venster",
        type=int,
        default=24,
        help="aantal uur vooruit waarin gezocht wordt (standaard 24)",
    )
    parser.add_argument(
        "--van",
        type=int,
        default=STANDAARD_VAN,
        help=f"de wasmachine mag starten vanaf dit uur (standaard {STANDAARD_VAN})",
    )
    parser.add_argument(
        "--tot",
        type=int,
        default=STANDAARD_TOT,
        help=f"de wasmachine moet klaar zijn vóór dit uur (standaard {STANDAARD_TOT})",
    )
    parser.add_argument(
        "--duur",
        type=int,
        default=STANDAARD_DUUR,
        help=f"duur van het wasprogramma in uren (standaard {STANDAARD_DUUR})",
    )
    args = parser.parse_args()

    if args.venster < 1 or args.venster > 48:
        parser.error("--venster moet tussen 1 en 48 uur liggen")
    if not 0 <= args.van <= 23:
        parser.error("--van moet tussen 0 en 23 liggen")
    if not 1 <= args.tot <= 24:
        parser.error("--tot moet tussen 1 en 24 liggen")
    if args.duur < 0:
        parser.error("--duur mag niet negatief zijn")
    if args.van + args.duur > args.tot:
        parser.error("het programma past niet tussen --van en --tot")

    vandaag = datetime.now(TIJDZONE).date()
    if args.morgen:
        dag = vandaag + timedelta(days=1)
    elif args.datum:
        try:
            dag = date.fromisoformat(args.datum)
        except ValueError:
            parser.error("ongeldige datum, gebruik het formaat JJJJ-MM-DD")
    else:
        dag = vandaag
    return dag, args


def main():
    dag, args = lees_argumenten()
    vandaag = datetime.now(TIJDZONE).date()

    try:
        uren = haal_uurprijzen(dag)
    except ServerFout as fout:
        sys.exit(str(fout))

    toon_tabel(dag, uren)

    if dag == vandaag:
        # De prijzen van morgen zijn pas rond 13:00 bekend; ontbreken ze, dan
        # gaan we door met alleen de uren van vandaag.
        try:
            uren_morgen = haal_uurprijzen(vandaag + timedelta(days=1))
        except ServerFout:
            uren_morgen = []
        toon_wachttijd(vandaag, uren, uren_morgen,
                       args.venster, args.van, args.tot, args.duur)

    toon_voettekst()


if __name__ == "__main__":
    main()
