from __future__ import annotations

import base64
import imaplib
import json

import httpx

from mailbox_manager.domain.models import (
    AccountStatus,
    EmailAccount,
    FetchRequest,
    MailMessage,
    PostAction,
    ProtocolType,
    SecurityMode,
)
from mailbox_manager.protocols.imap_client import ImapClient
from mailbox_manager.protocols.outlook_graph import OutlookGraphClient


def _imap_account() -> EmailAccount:
    return EmailAccount(
        email="owner@example.com",
        provider="custom",
        protocol=ProtocolType.IMAP,
        host="imap.example.com",
        port=993,
        security=SecurityMode.SSL,
        username="owner@example.com",
        secret="app-password",
    )


class FakeImap:
    def __init__(self, *_args, **_kwargs) -> None:
        self.logged_in = False
        self.closed = False

    def login(self, username: str, secret: str):
        assert username == "owner@example.com"
        assert secret == "app-password"
        self.logged_in = True
        return "OK", [b"authenticated"]

    def select(self, folder: str, readonly: bool = True):
        assert readonly is True
        return "OK", [b"1"]

    def uid(self, command: str, *_args):
        if command.casefold() == "search":
            return "OK", [b"42"]
        raw = (
            b"Subject: verification code\r\n"
            b"From: security@example.com\r\n"
            b"To: owner@example.com\r\n"
            b"Message-ID: <imap-42@example.com>\r\n\r\n"
            b"Code: 771204"
        )
        return "OK", [(b"42 (RFC822 {160})", raw)]

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"']

    def logout(self):
        self.closed = True
        return "BYE", [b"logout"]


def test_imap_client_fetches_and_parses_bounded_messages() -> None:
    fake = FakeImap()
    client = ImapClient(_imap_account(), connection_factory=lambda *_a, **_kw: fake)

    result = client.fetch_messages(FetchRequest(max_messages=1))
    client.close()

    assert result.status is AccountStatus.SUCCESS
    assert result.messages[0].provider_message_id == "<imap-42@example.com>"
    assert "771204" in result.messages[0].matched_values
    assert fake.closed is True


def test_imap_client_zero_limit_fetches_all_matching_messages() -> None:
    class UnlimitedImap(FakeImap):
        def uid(self, command: str, *args):
            if command.casefold() == "search":
                return "OK", [b"1 2 3"]
            identifier = args[0]
            value = (
                identifier.decode("ascii")
                if isinstance(identifier, bytes)
                else str(identifier)
            )
            raw = (
                f"Subject: message {value}\r\n"
                f"Message-ID: <imap-{value}@example.com>\r\n\r\nBody"
            ).encode()
            return "OK", [(b"1 (RFC822)", raw)]

    result = ImapClient(
        _imap_account(), connection_factory=UnlimitedImap
    ).fetch_messages(FetchRequest(max_messages=0))

    assert [message.subject for message in result.messages] == [
        "message 3",
        "message 2",
        "message 1",
    ]


def test_imap_client_classifies_authentication_failure() -> None:
    class RejectedImap(FakeImap):
        def login(self, _username: str, _secret: str):
            raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")

    client = ImapClient(_imap_account(), connection_factory=RejectedImap)

    result = client.test_connection()

    assert result.status is AccountStatus.AUTH_FAILED
    assert "AUTHENTICATIONFAILED" not in result.detail


def test_graph_client_exchanges_refresh_token_and_fetches_messages() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "oauth2" in request.url.path:
            assert b"scope=" not in request.content
            return httpx.Response(200, json={"access_token": "access", "expires_in": 3600})
        assert request.headers["Authorization"] == "Bearer access"
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": "graph-1",
                        "subject": "验证码",
                        "from": {"emailAddress": {"address": "security@example.com"}},
                        "toRecipients": [{"emailAddress": {"address": "owner@outlook.com"}}],
                        "receivedDateTime": "2026-07-13T10:00:00Z",
                        "body": {"contentType": "html", "content": "<p>Code <b>889900</b></p>"},
                        "internetMessageHeaders": [
                            {"name": "X-Original-To", "value": "alias@outlook.com"}
                        ],
                    }
                ]
            },
        )

    account = EmailAccount(
        email="owner@outlook.com",
        provider="outlook",
        protocol=ProtocolType.GRAPH,
        username="owner@outlook.com",
        refresh_token="refresh",
        client_id="00000000-0000-0000-0000-000000000001",
    )
    client = OutlookGraphClient(account, transport=httpx.MockTransport(handler))

    result = client.fetch_messages(FetchRequest(max_messages=5))

    assert result.status is AccountStatus.SUCCESS
    assert result.messages[0].catch_all_recipient == "alias@outlook.com"
    assert "889900" in result.messages[0].matched_values
    assert "<b>889900</b>" in result.messages[0].web_html_body
    assert any("oauth2" in call for call in calls)
    assert len(json.dumps(result.messages[0].__repr__())) < 1000


def test_graph_client_fetches_inline_cid_attachments() -> None:
    image = b"small-png-payload"

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2" in request.url.path:
            return httpx.Response(200, json={"access_token": "access", "expires_in": 3600})
        if request.url.path.endswith("/attachments"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "contentType": "image/png",
                            "contentId": "brand-logo",
                            "isInline": True,
                            "contentBytes": base64.b64encode(image).decode("ascii"),
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": "graph-cid",
                        "subject": "CID image",
                        "body": {
                            "contentType": "html",
                            "content": '<p>Hello</p><img src="cid:brand-logo">',
                        },
                        "toRecipients": [],
                        "internetMessageHeaders": [],
                    }
                ]
            },
        )

    account = EmailAccount(
        email="owner@outlook.com",
        provider="outlook",
        protocol=ProtocolType.GRAPH,
        refresh_token="refresh",
        client_id="00000000-0000-0000-0000-000000000001",
    )
    result = OutlookGraphClient(account, transport=httpx.MockTransport(handler)).fetch_messages(
        FetchRequest(max_messages=1)
    )

    assert result.status is AccountStatus.SUCCESS
    assert "data:image/png;base64," in result.messages[0].html_body
    assert "data:image/png;base64," in result.messages[0].web_html_body


def test_graph_client_fetches_downloadable_file_attachments() -> None:
    content = b"graph-pdf-content"

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2" in request.url.path:
            return httpx.Response(200, json={"access_token": "access", "expires_in": 3600})
        if request.url.path.endswith("/attachments"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "attachment-1",
                            "name": "report.pdf",
                            "contentType": "application/pdf",
                            "size": len(content),
                            "isInline": False,
                            "contentBytes": base64.b64encode(content).decode("ascii"),
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": "graph-file",
                        "subject": "Attachment",
                        "body": {"contentType": "text", "content": "See attachment"},
                        "hasAttachments": True,
                        "toRecipients": [],
                        "internetMessageHeaders": [],
                    }
                ]
            },
        )

    account = EmailAccount(
        email="owner@outlook.com",
        provider="outlook",
        protocol=ProtocolType.GRAPH,
        refresh_token="refresh",
        client_id="00000000-0000-0000-0000-000000000001",
    )

    result = OutlookGraphClient(
        account,
        transport=httpx.MockTransport(handler),
    ).fetch_messages(FetchRequest(max_messages=1))

    attachment = result.messages[0].attachments[0]
    assert attachment.filename == "report.pdf"
    assert attachment.content_type == "application/pdf"
    assert attachment.provider_attachment_id == "attachment-1"
    assert attachment.content == content
    assert attachment.is_truncated is False


def test_graph_zero_limit_follows_all_pagination_links() -> None:
    page_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal page_calls
        if "oauth2" in request.url.path:
            return httpx.Response(200, json={"access_token": "access", "expires_in": 3600})
        page_calls += 1
        identifier = f"page-{page_calls}"
        payload: dict[str, object] = {
            "value": [
                {
                    "id": identifier,
                    "subject": identifier,
                    "body": {"contentType": "text", "content": "body"},
                    "toRecipients": [],
                    "internetMessageHeaders": [],
                }
            ]
        }
        if page_calls == 1:
            payload["@odata.nextLink"] = (
                "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
                "?$skiptoken=next"
            )
        return httpx.Response(200, json=payload)

    account = EmailAccount(
        email="owner@outlook.com",
        provider="outlook",
        protocol=ProtocolType.GRAPH,
        refresh_token="refresh",
        client_id="00000000-0000-0000-0000-000000000001",
    )

    result = OutlookGraphClient(
        account, transport=httpx.MockTransport(handler)
    ).fetch_messages(FetchRequest(max_messages=0))

    assert [message.subject for message in result.messages] == ["page-1", "page-2"]
    assert page_calls == 2


def test_graph_client_maps_rate_limit_without_leaking_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2" in request.url.path:
            return httpx.Response(200, json={"access_token": "access", "expires_in": 3600})
        return httpx.Response(429, json={"error": {"message": "internal-provider-detail"}})

    account = EmailAccount(
        email="owner@outlook.com",
        provider="outlook",
        protocol=ProtocolType.GRAPH,
        username="owner@outlook.com",
        refresh_token="refresh",
        client_id="00000000-0000-0000-0000-000000000001",
    )
    result = OutlookGraphClient(account, transport=httpx.MockTransport(handler)).fetch_messages(
        FetchRequest()
    )

    assert result.status is AccountStatus.RATE_LIMITED
    assert "internal-provider-detail" not in result.detail


def test_graph_client_explains_expired_refresh_token_without_leaking_response() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": "invalid_grant",
                "error_description": "sensitive provider diagnostics",
            },
        )

    account = EmailAccount(
        email="owner@outlook.com",
        provider="Outlook",
        protocol=ProtocolType.GRAPH,
        refresh_token="expired-refresh",
        client_id="00000000-0000-0000-0000-000000000001",
    )
    result = OutlookGraphClient(account, transport=httpx.MockTransport(handler)).fetch_messages(
        FetchRequest()
    )

    assert result.status is AccountStatus.AUTH_FAILED
    assert "Refresh Token 已失效" in result.detail
    assert "sensitive provider diagnostics" not in result.detail


def test_graph_special_folder_scan_uses_discovered_folder_ids() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2" in request.url.path:
            return httpx.Response(200, json={"access_token": "access"})
        requested_paths.append(request.url.path)
        if request.url.path.endswith("/mailFolders"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {"id": "inbox-id", "displayName": "Inbox"},
                        {"id": "junk-id", "displayName": "Junk Email"},
                        {"id": "deleted-id", "displayName": "Deleted Items"},
                        {"id": "archive-id", "displayName": "Archive"},
                    ]
                },
            )
        folder_id = request.url.path.split("/mailFolders/", 1)[1].split("/", 1)[0]
        if folder_id in {"junk-id", "deleted-id"}:
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": f"message-{folder_id}",
                            "subject": "Special folder message",
                            "body": {"contentType": "text", "content": "body"},
                            "toRecipients": [],
                            "internetMessageHeaders": [],
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"value": []})

    account = EmailAccount(
        email="owner@outlook.com",
        provider="Outlook",
        protocol=ProtocolType.GRAPH,
        refresh_token="refresh",
        client_id="00000000-0000-0000-0000-000000000001",
    )
    result = OutlookGraphClient(
        account, transport=httpx.MockTransport(handler)
    ).fetch_messages(FetchRequest(max_messages=5, include_special_folders=True))

    assert result.status is AccountStatus.SUCCESS
    assert {message.folder for message in result.messages} == {
        "Junk Email",
        "Deleted Items",
    }
    assert any("/mailFolders/junk-id/messages" in path for path in requested_paths)
    assert any("/mailFolders/deleted-id/messages" in path for path in requested_paths)
    assert not any("/mailFolders/archive-id/messages" in path for path in requested_paths)


def test_graph_move_resolves_display_name_to_folder_id() -> None:
    moved_to: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2" in request.url.path:
            return httpx.Response(200, json={"access_token": "access"})
        if request.url.path.endswith("/mailFolders"):
            return httpx.Response(
                200,
                json={"value": [{"id": "archive-id", "displayName": "Archive"}]},
            )
        if request.url.path.endswith("/move"):
            moved_to.append(json.loads(request.content)["destinationId"])
            return httpx.Response(201, json={})
        return httpx.Response(404)

    account = EmailAccount(
        email="owner@outlook.com",
        provider="Outlook",
        protocol=ProtocolType.GRAPH,
        refresh_token="refresh",
        client_id="00000000-0000-0000-0000-000000000001",
    )
    client = OutlookGraphClient(account, transport=httpx.MockTransport(handler))

    applied = client.apply_action(
        MailMessage(
            provider_message_id="message-id",
            transport_id="message-id",
            folder="Inbox",
        ),
        PostAction.MOVE,
        "Archive",
        confirmed=True,
    )

    assert applied is True
    assert moved_to == ["archive-id"]
