"""Bericht zur Fraktionsverteilung einer Wahlperiode (Hauptaufgabe): Daten über MCP, Text vom Sprachmodell.

Arbeitsteilung: Zahlen und Tabelle erzeugt der Code aus dem Tool-Ergebnis; das Sprachmodell formuliert nur den
Auswertungstext. Alle Angaben (auch die Zählweise) stammen aus dem Tool-Ergebnis des MCP-Servers.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastmcp import Client

from dip_fraktionen.llm import LLM
from dip_fraktionen.prompts import prompt

TOOL = "dip_get_fraktionsverteilung"


class BerichtFehler(Exception):
    pass


@dataclass
class Bericht:
    dateien: list[Path]


def tabelle(daten: dict[str, Any]) -> str:
    zeilen = ["| Fraktion | Personen | Anteil |", "|---|---:|---:|"]
    zeilen += [f"| {v['fraktion']} | {v['anzahl']} | {str(v['anteil_prozent']).replace('.', ',')} % |" for v in daten["verteilung"]]
    zeilen.append(f"| **Gesamt** | **{daten['gesamt']}** | |")
    return "\n".join(zeilen)


async def bericht_erstellen(mcp: Client, llm: LLM, wahlperiode: int, ausgabe: Path) -> Bericht:
    r = await mcp.call_tool(TOOL, {"wahlperiode": wahlperiode}, raise_on_error=False)
    if r.is_error:
        raise BerichtFehler(r.content[0].text if r.content else "Unbekannter Fehler des MCP-Servers.")
    daten = r.structured_content
    csv_text = (await mcp.read_resource(f"dip://fraktionszugehoerigkeit/{wahlperiode}"))[0].text
    zaehlweise = daten.get("zaehlweise", "")

    eingabe = f"Daten (Ergebnis des Datendienstes):\n{json.dumps(daten, ensure_ascii=False)}"
    nachrichten = [{"role": "system", "content": prompt("bericht_system.md")}, {"role": "user", "content": eingabe}]
    auswertung = ((await asyncio.to_thread(llm.antwort, nachrichten)).content or "").strip()
    if not auswertung:
        raise BerichtFehler("Das Sprachmodell hat keinen Text geliefert.")

    # Dateien erst schreiben, wenn alles vorliegt: bei einem Fehler bleiben vorhandene Dateien unverändert.
    csv_datei = ausgabe / f"wp{wahlperiode}_fraktionszugehoerigkeit.csv"
    md_datei = ausgabe / f"wp{wahlperiode}_auswertung.md"

    teile = [
        f"# Fraktionsverteilung im Deutschen Bundestag – {wahlperiode}. Wahlperiode",
        "",
        auswertung,
        "",
        "## Daten",
        "",
        tabelle(daten),
        "",
        f"**Zählweise:** {zaehlweise}",
    ]
    if daten.get("hinweise"):
        teile += ["", "**Hinweise zu den Daten:** " + " ".join(daten["hinweise"])]
    teile += [
        "",
        "---",
        (
            f"_Quelle: DIP-API des Deutschen Bundestags (search.dip.bundestag.de), abgerufen am {dt.date.today():%d.%m.%Y}. "
            f"Zahlen und Tabelle berechnet; Text formuliert von {llm.modell}._"
        ),
        f"_Vollständige Zuordnung jeder Person: `{csv_datei.name}`._",
    ]
    ausgabe.mkdir(parents=True, exist_ok=True)
    csv_datei.write_text(csv_text, encoding="utf-8")
    md_datei.write_text("\n".join(teile) + "\n", encoding="utf-8")
    return Bericht([csv_datei, md_datei])
