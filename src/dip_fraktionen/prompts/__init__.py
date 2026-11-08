"""System-Prompts als eigene Dateien (getrennt vom Code, versionierbar, im Review lesbar)."""

from __future__ import annotations

from functools import cache
from importlib import resources


@cache
def prompt(name: str) -> str:
    return resources.files(__name__).joinpath(name).read_text(encoding="utf-8").strip()
