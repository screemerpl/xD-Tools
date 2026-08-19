"""Talking to a Telegram bot the user runs themselves, so an album can be
searched for and downloaded from it and handed to Record Folder to
MiniDisc -- see panels/folder_record_dialog.py, which this eventually feeds
exactly the way a folder of files already does.

**Why a real user login, not a bot token.** Telegram's Bot API forbids one
bot from messaging another bot outright -- MDTools can't send `/search
Nevermind` to the user's bot as a bot itself and get a reply. To talk to a
bot the way a person would in the Telegram app, this has to act as an
actual Telegram *user account* (phone number + code, optionally a 2FA
password) over the MTProto client protocol, which is what Telethon
(https://docs.telethon.dev) speaks. That needs its own API ID/API Hash pair
from https://my.telegram.org -- a credential for *this application acting
as a client*, completely unrelated to whatever bot token the user's own bot
uses internally. MDTools never needs the bot's token at all; it just
messages the bot like any other contact would.

No Qt in here, matching mdrem.py/foobar.py/cdrip.py -- the panel imports
this, never the other way round. Unlike those, everything here is async
(Telethon is asyncio-native), so the caller (panels/telegram_login_dialog.py's
worker thread) is what owns the event loop this runs on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Callable


class TelegramError(Exception):
    """Any failure talking to Telegram: connection, an invalid API ID/Hash,
    a wrong code, rate-limiting, or anything else the underlying client
    raised. One exception type, like MDRemError/CdRipError/FoobarError/
    MetadataLookupError elsewhere in this codebase, so nothing above this
    module ever needs to know Telethon's own exception hierarchy."""


class SignInResult(Enum):
    """What submit_code() actually accomplished. PASSWORD_REQUIRED is not a
    failure -- two-factor authentication is normal, expected behaviour for
    plenty of accounts, not something to raise TelegramError over."""

    SIGNED_IN = auto()
    PASSWORD_REQUIRED = auto()


@dataclass
class ChatMessage:
    """One message in a conversation with the bot, crossing the
    telegram_bot.py -> panels boundary -- nothing outside this module ever
    touches a raw Telethon Message, same "dependency injection at the
    boundary" reasoning as TelegramBotClient itself.

    `buttons` is a label grid ([] if the message has none) -- a row/column
    position in it is all a caller needs to click one, via
    TelegramBotClient.click(message_id, row, col)."""

    id: int
    outgoing: bool
    text: str
    buttons: list[list[str]] = field(default_factory=list)
    file_name: str | None = None
    file_size: int | None = None
    # A Telegram "photo" (sent through the picture picker) has no filename
    # attribute at all -- File.name looks for DocumentAttributeFilename,
    # which only a real Document carries -- so file_name/file_size stay
    # None for a photo even though it *is* a file in every practical sense.
    # Kept as its own flag rather than inferred from file_name being unset,
    # so a caller never has to know that distinction exists.
    is_photo: bool = False


def create_telethon_client(api_id: int, api_hash: str, session_path: Path):
    """The only place that imports and constructs the real
    telethon.TelegramClient -- kept as a thin factory specifically so tests
    never touch it: everything else (TelegramBotClient below) takes a
    client object as a parameter instead of building one itself.

    Must be called from inside the thread whose event loop will drive it
    (telethon.TelegramClient picks up whatever loop is current via
    asyncio.get_event_loop() at construction time) -- see
    panels/telegram_login_dialog.py's _LoginWorker.run() for why."""
    from telethon import TelegramClient

    return TelegramClient(str(session_path), api_id, api_hash)


def _describe(exc: Exception) -> str:
    """A friendlier message for the handful of failures a user is actually
    likely to hit, falling back to Telethon's own message for anything
    else rather than trying to translate every RPCError subtype."""
    from telethon.errors import (
        ApiIdInvalidError,
        DataInvalidError,
        FloodWaitError,
        PhoneCodeExpiredError,
        PhoneCodeInvalidError,
        PhoneNumberInvalidError,
    )

    if isinstance(exc, FloodWaitError):
        return f"Telegram is rate-limiting this account -- try again in {exc.seconds} seconds."
    if isinstance(exc, PhoneCodeInvalidError):
        return "That code was not correct."
    if isinstance(exc, PhoneCodeExpiredError):
        return "That code has expired -- request a new one."
    if isinstance(exc, PhoneNumberInvalidError):
        return "That phone number is not valid."
    if isinstance(exc, ApiIdInvalidError):
        return "The Telegram API ID/API Hash are not valid -- check them at my.telegram.org."
    if isinstance(exc, DataInvalidError):
        # Telegram's own server-side rejection of a button click's callback
        # data (RPC error DATA_INVALID, confirmed against Telethon's source
        # -- despite the alarming stock wording ("Encrypted data invalid"),
        # this is not a session/security problem on our end). Seen in
        # practice when a bot's own inline keyboard has gone stale (the bot
        # restarted, or its callback state for that button expired) --
        # nothing a retry from this side can fix; the bot has to send a
        # fresh keyboard.
        return "That button's data was rejected by Telegram -- it may have expired. Ask the bot for a fresh menu."
    return str(exc)


class TelegramBotClient:
    """Async wrapper around a duck-typed, Telethon-shaped client object,
    translating its exceptions into TelegramError at the boundary.

    Takes the client as a constructor parameter rather than building one
    itself -- dependency injection, the same reason MDRemClient takes a
    port string but it's the caller that owns the actual serial port
    object. Here the caller (production: _LoginWorker, via
    create_telethon_client(); tests: a fake) passes a pre-built client, so
    this class -- and the sign-in state machine it drives -- is fully
    testable with no real network or Telegram account involved."""

    def __init__(self, client) -> None:
        self._client = client
        self._phone: str | None = None
        self._entity = None
        # Every message this client has ever sent or seen, keyed by id --
        # click()/download() need the *raw* Telethon message back (its
        # .click()/.download_media() are what actually do the work), while
        # everything above this module only ever holds a plain id.
        self._messages: dict[int, object] = {}

    async def connect(self) -> None:
        try:
            await self._client.connect()
        except Exception as exc:
            raise TelegramError(f"could not connect to Telegram: {exc}") from exc

    async def is_authorized(self) -> bool:
        try:
            return bool(await self._client.is_user_authorized())
        except Exception as exc:
            raise TelegramError(f"could not check sign-in status: {exc}") from exc

    async def request_code(self, phone: str) -> None:
        """Remembers `phone` for submit_code() -- Telethon's own sign_in()
        needs it repeated back alongside the code."""
        self._phone = phone
        try:
            await self._client.send_code_request(phone)
        except Exception as exc:
            raise TelegramError(_describe(exc)) from exc

    async def submit_code(self, code: str) -> SignInResult:
        if self._phone is None:
            raise TelegramError("request_code() must be called before submit_code()")
        from telethon.errors import SessionPasswordNeededError

        try:
            await self._client.sign_in(self._phone, code)
        except SessionPasswordNeededError:
            return SignInResult.PASSWORD_REQUIRED
        except Exception as exc:
            raise TelegramError(_describe(exc)) from exc
        return SignInResult.SIGNED_IN

    async def submit_password(self, password: str) -> None:
        try:
            await self._client.sign_in(password=password)
        except Exception as exc:
            raise TelegramError(_describe(exc)) from exc

    async def me_display_name(self) -> str:
        """The signed-in account's name, for the login dialog to show back
        as confirmation of who it just signed in as."""
        try:
            me = await self._client.get_me()
        except Exception as exc:
            raise TelegramError(f"could not read account info: {exc}") from exc
        name = " ".join(
            part for part in (getattr(me, "first_name", None), getattr(me, "last_name", None)) if part
        )
        phone = getattr(me, "phone", None)
        return name or (f"+{phone}" if phone else "")

    async def disconnect(self) -> None:
        """Best-effort: called while shutting down, including on the
        failure path, so a second error here shouldn't mask the first."""
        try:
            await self._client.disconnect()
        except Exception:
            pass

    # --- chatting with the bot (Phase 2) ------------------------------------

    def _remember(self, message) -> ChatMessage:
        """Caches the raw message (click()/download() need it back) and
        returns the plain ChatMessage everything above this module deals
        in instead."""
        self._messages[message.id] = message
        buttons = message.buttons or []
        chat_message = ChatMessage(
            id=message.id,
            outgoing=bool(getattr(message, "out", False)),
            text=message.raw_text or "",
            buttons=[[button.text for button in row] for row in buttons],
            file_name=message.file.name if message.file else None,
            file_size=message.file.size if message.file else None,
            is_photo=bool(getattr(message, "photo", None)),
        )
        return chat_message

    async def resolve_bot(self, username: str) -> str:
        """Resolves and caches the bot's entity for send_text()/
        start_watching() to reuse, and returns a display name for the
        dialog's header."""
        try:
            self._entity = await self._client.get_entity(username)
        except Exception as exc:
            raise TelegramError(f"could not find {username}: {exc}") from exc
        return (
            getattr(self._entity, "first_name", None)
            or getattr(self._entity, "title", None)
            or getattr(self._entity, "username", None)
            or username
        )

    async def send_text(self, text: str) -> ChatMessage:
        """Sent through the same _remember() path an incoming message goes
        through, so the dialog renders our own messages exactly like the
        bot's replies -- one rendering code path, not two."""
        try:
            message = await self._client.send_message(self._entity, text)
        except Exception as exc:
            raise TelegramError(_describe(exc)) from exc
        return self._remember(message)

    async def start_watching(self, on_message: Callable[[ChatMessage], None]) -> None:
        """Registers handlers for both the bot's new messages *and* its
        edits to an already-sent one -- Telethon delivers these on this
        same event loop/thread, so `on_message` can be a plain synchronous
        callback (e.g. queue.put_nowait) with no cross-thread handoff
        needed, unlike commands arriving from the GUI thread.

        The edit half matters more than it might look: plenty of bots
        build a "menu" by editing one message's text/buttons in place
        (Telegram's own editMessageText/editMessageReplyMarkup) as you
        navigate, rather than sending a fresh message every step -- a real
        bug report from exactly this. `events.MessageEdited` is a subclass
        of `events.NewMessage` (confirmed via its MRO) sharing the same
        `.message` shape, so one handler function covers both. Routing an
        edit through the same _remember() the new-message path uses is
        what actually fixes the follow-on symptom too: it *overwrites* the
        message id's cache entry with the freshly edited object, so a
        button clicked after an edit sends the *current* callback_data
        instead of a stale one Telegram has already invalidated server-side
        (which is what a click on the old cached object surfaced as
        DataInvalidError)."""
        from telethon import events

        async def _handler(event) -> None:
            on_message(self._remember(event.message))

        self._client.add_event_handler(_handler, events.NewMessage(chats=self._entity, incoming=True))
        self._client.add_event_handler(_handler, events.MessageEdited(chats=self._entity, incoming=True))

    async def click(self, message_id: int, row: int, col: int) -> None:
        message = self._messages.get(message_id)
        if message is None:
            raise TelegramError(f"no such message: {message_id}")
        try:
            await message.click(row, col)
        except Exception as exc:
            raise TelegramError(_describe(exc)) from exc

    async def download(self, message_id: int, target_dir: Path, progress_callback=None) -> Path:
        message = self._messages.get(message_id)
        if message is None:
            raise TelegramError(f"no such message: {message_id}")
        if not message.file:
            raise TelegramError("that message has no file to download")
        try:
            # An *existing* directory path (checked via os.path.isdir inside
            # Telethon) makes it pick the message's own suggested filename
            # inside it -- the caller is responsible for target_dir already
            # existing, same as every other "create it, then use it" folder
            # in this codebase (cdrip.ensure_folder() and friends).
            saved = await message.download_media(file=str(target_dir), progress_callback=progress_callback)
        except Exception as exc:
            raise TelegramError(f"download failed: {exc}") from exc
        if not saved:
            raise TelegramError("download produced no file")
        return Path(saved)

    async def download_bytes(self, message_id: int) -> bytes:
        """The message's file downloaded straight into memory, for an
        inline chat preview -- a photo's whole point is being seen without
        an extra click, unlike an album's FLAC files, which download() above
        saves to disk on request. `file=bytes` is Telethon's own sentinel
        for an in-memory download (no path involved at all)."""
        message = self._messages.get(message_id)
        if message is None:
            raise TelegramError(f"no such message: {message_id}")
        if not message.file:
            raise TelegramError("that message has no file to download")
        try:
            data = await message.download_media(file=bytes)
        except Exception as exc:
            raise TelegramError(f"download failed: {exc}") from exc
        if not data:
            raise TelegramError("download produced no data")
        return data
