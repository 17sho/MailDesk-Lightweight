from __future__ import annotations

import base64
from email.message import EmailMessage

import httpx
import pytest

from mailbox_manager.domain.models import (
    AccountStatus,
    EmailAccount,
    FetchRequest,
    PostAction,
    ProtocolType,
    SecurityMode,
)
from mailbox_manager.protocols.imap_client import ImapClient
from mailbox_manager.protocols.oauth import OAuthTokenProvider
from mailbox_manager.protocols.pop3_client import Pop3Client
from mailbox_manager.protocols.smtp_client import SmtpClient


def _pop_account() -> EmailAccount:
    return EmailAccount(
        email="owner@example.com",
        provider="custom",
        protocol=ProtocolType.POP3,
        host="pop.example.com",
        port=995,
        security=SecurityMode.SSL,
        username="owner@example.com",
        secret="app-password",
    )


class FakePop3:
    def __init__(self, *_args, **_kwargs) -> None:
        self.closed = False

    def user(self, value: str):
        assert value == "owner@example.com"

    def pass_(self, value: str):
        assert value == "app-password"

    def stat(self):
        return 2, 200

    def retr(self, number: int):
        raw = [
            b"Subject: verification code",
            b"From: security@example.com",
            b"To: owner@example.com",
            f"Message-ID: <pop-{number}@example.com>".encode(),
            b"",
            b"Code 667788",
        ]
        return b"+OK", raw, 100

    def quit(self):
        self.closed = True


def test_pop3_client_fetches_latest_messages() -> None:
    fake = FakePop3()
    client = Pop3Client(_pop_account(), connection_factory=lambda *_a, **_kw: fake)

    result = client.fetch_messages(FetchRequest(max_messages=1))
    client.close()

    assert result.status is AccountStatus.SUCCESS
    assert result.messages[0].provider_message_id == "<pop-2@example.com>"
    assert "667788" in result.messages[0].matched_values
    assert fake.closed is True


def test_pop3_zero_limit_fetches_the_whole_mailbox() -> None:
    result = Pop3Client(
        _pop_account(), connection_factory=lambda *_a, **_kw: FakePop3()
    ).fetch_messages(FetchRequest(max_messages=0))

    assert len(result.messages) == 2
    assert [message.provider_message_id for message in result.messages] == [
        "<pop-2@example.com>",
        "<pop-1@example.com>",
    ]


def test_oauth_provider_supports_google_and_microsoft_refresh_tokens() -> None:
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})

    provider = OAuthTokenProvider(transport=httpx.MockTransport(handler))
    google = EmailAccount(
        email="owner@gmail.com",
        provider="Gmail",
        protocol=ProtocolType.IMAP,
        host="imap.gmail.com",
        port=993,
        username="owner@gmail.com",
        refresh_token="refresh",
        client_id="client",
        oauth_provider="google",
    )
    microsoft = EmailAccount(
        email="owner@outlook.com",
        provider="Outlook",
        protocol=ProtocolType.IMAP,
        host="outlook.office365.com",
        port=993,
        username="owner@outlook.com",
        refresh_token="refresh",
        client_id="client",
        oauth_provider="microsoft",
    )

    assert provider.access_token(google) == "token"
    assert provider.access_token(microsoft) == "token"
    provider.close()
    assert any("oauth2.googleapis.com/token" in url for url in urls)
    assert any("login.microsoftonline.com" in url for url in urls)


class FakeSmtp:
    def __init__(self, *_args, **_kwargs) -> None:
        self.sent: EmailMessage | None = None
        self.auth_payload = ""
        self.closed = False

    def ehlo(self):
        return 250, b"ok"

    def starttls(self, context=None):
        return 220, b"ready"

    def login(self, username: str, secret: str):
        assert username == "owner@example.com"
        assert secret == "app-password"

    def docmd(self, command: str, payload: str):
        assert command == "AUTH XOAUTH2"
        self.auth_payload = base64.b64decode(payload).decode()
        return 235, b"ok"

    def send_message(self, message: EmailMessage):
        self.sent = message

    def quit(self):
        self.closed = True


def _smtp_account() -> EmailAccount:
    return EmailAccount(
        email="owner@example.com",
        provider="custom",
        protocol=ProtocolType.IMAP,
        host="imap.example.com",
        port=993,
        username="owner@example.com",
        secret="app-password",
        smtp_host="smtp.example.com",
        smtp_port=465,
    )


def test_smtp_probe_requires_confirmed_owned_recipient_and_sends_uuid() -> None:
    fake = FakeSmtp()
    client = SmtpClient(_smtp_account(), connection_factory=lambda *_a, **_kw: fake)

    with pytest.raises(ValueError, match="确认"):
        client.send_probe("probe@example.net", confirmed_owned_target=False)

    probe_id = client.send_probe("probe@example.net", confirmed_owned_target=True)
    client.close()

    assert probe_id in fake.sent["Subject"]  # type: ignore[index]
    assert fake.sent["To"] == "probe@example.net"  # type: ignore[index]
    assert fake.closed is True


def test_fetch_request_requires_confirmation_for_destructive_actions() -> None:
    with pytest.raises(ValueError, match="显式确认"):
        FetchRequest(post_action=PostAction.DELETE)


def test_imap_scans_special_folders_and_applies_confirmed_post_action() -> None:
    class ActionImap:
        def __init__(self, *_args, **_kwargs) -> None:
            self.selected: list[str] = []
            self.stores: list[tuple[object, ...]] = []

        def login(self, _username, _secret):
            return "OK", [b"ok"]

        def list(self):
            return "OK", [
                b'(\\HasNoChildren) "/" "INBOX"',
                b'(\\HasNoChildren \\Junk) "/" "Junk"',
                b'(\\HasNoChildren \\Trash) "/" "Trash"',
            ]

        def select(self, folder, readonly=True):
            self.selected.append(folder)
            assert readonly is False
            return "OK", [b"1"]

        def uid(self, command, *args):
            if command.casefold() == "search":
                return "OK", [b"1"]
            if command.casefold() == "store":
                self.stores.append(args)
                return "OK", [b"stored"]
            raw = (
                b"Subject: verification code\r\nFrom: security@example.com\r\n"
                b"To: owner@example.com\r\nMessage-ID: <action@example.com>\r\n\r\nCode 445566"
            )
            return "OK", [(b"1 (RFC822)", raw)]

        def logout(self):
            return "BYE", [b"bye"]

    fake = ActionImap()
    account = EmailAccount(
        email="owner@example.com",
        provider="custom",
        protocol=ProtocolType.IMAP,
        host="imap.example.com",
        port=993,
        username="owner@example.com",
        secret="secret",
    )
    client = ImapClient(account, connection_factory=lambda *_a, **_kw: fake)

    result = client.fetch_messages(
        FetchRequest(
            max_messages=2,
            include_special_folders=True,
            post_action=PostAction.MARK_READ,
            confirmed_actions=True,
        )
    )

    assert result.status is AccountStatus.SUCCESS
    assert fake.selected == ["INBOX", "Junk"]
    assert len(fake.stores) == 2
