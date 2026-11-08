"""MCP-Server: zwei Tools und eine Resource über die DIP-API (Referenz: docs/mcp-referenz.md).

Aufteilung der Texte: Was ein Tool kann und nicht kann, steht in seiner Beschreibung; ergebnisspezifische Fakten
(Bereinigung, Fraktionswechsel) stehen in "hinweise" des Ergebnisses; Verhaltensregeln für ein Modell stehen
nicht im Server, sondern im Prompt des jeweiligen Clients.

Fehlerprinzip: Erwartbare Fehler (ungültige Eingabe, DIP nicht erreichbar) kommen als verständlicher Tool-Fehler zum
Modell. Alles Unerwartete wird maskiert (mask_error_details) und nur im Log (stderr) mit Details protokolliert.
"""

from __future__ import annotations

import collections
import csv
import io
import logging
from typing import Any, Protocol

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import Tool

from dip_fraktionen import __version__
from dip_fraktionen.dip_client import DipFehler, DipKonfigurationsfehler, DipNichtErreichbar
from dip_fraktionen.fraktion import Verteilung, verteilung
from dip_fraktionen.personen import UngueltigeEingabe, person_auskunft

log = logging.getLogger(__name__)

INSTRUCTIONS = (
    "Parlamentsdaten aus DIP, dem Dokumentations- und Informationssystem für Parlamentsmaterialien des Deutschen Bundestags, "
    "nur lesend: Fraktionsverteilungen je Wahlperiode und Angaben zu Abgeordneten, Regierungs- und Bundesratsmitgliedern. "
    "Drucksachen, Vorgänge und Plenarprotokolle aus DIP bietet dieser Server nicht an."
)

ZAEHLWEISE = (
    "Jede Person, die in der Wahlperiode einer Fraktion angehörte, auch Nachrücker, zählt einmal bei ihrer Hauptfraktion; "
    "das ist keine Sitzverteilung zu einem Stichtag, die Summe kann daher über der Sitzzahl liegen."
)
BESCHREIBUNG_VERTEILUNG = (
    "Liefert die Fraktionsverteilung im Deutschen Bundestag für eine Wahlperiode aus DIP: Anzahl und Prozentanteil der Personen je Fraktion. "
    "Geeignet für Fragen nach Zusammensetzung, Stärke oder Anteil der Fraktionen; für Vergleiche mehrerer Wahlperioden je Wahlperiode einmal aufrufen. "
    "Nicht für Auskünfte zu einzelnen Personen (dafür dip_get_person). "
    f"Zählweise: {ZAEHLWEISE} "
    "Rückgabe: Wahlperiode, Gesamtzahl, Zählweise, Fraktionen absteigend mit Anzahl und Anteil in Prozent sowie Hinweise zu den Daten."
)
BESCHREIBUNG_PERSON = (
    "Schlägt eine Person in DIP nach (Abgeordnete, Regierungsmitglieder, Mitglieder des Bundesrats) und liefert aktuelle Funktion, aktuelle Fraktion, "
    "Fraktion je Wahlperiode einschließlich Wechseln, Ressorts von Regierungsämtern (DIP nennt das Ministerium, nicht die genaue Funktion) "
    "und Landesämter, soweit DIP sie führt. "
    "Geeignet für Fragen wie „Wer ist X?“ oder „Welcher Fraktion gehört(e) X an?“; nicht für Fraktionsstärken (dafür dip_get_fraktionsverteilung). "
    "Ein bloßer Nachname genügt; passen mehrere Personen, liefert das Tool die Kandidaten. "
    "Genau einen der Parameter name oder person_id angeben. "
    "DIP enthält keine Parteimitgliedschaft, kein Geburtsdatum, keine Biografie und kein Abstimmungsverhalten; "
    "die Fraktion ist die in DIP geführte politische Zugehörigkeit. "
    "Das Ergebnis hat einen status: gefunden (mit person), mehrdeutig (bis zu 10 kandidaten mit person_id, weitere_treffer nennt den Rest) "
    "oder nicht_gefunden."
)
# Schemas bewusst explizit (statt aus Typannotationen erzeugt): optional = nicht in "required", kein null-Typ, kein "maximum"
# (Groq würde sonst mit HTTP 400 ablehnen, bevor der Server eine verständliche Meldung geben kann).
SCHEMA_VERTEILUNG = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "wahlperiode": {"type": "integer", "minimum": 1, "description": "Nummer der Wahlperiode als ganze Zahl ab 1, z. B. 20."}
    },
    "required": ["wahlperiode"],
}
SCHEMA_PERSON = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {
            "type": "string",
            "maxLength": 200,
            "description": "Vor- und Nachname oder nur Nachname, z. B. „Friedrich Merz“ oder „Merz“. "
            "Ohne Anrede angeben; Umlaute und Umschreibung (Müller/Mueller) funktionieren beide.",
        },
        "person_id": {
            "type": ["string", "integer"],
            "description": "DIP-Personen-ID aus den kandidaten eines früheren Ergebnisses, z. B. 8167. Ohne bekannte ID name verwenden.",
        },
    },
}
ANNOTATIONEN = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}

MELDUNG_NICHT_ERREICHBAR = "Die Datenquelle DIP ist derzeit nicht erreichbar."
MELDUNG_KONFIGURATION = "Der Zugriff auf die Datenquelle DIP ist derzeit nicht möglich."
MELDUNG_ANFRAGE = "Die Anfrage an die Datenquelle DIP ist fehlgeschlagen."
MELDUNG_WAHLPERIODE = "Die Wahlperiode ist eine ganze Zahl ab 1, z. B. 20."


class DipQuelle(Protocol):
    def personen_der_wahlperiode(self, wahlperiode: int) -> list[dict[str, Any]]: ...
    def personen_suchen(self, suchbegriff: str) -> list[dict[str, Any]]: ...
    def person_nach_id(self, person_id: str) -> list[dict[str, Any]]: ...


def _dip_fehler(e: DipFehler) -> ToolError:
    if isinstance(e, DipKonfigurationsfehler):
        log.error("DIP-Konfigurationsfehler (API-Key prüfen): %s", e)
        return ToolError(MELDUNG_KONFIGURATION)
    log.error("DIP-Fehler: %s", e)
    return ToolError(MELDUNG_NICHT_ERREICHBAR if isinstance(e, DipNichtErreichbar) else MELDUNG_ANFRAGE)


def _pruefe_wahlperiode(wp: Any) -> int:
    """Eigene Prüfung statt der englischen Standardmeldung der Bibliothek; Ziffern als Text (z. B. aus der Resource-URI) gelten.

    Ob es die Wahlperiode gibt, zeigt erst die Antwort von DIP.
    """
    if isinstance(wp, str) and wp.strip().isdigit():
        wp = int(wp)
    if isinstance(wp, bool) or not isinstance(wp, int) or wp < 1:
        raise ToolError(MELDUNG_WAHLPERIODE)
    return wp


def _verteilung_aus_dip(quelle: DipQuelle, wahlperiode: Any) -> tuple[int, Verteilung]:
    """Gemeinsamer Weg für Tool und Resource: Eingabe prüfen, Personen der Wahlperiode laden, zählen."""
    wp = _pruefe_wahlperiode(wahlperiode)
    try:
        docs = quelle.personen_der_wahlperiode(wp)
    except DipFehler as e:
        raise _dip_fehler(e) from None
    return wp, verteilung(docs, wp)


def fraktionsverteilung(quelle: DipQuelle, wahlperiode: Any) -> dict[str, Any]:
    wp, v = _verteilung_aus_dip(quelle, wahlperiode)
    if not v.gesamt:
        raise ToolError(f"DIP liefert für die {wp}. Wahlperiode keine Fraktionszugehörigkeiten.")
    return {
        "wahlperiode": wp,
        "gesamt": v.gesamt,
        "zaehlweise": ZAEHLWEISE,
        "verteilung": [{"fraktion": f, "anzahl": n, "anteil_prozent": p} for f, n, p in v.anteile],
        "hinweise": _hinweise(v),
    }


def _personen(n: int, verb_einzahl: str, verb_mehrzahl: str) -> str:
    return f"1 Person {verb_einzahl}" if n == 1 else f"{n} Personen {verb_mehrzahl}"


def _hinweise(v: Verteilung) -> list[str]:
    """Ergebnisspezifische Hinweise zu Datenbereinigung und Zählweise (nur wenn zutreffend)."""
    hinweise = []
    if v.dubletten:
        hinweise.append(f"{v.dubletten} doppelte Personeneinträge in DIP sind zusammengeführt.")
    if v.ohne_fraktion:
        anzahl = "1 Person" if v.ohne_fraktion == 1 else f"{v.ohne_fraktion} Personen"
        hinweise.append(
            f"Nicht gezählt: {anzahl} ohne Fraktionsangabe in DIP für diese Wahlperiode "
            "(z. B. Mitglieder des Bundesrats oder der Bundesregierung)."
        )
    weitere_je_person = [set(z.fraktionen) - {z.primaer} for z in v.zuordnungen]
    wechsel = collections.Counter(f for weitere in weitere_je_person for f in weitere)
    if wechsel:
        anzahl = sum(1 for weitere in weitere_je_person if weitere)
        ziele = ", ".join(f for f, _ in wechsel.most_common(3))
        hinweise.append(
            f"{_personen(anzahl, 'gehörte', 'gehörten')} in der Wahlperiode mehreren Fraktionen oder Gruppen an (u. a. {ziele}); "
            "gezählt wird nur die erste Fraktion, diese Fraktionen oder Gruppen erscheinen daher nicht oder kleiner in der Verteilung."
        )
    return hinweise


def zugehoerigkeit_csv(quelle: DipQuelle, wahlperiode: Any) -> str:
    """Fraktionszugehörigkeit jeder Person einer Wahlperiode als CSV (Semikolon, UTF-8)."""
    _, v = _verteilung_aus_dip(quelle, wahlperiode)
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";", lineterminator="\n")
    w.writerow(["person_id", "name", "fraktion", "fraktionen_in_wahlperiode"])
    for z in sorted(v.zuordnungen, key=lambda z: z.name):
        w.writerow([z.person_id, z.name, z.primaer, " | ".join(z.fraktionen)])
    return puffer.getvalue()


def create_server(quelle: DipQuelle) -> FastMCP:
    mcp = FastMCP("dip-fraktionen", instructions=INSTRUCTIONS, version=__version__, mask_error_details=True)

    # Parameter bewusst als Any: Typ und Wertebereich prüfen die Funktionen oben mit deutschen Meldungen;
    # das Modell sieht das explizite Schema (SCHEMA_*).
    def dip_get_fraktionsverteilung(wahlperiode: Any = None) -> dict[str, Any]:
        return fraktionsverteilung(quelle, wahlperiode)

    def dip_get_person(name: Any = None, person_id: Any = None) -> dict[str, Any]:
        if name and person_id not in (None, ""):
            raise ToolError("Genau einen der Parameter name oder person_id angeben, nicht beide.")
        try:
            return person_auskunft(quelle, name=name, person_id=person_id)
        except UngueltigeEingabe as e:
            raise ToolError(str(e)) from None
        except DipFehler as e:
            raise _dip_fehler(e) from None

    for funktion, titel, beschreibung, schema in (
        (dip_get_fraktionsverteilung, "Fraktionsverteilung einer Wahlperiode", BESCHREIBUNG_VERTEILUNG, SCHEMA_VERTEILUNG),
        (dip_get_person, "Person im Bundestag nachschlagen", BESCHREIBUNG_PERSON, SCHEMA_PERSON),
    ):
        tool = Tool.from_function(funktion, title=titel, description=beschreibung, annotations={**ANNOTATIONEN, "title": titel})
        tool.parameters = schema
        mcp.add_tool(tool)

    @mcp.resource(
        "dip://fraktionszugehoerigkeit/{wahlperiode}",
        name="fraktionszugehoerigkeit",
        title="Fraktionszugehörigkeit je Person",
        description="Alle Personen einer Wahlperiode mit ihrer Fraktion (CSV, Semikolon-getrennt).",
        mime_type="text/csv",
    )
    def fraktionszugehoerigkeit(wahlperiode: str) -> str:
        return zugehoerigkeit_csv(quelle, wahlperiode)

    return mcp
