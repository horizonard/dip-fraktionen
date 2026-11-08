# Annahmen und Entscheidungen

Was das Projekt annimmt, wie es zählt, wo die DIP-Daten abweichen, warum es so gebaut ist und wo seine Grenzen liegen. Tools, Felder und Betrieb des Servers: [mcp-referenz.md](mcp-referenz.md).

## 1. Annahmen

| # | Annahme |
|---|---|
| A1 | Gezählt werden Personen je Wahlperiode, auch Nachrücker, keine Sitze zu einem Stichtag. Jede Person zählt einmal bei ihrer Hauptfraktion. Als „Politiker“ gelten die Personen, die DIP der Wahlperiode zuordnet und für die DIP eine Fraktion führt; Mitglieder des Bundesrats und Personen ohne Fraktion in DIP werden nicht gezählt (Anzahl in `hinweise`). |
| A2 | Datenquelle ist ausschließlich die DIP-API. Abweichungen von amtlichen Zahlen sind laut Auftrag zulässig; die bekannten stehen in Abschnitt 3. |
| A3 | Mit gespeicherten DIP-Antworten getestet sind die Wahlperioden 19, 20 und 21. Die Wahlperioden 1 bis 18 lassen sich abfragen, sind aber nicht durch Tests abgesichert. |
| A4 | Der DIP-API-Key wird über `DIP_API_KEY` gesetzt; im Code ist kein Key hinterlegt. Für den Start genügt der öffentliche Key, den der Bundestag auf seiner Hilfeseite veröffentlicht (laut Bundestag zunächst bis Ende Mai 2027 gültig). |
| A5 | Fragen, Antworten und alle Texte für Nutzer und Modell sind auf Deutsch. Fachbegriffe aus DIP bleiben deutsch, auch im Code und in der MCP-Schnittstelle; technische Begriffe sind englisch. |
| A6 | Der Chat ist auf Einzelfragen ausgelegt. Folgefragen in derselben Sitzung funktionieren (z. B. Rückfragen bei mehrdeutigen Namen); der Verlauf wird nicht gespeichert und nicht gekürzt. |
| A7 | Fehlt in den Rollen einer Wahlperiode die Fraktion, gilt die aktuelle Fraktion aus dem Haupteintrag (Regel in Abschnitt 2). Wer zwischen Wahlperioden die Fraktion gewechselt hat, kann dadurch in einer früheren Wahlperiode der späteren Fraktion zugeordnet sein. |
| A8 | Datensätze mit gleichem Vornamen, Nachnamen und Namenszusatz in einer Wahlperiode gelten als dieselbe Person. DIP führt manche Personen unter mehreren IDs und bietet kein weiteres Merkmal, das eine Person eindeutig kennzeichnet; der Name ist daher der einzige Schlüssel. Die zusammengeführten Einträge der Wahlperioden 19 bis 21 ergaben keinen Hinweis auf verschiedene Personen gleichen Namens. |
| A9 | Hat eine Person in einer Wahlperiode mehrere Fraktionen, gilt die erste in der Reihenfolge von DIP (außer „fraktionslos“). DIP liefert dazu keine Zeitangaben; ob die Reihenfolge chronologisch ist, ist nicht dokumentiert. |

## 2. Zählweise

Grundlage ist `/person?f.wahlperiode=N`, also alle Personen, die DIP der Wahlperiode N zuordnet. Die Fraktion wird nur aus DIP gelesen (`fraktion.py`); fehlende oder abweichende Angaben werden nicht ergänzt oder korrigiert, sondern in Abschnitt 3 beschrieben.

1. **Fraktion je Person:** die Fraktionen aus den Rollen der Person in Wahlperiode N. Die Fraktion aus dem Haupteintrag (die aktuelle Fraktion laut DIP) kommt hinzu, wenn keine Rolle in N eine Fraktion nennt oder wenn N die letzte Wahlperiode der Person ist; das betrifft die meisten Zuordnungen, in der 20. Wahlperiode 623 von 774. Ausnahme: Führt DIP die Person in N nur als Mitglied des Bundesrats oder mit einem Landesamt, ist sie dort kein Mitglied des Bundestags und wird nicht gezählt.
2. **Doppelte Einträge:** Datensätze mit gleichem Vornamen, Nachnamen und Namenszusatz gelten als eine Person.
3. **Hauptfraktion:** Gezählt wird die erste Fraktion in DIP-Reihenfolge, die nicht „fraktionslos“ ist. Wer in DIP keine Fraktion hat, zählt nicht.

Der Anteil ist Anzahl geteilt durch Gesamtzahl, gerundet auf eine Nachkommastelle.

Folgen:
- In der 20. Wahlperiode zählt das Tool 774 Personen, mehr als der Bundestag Sitze hatte (736).
- Wer innerhalb einer Wahlperiode die Fraktion wechselt, zählt nur bei der ersten. In der 20. Wahlperiode betrifft das 46 Personen; die Gruppe BSW erscheint deshalb nicht in der Verteilung.
- DIP liefert keine Zeitpunkte für Fraktionswechsel; „Hauptfraktion“ heißt daher nicht „längste Zugehörigkeit“.

## 3. Beobachtete Datenabweichungen in DIP

| Beobachtung | Folge im Ergebnis |
|---|---|
| DIP ordnet Personen über Dokumente einer Wahlperiode zu, nicht über Mandate (z. B. fehlt Rolf Mützenich in der 21. Wahlperiode). | Abgeordnete ohne Dokument in einer Wahlperiode fehlen dort. |
| DIP führt manche Personen unter mehreren IDs (26 doppelte Einträge in der 20., 23 in der 21. Wahlperiode). | Zusammengeführt über den Namen; zwei gleichnamige Abgeordnete in derselben Wahlperiode würden ebenfalls zusammengeführt. |
| Bei Abgeordneten mit Regierungsamt nennt die Rolle der Wahlperiode keine Fraktion; Mitglieder des Bundesrats und von Landesregierungen haben keine Fraktion. | Abgeordnete mit Regierungsamt werden über den Haupteintrag gezählt, z. B. Franziska Brantner in der 20. Wahlperiode. Nicht gezählt: in der 20. Wahlperiode 239, in der 21. 192 Personen, darunter Friedrich Merz in der 21. (kein Fraktionseintrag im Haupteintrag). Die Anzahl steht in `hinweise`. |
| Sonderämter sind in DIP nicht immer als solche erkennbar. | Einzelne Personen werden fälschlich gezählt: Eva Högl (Wehrbeauftragte) in der 20. und 21., Michael Müller (Regierender Bürgermeister) in der 19. Wahlperiode als SPD. |
| DIP führt Fraktionen und Gruppen unter dem Namen, den sie in DIP tragen; in der 20. Wahlperiode z. B. „DIE LINKE“ und „Die Linke (Gruppe)“ getrennt. | Sie erscheinen als getrennte Zeilen (20. Wahlperiode: DIE LINKE 29, Die Linke (Gruppe) 12); Namen werden nicht zusammengefasst. |
| DIP enthält keine Partei, keine Biografie und kein Abstimmungsverhalten. | Die Fraktion ist nicht die Partei; solche Fragen kann der Chat nicht beantworten. |

## 4. Entscheidungen

| Entscheidung | Begründung |
|---|---|
| Eigenständiger MCP-Server; `report`, `chat` und `ask` greifen nur über MCP auf die Daten zu | Jeder andere MCP-Client bekommt dieselben Daten über dieselbe Schnittstelle. |
| Der Code berechnet Zahlen und Tabelle, das Modell formuliert nur den Text | Die Zahlen sind reproduzierbar und testbar; ein Fehler des Modells kann die Tabelle nicht verfälschen. |
| Fraktion nur aus DIP lesen, keine Korrekturregeln | Der Auftrag stellt die technische Machbarkeit in den Vordergrund, nicht die faktische Korrektheit. Abweichungen werden beschrieben (Abschnitt 3), nicht durch Annahmen ausgeglichen. |
| Vollständige Personenliste als Resource (CSV), nicht im Tool-Ergebnis | 600 bis 800 Zeilen sollen nicht im Kontext des Modells landen. |
| Tool-Wissen in den Tool-Beschreibungen, nicht im Chat-Prompt | Die Beschreibungen erreichen jeden MCP-Client. |
| OpenAI-SDK statt eines Agent-Frameworks | Die Schleife für zwei Tools ist kurz (`agent.py`); viele Anbieter bieten eine OpenAI-kompatible API, ein Wechsel ist Konfiguration. |
| `openai/gpt-oss-20b` bei Groq | Kostenloser Key, Tool-Calling; mit dieser Einstellung sind Beispiele und Abnahme erzeugt. Andere Modelle vor dem Einsatz mit `make abnahme` prüfen. |
| Temperatur 0,0 für Bericht und Chat | Die Daten sollen ohne Variation wiedergegeben werden. |
| Server ohne Zugangsdaten zum Sprachmodell, Cache nur im Prozessspeicher | Der Server braucht nur DIP; für diesen Umfang ist keine Datenbank nötig. |

Rate-Limits des Modellanbieters: Kurze Wartezeiten (bis `LLM_MAX_WAIT_S`) werden abgewartet, längere sofort mit Zeitangabe gemeldet.

## 5. Tests und Abnahme

**Offline-Tests** (`make check`): Tests ohne Netz und ohne Sprachmodell, mit gespeicherten DIP-Antworten der Wahlperioden 19 bis 21 (Abruf 2026-11-04). Sie prüfen u. a. die Gesamtzahlen (747, 774, 625) und die Anzahl je Fraktion, die Namenssuche, die Fehlermeldungen des Servers und die Fehlerbehandlung beim Sprachmodell.

**Abnahme** (`make abnahme`): 10 feste Fragen, je ein Lauf gegen DIP und das Modell; Protokoll in `examples/abnahme_<datum>.md`. Bewertet wird nur, ob das Modell die erwarteten Tools mit den erwarteten Argumenten aufruft (z. B. `dip_get_fraktionsverteilung` mit `wahlperiode: 20`); bei zwei Fragen, auf die mehrere Verhaltensweisen richtig sind (Rückfrage oder Suche), gibt es keine Erwartung. Die Antworttexte stehen im Protokoll und werden nicht automatisch bewertet, weil sie von Modell, Temperatur und Zufall abhängen. So eignet sich die Abnahme auch, um ein anderes Modell schnell zu prüfen.

## 6. Beobachtetes Modellverhalten

Tabelle und Zahlen im Bericht stammen aus dem Code; der Fließtext des Modells und die Chat-Antworten werden nicht geprüft. Beobachtet wurde:
- Der Berichtstext gibt Namen nicht immer wörtlich wieder („Die LINKE“ in `examples/wp20_auswertung.md`) und beschreibt die Zählweise teils falsch („auch wenn sie später Nachrücker wurde“ in `examples/wp21_auswertung.md`).
- Im Chat wertet das Modell beim Vergleich der 19. und 20. Wahlperiode trotz Prompt-Regel und gibt dabei eine Richtung falsch wieder: „AfD leicht stärker (11,0 % vs. 12,3 %)“, dazu „deutlich mehr Sitze“ (`examples/abnahme_2026-11-07.md`).
- Im Chat wird ein Fraktionswechsel verkürzt wiedergegeben: Für Sahra Wagenknecht in der 20. Wahlperiode nennt das Modell teils nur „BSW (Gruppe)“, obwohl das Tool DIE LINKE, fraktionslos und BSW (Gruppe) liefert.

Für einen Einsatz mit Nutzern wären die Antworten zu prüfen (Abschnitt 9).

## 7. Bekannte Grenzen

- Personensuche: höchstens 10 Kandidaten; getrennt geschriebene Doppelvornamen („Anna Lena Baerbock“) werden nicht gefunden.
- Beim kostenlosen Groq-Kontingent treten bei mehreren Fragen kurz hintereinander Rate-Limits auf.

## 8. Datenschutz

Fragen und Tool-Ergebnisse gehen an den konfigurierten Modellanbieter, beim Standard Groq an einen Anbieter mit Sitz in den USA. Die Fraktionszugehörigkeit kann als politische Meinung im Sinne von Art. 9 DSGVO gelten. Vor einem Betrieb mit echten Nutzern ist die Rechtsgrundlage zu prüfen; alternativ ein Anbieter in der EU oder eigenes Hosting (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` setzen; `LLM_REASONING_EFFORT` leeren, wenn der Anbieter diesen Parameter nicht kennt).

## 9. Ausblick

| Schritt | Nutzen |
|---|---|
| Eigenen DIP-Key beantragen, Modellanbieter für den Betrieb festlegen | Betrieb über Mai 2027 hinaus, Datenschutz, keine Rate-Limits |
| Stammdaten der Abgeordneten als zweite Quelle | genaue Mitgliedschaften und Sitzverteilung zu einem Stichtag |
| Gruppen wie BSW eigenständig ausweisen | weniger Fehlaussagen im Chat |
| Abnahme mit mehreren Läufen je Frage und inhaltlicher Prüfung | Qualität bei Modell- oder Prompt-Wechsel messbar |
| MCP-Server zusätzlich über HTTP mit Authentifizierung anbieten | ein zentral betriebener Server für mehrere Anwendungen |
