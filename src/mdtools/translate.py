"""Machine translation of a Telegram bot's messages into whatever language
xD-Tools' own UI is currently set to (mdtools.i18n.current_language()) --
so running xD-Tools in Polish or Japanese doesn't mean reading an
English-speaking bot's replies by hand. Used by
panels/telegram_chat_dialog.py only.

**MyMemory** (https://mymemory.translated.net), chosen for the same reason
metadata_lookup.py picked the iTunes Search API over anything requiring
sign-up: a genuinely free, publicly documented service that needs no API
key at all for casual, occasional use (a soft ~5000-words/day-per-IP cap on
anonymous requests -- plenty for chatting with one bot). Deliberately not
Google Translate's unofficial endpoint, which the popular `googletrans`
package scrapes -- that often translates better, but it is an undocumented,
unsupported endpoint that could break or start refusing requests without
notice; MyMemory is an actual, intended public API.

Plain blocking urllib.request, same as metadata_lookup.py -- this module
doesn't know or care that its only caller
(panels/telegram_chat_dialog.py's _ChatWorker) happens to run inside an
asyncio event loop. That caller is responsible for keeping this off the
loop (via loop.run_in_executor), exactly as it would for any other
blocking call; nothing here assumes async.

No Qt here, matching telegram_bot.py/mdrem.py/foobar.py.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

_ENDPOINT = "https://api.mymemory.translated.net/get"
_TIMEOUT_S = 10
_USER_AGENT = "xD-Tools (https://github.com/) -- Telegram bot chat translation"


class TranslationError(Exception):
    """Any failure reaching MyMemory or making sense of its response.
    Callers treat this as "show the original text instead" -- a missing
    translation is never worth interrupting a chat over."""


def translate(text: str, target_language: str) -> str:
    """`text` translated into `target_language` (an ISO 639-1 code --
    exactly what mdtools.i18n.current_language() already returns, so
    callers can pass that straight through). Source language is
    auto-detected by the service ("autodetect" in the langpair -- MyMemory
    rejects an empty/omitted source outright, confirmed against the live
    API, so this can't just be left blank).

    Returns `text` unchanged if it's empty/whitespace-only -- nothing to
    translate, and MyMemory's own API rejects an empty query anyway."""
    if not text.strip():
        return text

    params = urllib.parse.urlencode({"q": text, "langpair": f"autodetect|{target_language}"})
    request = urllib.request.Request(
        f"{_ENDPOINT}?{params}", headers={"User-Agent": _USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise TranslationError(f"could not reach the translation service: {exc}") from exc

    status = payload.get("responseStatus")
    if status not in (200, "200"):
        raise TranslationError(
            f"translation service returned {status}: {payload.get('responseDetails')}"
        )
    translated = payload.get("responseData", {}).get("translatedText")
    if not translated:
        raise TranslationError("translation service returned no text")
    return translated
