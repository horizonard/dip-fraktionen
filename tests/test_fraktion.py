"""Golden-Tests: erwartete Werte aus den gespeicherten DIP-Antworten (Abruf 2026-11-04)."""

import pytest

from dip_fraktionen.fraktion import verteilung

GOLDEN = {
    19: (
        747,
        {"CDU/CSU": 259, "SPD": 166, "AfD": 92, "FDP": 85, "BÜNDNIS 90/DIE GRÜNEN": 72, "DIE LINKE": 71, "fraktionslos": 2},
    ),
    20: (
        774,
        {
            "SPD": 219,
            "CDU/CSU": 204,
            "BÜNDNIS 90/DIE GRÜNEN": 125,
            "FDP": 98,
            "AfD": 85,
            "DIE LINKE": 29,
            "Die Linke (Gruppe)": 12,
            "fraktionslos": 2,
        },
    ),
    21: (625, {"CDU/CSU": 201, "AfD": 151, "SPD": 118, "BÜNDNIS 90/DIE GRÜNEN": 89, "DIE LINKE": 65, "fraktionslos": 1}),
}


@pytest.mark.parametrize("wp", sorted(GOLDEN))
def test_verteilung_golden(dip, wp):
    v = verteilung(dip.personen_der_wahlperiode(wp), wp)
    gesamt, erwartet = GOLDEN[wp]
    assert v.gesamt == gesamt
    assert {f: n for f, n, _ in v.anteile} == erwartet


def test_prozente_wp20(dip):
    v = verteilung(dip.personen_der_wahlperiode(20), 20)
    prozent = {f: p for f, _, p in v.anteile}
    assert prozent["SPD"] == 28.3 and prozent["CDU/CSU"] == 26.4 and prozent["BÜNDNIS 90/DIE GRÜNEN"] == 16.1
    assert v.dubletten == 26


def test_rollen_ohne_fraktion(dip):
    # Regierungsamt eines Abgeordneten: Fraktion aus dem Haupteintrag; nur Bundesrat/Landesamt: nicht gezählt;
    # ohne Fraktion im Haupteintrag (z. B. Merz als Bundeskanzler in WP 21): nicht gezählt.
    def zuordnung(wp):
        return {z.name: z.primaer for z in verteilung(dip.personen_der_wahlperiode(wp), wp).zuordnungen}

    wp20, wp19, wp21 = zuordnung(20), zuordnung(19), zuordnung(21)
    assert wp20["Franziska Brantner"] == "BÜNDNIS 90/DIE GRÜNEN" and wp20["Olaf Scholz"] == "SPD"
    assert "Tarek Al-Wazir" not in wp20 and "Christian Görke" not in wp19
    assert "Friedrich Merz" not in wp21


def test_fraktionswechsel_wagenknecht(dip):
    v = verteilung(dip.personen_der_wahlperiode(20), 20)
    w = next(z for z in v.zuordnungen if z.name == "Sahra Wagenknecht")
    assert "DIE LINKE" in w.fraktionen and "fraktionslos" in w.fraktionen and w.primaer == "DIE LINKE"
