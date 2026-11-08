import pytest

from dip_fraktionen.fraktion import zuordnen
from dip_fraktionen.personen import UngueltigeEingabe, person_auskunft


@pytest.mark.parametrize("name", ["Friedrich Merz", "Merz", "Merz, Friedrich", "merz"])
def test_merz_wird_gefunden(dip, name):
    r = person_auskunft(dip, name=name)
    assert r["status"] == "gefunden"
    p = r["person"]
    assert p["name"] == "Friedrich Merz" and p["funktion_aktuell"] == "Bundeskanzl." and "fraktion_aktuell" not in p
    assert p["fraktion_je_wahlperiode"]["20"] == ["CDU/CSU"] and "21" not in p["fraktion_je_wahlperiode"]
    assert any("keine aktuelle Fraktion" in h for h in p["hinweise"])  # DIP führt für Regierungsmitglieder keine Fraktion
    assert any("keine Fraktionszugehörigkeit" in h for h in p["hinweise"])  # Lücke WP 17-19


def test_person_id_als_zahl_oder_text(dip):
    assert person_auskunft(dip, person_id=8167)["person"]["name"] == "Friedrich Merz"
    assert person_auskunft(dip, person_id="8167")["person"]["name"] == "Friedrich Merz"


def test_mehrdeutig_mit_kandidaten(dip):
    r = person_auskunft(dip, name="Mueller")
    assert r["status"] == "mehrdeutig"
    assert 1 < len(r["kandidaten"]) <= 10 and all("person_id" in k for k in r["kandidaten"])


def test_nicht_gefunden_ohne_leere_felder(dip):
    assert person_auskunft(dip, name="Max Mustermann") == {"status": "nicht_gefunden", "gesucht": "Max Mustermann"}


def test_dubletten_werden_zusammengefasst(dip):
    r = person_auskunft(dip, name="Philipp Amthor")
    assert r["status"] == "gefunden" and r["person"]["weitere_ids"]


def test_fraktionswechsel_im_profil(dip):
    p = person_auskunft(dip, name="Sahra Wagenknecht")["person"]
    assert {"DIE LINKE", "fraktionslos"} <= set(p["fraktion_je_wahlperiode"]["20"])


def test_ungueltige_eingaben(dip):
    with pytest.raises(UngueltigeEingabe):
        person_auskunft(dip)
    with pytest.raises(UngueltigeEingabe):
        person_auskunft(dip, person_id="abc")


def test_gleichnamige_ohne_gemeinsame_wahlperiode_sind_verschiedene_personen():
    from dip_fraktionen.personen import personen_gruppieren

    a = {"id": "1", "vorname": "Christian", "nachname": "Schmidt", "wahlperiode": [10]}
    b = {"id": "2", "vorname": "Christian", "nachname": "Schmidt", "wahlperiode": [12, 13]}
    c = {"id": "3", "vorname": "Christian", "nachname": "Schmidt", "wahlperiode": [13, 14]}  # Dublette von 2
    gruppen = personen_gruppieren([a, b, c])
    assert sorted(sorted(d["id"] for d in g) for g in gruppen) == [["1"], ["2", "3"]]


def test_ressort_statt_amt(dip):
    p = person_auskunft(dip, name="Olaf Scholz")["person"]
    assert {"ressort": "Bundesministerium der Finanzen", "wahlperioden": [19, 20]} in p["aemter"]
    assert not any("amt" in a for a in p["aemter"])


def test_namenszusatz_bleibt_im_namen(dip):
    assert person_auskunft(dip, name="Beatrix von Storch")["person"]["name"] == "Beatrix von Storch"


@pytest.mark.parametrize(
    "name, erwartet",
    [
        ("Ursula von der Leyen", "Ursula von der Leyen"),
        ("Catarina dos Santos-Wintz", "Catarina dos Santos-Wintz"),
        ("Christian Freiherr von Stetten", "Christian Freiherr von Stetten"),
        ("Dr. Janosch Dahmen", "Janosch Dahmen"),
        ("Juergen Hardt", "Jürgen Hardt"),
        ("Baerbel Kofler", "Bärbel Kofler"),
    ],
)
def test_namenszusatz_und_titel_aus_dip_daten(dip, name, erwartet):
    # Namenszusätze und Titel werden mit den Angaben von DIP abgeglichen, nicht mit einer eigenen Liste.
    r = person_auskunft(dip, name=name)
    assert r["status"] == "gefunden" and r["person"]["name"] == erwartet


@pytest.mark.parametrize("wp", [19, 20, 21])
def test_profil_und_zaehlung_stimmen_ueberein(dip, wp):
    # Zählung und Personenauskunft nutzen dieselbe Regel: Wer in der Wahlperiode gezählt wird, hat sie im Profil mit derselben Fraktion.
    for z in zuordnen(dip.personen_der_wahlperiode(wp), wp)[0]:
        je_wp = person_auskunft(dip, person_id=z.person_id)["person"]["fraktion_je_wahlperiode"]
        assert z.primaer in je_wp.get(str(wp), []), z.name


def test_einteiliger_name_ohne_treffer_nur_eine_suche(dip):
    suchen = []

    class Zaehler:
        def personen_suchen(self, begriff):
            suchen.append(begriff)
            return dip.personen_suchen(begriff)

        person_nach_id = staticmethod(dip.person_nach_id)

    assert person_auskunft(Zaehler(), name="Mustermann")["status"] == "nicht_gefunden" and suchen == ["Mustermann"]


def test_ohne_aktuelle_fraktion_kein_widerspruch(dip):
    # Führt DIP keine aktuelle Fraktion (z. B. Regierungsmitglied), fehlt fraktion_aktuell; der Hinweis sagt dasselbe.
    p = person_auskunft(dip, name="Lars Klingbeil")["person"]
    assert "fraktion_aktuell" not in p and any("keine aktuelle Fraktion" in h for h in p["hinweise"])
    assert p["fraktion_je_wahlperiode"]["21"] == ["SPD"]
