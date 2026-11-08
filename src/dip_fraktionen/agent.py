"""Chat-Agent: Tool-Calling-Schleife über MCP (Bonusaufgabe). Das Modell wählt die Tools selbst.

System-Prompt: prompts/chat_system.md (nur Rolle, Arbeitsweise, Umgang mit Ergebnissen, Grenzen, Format; kein Tool-Wissen –
das steht in den Tool-Beschreibungen des Servers). Die Server-instructions aus dem MCP-Handshake werden angehängt.
gpt-oss/Groq-Besonderheiten: Reasoning wird bei Tool-Aufrufen zurückgegeben (Harmony), keine parallelen Tool-Aufrufe,
im letzten erlaubten Schritt keine Tools mehr (Abschlussantwort statt Abbruch).
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from fastmcp import Client

from dip_fraktionen.llm import LLM, LeereAntwort
from dip_fraktionen.prompts import prompt

log = logging.getLogger(__name__)

SYSTEM_PROMPT = prompt("chat_system.md")


@dataclass
class Antwort:
    text: str
    tool_aufrufe: list[dict[str, Any]] = field(default_factory=list)


class Agent:
    def __init__(self, mcp: Client, llm: LLM, max_steps: int = 5):
        self.mcp, self.llm, self.max_steps = mcp, llm, max_steps
        self.verlauf: list[dict[str, Any]] = []
        self.tools: list[dict[str, Any]] = []

    async def starten(self) -> None:
        """Tools und instructions vom verbundenen MCP-Server übernehmen (Client muss bereits verbunden sein)."""
        self.tools = [
            {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.input_schema}}
            for t in await self.mcp.list_tools()
        ]
        system = SYSTEM_PROMPT
        if self.mcp.instructions:
            system += "\n\n# Hinweise des Datendienstes\n" + self.mcp.instructions
        self.verlauf = [{"role": "system", "content": system}]

    async def frage(self, text: str) -> Antwort:
        self.verlauf.append({"role": "user", "content": text})
        aufrufe: list[dict[str, Any]] = []
        for schritt in range(self.max_steps):
            letzter = schritt == self.max_steps - 1
            m = await asyncio.to_thread(self.llm.antwort, self.verlauf, self.tools, "none" if letzter else "auto")
            tool_calls = getattr(m, "tool_calls", None) or []
            if not tool_calls:
                inhalt = (m.content or "").strip()
                if not inhalt:  # API meldet Erfolg, aber ohne Text: nicht als leere Antwort durchreichen
                    raise LeereAntwort("Das Sprachmodell hat keine Antwort geliefert. Bitte erneut versuchen.")
                self.verlauf.append({"role": "assistant", "content": inhalt})
                return Antwort(inhalt, aufrufe)
            nachricht: dict[str, Any] = {
                "role": "assistant",
                "content": m.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}}
                    for tc in tool_calls
                ],
            }
            reasoning = getattr(m, "reasoning", None) or (getattr(m, "model_extra", None) or {}).get("reasoning")
            if reasoning:
                nachricht["reasoning"] = reasoning  # gpt-oss/Harmony: Gedankengang bei Tool-Aufrufen zurückgeben
            self.verlauf.append(nachricht)
            for tc in tool_calls:
                ergebnis, fehler, args = await self._tool_ausfuehren(tc.function.name, tc.function.arguments)
                aufrufe.append({"tool": tc.function.name, "argumente": args, "fehler": fehler})
                self.verlauf.append({"role": "tool", "tool_call_id": tc.id, "content": ergebnis})
        return Antwort("Ich konnte die Frage nicht in der verfügbaren Anzahl von Schritten beantworten.", aufrufe)

    async def _tool_ausfuehren(self, name: str, argumente: str | None) -> tuple[str, bool, Any]:
        try:
            args = json.loads(argumente or "{}")
        except json.JSONDecodeError:
            args = None
        if not isinstance(args, dict):  # kaputtes JSON oder kein Objekt (z. B. [20]): Modell soll den Aufruf korrigieren
            return "Die Tool-Argumente waren kein gültiges JSON-Objekt.", True, argumente
        log.info("Tool-Aufruf %s %s", name, args)
        r = await self.mcp.call_tool(name, args, raise_on_error=False)
        text = "\n".join(getattr(c, "text", "") for c in r.content) or ("Fehler ohne Text." if r.is_error else "")
        return text, bool(r.is_error), args
