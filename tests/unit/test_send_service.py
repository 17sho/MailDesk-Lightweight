from __future__ import annotations

import base64
import json
import logging
import smtplib
from dataclasses import replace
from email.message import EmailMessage

import httpx
import pytest

from mailbox_manager.domain.models import EmailAccount, ProtocolType, SecurityMode
from mailbox_manager.protocols.outlook_graph import OutlookGraphClient
from mailbox_manager.protocols.smtp_client import SmtpClient
from mailbox_manager.services.send_service import (
    OutgoingAttachment,
    OutgoingDraft,
    SendResult,
    SendService,
    SendStatus,
    SmtpOAuthTokenProvider,
)


def _smtp_account(email: str = "sender@example.com") -> EmailAccount:
    return EmailAccount(
        email=email,
        provider="custom",
        protocol=ProtocolType.IMAP,
        host="imap.example.com",
        port=993,
        security=SecurityMode.SSL,
        username=email,
        secret="app-password",
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_security=SecurityMode.SSL,
    )


def _graph_account() -> EmailAccount:
    return EmailAccount(
        email="sender@outlook.com",
        provider="Outlook",
        protocol=ProtocolType.GRAPH,
        refresh_token="refresh-token",
        client_id="00000000-0000-0000-0000-000000000001",
    )


def _draft() -> OutgoingDraft:
    return OutgoingDraft(
        to=("Primary@Example.net",),
        cc=("copy@example.net",),
        bcc=("hidden@example.net",),
        subject="带附件测试",
        text_body="plain body",
        html_body="<p>html body</p>",
        attachments=(
            OutgoingAttachment("说明.txt", "text/plain", b"attachment-body"),
            OutgoingAttachment("pixel.png", "image/png", b"png-payload"),
        ),
    )


class FakeSmtp:
    def __init__(self, *_args, **_kwargs) -> None:
        self.message: EmailMessage | None = None
        self.from_addr = ""
        self.to_addrs: list[str] = []
        self.closed = False

    def ehlo(self):
        return 250, b"ok"

    def login(self, username: str, secret: str):
        assert username == "sender@example.com"
        assert secret == "app-password"

    def send_message(self, message: EmailMessage, *, from_addr: str, to_addrs: list[str]):
        self.message = message
        self.from_addr = from_addr
        self.to_addrs = to_addrs
        return {}

    def quit(self):
        self.closed = True


def test_smtp_sends_to_cc_bcc_html_and_multiple_attachments() -> None:
    fake = FakeSmtp()
    client = SmtpClient(_smtp_account(), connection_factory=lambda *_a, **_kw: fake)

    result = client.send_message(_draft())
    client.close()

    assert result.status is SendStatus.SUCCESS
    assert fake.from_addr == "sender@example.com"
    assert fake.to_addrs == [
        "Primary@example.net",
        "copy@example.net",
        "hidden@example.net",
    ]
    assert fake.message is not None
    assert fake.message["Bcc"] == "hidden@example.net"
    assert fake.message.get_body(preferencelist=("html",)).get_content() == "<p>html body</p>\n"
    assert [item.get_filename() for item in fake.message.iter_attachments()] == [
        "说明.txt",
        "pixel.png",
    ]
    assert fake.closed is True


def test_smtp_classifies_rejected_recipients_without_provider_details() -> None:
    class RejectedSmtp(FakeSmtp):
        def send_message(self, *_args, **_kwargs):
            raise smtplib.SMTPRecipientsRefused(
                {"denied@example.net": (550, b"sensitive provider response")}
            )

    client = SmtpClient(_smtp_account(), connection_factory=RejectedSmtp)

    result = client.send_message(_draft())

    assert result.status is SendStatus.RECIPIENT_REJECTED
    assert result.rejected_recipients == ("denied@example.net",)
    assert "sensitive" not in result.detail


def test_graph_sendmail_contains_all_recipients_and_file_attachment() -> None:
    sent_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2" in request.url.path:
            return httpx.Response(200, json={"access_token": "access", "expires_in": 3600})
        assert request.url.path.endswith("/me/sendMail")
        assert request.headers["Authorization"] == "Bearer access"
        sent_payloads.append(json.loads(request.content))
        return httpx.Response(202)

    client = OutlookGraphClient(
        _graph_account(),
        transport=httpx.MockTransport(handler),
    )

    result = client.send_message(_draft())

    assert result.status is SendStatus.SUCCESS
    message = sent_payloads[0]["message"]
    assert message["toRecipients"][0]["emailAddress"]["address"] == "Primary@example.net"
    assert message["ccRecipients"][0]["emailAddress"]["address"] == "copy@example.net"
    assert message["bccRecipients"][0]["emailAddress"]["address"] == "hidden@example.net"
    assert message["body"] == {"contentType": "HTML", "content": "<p>html body</p>"}
    assert [item["name"] for item in message["attachments"]] == ["说明.txt", "pixel.png"]
    assert base64.b64decode(message["attachments"][0]["contentBytes"]) == b"attachment-body"
    assert sent_payloads[0]["saveToSentItems"] is True


def test_graph_sendmail_classifies_missing_send_permission() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2" in request.url.path:
            return httpx.Response(200, json={"access_token": "access"})
        return httpx.Response(403, json={"error": {"code": "ErrorAccessDenied"}})

    result = OutlookGraphClient(
        _graph_account(), transport=httpx.MockTransport(handler)
    ).send_message(_draft())

    assert result.status is SendStatus.AUTH_FAILED
    assert "Mail.Send" in result.detail


def test_microsoft_smtp_oauth_requests_send_scope() -> None:
    requested_body = b""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requested_body
        requested_body = request.content
        return httpx.Response(200, json={"access_token": "smtp-access"})

    account = EmailAccount(
        email="sender@outlook.com",
        provider="Outlook",
        protocol=ProtocolType.IMAP,
        host="outlook.office365.com",
        port=993,
        refresh_token="refresh-token",
        client_id="00000000-0000-0000-0000-000000000001",
        oauth_provider="microsoft",
        smtp_host="smtp.office365.com",
        smtp_port=587,
        smtp_security=SecurityMode.STARTTLS,
    )
    provider = SmtpOAuthTokenProvider(transport=httpx.MockTransport(handler))

    token = provider.access_token(account)
    provider.close()

    assert token == "smtp-access"
    assert b"SMTP.Send" in requested_body


def test_outgoing_draft_rejects_invalid_recipient_and_header_injection() -> None:
    with pytest.raises(ValueError, match="收件地址"):
        OutgoingDraft(to=("not-an-email",), text_body="body")
    with pytest.raises(ValueError, match="主题"):
        OutgoingDraft(
            to=("valid@example.com",),
            subject="subject\r\nBcc: injected@example.com",
            text_body="body",
        )


def test_send_service_requires_batch_confirmation_and_isolates_account_failures() -> None:
    closed: list[str] = []

    class FakeClient:
        def __init__(self, account: EmailAccount) -> None:
            self.account = account

        def send_message(self, _draft: OutgoingDraft) -> SendResult:
            if self.account.email.startswith("failed"):
                return SendResult(SendStatus.AUTH_FAILED, "鉴权失败")
            return SendResult(SendStatus.SUCCESS, "发送成功")

        def close(self) -> None:
            closed.append(self.account.email)

    service = SendService(client_factory=FakeClient)
    accounts = (_smtp_account("ok@example.com"), _smtp_account("failed@example.com"))
    draft = OutgoingDraft(to=("target@example.net",), text_body="body")

    with pytest.raises(ValueError, match="显式确认"):
        service.send_batch(accounts, draft, confirmed=False)
    result = service.send_batch(accounts, draft, confirmed=True)

    assert result.success_count == 1
    assert result.failure_count == 1
    assert closed == ["ok@example.com", "failed@example.com"]


def test_send_service_logs_batch_progress_without_message_or_credential_data(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FakeClient:
        def __init__(self, account: EmailAccount) -> None:
            self.account = account

        def send_message(self, _draft: OutgoingDraft) -> SendResult:
            status = (
                SendStatus.SUCCESS
                if self.account.account_id == 101
                else SendStatus.AUTH_FAILED
            )
            return SendResult(status, "provider detail must not be logged")

        def close(self) -> None:
            return None

    accounts = (
        replace(
            _smtp_account("private-sender-one@example.com"),
            account_id=101,
            secret="super-secret-app-password-one",
        ),
        replace(
            _smtp_account("private-sender-two@example.com"),
            account_id=102,
            secret="super-secret-app-password-two",
        ),
    )
    draft = OutgoingDraft(
        to=("sensitive-recipient@example.net",),
        subject="private subject marker",
        text_body="sensitive body payload",
        attachments=(
            OutgoingAttachment(
                "secret-attachment-name.txt",
                "text/plain",
                b"private attachment bytes",
            ),
        ),
    )

    with caplog.at_level(logging.INFO, logger="maildesk.services.send"):
        result = SendService(client_factory=FakeClient).send_batch(
            accounts,
            draft,
            confirmed=True,
        )

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert result.success_count == 1
    assert "批量发件开始 accounts=2 recipients=1 attachments=1" in rendered
    assert "发件任务完成 account_id=101 protocol=imap outcome=success" in rendered
    assert "发件任务完成 account_id=102 protocol=imap outcome=auth_failed" in rendered
    assert "批量发件完成 accounts=2 success=1 failed=1" in rendered
    for forbidden in (
        "private-sender-one@example.com",
        "private-sender-two@example.com",
        "sensitive-recipient@example.net",
        "private subject marker",
        "sensitive body payload",
        "secret-attachment-name.txt",
        "private attachment bytes",
        "super-secret-app-password-one",
        "super-secret-app-password-two",
        "provider detail must not be logged",
    ):
        assert forbidden not in rendered
