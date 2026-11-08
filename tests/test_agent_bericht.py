"""Agent-Schleife und Bericht offline: Fake-Sprachmodell mit vorgegebenen Antworten, MCP-Server im Speicher."""

import asyncio
import json
from types import SimpleNamespace as NS

import pytest
from fastmcp import Client

from dip_fraktionen.agent import SYSTEM_PROMPT, Agent
from dip_fraktionen.bericht import BerichtFehler, bericht_erstellen
from dip_fraktionen.llm import LeereAntwort
from dip_fraktionen.server import INSTRUCTIONS, ZAEHLWEISE, create_server


def tool_call(i, name, args):
    return NS(id=f"c{i}", function=NS(name=name, arguments=json.dumps(args)))


class FakeLLM:
    modell = "fake-modell"

    def __init__(self, antworten):
        self.antworten, self.aufrufe = list(antworten), []

    def antwort(self, messages, tools=None, tool_choice=None):
        self.aufrufe.append({"messages": [dict(m) for m in messages], "tools": tools, "tool_choice": tool_choice})
        return self.antworten.pop(0)


def mit_agent(dip, llm, fragen, max_steps=5):
    async def lauf():
        async with Client(create_server(dip)) as mcp:
            agent = Agent(mcp, llm, max_steps)
            await agent.starten()
            return [await agent.frage(f) for f in fragen], agent

    return asyncio.run(lauf())


def test_leere_modellantwort_ist_fehler(dip):
    # Die API meldet Erfolg, liefert aber keinen Text (z. B. nur Reasoning): das darf nicht als leere Antwort durchgehen.
    with pytest.raises(LeereAntwort):
        mit_agent(dip, FakeLLM([NS(content="", tool_calls=None)]), ["Wer ist Friedrich Merz?"])


def test_bericht_ohne_modelltext_schreibt_keine_dateien(dip, tmp_path):
    # Bei einem Fehler des Sprachmodells bleiben keine halben Ergebnisse (nur CSV, kein Bericht) im Ausgabeordner.
    async def lauf():
        async with Client(create_server(dip)) as mcp:
            await bericht_erstellen(mcp, FakeLLM([NS(content="", tool_calls=None)]), 20, tmp_path / "out")

    with pytest.raises(BerichtFehler):
        asyncio.run(lauf())
    assert not (tmp_path / "out").exists()


def test_system_prompt_mit_instructions_und_tools(dip):
    llm = FakeLLM([NS(content="Hallo", tool_calls=None)])
    mit_agent(dip, llm, ["Hallo"])
    system = llm.aufrufe[0]["messages"][0]["content"]
    assert system == SYSTEM_PROMPT + "\n\n# Hinweise des Datendienstes\n" + INSTRUCTIONS
    assert [t["function"]["name"] for t in llm.aufrufe[0]["tools"]] == ["dip_get_fraktionsverteilung", "dip_get_person"]


def test_tool_aufruf_und_reasoning_rueckgabe(dip):
    llm = FakeLLM(
        [
            NS(content="", tool_calls=[tool_call(1, "dip_get_person", {"person_id": 8167})], reasoning="Ich suche Merz."),
            NS(content="Friedrich Merz ist Bundeskanzler (CDU/CSU).", tool_calls=None),
        ]
    )
    (antwort,), _ = mit_agent(dip, llm, ["Wer ist Friedrich Merz?"])
    assert antwort.text.startswith("Friedrich Merz") and antwort.tool_aufrufe[0]["tool"] == "dip_get_person"
    zweiter = llm.aufrufe[1]["messages"]
    assert zweiter[-2]["reasoning"] == "Ich suche Merz." and zweiter[-2]["tool_calls"][0]["id"] == "c1"
    assert zweiter[-1]["role"] == "tool" and '"Bundeskanzl."' in zweiter[-1]["content"]


def test_tool_fehler_geht_als_text_ans_modell(dip):
    llm = FakeLLM(
        [
            NS(content="", tool_calls=[tool_call(1, "dip_get_fraktionsverteilung", {"wahlperiode": 25})]),
            NS(content="Gibt es nicht.", tool_calls=None),
        ]
    )
    (antwort,), _ = mit_agent(dip, llm, ["WP 25?"])
    assert antwort.tool_aufrufe[0]["fehler"] is True
    assert "keine Fraktionszugehörigkeiten" in llm.aufrufe[1]["messages"][-1]["content"]


@pytest.mark.parametrize("argumente", ['{"wahlperiode": 20', "[20]"])
def test_ungueltige_tool_argumente_gehen_als_fehler_ans_modell(dip, argumente):
    # Kaputtes JSON oder kein Objekt: kein Absturz, das Modell bekommt eine Fehlermeldung und kann korrigieren.
    kaputt = NS(id="c1", function=NS(name="dip_get_fraktionsverteilung", arguments=argumente))
    llm = FakeLLM([NS(content="", tool_calls=[kaputt]), NS(content="Korrigiert.", tool_calls=None)])
    (antwort,), _ = mit_agent(dip, llm, ["WP 20?"])
    assert antwort.tool_aufrufe[0]["fehler"] is True and antwort.text == "Korrigiert."
    assert "kein gültiges JSON-Objekt" in llm.aufrufe[1]["messages"][-1]["content"]


def test_letzter_schritt_ohne_tools(dip):
    schleife = [NS(content="", tool_calls=[tool_call(i, "dip_get_fraktionsverteilung", {"wahlperiode": 20})]) for i in range(2)]
    llm = FakeLLM([*schleife, NS(content="Zusammenfassung.", tool_calls=None)])
    (antwort,), _ = mit_agent(dip, llm, ["Frage"], max_steps=3)
    assert [a["tool_choice"] for a in llm.aufrufe] == ["auto", "auto", "none"] and antwort.text == "Zusammenfassung."


def test_folgefrage_behaelt_verlauf(dip):
    llm = FakeLLM([NS(content="Welchen Müller?", tool_calls=None), NS(content="Sascha Müller …", tool_calls=None)])
    mit_agent(dip, llm, ["Wer ist Müller?", "Sascha Müller"])
    assert [m["role"] for m in llm.aufrufe[1]["messages"]] == ["system", "user", "assistant", "user"]


def test_bericht_dateien_tabelle_und_zaehlweise_ueber_mcp(dip, tmp_path):
    text = "In der 20. Wahlperiode zählt DIP 774 Personen; stärkste Fraktion ist die SPD mit 219 Personen (28,3 %)."
    llm = FakeLLM([NS(content=text, tool_calls=None)])

    async def lauf():
        async with Client(create_server(dip)) as mcp:
            return await bericht_erstellen(mcp, llm, 20, tmp_path)

    b = asyncio.run(lauf())
    assert sorted(d.name for d in b.dateien) == ["wp20_auswertung.md", "wp20_fraktionszugehoerigkeit.csv"]
    md = (tmp_path / "wp20_auswertung.md").read_text(encoding="utf-8")
    assert text in md and "| SPD | 219 | 28,3 % |" in md and "| **Gesamt** | **774** | |" in md
    assert f"**Zählweise:** {ZAEHLWEISE}" in md  # aus dem Feld zaehlweise des Tool-Ergebnisses
    assert "BSW (Gruppe)" in md  # Hinweis auf Fraktionswechsel aus dem Tool-Ergebnis
    assert llm.aufrufe[0]["tools"] is None and ZAEHLWEISE in llm.aufrufe[0]["messages"][1]["content"]
