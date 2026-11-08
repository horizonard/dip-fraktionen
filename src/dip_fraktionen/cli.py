"""Kommandozeile.

dip-fraktionen serve                          MCP-Server starten (stdio)
dip-fraktionen report --wahlperiode 20        Bericht: CSV je Person und vom Sprachmodell formulierte Auswertung
dip-fraktionen chat                           Interaktiver Chat (das Modell wählt die Tools selbst)
dip-fraktionen ask "Wer ist Friedrich Merz?"  Einzelne Frage
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path


def _logging(stufe: str) -> None:
    # stderr ist Pflicht: Bei stdio-Transport gehört stdout ausschließlich dem MCP-Protokoll.
    logging.basicConfig(stream=sys.stderr, level=stufe.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for name in ("httpx", "httpx2"):  # keine Zeile je HTTP-Anfrage (DIP-Seiten, LLM-Aufrufe)
        logging.getLogger(name).setLevel(logging.WARNING)


def _serve(a: argparse.Namespace) -> None:
    from dip_fraktionen.dip_client import DipClient
    from dip_fraktionen.server import create_server
    from dip_fraktionen.settings import Settings

    create_server(DipClient(Settings.aus_umgebung())).run(show_banner=False)


async def _report(a: argparse.Namespace) -> int:
    from dip_fraktionen.bericht import bericht_erstellen
    from dip_fraktionen.llm import LLM
    from dip_fraktionen.mcp_verbindung import mcp_client
    from dip_fraktionen.settings import Settings

    llm = LLM(Settings.aus_umgebung())
    async with mcp_client() as mcp:
        b = await bericht_erstellen(mcp, llm, a.wahlperiode, Path(a.ausgabe))
    for d in b.dateien:
        print(d)
    return 0


async def _chat(a: argparse.Namespace) -> int:
    from dip_fraktionen.agent import Agent
    from dip_fraktionen.llm import LLM, LLMFehler
    from dip_fraktionen.mcp_verbindung import mcp_client
    from dip_fraktionen.settings import Settings

    s = Settings.aus_umgebung()
    llm = LLM(s)
    async with mcp_client() as mcp:
        agent = Agent(mcp, llm, s.agent_max_steps)
        await agent.starten()
        if a.befehl == "ask":
            print((await agent.frage(a.frage)).text)
            return 0
        print(f"Bundestag-Auskunft ({llm.modell}). Beenden mit 'exit'.")
        while True:
            try:
                eingabe = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if eingabe.lower() in {"exit", "quit", "ende"}:
                return 0
            if eingabe:
                try:
                    print("\n" + (await agent.frage(eingabe)).text)
                except LLMFehler as e:  # Sitzung bleibt offen, die Frage kann erneut gestellt werden
                    print(f"\nFehler: {e}", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="dip-fraktionen", description="Fraktionsauswertung des Deutschen Bundestags über die DIP-API (MCP).")
    p.add_argument("--log-level", default="WARNING", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    sub = p.add_subparsers(dest="befehl", required=True)
    sub.add_parser("serve", help="MCP-Server über stdio starten (für MCP-Clients)")
    r = sub.add_parser("report", help="Bericht zur Fraktionsverteilung einer Wahlperiode erzeugen")
    r.add_argument("--wahlperiode", type=int, required=True)
    r.add_argument("--ausgabe", default="out", help="Ausgabeordner (Standard: out)")
    sub.add_parser("chat", help="Interaktiver Chat")
    q = sub.add_parser("ask", help="Einzelne Frage stellen")
    q.add_argument("frage")
    a = p.parse_args(argv)
    os.environ.setdefault("FASTMCP_LOG_LEVEL", a.log_level)  # vor dem ersten Import von fastmcp setzen
    _logging(a.log_level)

    from dip_fraktionen.bericht import BerichtFehler
    from dip_fraktionen.llm import LLMFehler
    from dip_fraktionen.settings import KonfigurationsFehler, Settings

    try:  # Konfiguration einmal vorab prüfen, damit Fehler als Meldung statt als Traceback erscheinen
        Settings.fuer_befehle()
    except KonfigurationsFehler as e:
        print(f"Fehler: {e}", file=sys.stderr)
        sys.exit(1)
    try:
        if a.befehl == "serve":
            _serve(a)
        elif a.befehl == "report":
            sys.exit(asyncio.run(_report(a)))
        else:
            sys.exit(asyncio.run(_chat(a)))
    except (LLMFehler, BerichtFehler) as e:
        print(f"Fehler: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
