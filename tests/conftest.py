"""Offline-Testdaten: gespeicherte DIP-Antworten (person, f.wahlperiode=19/20/21, Abruf 2026-11-04)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _falten(s: str) -> str:
    s = (s or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return s


class FakeDip:
    """Bildet die DIP-Namenssuche nach: Treffer, wenn der Suchbegriff einem Vor- oder Nachnamensteil entspricht."""

    def __init__(self):
        self.wp = {w: json.loads((FIXTURES / f"person_wp{w}.json").read_text(encoding="utf-8")) for w in (19, 20, 21)}
        alle = {}
        for docs in self.wp.values():
            for d in docs:
                alle[d["id"]] = d
        self.alle = list(alle.values())

    def personen_der_wahlperiode(self, wahlperiode: int):
        return self.wp.get(wahlperiode, [])

    def personen_suchen(self, suchbegriff: str):
        s = _falten(suchbegriff)
        return [d for d in self.alle if s in re.split(r"[\s\-]+", _falten(f"{d.get('vorname', '')} {d.get('nachname', '')}"))]

    def person_nach_id(self, person_id: str):
        return [d for d in self.alle if d["id"] == str(person_id)]


@pytest.fixture(scope="session")
def dip():
    return FakeDip()
