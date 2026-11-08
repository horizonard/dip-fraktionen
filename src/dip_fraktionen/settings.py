"""Konfiguration ausschließlich über Umgebungsvariablen (siehe .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


class KonfigurationsFehler(ValueError):
    """Eine Umgebungsvariable fehlt oder hat einen ungültigen Wert; die Meldung ist für Nutzer gedacht."""


MELDUNG_DIP_KEY = (
    "Kein DIP-API-Key gesetzt (DIP_API_KEY). Einen öffentlichen Key veröffentlicht der Bundestag unter "
    "https://dip.bundestag.de/über-dip/hilfe/api; für den Dauerbetrieb einen eigenen Key beantragen."
)


@dataclass(frozen=True)
class Settings:
    dip_api_key: str
    dip_base_url: str
    dip_timeout_s: float
    cache_ttl_s: int
    llm_api_key: str | None
    llm_base_url: str
    llm_model: str
    llm_reasoning_effort: str
    llm_temperature: float
    agent_max_steps: int
    llm_max_wait_s: float

    @classmethod
    def aus_umgebung(cls) -> Settings:
        env = os.environ.get
        return cls(
            dip_api_key=env("DIP_API_KEY", ""),
            dip_base_url=env("DIP_BASE_URL", "https://search.dip.bundestag.de/api/v1"),
            dip_timeout_s=_zahl("DIP_TIMEOUT_S", "30", float),
            cache_ttl_s=_zahl("CACHE_TTL_S", "86400", int),
            llm_api_key=env("LLM_API_KEY") or env("GROQ_API_KEY"),
            llm_base_url=env("LLM_BASE_URL", "https://api.groq.com/openai/v1"),
            llm_model=env("LLM_MODEL", "openai/gpt-oss-20b"),
            llm_reasoning_effort=env("LLM_REASONING_EFFORT", "low"),
            llm_temperature=_zahl("LLM_TEMPERATURE", "0.0", float),
            agent_max_steps=_zahl("AGENT_MAX_STEPS", "5", int),
            llm_max_wait_s=_zahl("LLM_MAX_WAIT_S", "60", float),
        )

    @classmethod
    def fuer_befehle(cls) -> Settings:
        """Einstellungen für CLI und Abnahme: wie aus_umgebung, zusätzlich ist der DIP-Key Pflicht (alle Befehle nutzen DIP)."""
        s = cls.aus_umgebung()
        if not s.dip_api_key:
            raise KonfigurationsFehler(MELDUNG_DIP_KEY)
        return s


def _zahl(name: str, standard: str, typ: type[int | float]) -> Any:
    wert = os.environ.get(name, standard)
    try:
        return typ(wert)
    except ValueError:
        raise KonfigurationsFehler(f"{name} muss eine Zahl sein, z. B. {standard} (gesetzt: „{wert}“).") from None
