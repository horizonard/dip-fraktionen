# MCP-Server: Referenz

Der Server stellt Daten aus der DIP-API des Bundestags (Dokumentations- und Informationssystem für Parlamentsmaterialien) über das Model Context Protocol bereit. Er liest nur. Quelle der Angaben auf dieser Seite: `src/dip_fraktionen/server.py`, `fraktion.py`, `personen.py`, `dip_client.py`, `cli.py`, `settings.py`, `Dockerfile`.

Wie die Fraktion einer Person bestimmt wird und welche Abweichungen das erzeugt, steht in [annahmen-und-entscheidungen.md](annahmen-und-entscheidungen.md).

| Bestandteil | Name | Zweck |
|---|---|---|
| Tool | `dip_get_fraktionsverteilung` | Anzahl und Anteil der Personen je Fraktion in einer Wahlperiode |
| Tool | `dip_get_person` | Auskunft zu einer Person |
| Resource | `dip://fraktionszugehoerigkeit/{wahlperiode}` | Fraktion jeder Person einer Wahlperiode als CSV |

## 1. Start und Anbindung

```bash
uv run dip-fraktionen serve               # lokal
docker run --rm -i dip-fraktionen serve   # im Container
```

Der Server spricht MCP über stdio: Der Client startet ihn als eigenen Prozess. Logs gehen nach stderr, Stufe über `--log-level` (Standard `WARNING`), weil stdout dem MCP-Protokoll gehört.

Einbindung in einen MCP-Client, der lokale Server per Befehl startet (Beispiel Claude Desktop, `claude_desktop_config.json`):
```json
{"mcpServers": {"dip-fraktionen": {"command": "uv", "args": ["--directory", "C:/Pfad/zu/dip-fraktionen", "run", "dip-fraktionen", "serve"]}}}
```

`report`, `chat` und `ask` starten den Server auf dieselbe Weise selbst. Der Server-Prozess erhält keine Umgebungsvariablen, die mit `LLM_`, `GROQ_` oder `OPENAI_` beginnen.

**Umgebungsvariablen des Servers**

| Variable | Standard | Bedeutung |
|---|---|---|
| `DIP_API_KEY` | – (Pflicht) | öffentlicher Key von https://dip.bundestag.de/über-dip/hilfe/api (laut Bundestag zunächst bis Ende Mai 2027 gültig) oder eigener Key für den Dauerbetrieb |
| `DIP_BASE_URL` | `https://search.dip.bundestag.de/api/v1` | |
| `DIP_TIMEOUT_S` | `30` | Timeout je HTTP-Anfrage in Sekunden |
| `CACHE_TTL_S` | `86400` | Gültigkeit der zwischengespeicherten Personenliste je Wahlperiode in Sekunden |

## 2. Server-instructions

Der Server sendet beim Verbindungsaufbau diesen Text:

> Parlamentsdaten aus DIP, dem Dokumentations- und Informationssystem für Parlamentsmaterialien des Deutschen Bundestags, nur lesend: Fraktionsverteilungen je Wahlperiode und Angaben zu Abgeordneten, Regierungs- und Bundesratsmitgliedern. Drucksachen, Vorgänge und Plenarprotokolle aus DIP bietet dieser Server nicht an.

Nicht jeder Client wertet instructions aus. Alles, was ein Modell für einen korrekten Aufruf braucht, steht deshalb in den Tool-Beschreibungen.

## 3. Tools

Gemeinsam für beide Tools:
- Annotationen `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: true` und ein `title`.
- Die Eingabeschemas sind von Hand geschrieben: optionale Parameter stehen nicht in `required`, es gibt keinen `null`-Typ, kein `anyOf` und kein `maximum`. Grund: Groq prüft Tool-Argumente selbst gegen das Schema und lehnt Verstöße mit HTTP 400 ab, bevor der Server eine verständliche Meldung geben kann. Typ und Wertebereich der bekannten Parameter prüft der Server selbst, damit diese Fehlermeldungen auf Deutsch und verständlich sind (Abschnitt 3.3). Unbekannte Parameter schließt das Schema aus (`additionalProperties: false`); kommen sie trotzdem, weist sie die MCP-Bibliothek fastmcp vor dem Server-Code mit ihrer eigenen, englischen Meldung ab.
- Das Ergebnis ist JSON, als `structuredContent` und als Text. Felder ohne Wert werden weggelassen.
- Beschreibung und Schema im Wortlaut: `BESCHREIBUNG_VERTEILUNG`, `SCHEMA_VERTEILUNG`, `BESCHREIBUNG_PERSON`, `SCHEMA_PERSON` in `server.py`, oder per `tools/list`.

### 3.1 `dip_get_fraktionsverteilung`

**Eingabe:** `wahlperiode` (Pflicht, ganze Zahl ab 1).

**Ergebnis** (WP 20, Hinweise gekürzt):
```json
{"wahlperiode": 20, "gesamt": 774,
 "zaehlweise": "Jede Person, die in der Wahlperiode einer Fraktion angehörte, auch Nachrücker, zählt einmal bei ihrer Hauptfraktion; …",
 "verteilung": [{"fraktion": "SPD", "anzahl": 219, "anteil_prozent": 28.3},
                {"fraktion": "CDU/CSU", "anzahl": 204, "anteil_prozent": 26.4}, …],
 "hinweise": ["26 doppelte Personeneinträge in DIP sind zusammengeführt.",
              "Nicht gezählt: 239 Personen ohne Fraktionsangabe in DIP für diese Wahlperiode (z. B. Mitglieder des Bundesrats oder der Bundesregierung).",
              "46 Personen gehörten in der Wahlperiode mehreren Fraktionen oder Gruppen an (u. a. fraktionslos, Die Linke (Gruppe), BSW (Gruppe)); …"]}
```

| Feld | Bedeutung |
|---|---|
| `gesamt` | Anzahl Personen mit Fraktion in der Wahlperiode |
| `zaehlweise` | fester Text, der die Zählweise beschreibt; der Bericht übernimmt ihn aus diesem Feld |
| `verteilung` | absteigend nach Anzahl, bei Gleichstand alphabetisch; Anteil auf eine Nachkommastelle gerundet, die Summe kann daher von 100 abweichen |
| `hinweise` | nur wenn zutreffend: Anzahl nicht gezählter Personen ohne Fraktionsangabe in DIP, Anzahl zusammengeführter doppelter Einträge, Anzahl der Personen mit mehreren Fraktionen oder Gruppen (mit den drei häufigsten weiteren) |

### 3.2 `dip_get_person`

**Eingabe:** genau einer von `name` (Text, höchstens 200 Zeichen) oder `person_id` (Ziffern, als Text oder Zahl).

**Ergebnis** je nach `status` (Beispiele gekürzt):
```json
{"status": "gefunden", "person": {"person_id": "8167", "name": "Friedrich Merz", "funktion_aktuell": "Bundeskanzl.",
  "fraktion_je_wahlperiode": {"13": ["CDU/CSU"], …, "20": ["CDU/CSU"]},
  "hinweise": ["DIP führt für diese Person keine aktuelle Fraktion; bei Mitgliedern der Bundesregierung ist das in DIP üblich.", …]}}

{"status": "mehrdeutig", "gesucht": "Mueller",
 "kandidaten": [{"person_id": "…", "name": "…", "funktion": "…", "fraktion": "…", "wahlperioden": [20, 21]}, …],
 "weitere_treffer": …}

{"status": "nicht_gefunden", "gesucht": "Max Mustermann"}
```

| Feld in `person` | Bedeutung |
|---|---|
| `name` | Vorname, Namenszusatz und Nachname, z. B. „Beatrix von Storch“, „Ursula von der Leyen“ |
| `weitere_ids` | nur wenn DIP die Person unter mehreren IDs führt |
| `funktion_aktuell` | aktuelle Funktion so, wie DIP sie führt, teils abgekürzt (z. B. „Bundeskanzl.“) |
| `fraktion_aktuell` | aktuelle Fraktion laut DIP; fehlt, wenn DIP keine führt (z. B. bei Regierungsmitgliedern) |
| `fraktion_je_wahlperiode` | Wahlperiode → Fraktionen in DIP-Reihenfolge, nach derselben Regel wie die Zählung in `dip_get_fraktionsverteilung`; mehrere Einträge bedeuten einen Wechsel innerhalb der Wahlperiode |
| `aemter` | `{"ressort", "wahlperioden"}` für Regierungsämter (DIP nennt nur das Ministerium, nicht ob Minister oder Staatssekretär) und `{"landesamt", "land", "wahlperioden"}` |
| `hinweise` | keine aktuelle Fraktion in DIP; Lücken in der Folge der Wahlperioden |

`kandidaten` sind nach der jüngsten Wahlperiode sortiert, höchstens 10; `weitere_treffer` nennt die Zahl der übrigen. Ausgewertet wird die erste Ergebnisseite der DIP-Namenssuche; bei sehr häufigen Namen kann `weitere_treffer` daher zu niedrig sein. Eine unbekannte `person_id` ergibt `nicht_gefunden`, keinen Fehler.

**Namenssuche.** Die DIP-Suche findet einzelne Namensteile („Merz“), aber nicht „Friedrich Merz“. Der Server geht deshalb so vor:
1. Die Eingabe in Namensteile zerlegen (auch „Merz, Friedrich“).
2. In DIP mit dem letzten Namensteil suchen; ohne Treffer mit dem ersten.
3. Die übrigen Namensteile gegen die Angaben prüfen, die DIP zur Person führt: Anfang eines Vornamens, Nachname, Namenszusatz (z. B. „von der“, „dos“) oder akademischer Titel (z. B. „Dr.“); Groß-/Kleinschreibung egal, Umlaute und ß auch in Umschreibung („Juergen“ = „Jürgen“). Es gibt keine eigene Liste von Titeln oder Namenszusätzen.
4. Treffer mit gleichem Vornamen, Nachnamen und Namenszusatz zu einer Person zusammenfassen, wenn sie mindestens eine Wahlperiode gemeinsam haben. Ohne gemeinsame Wahlperiode gelten sie als verschiedene Personen.

Grenzen der Suche: getrennt geschriebene Doppelvornamen („Anna Lena Baerbock“) werden nicht gefunden, „Annalena Baerbock“ und „Baerbock“ schon. Anreden („Herr“, „Frau“) und Titel, die DIP für die Person nicht führt, verhindern einen Treffer. Es gibt keinen Filter, etwa nach Wahlperiode.

### 3.3 Fehlermeldungen

Fehler kommen als Tool-Ergebnis mit `isError: true` und diesem Text:

| Situation | Meldung |
|---|---|
| `wahlperiode` fehlt, ist keine ganze Zahl (Ziffern als Text gelten) oder kleiner als 1 | „Die Wahlperiode ist eine ganze Zahl ab 1, z. B. 20.“ |
| DIP liefert für die Wahlperiode keine Person mit Fraktion, auch bei einer Wahlperiode, die es nicht gibt (z. B. 25) | „DIP liefert für die N. Wahlperiode keine Fraktionszugehörigkeiten.“ |
| unbekannter Parameter (z. B. `wahlperiode` an `dip_get_person`) | Meldung der MCP-Bibliothek fastmcp (englisch) |
| weder `name` noch `person_id` | „Entweder name oder person_id angeben.“ |
| beide Parameter | „Genau einen der Parameter name oder person_id angeben, nicht beide.“ |
| `name` kein Text oder länger als 200 Zeichen | „name ist ein Text mit höchstens 200 Zeichen, z. B. „Friedrich Merz“.“ |
| `person_id` weder Ziffern als Text noch ganze Zahl | „person_id besteht nur aus Ziffern, z. B. 8167. Ohne bekannte ID mit name suchen.“ |
| DIP nach allen Versuchen nicht erreichbar | „Die Datenquelle DIP ist derzeit nicht erreichbar.“ |
| DIP antwortet mit 401 oder 403 | „Der Zugriff auf die Datenquelle DIP ist derzeit nicht möglich.“ |
| andere 4xx-Antwort von DIP | „Die Anfrage an die Datenquelle DIP ist fehlgeschlagen.“ |
| unerwarteter Fehler | allgemeine Meldung ohne Details (`mask_error_details`) |

Details stehen nur im Log.

## 4. Resource `dip://fraktionszugehoerigkeit/{wahlperiode}`

CSV, UTF-8, Semikolon als Trenner, eine Zeile je Person, nach Namen sortiert. Ungültige Wahlperioden und DIP-Fehler ergeben dieselben Meldungen wie bei `dip_get_fraktionsverteilung`; liefert DIP keine Person mit Fraktion, enthält die CSV nur die Kopfzeile. Beispiel aus `examples/wp21_fraktionszugehoerigkeit.csv`:
```
person_id;name;fraktion;fraktionen_in_wahlperiode
2151;Beatrix von Storch;AfD;AfD
1567;Mahmut Özdemir;SPD;SPD
```

| Spalte | Bedeutung |
|---|---|
| `fraktion` | Hauptfraktion, so wie sie in die Verteilung eingeht |
| `fraktionen_in_wahlperiode` | alle Fraktionen der Person in der Wahlperiode, getrennt durch „ \| “ |

## 5. Betrieb

| Thema | Verhalten |
|---|---|
| DIP-Anfragen | nacheinander. Eine Wahlperiode lädt alle Seiten von `/person?f.wahlperiode=N` (Cursor-Pagination). Eine Namenssuche braucht 1 bis 2 Anfragen, eine Suche per `person_id` 2 (die zweite findet weitere DIP-Einträge derselben Person) |
| Cache | nur die Personenliste je Wahlperiode, im Prozessspeicher, für `CACHE_TTL_S`. Neustart leert ihn. Neue DIP-Daten erscheinen erst nach Ablauf oder Neustart |
| Wiederholungen | bis zu 4 Versuche bei 429, 5xx, Timeout und Netzwerkfehlern; Pause 0,5, 1, 2 s, bei `Retry-After` dessen Wert (höchstens 30 s). 401, 403 und andere 4xx werden nicht wiederholt, 404 gilt als leeres Ergebnis |
| API-Key | im Header `Authorization: ApiKey …`, nicht in URLs oder Logs |

Die erste Abfrage einer Wahlperiode kann bei langsamer DIP-API länger dauern als das Tool-Timeout mancher Clients. Eine Wiederholung kommt dann aus dem Cache, sofern der Server den Abruf abgeschlossen hat.

## 6. Sicherheit

- Nur lesender Zugriff auf eine öffentliche API, kein freier Durchgriff: zwei Tools mit begrenzten Parametern.
- Der Server ist nicht über das Netz erreichbar; nur der Prozess, der ihn startet, kann ihn nutzen.
- Zugangsdaten nur über Umgebungsvariablen. Der Container läuft als Benutzer `app`, nicht als root.
- Der Server speichert nichts dauerhaft. Zum Datenschutz siehe [annahmen-und-entscheidungen.md](annahmen-und-entscheidungen.md#8-datenschutz).

## 7. Grenzen der Schnittstelle

- Kein detailliertes `outputSchema`; die Struktur der Ergebnisse steht nur in dieser Referenz und in den Tool-Beschreibungen.
- Fehler sind Text ohne maschinenlesbaren Code.
