"""mdtools.translate -- MyMemory-backed translation, driven against a fake
urlopen (no real network), same pattern test_metadata_lookup.py already
uses for its own urllib.request calls."""

import json

import pytest

from mdtools import translate
from mdtools.translate import TranslationError


class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._body


def _fake_urlopen(payload: dict):
    def urlopen(request, timeout=None):
        return _FakeResponse(payload)

    return urlopen


def test_empty_text_is_returned_unchanged_without_a_network_call(monkeypatch):
    def urlopen(request, timeout=None):
        pytest.fail("must not make a request for empty text")

    monkeypatch.setattr(translate.urllib.request, "urlopen", urlopen)

    assert translate.translate("   ", "pl") == "   "


def test_a_successful_response_returns_the_translated_text(monkeypatch):
    payload = {"responseStatus": 200, "responseData": {"translatedText": "Cześć świecie"}}
    monkeypatch.setattr(translate.urllib.request, "urlopen", _fake_urlopen(payload))

    assert translate.translate("Hello world", "pl") == "Cześć świecie"


def test_the_langpair_uses_autodetect_as_the_source(monkeypatch):
    """MyMemory's live API rejects an empty/omitted source outright --
    confirmed against the real service -- so this can't be left blank."""
    seen = {}

    def urlopen(request, timeout=None):
        seen["url"] = request.full_url
        return _FakeResponse({"responseStatus": 200, "responseData": {"translatedText": "x"}})

    monkeypatch.setattr(translate.urllib.request, "urlopen", urlopen)

    translate.translate("hello", "ja")

    assert "langpair=autodetect%7Cja" in seen["url"]


def test_a_non_200_response_status_raises_translation_error(monkeypatch):
    payload = {"responseStatus": 403, "responseDetails": "INVALID LANGUAGE PAIR"}
    monkeypatch.setattr(translate.urllib.request, "urlopen", _fake_urlopen(payload))

    with pytest.raises(TranslationError):
        translate.translate("hello", "xx")


def test_a_response_with_no_translated_text_raises_translation_error(monkeypatch):
    payload = {"responseStatus": 200, "responseData": {}}
    monkeypatch.setattr(translate.urllib.request, "urlopen", _fake_urlopen(payload))

    with pytest.raises(TranslationError):
        translate.translate("hello", "pl")


def test_a_connection_failure_raises_translation_error(monkeypatch):
    import urllib.error

    def broken_urlopen(request, timeout=None):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr(translate.urllib.request, "urlopen", broken_urlopen)

    with pytest.raises(TranslationError):
        translate.translate("hello", "pl")
