from __future__ import annotations

import pytest

from mailbox_manager.domain.models import (
    AccountStatus,
    EmailAccount,
    FetchRequest,
    FetchResult,
    MailMessage,
    ProtocolType,
    SecurityMode,
)
from mailbox_manager.services.fetch_service import FetchService
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.repositories import AccountRepository, MessageRepository


class FakeClient:
    def __init__(
        self,
        result: FetchResult,
        loaded_message: MailMessage | None = None,
    ) -> None:
        self.result = result
        self.loaded_message = loaded_message
        self.closed = False
        self.aborted = False
        self.fetch_message_calls = 0
        self.request: FetchRequest | None = None

    def fetch_messages(self, request: FetchRequest) -> FetchResult:
        self.request = request
        return self.result

    def fetch_message(self, _message: MailMessage, request: FetchRequest) -> MailMessage:
        self.fetch_message_calls += 1
        self.request = request
        if self.loaded_message is None:
            raise RuntimeError("no lazy body configured")
        return self.loaded_message

    def search_messages(self, _query: str, request: FetchRequest) -> FetchResult:
        self.request = request
        return self.result

    def close(self) -> None:
        self.closed = True

    def abort(self) -> None:
        self.aborted = True
        self.closed = True


def test_fetch_service_persists_messages_and_updates_account_status(tmp_path) -> None:
    database = Database(tmp_path / "maildesk.db")
    database.initialize()
    cipher = CredentialCipher.from_raw_key(b"C" * 32)
    accounts = AccountRepository(database, cipher)
    account = EmailAccount(
        email="owner@example.com",
        provider="custom",
        protocol=ProtocolType.IMAP,
        host="imap.example.com",
        port=993,
        security=SecurityMode.SSL,
        username="owner@example.com",
        secret="secret",
    )
    accounts.add_many([account])
    stored = accounts.list_all()[0]
    message = MailMessage(
        provider_message_id="mail-1",
        folder="INBOX",
        subject="验证码",
        matched_values=("123456",),
        text_body="验证码 123456",
    )
    client = FakeClient(FetchResult(AccountStatus.SUCCESS, (message,), "ok"))
    service = FetchService(accounts, MessageRepository(database), client_factory=lambda _a: client)

    result = service.fetch_account(stored, FetchRequest())

    assert result.status is AccountStatus.SUCCESS
    assert client.closed is False
    assert accounts.get(stored.account_id).status is AccountStatus.SUCCESS  # type: ignore[arg-type]
    assert MessageRepository(database).list_for_account(stored.account_id)[0].subject == "验证码"  # type: ignore[arg-type]
    service.close_message_sessions()
    assert client.aborted is True


def test_fetch_service_reuses_list_session_for_first_message_body(tmp_path) -> None:
    database = Database(tmp_path / "list-to-body-session.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"L" * 32))
    accounts.add_many(
        [
            EmailAccount(
                email="list-session@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                secret="secret",
            )
        ]
    )
    account = accounts.list_all()[0]
    assert account.account_id is not None
    header = MailMessage(
        "provider-1",
        "INBOX",
        transport_id="1",
        body_loaded=False,
    )
    loaded = MailMessage(
        "server-provider",
        "INBOX",
        transport_id="1",
        text_body="完整正文",
        body_loaded=True,
    )
    client = FakeClient(
        FetchResult(AccountStatus.SUCCESS, (header,)),
        loaded,
    )
    factory_calls = 0

    def factory(_account: EmailAccount) -> FakeClient:
        nonlocal factory_calls
        factory_calls += 1
        return client

    messages = MessageRepository(database)
    service = FetchService(accounts, messages, client_factory=factory)

    service.fetch_account(account, FetchRequest())
    stored_header = messages.list_for_account(account.account_id)[0]
    result = service.load_message(account, stored_header, FetchRequest())

    assert result.body_loaded is True
    assert result.text_body == "完整正文"
    assert factory_calls == 1
    assert client.fetch_message_calls == 1
    assert client.closed is False
    service.close_message_sessions()
    assert client.aborted is True


def test_fetch_service_deep_search_updates_existing_header_without_duplicate(
    tmp_path,
) -> None:
    database = Database(tmp_path / "deep-search.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"Q" * 32))
    accounts.add_many(
        [
            EmailAccount(
                email="deep@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                secret="secret",
            )
        ]
    )
    account = accounts.list_all()[0]
    assert account.account_id is not None
    messages = MessageRepository(database)
    messages.add_many(
        account.account_id,
        (
            MailMessage(
                "provider-42",
                "INBOX",
                transport_id="42",
                subject="邮件头",
                body_loaded=False,
            ),
        ),
    )
    client = FakeClient(
        FetchResult(
            AccountStatus.SUCCESS,
            (
                MailMessage(
                    "graph-or-server-id",
                    "搜索结果",
                    transport_id="42",
                    subject="完整邮件",
                    text_body="如果您更改了登录设置",
                    body_loaded=True,
                ),
            ),
        )
    )
    service = FetchService(accounts, messages, client_factory=lambda _account: client)

    result = service.search_account(account, "如果您更改了", FetchRequest())
    stored = messages.list_for_account(account.account_id)

    assert result.status is AccountStatus.SUCCESS
    assert len(stored) == 1
    assert stored[0].folder == "INBOX"
    assert stored[0].provider_message_id == "provider-42"
    assert stored[0].body_loaded is True
    assert "如果您更改了" in stored[0].text_body
    service.close_message_sessions()


def test_fetch_service_reuses_one_message_session_per_account(tmp_path) -> None:
    database = Database(tmp_path / "message-session.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"S" * 32))
    accounts.add_many(
        [
            EmailAccount(
                email="session@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                secret="secret",
            )
        ]
    )
    account = accounts.list_all()[0]
    assert account.account_id is not None
    messages = MessageRepository(database)
    messages.add_many(
        account.account_id,
        (
            MailMessage("provider-1", "INBOX", transport_id="1", body_loaded=False),
            MailMessage("provider-2", "INBOX", transport_id="2", body_loaded=False),
        ),
    )
    headers = messages.list_for_account(account.account_id)
    client = FakeClient(
        FetchResult(AccountStatus.SUCCESS),
        MailMessage(
            "server-provider",
            "INBOX",
            transport_id="server-id",
            text_body="完整正文",
            body_loaded=True,
        ),
    )
    factory_calls = 0

    def factory(_account: EmailAccount) -> FakeClient:
        nonlocal factory_calls
        factory_calls += 1
        return client

    service = FetchService(accounts, messages, client_factory=factory)

    service.load_message(account, headers[0], FetchRequest())
    service.load_message(account, headers[1], FetchRequest())

    assert factory_calls == 1
    assert client.fetch_message_calls == 2
    assert client.closed is False
    service.close_message_sessions()
    assert client.aborted is True


def test_fetch_service_replaces_expired_message_session(tmp_path) -> None:
    database = Database(tmp_path / "expired-message-session.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"T" * 32))
    accounts.add_many(
        [
            EmailAccount(
                email="expired@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                secret="secret",
            )
        ]
    )
    account = accounts.list_all()[0]
    assert account.account_id is not None
    messages = MessageRepository(database)
    messages.add_many(
        account.account_id,
        (MailMessage("provider", "INBOX", transport_id="9", body_loaded=False),),
    )
    header = messages.list_for_account(account.account_id)[0]
    now = [0.0]
    clients: list[FakeClient] = []

    def factory(_account: EmailAccount) -> FakeClient:
        client = FakeClient(
            FetchResult(AccountStatus.SUCCESS),
            MailMessage(
                "server-provider",
                "INBOX",
                transport_id="9",
                text_body="完整正文",
                body_loaded=True,
            ),
        )
        clients.append(client)
        return client

    service = FetchService(
        accounts,
        messages,
        client_factory=factory,
        message_session_ttl=10,
        clock=lambda: now[0],
    )
    service.load_message(account, header, FetchRequest())
    now[0] = 11.0
    service.load_message(account, header, FetchRequest())

    assert len(clients) == 2
    assert clients[0].aborted is True
    assert clients[1].closed is False
    service.close_message_sessions()
    assert clients[1].aborted is True


def test_fetch_service_discards_failed_reused_message_session(tmp_path) -> None:
    database = Database(tmp_path / "failed-message-session.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"F" * 32))
    accounts.add_many(
        [
            EmailAccount(
                email="failed-session@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                secret="secret",
            )
        ]
    )
    account = accounts.list_all()[0]
    assert account.account_id is not None
    messages = MessageRepository(database)
    messages.add_many(
        account.account_id,
        (MailMessage("provider", "INBOX", transport_id="10", body_loaded=False),),
    )
    header = messages.list_for_account(account.account_id)[0]
    body = MailMessage(
        "server-provider",
        "INBOX",
        transport_id="10",
        text_body="完整正文",
        body_loaded=True,
    )
    first = FakeClient(FetchResult(AccountStatus.SUCCESS), body)
    replacement = FakeClient(FetchResult(AccountStatus.SUCCESS), body)
    clients = iter((first, replacement))
    service = FetchService(
        accounts,
        messages,
        client_factory=lambda _account: next(clients),
    )

    service.load_message(account, header, FetchRequest())
    first.loaded_message = None
    with pytest.raises(RuntimeError, match="no lazy body configured"):
        service.load_message(account, header, FetchRequest())
    assert first.aborted is True

    service.load_message(account, header, FetchRequest())
    assert replacement.fetch_message_calls == 1
    assert replacement.closed is False
    service.close_message_sessions()


def test_fetch_service_passes_persisted_transport_ids_to_client(tmp_path) -> None:
    database = Database(tmp_path / "incremental.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"I" * 32))
    accounts.add_many(
        [
            EmailAccount(
                email="incremental@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                secret="secret",
            )
        ]
    )
    stored = accounts.list_all()[0]
    assert stored.account_id is not None
    messages = MessageRepository(database)
    messages.add_many(
        stored.account_id,
        (
            MailMessage(
                provider_message_id="provider-42",
                transport_id="42",
                folder="INBOX",
            ),
        ),
    )
    client = FakeClient(FetchResult(AccountStatus.SUCCESS))
    service = FetchService(accounts, messages, client_factory=lambda _account: client)

    service.fetch_account(stored, FetchRequest())

    assert client.request is not None
    assert client.request.known_transport_ids == frozenset({("INBOX", "42")})


def test_fetch_service_loads_and_persists_one_selected_message(tmp_path) -> None:
    database = Database(tmp_path / "lazy-message.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"L" * 32))
    accounts.add_many(
        [
            EmailAccount(
                email="lazy@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                secret="secret",
            )
        ]
    )
    account = accounts.list_all()[0]
    assert account.account_id is not None
    messages = MessageRepository(database)
    messages.add_many(
        account.account_id,
        (
            MailMessage(
                provider_message_id="lazy-provider",
                transport_id="77",
                folder="INBOX",
                subject="邮件列表项",
                body_loaded=False,
            ),
        ),
    )
    header = messages.list_for_account(account.account_id)[0]
    client = FakeClient(
        FetchResult(AccountStatus.SUCCESS),
        MailMessage(
            provider_message_id="provider-returned-by-server",
            transport_id="77",
            folder="INBOX",
            subject="邮件列表项",
            text_body="点击后加载的完整正文 123456",
            matched_values=("123456",),
            body_loaded=True,
        ),
    )
    service = FetchService(accounts, messages, client_factory=lambda _account: client)

    loaded = service.load_message(account, header, FetchRequest())

    assert loaded.message_id == header.message_id
    assert loaded.provider_message_id == "lazy-provider"
    assert loaded.body_loaded is True
    assert loaded.text_body == "点击后加载的完整正文 123456"
    assert messages.get(header.message_id).body_loaded is True  # type: ignore[arg-type,union-attr]
    assert client.closed is False
    service.close_message_sessions(account.account_id)
    assert client.closed is True
    assert client.aborted is True


def test_fetch_service_persists_failure_status_without_messages(tmp_path) -> None:
    database = Database(tmp_path / "maildesk.db")
    database.initialize()
    cipher = CredentialCipher.from_raw_key(b"D" * 32)
    accounts = AccountRepository(database, cipher)
    accounts.add_many(
        [
            EmailAccount(
                email="owner@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                security=SecurityMode.SSL,
                username="owner@example.com",
                secret="secret",
            )
        ]
    )
    stored = accounts.list_all()[0]
    client = FakeClient(FetchResult(AccountStatus.AUTH_FAILED, detail="bad"))
    service = FetchService(accounts, MessageRepository(database), client_factory=lambda _a: client)

    service.fetch_account(stored, FetchRequest())

    assert accounts.get(stored.account_id).status is AccountStatus.AUTH_FAILED  # type: ignore[arg-type]


def test_fetch_service_converts_unexpected_client_error_to_visible_status(tmp_path) -> None:
    class RaisingClient:
        def fetch_messages(self, _request):
            raise RuntimeError("provider detail must not escape")

        def close(self) -> None:
            pass

    database = Database(tmp_path / "exception.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"X" * 32))
    accounts.add_many(
        [
            EmailAccount(
                email="owner@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                secret="secret",
            )
        ]
    )
    stored = accounts.list_all()[0]
    service = FetchService(
        accounts,
        MessageRepository(database),
        client_factory=lambda _account: RaisingClient(),
    )

    result = service.fetch_account(stored, FetchRequest())

    assert result.status is AccountStatus.UNKNOWN_ERROR
    assert "provider detail" not in result.detail
    assert accounts.get(stored.account_id).status is AccountStatus.UNKNOWN_ERROR  # type: ignore[arg-type]
