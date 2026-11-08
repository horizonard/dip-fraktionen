"""Fehlerbehandlung beim Modellaufruf: wann gewartet, wiederholt oder sofort abgebrochen wird."""

from types import SimpleNamespace

import httpx
import openai
import pytest

from dip_fraktionen import llm as llm_modul
from dip_fraktionen.llm import LLM, LLMFehler
from dip_fraktionen.settings import Settings

ANTWORT = SimpleNamespace(choices=[SimpleNamespace(message="ok")], usage=None)


def _fehler(klasse, status, text="", retry_after=None):
    headers = {"retry-after": str(retry_after)} if retry_after is not None else {}
    response = httpx.Response(status, headers=headers, request=httpx.Request("POST", "https://llm.test/chat/completions"))
    return klasse(text, response=response, body=None)


class FakeClient:
    """Liefert der Reihe nach die vorgegebenen Fehler und danach eine Antwort."""

    def __init__(self, *fehler):
        self.fehler, self.aufrufe = list(fehler), 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **_):
        self.aufrufe += 1
        if self.fehler:
            raise self.fehler.pop(0)
        return ANTWORT


@pytest.fixture
def wartezeiten(monkeypatch):
    gewartet = []
    monkeypatch.setattr(llm_modul.time, "sleep", gewartet.append)
    return gewartet


def _llm(client):
    return LLM(Settings.aus_umgebung(), client=client)


def test_kurzes_rate_limit_wird_abgewartet(wartezeiten):
    client = FakeClient(_fehler(openai.RateLimitError, 429, retry_after=5))
    assert _llm(client).antwort([]) == "ok"
    assert wartezeiten == [5.0] and client.aufrufe == 2


def test_langes_rate_limit_bricht_sofort_ab(wartezeiten):
    client = FakeClient(_fehler(openai.RateLimitError, 429, retry_after=735))
    with pytest.raises(LLMFehler, match="in etwa 12 Minute"):
        _llm(client).antwort([])
    assert wartezeiten == [] and client.aufrufe == 1


def test_fehlerhafter_tool_aufruf_hoechstens_zweimal_wiederholt(wartezeiten):
    tool_400 = [_fehler(openai.BadRequestError, 400, "tool_use_failed") for _ in range(3)]
    client = FakeClient(*tool_400)
    with pytest.raises(LLMFehler, match="abgelehnt"):
        _llm(client).antwort([])
    assert client.aufrufe == 3


def test_ungueltiger_key_ohne_wiederholung(wartezeiten):
    client = FakeClient(_fehler(openai.AuthenticationError, 401))
    with pytest.raises(LLMFehler, match="ungültig"):
        _llm(client).antwort([])
    assert client.aufrufe == 1 and wartezeiten == []
