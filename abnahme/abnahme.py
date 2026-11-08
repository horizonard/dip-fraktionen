"""Live-Abnahmetest: Ruft das Sprachmodell die richtigen Tools mit den richtigen Argumenten auf?

10 feste Fragen, je ein Lauf, echtes DIP und echtes Sprachmodell. Bewertet wird nur die Tool-Wahl einschließlich der
Argumente; das ist weitgehend unabhängig vom Modell und eignet sich, um ein anderes Modell schnell zu prüfen. Den
Antworttext bewertet der Test nicht, weil er von Modell, Temperatur und Zufall abhängt; er steht zum Lesen im Protokoll.
Ergebnis als Markdown unter examples/abnahme_<datum>.md (oder im angegebenen Zielordner).
Aufruf: uv run python abnahme/abnahme.py [zielordner]   (LLM_API_KEY bzw. GROQ_API_KEY und DIP_API_KEY müssen gesetzt sein)
Exit-Code: 0 alle bewerteten Fragen bestanden, 1 nicht alle bestanden, 2 Lauf abgebrochen.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import sys
import time
from pathlib import Path
from typing import Any

from dip_fraktionen.agent import Agent
from dip_fraktionen.llm import LLM, LeereAntwort, LLMFehler
from dip_fraktionen.mcp_verbindung import mcp_client
from dip_fraktionen.settings import KonfigurationsFehler, Settings

V, P = "dip_get_fraktionsverteilung", "dip_get_person"
# Je Frage die erwarteten Aufrufe: Tool und Argumente (Text = Teilstring ohne Groß-/Kleinschreibung, Zahl = gleicher Wert).
# None = keine Erwartung (mehrere Verhaltensweisen sind richtig); die Antwort steht nur zum Lesen im Protokoll.
FRAGEN: list[tuple[str, list[tuple[str, dict[str, Any]]] | None]] = [
    ("Wie ist die Fraktionsverteilung in der 20. Wahlperiode?", [(V, {"wahlperiode": 20})]),
    ("Wer ist Friedrich Merz?", [(P, {"name": "merz"})]),
    ("Wie viel Prozent der Abgeordneten gehörten in der 20. Wahlperiode zur SPD?", [(V, {"wahlperiode": 20})]),
    ("Wie ist die Fraktionsverteilung in der 19. Wahlperiode?", [(V, {"wahlperiode": 19})]),
    ("Vergleiche die Fraktionsverteilung der 19. und 20. Wahlperiode.", [(V, {"wahlperiode": 19}), (V, {"wahlperiode": 20})]),
    ("Welcher Fraktion gehörte Sahra Wagenknecht in der 20. Wahlperiode an?", [(P, {"name": "wagenknecht"})]),
    ("Wer ist Müller?", None),  # Suche mit Kandidatenliste oder direkte Rückfrage sind beide richtig
    ("Wer ist Max Mustermann?", [(P, {"name": "mustermann"})]),
    ("Wie ist die Fraktionsverteilung in der 25. Wahlperiode?", [(V, {"wahlperiode": 25})]),
    ("Wie hat Friedrich Merz zum Heizungsgesetz abgestimmt?", None),  # Absage mit oder ohne Personensuche ist richtig
]


def argumente_passen(erwartet: dict[str, Any], ist: Any) -> bool:
    if not isinstance(ist, dict):
        return False
    for schluessel, wert in erwartet.items():
        if isinstance(wert, str):
            if wert.lower() not in str(ist.get(schluessel, "")).lower():
                return False
        elif str(ist.get(schluessel)) != str(wert):  # 20 und "20" gelten als gleich
            return False
    return True


async def main() -> int:
    try:
        s = Settings.fuer_befehle()
    except KonfigurationsFehler as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return 2
    llm = LLM(s)
    zeilen, bestanden, bewertet, abbruch = [], 0, 0, ""
    async with mcp_client() as mcp:
        for i, (frage, erwartet) in enumerate(FRAGEN, 1):
            bewertet += erwartet is not None
            agent = Agent(mcp, llm, s.agent_max_steps)
            await agent.starten()
            t0 = time.time()
            try:
                antwort = await agent.frage(frage)
            except LeereAntwort as e:  # betrifft nur diese Frage, der Lauf geht weiter
                zeilen.append(f"### {i}. {frage}\n\n**{'NICHT bestanden' if erwartet is not None else 'ohne Erwartung'}** · {e}\n")
                print(f"{i:2d} FAIL {e}", flush=True)
                continue
            except LLMFehler as e:  # z. B. Rate-Limit: kein gültiges Ergebnis, die übrigen Fragen werden nicht gestellt
                abbruch = f"Lauf bei Frage {i} abgebrochen: {e}"
                zeilen.append(f"### {i}. {frage}\n\n**abgebrochen** · {abbruch}\n")
                print(f"{i:2d} FAIL {abbruch}", flush=True)
                break
            dauer = time.time() - t0
            aufrufe = ", ".join(f"{a['tool']}({a['argumente']})" for a in antwort.tool_aufrufe) or "–"
            if erwartet is None:
                urteil, fehlend = "ohne Erwartung", []
            else:
                fehlend = [
                    f"{t}({a})"
                    for t, a in erwartet
                    if not any(x["tool"] == t and argumente_passen(a, x["argumente"]) for x in antwort.tool_aufrufe)
                ]
                urteil = "NICHT bestanden" if fehlend else "bestanden"
                bestanden += not fehlend
            zeilen.append(
                f"### {i}. {frage}\n\n**{urteil}** · Tools: {aufrufe} · {dauer:.1f} s"
                + (f" · erwarteter Aufruf fehlt: {', '.join(fehlend)}" if fehlend else "")
                + f"\n\n{antwort.text}\n"
            )
            print(f"{i:2d} {'FAIL' if fehlend else 'OK  '} {dauer:5.1f}s {aufrufe}", flush=True)
    kopf = (
        f"# Abnahmetest {dt.date.today().isoformat()}\n\nModell: {llm.modell} · "
        f"Tool-Wahl: **{bestanden}/{bewertet} bestanden**{f' ({abbruch})' if abbruch else ''}\n\n"
        "Bewertet wird nur, ob die erwarteten Tools mit den erwarteten Argumenten aufgerufen wurden. "
        "Die Antworttexte stehen zum Lesen darunter; sie werden nicht automatisch bewertet.\n"
    )
    ordner = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "examples"
    ziel = ordner / f"abnahme_{dt.date.today().isoformat()}.md"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(kopf + "\n" + "\n".join(zeilen), encoding="utf-8")
    print(f"{bestanden}/{bewertet} bestanden -> {ziel}")
    if abbruch:
        return 2  # Lauf unvollständig (z. B. Rate-Limit), kein gültiges Ergebnis
    return 0 if bestanden == bewertet else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
