"""HTTP-Zugriff auf die DIP-API: Authentifizierung, Cursor-Pagination, Retry, Cache der Personenlisten je Wahlperiode."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from typing import Any

import httpx

from dip_fraktionen.settings import Settings

log = logging.getLogger(__name__)


class DipFehler(Exception):
    """Basisklasse für Fehler beim Zugriff auf DIP."""


class DipNichtErreichbar(DipFehler):
    """DIP antwortet nicht oder mit 5xx/429, auch nach Wiederholungen."""


class DipKonfigurationsfehler(DipFehler):
    """DIP lehnt den Zugriff ab (401/403), z. B. ungültiger API-Key."""


class DipClient:
    MAX_VERSUCHE = 4

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self._settings = settings
        self._http = httpx.Client(
            base_url=settings.dip_base_url,
            headers={"Authorization": f"ApiKey {settings.dip_api_key}", "Accept": "application/json"},
            timeout=settings.dip_timeout_s,
            transport=transport,
        )
        self._wp_cache: dict[int, tuple[float, list[dict[str, Any]]]] = {}

    def get(self, pfad: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET mit Retry nur bei 429, 5xx, Timeout und Netzwerkfehlern. 404 liefert {} statt Fehler."""
        for versuch in range(1, self.MAX_VERSUCHE + 1):
            try:
                r = self._http.get(pfad, params=params)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                grund = type(e).__name__
            else:
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 404:
                    return {}
                if r.status_code in (401, 403):
                    raise DipKonfigurationsfehler(f"DIP lehnt den Zugriff ab (HTTP {r.status_code})")
                if r.status_code != 429 and r.status_code < 500:
                    raise DipFehler(f"DIP-Anfrage fehlerhaft (HTTP {r.status_code}): {pfad}")
                grund = f"HTTP {r.status_code}"
                wartezeit = r.headers.get("Retry-After")
                if wartezeit and wartezeit.isdigit() and versuch < self.MAX_VERSUCHE:
                    time.sleep(min(int(wartezeit), 30))
                    continue
            log.warning("DIP %s, Versuch %d/%d: %s", pfad, versuch, self.MAX_VERSUCHE, grund)
            if versuch < self.MAX_VERSUCHE:
                time.sleep(0.5 * 2 ** (versuch - 1))
        raise DipNichtErreichbar(f"DIP nicht erreichbar: {pfad}")

    def alle(self, ressource: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Alle Dokumente einer Abfrage über die Cursor-Pagination (Ende: leere Seite oder unveränderter Cursor)."""
        return list(self._seiten(ressource, params))

    def _seiten(self, ressource: str, params: dict[str, Any]) -> Iterator[dict[str, Any]]:
        cursor = None
        while True:
            seite = self.get(f"/{ressource}", {**params, **({"cursor": cursor} if cursor else {})})
            docs = seite.get("documents", [])
            yield from docs
            if not docs or seite.get("cursor") in (None, cursor):
                return
            cursor = seite["cursor"]

    def personen_der_wahlperiode(self, wahlperiode: int) -> list[dict[str, Any]]:
        """Alle Personendatensätze einer Wahlperiode (ca. 10 Seiten). Einziger Cache: im Prozess, mit Ablaufzeit (CACHE_TTL_S)."""
        jetzt = time.monotonic()
        treffer = self._wp_cache.get(wahlperiode)
        if treffer and jetzt - treffer[0] < self._settings.cache_ttl_s:
            return treffer[1]
        docs = self.alle("person", {"f.wahlperiode": wahlperiode})
        self._wp_cache[wahlperiode] = (jetzt, docs)
        return docs

    def personen_suchen(self, suchbegriff: str) -> list[dict[str, Any]]:
        """Namenssuche über f.person (DIP findet Nach- und Vornamen, nicht aber 'Vorname Nachname' als Ganzes)."""
        return self.get("/person", {"f.person": suchbegriff}).get("documents", [])

    def person_nach_id(self, person_id: str) -> list[dict[str, Any]]:
        return self.get("/person", {"f.id": person_id}).get("documents", [])
