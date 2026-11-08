"""Verbindung der Befehle report/chat/ask zum MCP-Server: der Server läuft als eigener Prozess, Kommunikation über stdio."""

from __future__ import annotations

import logging
import os
import sys

from fastmcp import Client
from fastmcp.client.transports import StdioTransport


def server_umgebung() -> dict[str, str]:
    """Umgebung des Server-Prozesses ohne Zugangsdaten zum Sprachmodell (der Server braucht nur DIP)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LLM_", "GROQ_", "OPENAI_"))}
    env.setdefault("FASTMCP_LOG_LEVEL", "WARNING")
    return env


def mcp_client() -> Client:
    stufe = logging.getLevelName(logging.getLogger().getEffectiveLevel())  # z. B. --log-level DEBUG gilt auch für den Server
    if stufe not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        stufe = "WARNING"
    return Client(
        StdioTransport(command=sys.executable, args=["-m", "dip_fraktionen", "--log-level", stufe, "serve"], env=server_umgebung())
    )
