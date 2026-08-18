"""TelegramBotClient's sign-in state machine, driven against a fake
Telethon-shaped client -- no real network, no real Telegram account, same
"fake the hardware/service, test the logic above it" approach test_mdrem.py
takes for MDRemClient's own protocol handling."""

import asyncio
from pathlib import Path

import pytest

from mdtools.telegram_bot import ChatMessage, SignInResult, TelegramBotClient, TelegramError


class FakeFile:
    def __init__(self, name: str | None, size: int):
        # name=None matches a real Telegram photo: File.name looks for a
        # DocumentAttributeFilename, which only an actual Document carries.
        self.name = name
        self.size = size


class FakeButton:
    def __init__(self, text: str):
        self.text = text


_next_message_id = [1000]


class FakeMessage:
    """Stands in for telethon.tl.custom.message.Message -- just the surface
    TelegramBotClient actually touches (.id, .out, .raw_text, .buttons,
    .file, .click(), .download_media())."""

    def __init__(
        self,
        text: str = "",
        out: bool = False,
        buttons=None,
        file: FakeFile | None = None,
        photo: bool = False,
        content: bytes = b"fake-downloaded-bytes",
        click_error: Exception | None = None,
    ):
        _next_message_id[0] += 1
        self.id = _next_message_id[0]
        self.out = out
        self.raw_text = text
        self._buttons = buttons
        self.file = file
        self.photo = photo
        self.content = content
        self._click_error = click_error
        self.clicked: list[tuple[int, int]] = []
        self.download_target = None

    @property
    def buttons(self):
        return self._buttons

    async def click(self, row, col):
        if self._click_error is not None:
            raise self._click_error
        self.clicked.append((row, col))

    async def download_media(self, file, progress_callback=None):
        self.download_target = file
        size = self.file.size if self.file else len(self.content)
        if progress_callback:
            progress_callback(size, size)
        if file is bytes:
            return self.content
        # Actually writes the file -- callers further up (e.g.
        # album_sort.sort_downloads(), which only ever acts on files that
        # really exist on disk) need a real path to find, not just a
        # computed string.
        target = Path(file) / (self.file.name or f"photo_{self.id}.jpg")
        target.write_bytes(self.content)
        return str(target)


class FakeEntity:
    def __init__(self, username: str, *, title: str | None = None, first_name: str | None = None):
        self.username = username.lstrip("@")
        self.title = title
        self.first_name = first_name


class FakeEvent:
    def __init__(self, message: FakeMessage):
        self.message = message


class FakeTelethonClient:
    def __init__(
        self,
        *,
        authorized: bool = False,
        valid_code: str = "12345",
        needs_password: bool = False,
        password: str = "hunter2",
        me_name: str = "Jane Doe",
        me_phone: str = "15550100",
        flood_seconds: int | None = None,
        entity_error: bool = False,
    ):
        self.authorized = authorized
        self.valid_code = valid_code
        self.needs_password = needs_password
        self.password = password
        self.me_name = me_name
        self.me_phone = me_phone
        self.flood_seconds = flood_seconds
        self.connected = False
        self.disconnected = False
        self.password_verified = False
        self.code_requests: list[str] = []
        self.sent_messages: list[FakeMessage] = []
        self.handlers: list[tuple] = []
        self.entity_error = entity_error

    async def connect(self):
        self.connected = True

    async def is_user_authorized(self):
        return self.authorized

    async def send_code_request(self, phone):
        if self.flood_seconds is not None:
            from telethon.errors import FloodWaitError

            raise FloodWaitError(request=None, capture=self.flood_seconds)
        self.code_requests.append(phone)

    async def sign_in(self, phone=None, code=None, *, password=None, **kwargs):
        if password is not None:
            if password != self.password:
                from telethon.errors.rpcbaseerrors import RPCError

                raise RPCError(request=None, message="wrong password")
            self.password_verified = True
            self.authorized = True
            return object()

        if code != self.valid_code:
            from telethon.errors import PhoneCodeInvalidError

            raise PhoneCodeInvalidError(request=None)
        if self.needs_password:
            from telethon.errors import SessionPasswordNeededError

            raise SessionPasswordNeededError(request=None)
        self.authorized = True
        return object()

    async def get_me(self):
        class _Me:
            pass

        me = _Me()
        me.first_name = self.me_name
        me.last_name = None
        me.phone = self.me_phone
        return me

    async def disconnect(self):
        self.disconnected = True

    async def get_entity(self, username):
        if self.entity_error:
            raise ValueError(f"no such user: {username}")
        return FakeEntity(username)

    async def send_message(self, entity, text):
        message = FakeMessage(text=text, out=True)
        self.sent_messages.append(message)
        return message

    def add_event_handler(self, callback, event):
        self.handlers.append((callback, event))


def _run(coro):
    return asyncio.run(coro)


# --- already authorized -----------------------------------------------------


def test_already_authorized_short_circuits_the_code_flow():
    fake = FakeTelethonClient(authorized=True)
    client = TelegramBotClient(fake)

    async def scenario():
        await client.connect()
        assert await client.is_authorized() is True
        return await client.me_display_name()

    name = _run(scenario())
    assert name == "Jane Doe"
    assert fake.code_requests == []


# --- plain code sign-in ------------------------------------------------------


def test_a_valid_code_signs_in_with_no_password_needed():
    fake = FakeTelethonClient(valid_code="99999")
    client = TelegramBotClient(fake)

    async def scenario():
        await client.connect()
        assert await client.is_authorized() is False
        await client.request_code("+15550100")
        return await client.submit_code("99999")

    result = _run(scenario())
    assert result is SignInResult.SIGNED_IN
    assert fake.authorized is True
    assert fake.code_requests == ["+15550100"]


def test_an_invalid_code_raises_telegram_error():
    fake = FakeTelethonClient(valid_code="99999")
    client = TelegramBotClient(fake)

    async def scenario():
        await client.request_code("+15550100")
        await client.submit_code("wrong")

    with pytest.raises(TelegramError):
        _run(scenario())
    assert fake.authorized is False


def test_submit_code_before_request_code_is_a_telegram_error():
    client = TelegramBotClient(FakeTelethonClient())

    with pytest.raises(TelegramError):
        _run(client.submit_code("12345"))


# --- two-factor password -----------------------------------------------------


def test_password_required_is_reported_not_raised():
    fake = FakeTelethonClient(valid_code="99999", needs_password=True)
    client = TelegramBotClient(fake)

    async def scenario():
        await client.request_code("+15550100")
        return await client.submit_code("99999")

    result = _run(scenario())
    assert result is SignInResult.PASSWORD_REQUIRED
    assert fake.authorized is False  # not yet -- the password step still has to happen


def test_the_right_password_completes_sign_in():
    fake = FakeTelethonClient(valid_code="99999", needs_password=True, password="correct horse")
    client = TelegramBotClient(fake)

    async def scenario():
        await client.request_code("+15550100")
        await client.submit_code("99999")
        await client.submit_password("correct horse")

    _run(scenario())
    assert fake.authorized is True
    assert fake.password_verified is True


def test_the_wrong_password_raises_telegram_error():
    fake = FakeTelethonClient(valid_code="99999", needs_password=True, password="correct horse")
    client = TelegramBotClient(fake)

    async def scenario():
        await client.request_code("+15550100")
        await client.submit_code("99999")
        await client.submit_password("nope")

    with pytest.raises(TelegramError):
        _run(scenario())


# --- rate limiting -----------------------------------------------------------


def test_flood_wait_names_the_wait_time_in_the_message():
    fake = FakeTelethonClient(flood_seconds=137)
    client = TelegramBotClient(fake)

    with pytest.raises(TelegramError, match="137"):
        _run(client.request_code("+15550100"))


def test_a_stale_buttons_callback_gets_a_friendlier_message():
    """Real report: clicking a bot's button surfaced Telethon's raw
    "Encrypted data invalid" (DataInvalidError, RPC error DATA_INVALID) --
    a genuine server-side rejection of that button's callback data, not a
    bug in how we send the click. Translated into something that says what
    it actually means instead of the alarming stock wording."""
    from telethon.errors import DataInvalidError

    fake = FakeTelethonClient()
    client = TelegramBotClient(fake)
    received: list[ChatMessage] = []

    async def scenario():
        await client.resolve_bot("@my_bot")
        await client.start_watching(received.append)
        callback, _ = fake.handlers[0]
        raw = FakeMessage(
            text="pick one",
            buttons=[[FakeButton("Album A")]],
            click_error=DataInvalidError(request=None),
        )
        await callback(FakeEvent(raw))
        await client.click(received[0].id, 0, 0)

    with pytest.raises(TelegramError, match="expired"):
        _run(scenario())


# --- connection / disconnection ----------------------------------------------


def test_connect_and_disconnect_reach_the_underlying_client():
    fake = FakeTelethonClient()
    client = TelegramBotClient(fake)

    _run(client.connect())
    assert fake.connected is True

    _run(client.disconnect())
    assert fake.disconnected is True


def test_disconnect_swallows_its_own_failure():
    """Best-effort on the way out -- a second error while shutting down
    should not mask whatever actually failed."""

    class _BrokenDisconnect(FakeTelethonClient):
        async def disconnect(self):
            raise RuntimeError("already gone")

    client = TelegramBotClient(_BrokenDisconnect())
    _run(client.disconnect())  # must not raise


# --- chatting with the bot (Phase 2) -----------------------------------------


def test_resolve_bot_returns_a_display_name():
    fake = FakeTelethonClient()
    client = TelegramBotClient(fake)

    name = _run(client.resolve_bot("@my_bot"))

    assert name == "my_bot"  # FakeEntity has no first_name/title, falls back to username


def test_resolve_bot_wraps_a_lookup_failure():
    fake = FakeTelethonClient(entity_error=True)
    client = TelegramBotClient(fake)

    with pytest.raises(TelegramError):
        _run(client.resolve_bot("@nonexistent"))


def test_send_text_returns_a_chat_message_and_reaches_the_client():
    fake = FakeTelethonClient()
    client = TelegramBotClient(fake)

    async def scenario():
        await client.resolve_bot("@my_bot")
        return await client.send_text("hello")

    result = _run(scenario())

    assert isinstance(result, ChatMessage)
    assert result.outgoing is True
    assert result.text == "hello"
    assert len(fake.sent_messages) == 1


def test_start_watching_delivers_incoming_messages_as_chat_messages():
    fake = FakeTelethonClient()
    client = TelegramBotClient(fake)
    received: list[ChatMessage] = []

    async def scenario():
        await client.resolve_bot("@my_bot")
        await client.start_watching(received.append)
        callback, _event_filter = fake.handlers[0]
        incoming = FakeMessage(text="here's your album", out=False)
        await callback(FakeEvent(incoming))

    _run(scenario())

    assert len(received) == 1
    assert received[0].outgoing is False
    assert received[0].text == "here's your album"


def test_start_watching_registers_both_new_and_edited_message_handlers():
    """Plenty of bots build a "menu" by editing one message's text/buttons
    in place (Telegram's own editMessageText/editMessageReplyMarkup) as the
    user navigates, rather than sending a fresh message every step -- a
    real bug report traced back to only ever listening for brand new
    messages, so an edit was silently invisible to the dialog."""
    fake = FakeTelethonClient()
    client = TelegramBotClient(fake)

    async def scenario():
        await client.resolve_bot("@my_bot")
        await client.start_watching(lambda message: None)

    _run(scenario())

    assert len(fake.handlers) == 2
    from telethon import events

    filters = [handler[1] for handler in fake.handlers]
    assert any(isinstance(f, events.NewMessage) and not isinstance(f, events.MessageEdited) for f in filters)
    assert any(isinstance(f, events.MessageEdited) for f in filters)


def test_an_edit_overwrites_the_cached_message_so_a_later_click_uses_fresh_data():
    """The follow-on symptom of the same bug: clicking a button after the
    bot edited its own message surfaced Telethon's DataInvalidError,
    because the *old*, pre-edit callback_data was still what got sent --
    Telegram had already invalidated it server-side the moment the bot
    edited the message. Overwriting the cache on every edit (both handlers
    funnel through the same _remember()) is what actually fixes that."""
    fake = FakeTelethonClient()
    client = TelegramBotClient(fake)
    received: list[ChatMessage] = []

    async def scenario():
        await client.resolve_bot("@my_bot")
        await client.start_watching(received.append)
        callback, _ = fake.handlers[0]

        original = FakeMessage(text="pick an album", buttons=[[FakeButton("Old Album")]])
        await callback(FakeEvent(original))

        edited = FakeMessage(text="pick a different album", buttons=[[FakeButton("New Album")]])
        edited.id = original.id  # Telegram keeps the id across an edit
        await callback(FakeEvent(edited))

        await client.click(original.id, 0, 0)
        return original, edited

    original, edited = _run(scenario())

    assert original.clicked == [], "the stale pre-edit object must never be clicked"
    assert edited.clicked == [(0, 0)]
    assert len(received) == 2
    assert received[1].text == "pick a different album"
    assert received[1].buttons == [["New Album"]]


def test_a_message_with_buttons_reports_the_label_grid():
    fake = FakeTelethonClient()
    client = TelegramBotClient(fake)
    received: list[ChatMessage] = []

    async def scenario():
        await client.resolve_bot("@my_bot")
        await client.start_watching(received.append)
        buttons = [[FakeButton("Album A"), FakeButton("Album B")]]
        callback, _ = fake.handlers[0]
        await callback(FakeEvent(FakeMessage(text="pick one", buttons=buttons)))

    _run(scenario())

    assert received[0].buttons == [["Album A", "Album B"]]


def test_clicking_a_button_reaches_the_raw_message():
    fake = FakeTelethonClient()
    client = TelegramBotClient(fake)
    received: list[ChatMessage] = []

    async def scenario():
        await client.resolve_bot("@my_bot")
        await client.start_watching(received.append)
        callback, _ = fake.handlers[0]
        raw = FakeMessage(text="pick one", buttons=[[FakeButton("Album A")]])
        await callback(FakeEvent(raw))
        await client.click(received[0].id, 0, 0)
        return raw

    raw = _run(scenario())
    assert raw.clicked == [(0, 0)]


def test_clicking_an_unknown_message_id_is_a_telegram_error():
    client = TelegramBotClient(FakeTelethonClient())

    with pytest.raises(TelegramError):
        _run(client.click(999999, 0, 0))


def test_a_message_with_a_file_reports_its_name_and_size():
    fake = FakeTelethonClient()
    client = TelegramBotClient(fake)
    received: list[ChatMessage] = []

    async def scenario():
        await client.resolve_bot("@my_bot")
        await client.start_watching(received.append)
        callback, _ = fake.handlers[0]
        raw = FakeMessage(text="here", file=FakeFile("Unleashed.flac", 40_000_000))
        await callback(FakeEvent(raw))

    _run(scenario())

    assert received[0].file_name == "Unleashed.flac"
    assert received[0].file_size == 40_000_000


def test_downloading_a_file_reaches_the_client_and_returns_the_saved_path(tmp_path):
    fake = FakeTelethonClient()
    client = TelegramBotClient(fake)
    received: list[ChatMessage] = []
    progress: list[tuple[int, int]] = []

    async def scenario():
        await client.resolve_bot("@my_bot")
        await client.start_watching(received.append)
        callback, _ = fake.handlers[0]
        raw = FakeMessage(text="here", file=FakeFile("Unleashed.flac", 100))
        await callback(FakeEvent(raw))
        return await client.download(
            received[0].id, tmp_path, progress_callback=lambda cur, total: progress.append((cur, total))
        )

    saved = _run(scenario())

    assert saved == tmp_path / "Unleashed.flac"
    assert progress == [(100, 100)]


def test_downloading_a_message_with_no_file_is_a_telegram_error():
    fake = FakeTelethonClient()
    client = TelegramBotClient(fake)
    received: list[ChatMessage] = []

    async def scenario():
        await client.resolve_bot("@my_bot")
        await client.start_watching(received.append)
        callback, _ = fake.handlers[0]
        await callback(FakeEvent(FakeMessage(text="no attachment here")))
        return received[0].id

    message_id = _run(scenario())

    with pytest.raises(TelegramError):
        _run(client.download(message_id, Path(".")))


def test_downloading_an_unknown_message_id_is_a_telegram_error(tmp_path):
    client = TelegramBotClient(FakeTelethonClient())

    with pytest.raises(TelegramError):
        _run(client.download(999999, tmp_path))


# --- photos (inline preview) --------------------------------------------------


def test_a_photo_message_is_flagged_and_carries_no_filename():
    """A Telegram photo has no DocumentAttributeFilename at all -- unlike a
    document, its ChatMessage.file_name must stay None even though it does
    have a file in every practical sense (ChatMessage.is_photo is what
    distinguishes the two)."""
    fake = FakeTelethonClient()
    client = TelegramBotClient(fake)
    received: list[ChatMessage] = []

    async def scenario():
        await client.resolve_bot("@my_bot")
        await client.start_watching(received.append)
        callback, _ = fake.handlers[0]
        raw = FakeMessage(text="here's the cover", photo=True, file=FakeFile(None, 45_000))
        await callback(FakeEvent(raw))

    _run(scenario())

    assert received[0].is_photo is True
    assert received[0].file_name is None


def test_a_plain_document_is_not_flagged_as_a_photo():
    fake = FakeTelethonClient()
    client = TelegramBotClient(fake)
    received: list[ChatMessage] = []

    async def scenario():
        await client.resolve_bot("@my_bot")
        await client.start_watching(received.append)
        callback, _ = fake.handlers[0]
        await callback(FakeEvent(FakeMessage(text="here", file=FakeFile("Unleashed.flac", 100))))

    _run(scenario())

    assert received[0].is_photo is False


def test_download_bytes_returns_the_in_memory_data():
    fake = FakeTelethonClient()
    client = TelegramBotClient(fake)
    received: list[ChatMessage] = []

    async def scenario():
        await client.resolve_bot("@my_bot")
        await client.start_watching(received.append)
        callback, _ = fake.handlers[0]
        raw = FakeMessage(photo=True, file=FakeFile(None, 3), content=b"\xff\xd8\xff-jpeg-bytes")
        await callback(FakeEvent(raw))
        return await client.download_bytes(received[0].id), raw

    data, raw = _run(scenario())

    assert data == b"\xff\xd8\xff-jpeg-bytes"
    assert raw.download_target is bytes


def test_download_bytes_on_a_message_with_no_file_is_a_telegram_error():
    fake = FakeTelethonClient()
    client = TelegramBotClient(fake)
    received: list[ChatMessage] = []

    async def scenario():
        await client.resolve_bot("@my_bot")
        await client.start_watching(received.append)
        callback, _ = fake.handlers[0]
        await callback(FakeEvent(FakeMessage(text="no attachment here")))
        return received[0].id

    message_id = _run(scenario())

    with pytest.raises(TelegramError):
        _run(client.download_bytes(message_id))


def test_download_bytes_on_an_unknown_message_id_is_a_telegram_error():
    client = TelegramBotClient(FakeTelethonClient())

    with pytest.raises(TelegramError):
        _run(client.download_bytes(999999))
