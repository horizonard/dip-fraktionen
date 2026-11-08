import httpx
import pytest

import dip_fraktionen.dip_client as modul
from dip_fraktionen.dip_client import DipClient, DipKonfigurationsfehler, DipNichtErreichbar
from dip_fraktionen.settings import Settings


@pytest.fixture(autouse=True)
def kein_warten(monkeypatch):
    monkeypatch.setattr(modul.time, "sleep", lambda s: None)


def client(handler):
    return DipClient(Settings.aus_umgebung(), transport=httpx.MockTransport(handler))


def test_retry_bei_503_dann_erfolg():
    antworten = iter([503, 503, 200])
    c = client(lambda req: httpx.Response(next(antworten), json={"documents": []}))
    assert c.get("/person") == {"documents": []}


def test_dauerhaft_nicht_erreichbar():
    c = client(lambda req: httpx.Response(503))
    with pytest.raises(DipNichtErreichbar):
        c.get("/person")


def test_401_ist_konfigurationsfehler_ohne_retry():
    aufrufe = []
    c = client(lambda req: aufrufe.append(1) or httpx.Response(401))
    with pytest.raises(DipKonfigurationsfehler):
        c.get("/person")
    assert len(aufrufe) == 1


def test_404_liefert_leeres_ergebnis():
    assert client(lambda req: httpx.Response(404)).get("/person/1") == {}


def test_api_key_im_header():
    c = client(lambda req: httpx.Response(200, json={"ok": req.headers["Authorization"].startswith("ApiKey ")}))
    assert c.get("/person") == {"ok": True}


def test_pagination_und_cache():
    seiten = {
        None: {"documents": [{"id": "1"}], "cursor": "A"},
        "A": {"documents": [{"id": "2"}], "cursor": "B"},
        "B": {"documents": [], "cursor": "B"},
    }
    aufrufe = []

    def handler(req):
        aufrufe.append(1)
        return httpx.Response(200, json=seiten[req.url.params.get("cursor")])

    c = client(handler)
    assert [d["id"] for d in c.personen_der_wahlperiode(20)] == ["1", "2"]
    c.personen_der_wahlperiode(20)
    assert len(aufrufe) == 3  # zweiter Aufruf aus dem Cache
