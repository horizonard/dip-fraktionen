"""Fraktionszugehörigkeit je Person und Wahlperiode und Fraktionsverteilung.

Reine Funktionen ohne I/O; die Fraktion wird nur aus DIP gelesen (Zählweise: docs/annahmen-und-entscheidungen.md, Abschnitt 2):
  - Fraktionen aus person_roles, deren wahlperiode_nummer N enthält
  - dazu die Fraktion des Haupteintrags, wenn N die letzte Wahlperiode der Person ist oder keine Rolle in N eine Fraktion nennt
    (der Haupteintrag nennt die aktuelle Fraktion, die Rollen die früheren); nicht, wenn die Person in N nur als
    Mitglied des Bundesrats oder mit einem Landesamt geführt wird
Doppelte Einträge werden zusammengeführt; gezählt wird jede Person einmal bei der ersten Fraktion außer "fraktionslos".
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import Any

Doc = dict[str, Any]


def _rollen_in(d: Doc, wp: int) -> list[Doc]:
    return [r for r in d.get("person_roles", []) if wp in (r.get("wahlperiode_nummer") or [])]


def _letzte_wp(d: Doc) -> int:
    return max(d.get("wahlperiode") or [0])


def haupt_fraktion(d: Doc) -> str | None:
    """Fraktion im Haupteintrag eines DIP-Personendatensatzes (die aktuelle Fraktion laut DIP)."""
    return (d.get("fraktion") or [None])[0]


def name(d: Doc) -> str:
    """Anzeigename inkl. Namenszusatz, z. B. „Ursula von der Leyen“ (DIP führt „von der“ getrennt vom Nachnamen)."""
    return " ".join(t for t in (d.get("vorname"), d.get("namenszusatz"), d.get("nachname")) if t)


def fraktionen_in(d: Doc, wp: int) -> list[str]:
    """Fraktionen eines einzelnen DIP-Personendatensatzes in Wahlperiode wp, in DIP-Reihenfolge."""
    rollen = _rollen_in(d, wp)
    fr = [r["fraktion"] for r in rollen if r.get("fraktion")]
    haupt = haupt_fraktion(d)
    # Rollen ohne Fraktion: Regierungsamt eines Abgeordneten -> Fraktion aus dem Haupteintrag;
    # nur Bundesrat oder Landesamt (Feld bundesland) -> in dieser Wahlperiode kein Mitglied des Bundestags.
    nur_land = bool(rollen) and all(r.get("bundesland") for r in rollen)
    if haupt and not nur_land and (wp == _letzte_wp(d) or not fr):
        fr.append(haupt)
    return list(dict.fromkeys(fr))


def fraktionen_der_person(gruppe: list[Doc], wp: int) -> list[str]:
    """Fraktionen einer (ggf. aus Dubletten zusammengeführten) Person in Wahlperiode wp.

    Einzige Stelle für diese Regel: Zählung und Personenauskunft nutzen sie gemeinsam. Berücksichtigt werden nur
    Datensätze, die DIP der Wahlperiode zuordnet oder die eine Rolle in ihr haben.
    """
    passend = [d for d in gruppe if wp in (d.get("wahlperiode") or []) or _rollen_in(d, wp)]
    return list(dict.fromkeys(f for d in passend for f in fraktionen_in(d, wp)))


def dubletten_gruppieren(docs: list[Doc]) -> list[list[Doc]]:
    """DIP führt manche Personen unter mehreren IDs; Zusammenführung über (Vorname, Nachname, Namenszusatz)."""
    gruppen: dict[tuple, list[Doc]] = collections.defaultdict(list)
    for d in docs:
        gruppen[(d.get("vorname"), d.get("nachname"), d.get("namenszusatz"))].append(d)
    return list(gruppen.values())


@dataclass
class Zuordnung:
    person_id: str
    name: str
    fraktionen: list[str]
    primaer: str


@dataclass
class Verteilung:
    zuordnungen: list[Zuordnung]
    dubletten: int
    anteile: list[tuple[str, int, float]] = field(default_factory=list)
    ohne_fraktion: int = 0  # Personen der Wahlperiode, für die DIP keine Fraktion führt (nicht gezählt)

    @property
    def gesamt(self) -> int:
        return len(self.zuordnungen)


def zuordnen(docs: list[Doc], wp: int) -> tuple[list[Zuordnung], int]:
    """Fraktionszugehörigkeit jeder Person in Wahlperiode wp. Liefert Zuordnungen und Anzahl zusammengeführter Dubletten."""
    gruppen = dubletten_gruppieren(docs)
    ergebnis: list[Zuordnung] = []
    for gruppe in gruppen:
        fr = fraktionen_der_person(gruppe, wp)
        if not fr:
            continue
        d = gruppe[0]
        ergebnis.append(
            Zuordnung(
                person_id=d["id"],
                name=name(d),
                fraktionen=fr,
                primaer=([f for f in fr if f != "fraktionslos"] or fr)[0],
            )
        )
    return ergebnis, len(docs) - len(gruppen)


def verteilung(docs: list[Doc], wp: int) -> Verteilung:
    """Fraktionsverteilung: jede Person einmal mit ihrer Primärfraktion; Anteile in Prozent mit einer Nachkommastelle."""
    zuordnungen, dubletten = zuordnen(docs, wp)
    zaehler = collections.Counter(z.primaer for z in zuordnungen)
    gesamt = sum(zaehler.values())
    anteile = [(f, n, round(100 * n / gesamt, 1)) for f, n in sorted(zaehler.items(), key=lambda x: (-x[1], x[0]))] if gesamt else []
    ohne_fraktion = len(docs) - dubletten - len(zuordnungen)
    return Verteilung(zuordnungen=zuordnungen, dubletten=dubletten, anteile=anteile, ohne_fraktion=ohne_fraktion)
