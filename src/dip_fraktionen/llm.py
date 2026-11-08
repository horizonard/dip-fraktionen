"""Zugriff auf ein Sprachmodell über eine OpenAI-kompatible API (Standard: Groq, openai/gpt-oss-20b).

Anbieterwechsel nur per Konfiguration (LLM_BASE_URL, LLM_MODEL, LLM_API_KEY). Wiederholungen bei 429 (Retry-After),
Verbindungsfehlern und den von Groq gemeldeten fehlerhaften Tool-Aufrufen (HTTP 400, failed_generation).
"""

from __future__ import annotations

import logging
import time
from typing import Any

import openai

from dip_fraktionen.settings import Settings

log = logging.getLogger(__name__)
TOOL_400_MERKMALE = ("tool_use_failed", "failed_generation", "Failed to call a function", "tool call validation failed")


class LLMFehler(Exception):
    """Das Sprachmodell ist nicht nutzbar (fehlender Key, Anbieter nicht erreichbar, wiederholte Fehler)."""


class LeereAntwort(LLMFehler):
    """Der Aufruf war erfolgreich, das Modell hat aber keinen Antworttext geliefert (z. B. nur Reasoning)."""


class LLM:
    def __init__(self, settings: Settings, client: Any | None = None):
        if client is None and not settings.llm_api_key:
            raise LLMFehler("Kein API-Key für das Sprachmodell gesetzt (LLM_API_KEY oder GROQ_API_KEY).")
        self.settings = settings
        self.modell = settings.llm_model
        self._client = client or openai.OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key, max_retries=0)

    def antwort(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> Any:
        """Ein Modellaufruf; liefert die Assistant-Nachricht (content, tool_calls, ggf. reasoning)."""
        kwargs: dict[str, Any] = {"model": self.modell, "messages": messages, "temperature": self.settings.llm_temperature}
        if self.settings.llm_reasoning_effort:
            kwargs["reasoning_effort"] = self.settings.llm_reasoning_effort
        if tools:
            kwargs["tools"], kwargs["tool_choice"] = tools, tool_choice or "auto"
        tool_fehler = verbindung = rate = 0
        while True:
            try:
                return self._client.chat.completions.create(**kwargs).choices[0].message
            except openai.RateLimitError as e:
                rate += 1
                warte = _retry_after(e) or 10.0
                # Kurze Wartezeiten abwarten; bei langen (z. B. Tageslimit) sofort mit Zeitangabe abbrechen statt zu blockieren.
                if rate > 5 or warte > self.settings.llm_max_wait_s:
                    raise LLMFehler(
                        f"Das Sprachmodell ist derzeit ausgelastet (Rate-Limit). Bitte in etwa {max(1, round(warte / 60))} Minute(n) erneut versuchen."
                    ) from None
                log.warning("LLM Rate-Limit, warte %.0f s", warte)
                time.sleep(warte)
            except openai.BadRequestError as e:
                if any(m in str(e) for m in TOOL_400_MERKMALE) and tool_fehler < 2:
                    tool_fehler += 1
                    log.warning("Anbieter lehnt fehlerhaften Tool-Aufruf ab, Wiederholung %d: %s", tool_fehler, str(e)[:300])
                    continue
                raise LLMFehler(f"Das Sprachmodell hat die Anfrage abgelehnt: {str(e)[:200]}") from None
            except (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError):
                verbindung += 1
                if verbindung > 3:
                    raise LLMFehler("Das Sprachmodell ist derzeit nicht erreichbar.") from None
                time.sleep(2**verbindung)
            except openai.AuthenticationError:
                raise LLMFehler("Der API-Key für das Sprachmodell ist ungültig.") from None


def _retry_after(e: Exception) -> float | None:
    try:
        return float(e.response.headers.get("retry-after"))  # type: ignore[attr-defined]
    except (AttributeError, TypeError, ValueError):
        return None
