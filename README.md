# dip-fraktionen

Das Projekt ermittelt aus der DIP-API des Deutschen Bundestags die Fraktionszugehörigkeit jeder Person einer Wahlperiode und berechnet den Anteil je Fraktion. Die Daten stellt ein MCP-Server bereit. Ein Sprachmodell formuliert daraus einen Bericht und beantwortet im Chat Fragen, für die es die Tools selbst wählt.

Erstübergabe.

## Schnellstart

Die Befehle sind für eine Linux- oder macOS-Shell; unter Windows WSL oder Docker Desktop verwenden.

Mit Docker:
```bash
cp .env.example .env      # LLM_API_KEY und DIP_API_KEY eintragen (siehe Kommentare in .env.example)
docker build -t dip-fraktionen .
mkdir -p out              # Ausgabeordner vorab anlegen, damit der Container hineinschreiben darf
docker run --rm --env-file .env -v "$PWD/out:/app/out" dip-fraktionen report --wahlperiode 20
docker run --rm -it --env-file .env dip-fraktionen chat
```

Lokal mit [uv](https://docs.astral.sh/uv/) und Python 3.12:
```bash
uv sync
export LLM_API_KEY=...    # oder GROQ_API_KEY; kostenloser Key: https://console.groq.com/keys
export DIP_API_KEY=...    # öffentlicher Key: https://dip.bundestag.de/über-dip/hilfe/api
uv run dip-fraktionen report --wahlperiode 20
uv run dip-fraktionen ask "Wer ist Friedrich Merz?"
```
Alternativ die Keys in `.env` eintragen (`cp .env.example .env`) und mit `uv run --env-file .env dip-fraktionen …` starten; ohne `--env-file` liest das Programm die Datei nicht.

Alle Einstellungen (Modell, Anbieter, DIP-Key, Cache) stehen mit Standardwerten in [.env.example](.env.example). Im Code ist kein Key hinterlegt.

## Befehle

| Befehl | Zweck |
|---|---|
| `dip-fraktionen report --wahlperiode N [--ausgabe out]` | schreibt `wpN_fraktionszugehoerigkeit.csv` (Fraktion jeder Person) und `wpN_auswertung.md` (Text vom Sprachmodell, Tabelle und Zählweise vom Code); bei einem Fehler werden keine Dateien geschrieben |
| `dip-fraktionen ask "Frage"` | eine Frage beantworten |
| `dip-fraktionen chat` | Chat, beenden mit `exit` |
| `dip-fraktionen serve` | nur den MCP-Server starten, zur Einbindung in andere MCP-Clients |
| `dip-fraktionen --log-level DEBUG …` | ausführlichere Logs auf stderr |

| Make-Ziel | Zweck |
|---|---|
| `make check` | Lint und Offline-Tests (ohne Netz und ohne Sprachmodell); einzeln: `make lint`, `make test` |
| `make abnahme` | Abnahmetest mit 10 Fragen gegen DIP und das Sprachmodell: werden die richtigen Tools mit den richtigen Argumenten aufgerufen? |
| `make examples` | alle Dateien in `examples/` neu erzeugen (nutzt DIP und das Sprachmodell); der Ordner wird nur ersetzt, wenn kein Schritt abbricht (nicht bestandene Abnahmefragen sind ein Ergebnis, kein Abbruch) |
| `make docker-build` | Docker-Image bauen |

## Architektur

```
 report        chat / ask         anderer MCP-Client
    │               │                     │
    └──────── MCP (stdio) ────────────────┘
                    │
     ┌──────────────▼───────────────────────────┐
     │ MCP-Server                               │
     │  Tool dip_get_fraktionsverteilung        │
     │  Tool dip_get_person                     │
     │  Resource dip://fraktionszugehoerigkeit/ │
     └──────────────┬───────────────────────────┘
                    │ HTTPS
       search.dip.bundestag.de/api/v1/person

 Sprachmodell (Standard: Groq, openai/gpt-oss-20b):
 formuliert den Bericht, wählt im Chat die Tools; die Zahlen berechnet der Code.
```

`report`, `chat` und `ask` starten den Server als eigenen Prozess und greifen nur über MCP auf die Daten zu.

| Datei | Inhalt |
|---|---|
| `src/dip_fraktionen/server.py` | Tools, Resource, Fehlermeldungen |
| `fraktion.py` | Zuordnung zur Fraktion und Verteilung |
| `personen.py` | Personensuche |
| `dip_client.py` | Zugriff auf DIP |
| `bericht.py`, `agent.py`, `llm.py` | Bericht, Chat, Sprachmodell |
| `prompts/` | System-Prompts für Bericht und Chat |
| `tests/`, `abnahme/` | Offline-Tests, Abnahmetest |

## Ergebnis

In der 20. Wahlperiode zählt das Tool 774 Personen, die stärkste Fraktion ist die SPD mit 219 Personen (28,3 %). Berichte und CSV-Dateien für die 20. und 21. Wahlperiode, Chat-Antworten auf die beiden Fragen aus dem Auftrag und das Protokoll des Abnahmetests (`abnahme_<datum>.md`) liegen in [examples/](examples/).

## Dokumentation

- [docs/annahmen-und-entscheidungen.md](docs/annahmen-und-entscheidungen.md): Annahmen, Zählweise, Datenabweichungen in DIP, Architekturentscheidungen, Tests und Abnahme, beobachtetes Modellverhalten, Grenzen, Datenschutz, Ausblick
- [docs/mcp-referenz.md](docs/mcp-referenz.md): Tools, Ergebnisfelder, Fehlermeldungen, Resource, Betrieb, Sicherheit
