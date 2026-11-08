"""MCP-Ebene: Schemas (öffentlicher Vertrag), Ergebnisse, Fehlertexte, Resource – über den In-Memory-Client."""

import asyncio
import json

import pytest
from fastmcp import Client

from dip_fraktionen import __version__
from dip_fraktionen.dip_client import DipKonfigurationsfehler, DipNichtErreichbar
from dip_fraktionen.server import INSTRUCTIONS, MELDUNG_KONFIGURATION, MELDUNG_NICHT_ERREICHBAR, create_server


def lauf(quelle, coro_fn):
    async def inner():
        async with Client(create_server(quelle)) as c:
            return await coro_fn(c)

    return asyncio.run(inner())


def aufruf(quelle, tool, args):
    async def f(c):
        r = await c.call_tool(tool, args, raise_on_error=False)
        return r.is_error, r.content[0].text

    return lauf(quelle, f)


def test_vertrag_tools_und_server(dip):
    async def f(c):
        return c.instructions, c.server_info, {t.name: t for t in await c.list_tools()}

    instructions, info, tools = lauf(dip, f)
    assert instructions == INSTRUCTIONS
    assert info.name == "dip-fraktionen" and info.version == __version__
    assert list(tools) == ["dip_get_fraktionsverteilung", "dip_get_person"]
    v, p = tools["dip_get_fraktionsverteilung"], tools["dip_get_person"]
    assert v.input_schema["required"] == ["wahlperiode"] and "maximum" not in v.input_schema["properties"]["wahlperiode"]
    assert "required" not in p.input_schema
    assert p.input_schema["properties"]["person_id"]["type"] == ["string", "integer"]
    alles = json.dumps([t.input_schema for t in tools.values()])
    assert "null" not in alles and "anyOf" not in alles
    assert v.annotations.read_only_hint is True and p.annotations.read_only_hint is True


def test_verteilung_wp20(dip):
    fehler, text = aufruf(dip, "dip_get_fraktionsverteilung", {"wahlperiode": 20})
    r = json.loads(text)
    assert not fehler and r["gesamt"] == 774 and "zeitraum" not in r
    assert r["verteilung"][0] == {"fraktion": "SPD", "anzahl": 219, "anteil_prozent": 28.3}
    assert any("26 doppelte" in h for h in r["hinweise"])
    assert any(h.startswith("Nicht gezählt: 239 Personen ohne Fraktionsangabe") for h in r["hinweise"])
    assert r["zaehlweise"].startswith("Jede Person")


@pytest.mark.parametrize(
    "wp, erwartet", [(25, "DIP liefert für die 25. Wahlperiode keine Fraktionszugehörigkeiten."), (0, "ganze Zahl ab 1")]
)
def test_ungueltige_wahlperiode(dip, wp, erwartet):
    fehler, text = aufruf(dip, "dip_get_fraktionsverteilung", {"wahlperiode": wp})
    assert fehler and erwartet in text


def test_person_status_varianten(dip):
    assert json.loads(aufruf(dip, "dip_get_person", {"name": "Friedrich Merz"})[1])["person"]["funktion_aktuell"] == "Bundeskanzl."
    assert json.loads(aufruf(dip, "dip_get_person", {"person_id": 8167})[1])["status"] == "gefunden"
    assert json.loads(aufruf(dip, "dip_get_person", {"name": "Mueller"})[1])["status"] == "mehrdeutig"


@pytest.mark.parametrize("args, erwartet", [({}, "Entweder name oder person_id"), ({"name": "Merz", "person_id": 8167}, "nicht beide")])
def test_person_eingabefehler(dip, args, erwartet):
    fehler, text = aufruf(dip, "dip_get_person", args)
    assert fehler and erwartet in text


@pytest.mark.parametrize(
    "tool, args, erwartet",
    [
        ("dip_get_fraktionsverteilung", {"wahlperiode": "zwanzig"}, "Die Wahlperiode ist eine ganze Zahl ab 1"),
        ("dip_get_fraktionsverteilung", {"wahlperiode": True}, "Die Wahlperiode ist eine ganze Zahl ab 1"),
        ("dip_get_fraktionsverteilung", {"wahlperiode": [20]}, "Die Wahlperiode ist eine ganze Zahl ab 1"),
        ("dip_get_fraktionsverteilung", {}, "Die Wahlperiode ist eine ganze Zahl ab 1"),
        ("dip_get_person", {"name": 123}, "name ist ein Text mit höchstens 200 Zeichen"),
        ("dip_get_person", {"name": "x" * 201}, "name ist ein Text mit höchstens 200 Zeichen"),
        ("dip_get_person", {"person_id": [8167]}, "person_id besteht nur aus Ziffern"),
        ("dip_get_person", {"person_id": True}, "person_id besteht nur aus Ziffern"),
    ],
)
def test_falscher_typ_ergibt_deutsche_meldung(dip, tool, args, erwartet):
    # Typfehler prüft der Server selbst, damit keine englische Standardmeldung der Bibliothek beim Modell ankommt.
    fehler, text = aufruf(dip, tool, args)
    assert fehler and erwartet in text and "pydantic" not in text.lower()


def test_wahlperiode_als_ziffern_text(dip):
    assert json.loads(aufruf(dip, "dip_get_fraktionsverteilung", {"wahlperiode": "20"})[1])["gesamt"] == 774


class Kaputt:
    def __init__(self, fehler):
        self.fehler = fehler

    def personen_der_wahlperiode(self, wp):
        raise self.fehler

    personen_suchen = person_nach_id = personen_der_wahlperiode


@pytest.mark.parametrize(
    "fehler, meldung",
    [(DipNichtErreichbar("HTTP 503"), MELDUNG_NICHT_ERREICHBAR), (DipKonfigurationsfehler("HTTP 401 key xyz"), MELDUNG_KONFIGURATION)],
)
def test_dip_fehler_ohne_interna(fehler, meldung):
    for tool, args in (("dip_get_fraktionsverteilung", {"wahlperiode": 20}), ("dip_get_person", {"name": "Merz"})):
        ist_fehler, text = aufruf(Kaputt(fehler), tool, args)
        assert ist_fehler and text == meldung


def test_unerwartete_fehler_werden_maskiert():
    ist_fehler, text = aufruf(Kaputt(RuntimeError("geheimes Detail /pfad/zum/server")), "dip_get_fraktionsverteilung", {"wahlperiode": 20})
    assert ist_fehler and "geheimes Detail" not in text


def test_resource_csv_wp20(dip):
    async def f(c):
        vorlagen = await c.list_resource_templates()
        inhalt = await c.read_resource("dip://fraktionszugehoerigkeit/20")
        return [v.uri_template for v in vorlagen], inhalt[0].text

    vorlagen, csv_text = lauf(dip, f)
    zeilen = csv_text.strip().split("\n")
    assert vorlagen == ["dip://fraktionszugehoerigkeit/{wahlperiode}"]
    assert zeilen[0] == "person_id;name;fraktion;fraktionen_in_wahlperiode" and len(zeilen) == 775
    assert any(z.startswith("7744;Sahra Wagenknecht;DIE LINKE;") for z in zeilen)


def test_hinweis_auf_fraktionswechsel_wp20(dip):
    r = json.loads(aufruf(dip, "dip_get_fraktionsverteilung", {"wahlperiode": 20})[1])
    wechsel = [h for h in r["hinweise"] if "mehreren Fraktionen oder Gruppen" in h]
    assert wechsel and "BSW (Gruppe)" in wechsel[0]


def test_server_unterprozess_erhaelt_keinen_llm_key(monkeypatch):
    from dip_fraktionen.mcp_verbindung import server_umgebung

    monkeypatch.setenv("LLM_API_KEY", "geheim")
    monkeypatch.setenv("GROQ_API_KEY", "geheim")
    monkeypatch.setenv("DIP_API_KEY", "dip")
    env = server_umgebung()
    assert "LLM_API_KEY" not in env and "GROQ_API_KEY" not in env and env["DIP_API_KEY"] == "dip"


def test_ohne_dip_key_klare_meldung(monkeypatch, capsys):
    from dip_fraktionen import cli

    monkeypatch.delenv("DIP_API_KEY", raising=False)
    with pytest.raises(SystemExit) as e:
        cli.main(["ask", "Wer ist Friedrich Merz?"])
    assert e.value.code == 1 and "Kein DIP-API-Key gesetzt" in capsys.readouterr().err


def test_ungueltige_zahl_in_konfiguration_klare_meldung(monkeypatch, capsys):
    from dip_fraktionen import cli

    monkeypatch.setenv("DIP_API_KEY", "dip")
    monkeypatch.setenv("DIP_TIMEOUT_S", "30s")
    with pytest.raises(SystemExit) as e:
        cli.main(["ask", "Wer ist Friedrich Merz?"])
    assert e.value.code == 1 and "DIP_TIMEOUT_S muss eine Zahl sein" in capsys.readouterr().err
