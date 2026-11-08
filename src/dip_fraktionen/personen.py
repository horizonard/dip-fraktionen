"""Personenauskunft: Namensauflösung gegen DIP und Personenprofil.

DIP findet mit f.person nur einzelne Namensteile ("Merz", "Friedrich"), nicht "Friedrich Merz".
Deshalb: mit einem Namensteil suchen, die übrigen Teile lokal mit den Angaben von DIP abgleichen, Dubletten zusammenfassen.
"""

from __future__ import annotations

import unicodedata
from typing import Any, Protocol

from dip_fraktionen.fraktion import dubletten_gruppieren, fraktionen_der_person, haupt_fraktion, name

Doc = dict[str, Any]
MAX_KANDIDATEN = 10
MAX_NAME = 200
MELDUNG_PERSON_ID = "person_id besteht nur aus Ziffern, z. B. 8167. Ohne bekannte ID mit name suchen."


class PersonenQuelle(Protocol):
    def personen_suchen(self, suchbegriff: str) -> list[Doc]: ...
    def person_nach_id(self, person_id: str) -> list[Doc]: ...


class UngueltigeEingabe(ValueError):
    pass


def _norm(s: str | None) -> str:
    """Vergleichsform: klein, deutsche Umschreibung (ä→ae, ß→ss), übrige Akzente entfernt; „Jürgen“ = „Juergen“."""
    s = (s or "").lower()
    for zeichen, umschrift in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(zeichen, umschrift)
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _wahlperioden(gruppe: list[Doc]) -> list[int]:
    return sorted({w for d in gruppe for w in d.get("wahlperiode", [])})


def _funktion(d: Doc) -> str | None:
    return (d.get("funktion") or [None])[0]


def _ohne_leere(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _ohne_leere(v) for k, v in obj.items() if v not in (None, "", [], {})}
    if isinstance(obj, list):
        return [_ohne_leere(v) for v in obj]
    return obj


def profil(gruppe: list[Doc]) -> dict[str, Any]:
    """Profil einer (ggf. aus Dubletten zusammengeführten) Person."""
    d = gruppe[0]
    aemter = []
    for x in gruppe:
        for r in x.get("person_roles", []):
            if r.get("ressort_titel"):  # DIP nennt nur das Ressort, nicht die Funktion (Minister, Staatssekretär …)
                aemter.append({"ressort": r["ressort_titel"], "wahlperioden": r.get("wahlperiode_nummer") or []})
            if r.get("bundesland") and r.get("funktionszusatz"):
                aemter.append(
                    {"landesamt": r["funktionszusatz"], "land": r["bundesland"], "wahlperioden": r.get("wahlperiode_nummer") or []}
                )
    wps = _wahlperioden(gruppe)
    rollen_wps = {w for x in gruppe for r in x.get("person_roles", []) for w in r.get("wahlperiode_nummer") or []}
    # Fraktion je Wahlperiode nach derselben Regel wie in der Zählung (fraktion.fraktionen_der_person)
    je_wp = {w: fr for w in sorted(set(wps) | rollen_wps) if (fr := fraktionen_der_person(gruppe, w))}
    haupt = next((h for x in gruppe if (h := haupt_fraktion(x))), None)
    hinweise = []
    if wps and not haupt:
        hinweise.append("DIP führt für diese Person keine aktuelle Fraktion; bei Mitgliedern der Bundesregierung ist das in DIP üblich.")
    if je_wp and max(je_wp) - min(je_wp) + 1 > len(je_wp):
        hinweise.append("In nicht aufgeführten Wahlperioden enthält DIP keine Fraktionszugehörigkeit dieser Person.")
    return _ohne_leere(
        {
            "person_id": d["id"],
            "weitere_ids": [x["id"] for x in gruppe[1:]],
            "name": name(d),
            "funktion_aktuell": _funktion(d),
            "fraktion_aktuell": haupt,  # nur die aktuelle Fraktion laut DIP; frühere stehen in fraktion_je_wahlperiode
            "fraktion_je_wahlperiode": {str(w): je_wp[w] for w in je_wp},
            "aemter": aemter,
            "hinweise": hinweise,
        }
    )


def personen_gruppieren(docs: list[Doc]) -> list[list[Doc]]:
    """Suchtreffer zu Personen zusammenfassen.

    DIP führt manche Personen unter mehreren IDs (Dubletten mit gleichem Namen und überlappenden Wahlperioden).
    Gleichnamige Datensätze ohne gemeinsame Wahlperiode gelten als verschiedene Personen
    (z. B. zwei Abgeordnete namens Christian Schmidt in WP 10 und ab WP 12).
    """
    personen: list[list[Doc]] = []
    for gruppe in dubletten_gruppieren(docs):
        cluster: list[tuple[set[int], list[Doc]]] = []  # (gemeinsame Wahlperioden, Datensätze) je Person
        for d in gruppe:
            wps = set(d.get("wahlperiode") or [])
            passend = [c for c in cluster if wps & c[0]]
            for c in passend:  # alle überlappenden Cluster zu einer Person vereinen
                cluster.remove(c)
            cluster.append((wps.union(*(c[0] for c in passend)), [x for c in passend for x in c[1]] + [d]))
        personen.extend(datensaetze for _, datensaetze in cluster)
    return personen


def _kandidat(gruppe: list[Doc]) -> dict[str, Any]:
    d = gruppe[0]
    return _ohne_leere(
        {
            "person_id": d["id"],
            "name": name(d),
            "funktion": _funktion(d),
            "fraktion": haupt_fraktion(d),
            "wahlperioden": _wahlperioden(gruppe),
        }
    )


def _namensteile(name: str) -> list[str]:
    return [t for t in (t.strip(",.") for t in name.replace(",", " ").split()) if t]


def _passt(teil: str, d: Doc) -> bool:
    """Ein Namensteil der Eingabe passt zu einer Person, wenn DIP ihn zu ihr führt: Anfang eines Vornamens, Nachname,
    Namenszusatz („von der“, „dos“) oder akademischer Titel („Dr.“). Keine eigene Liste von Titeln oder Zusätzen."""
    t = _norm(teil)
    vorname = d.get("vorname") or ""
    titel = (d.get("titel") or "").split(vorname)[0] if vorname else ""  # DIP: „Dr. Janosch Dahmen, MdB, …“
    nachname = _norm(d.get("nachname"))
    exakt = {nachname, *nachname.split("-"), *_norm(d.get("namenszusatz")).split(), *_norm(titel).replace(".", " ").split()}
    return any(v.startswith(t) for v in _norm(vorname).split()) or t in exakt


def person_auskunft(quelle: PersonenQuelle, name: str | None = None, person_id: str | int | None = None) -> dict[str, Any]:
    """Status 'gefunden' (person), 'mehrdeutig' (kandidaten) oder 'nicht_gefunden'.

    Eingaben werden hier geprüft (nicht von der MCP-Bibliothek), damit jede Fehlermeldung verständlich und auf Deutsch ist.
    """
    if name is not None and (not isinstance(name, str) or len(name) > MAX_NAME):
        raise UngueltigeEingabe(f"name ist ein Text mit höchstens {MAX_NAME} Zeichen, z. B. „Friedrich Merz“.")
    if isinstance(person_id, bool) or (person_id not in (None, "") and not isinstance(person_id, (str, int))):
        raise UngueltigeEingabe(MELDUNG_PERSON_ID)
    name = (name or "").strip()
    pid = str(person_id).strip() if person_id not in (None, "") else ""
    if pid:
        if not pid.isdigit():
            raise UngueltigeEingabe(MELDUNG_PERSON_ID)
        docs = quelle.person_nach_id(pid)
        if docs:  # wie bei der Namenssuche: weitere DIP-Einträge derselben Person (Dubletten) einbeziehen
            gleichnamige = personen_gruppieren(quelle.personen_suchen(docs[0].get("nachname") or ""))
            docs = next((g for g in gleichnamige if any(x["id"] == pid for x in g)), docs)
        gesucht = pid
    elif name:
        teile = _namensteile(name)
        if not teile:
            raise UngueltigeEingabe("Entweder name oder person_id angeben.")
        docs = []
        varianten = [(teile[-1], teile[:-1])] + ([(teile[0], teile[1:])] if len(teile) > 1 else [])
        for nachname, rest in varianten:
            docs = quelle.personen_suchen(nachname)
            if rest:
                docs = [d for d in docs if all(_passt(t, d) for t in rest)]
            if docs:
                break
        gesucht = name
    else:
        raise UngueltigeEingabe("Entweder name oder person_id angeben.")

    gruppen = personen_gruppieren(docs)
    if not gruppen:
        return {"status": "nicht_gefunden", "gesucht": gesucht}
    if len(gruppen) == 1:
        return {"status": "gefunden", "person": profil(gruppen[0])}
    gruppen.sort(key=lambda g: -max(_wahlperioden(g) or [0]))
    weitere = len(gruppen) - MAX_KANDIDATEN
    return _ohne_leere(
        {
            "status": "mehrdeutig",
            "gesucht": gesucht,
            "kandidaten": [_kandidat(g) for g in gruppen[:MAX_KANDIDATEN]],
            "weitere_treffer": weitere if weitere > 0 else None,
        }
    )
