from __future__ import annotations

import base64
import smtplib
import ssl
from collections.abc import Callable
from contextlib import suppress
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from uuid import uuid4

from mailbox_manager.domain.models import ConnectionResult, EmailAccount, SecurityMode
from mailbox_manager.domain.status import AccountStatus
from mailbox_manager.services.send_service import OutgoingDraft, SendResult, SendStatus

SmtpConnection = smtplib.SMTP | smtplib.SMTP_SSL
ConnectionFactory = Callable[..., SmtpConnection]


class SmtpClient:
    def __init__(
        self,
        account: EmailAccount,
        *,
        oauth_access_token: str = "",
        timeout: float = 20.0,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        if not account.smtp_host or not account.smtp_port:
            raise ValueError("账号未配置 SMTP 服务器")
        self._account = account
        self._oauth_access_token = oauth_access_token
        self._timeout = timeout
        self._factory = connection_factory
        self._connection: SmtpConnection | None = None

    def _connect(self) -> SmtpConnection:
        if self._connection is not None:
            return self._connection
        factory = self._factory
        if factory is None:
            factory = (
                smtplib.SMTP_SSL
                if self._account.smtp_security is SecurityMode.SSL
                else smtplib.SMTP
            )
        connection = factory(
            self._account.smtp_host, self._account.smtp_port, timeout=self._timeout
        )
        connection.ehlo()
        if self._account.smtp_security is SecurityMode.STARTTLS:
            connection.starttls(context=ssl.create_default_context())
            connection.ehlo()
        username = self._account.username or self._account.email
        if self._oauth_access_token:
            auth = f"user={username}\x01auth=Bearer {self._oauth_access_token}\x01\x01"
            encoded = base64.b64encode(auth.encode()).decode("ascii")
            code, _ = connection.docmd("AUTH XOAUTH2", encoded)
            if code not in {235, 250}:
                raise smtplib.SMTPAuthenticationError(code, b"OAuth2 authentication failed")
        else:
            connection.login(username, self._account.secret)
        self._connection = connection
        return connection

    def test_connection(self) -> ConnectionResult:
        try:
            self._connect()
            return ConnectionResult(AccountStatus.SUCCESS, "SMTP 鉴权成功")
        except smtplib.SMTPAuthenticationError:
            return ConnectionResult(AccountStatus.AUTH_FAILED, "SMTP 鉴权失败")
        except (OSError, smtplib.SMTPException):
            return ConnectionResult(AccountStatus.NETWORK_ERROR, "SMTP 连接失败")

    def send_probe(self, recipient: str, *, confirmed_owned_target: bool) -> str:
        if not confirmed_owned_target:
            raise ValueError("发送测试邮件前必须确认目标邮箱归你所有")
        _validate_email(recipient)
        probe_id = str(uuid4())
        message = EmailMessage()
        message["From"] = self._account.email
        message["To"] = recipient.casefold()
        message["Subject"] = f"MailDesk SMTP Probe {probe_id}"
        message.set_content(f"MailDesk SMTP permission probe. ID: {probe_id}")
        self._connect().send_message(message)
        return probe_id

    def send_message(self, draft: OutgoingDraft) -> SendResult:
        """Send one validated draft, including Bcc envelope recipients and attachments."""

        message_id = make_msgid(domain=self._account.email.rsplit("@", 1)[-1])
        try:
            message = _build_message(self._account.email, message_id, draft)
            refused = self._connect().send_message(
                message,
                from_addr=self._account.email,
                to_addrs=list(draft.all_recipients),
            )
            rejected = tuple(str(address) for address in (refused or {}))
            if rejected:
                return SendResult(
                    SendStatus.PARTIAL_SUCCESS,
                    f"邮件已提交，但有 {len(rejected)} 个收件地址被服务器拒绝",
                    message_id,
                    rejected,
                )
            return SendResult(SendStatus.SUCCESS, "邮件发送成功", message_id)
        except Exception as exc:
            status, detail, rejected = _classify_smtp_send_error(exc)
            return SendResult(status, detail, message_id, rejected)

    def forward_message(
        self,
        raw_eml: bytes,
        recipient: str,
        *,
        confirmed_forwarding: bool,
    ) -> str:
        if not confirmed_forwarding:
            raise ValueError("自动转发必须由用户显式启用并确认")
        _validate_email(recipient)
        forward_id = str(uuid4())
        message = EmailMessage()
        message["From"] = self._account.email
        message["To"] = recipient.casefold()
        message["Subject"] = f"Fwd: MailDesk matched message [{forward_id}]"
        message.set_content("Forwarded by a user-confirmed MailDesk automation rule.")
        message.add_attachment(
            raw_eml,
            maintype="message",
            subtype="rfc822",
            filename="forwarded.eml",
        )
        self._connect().send_message(message)
        return forward_id

    def close(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            with suppress(smtplib.SMTPException, OSError):
                connection.quit()


def _validate_email(value: str) -> None:
    if len(value) > 320 or "@" not in value or any(character.isspace() for character in value):
        raise ValueError("目标邮箱地址格式不正确")


def _build_message(sender: str, message_id: str, draft: OutgoingDraft) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(draft.to)
    if draft.cc:
        message["Cc"] = ", ".join(draft.cc)
    if draft.bcc:
        message["Bcc"] = ", ".join(draft.bcc)
    message["Subject"] = draft.subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = message_id
    if draft.text_body:
        message.set_content(draft.text_body)
        if draft.html_body:
            message.add_alternative(draft.html_body, subtype="html")
    else:
        message.set_content(draft.html_body, subtype="html")
    for attachment in draft.attachments:
        maintype, subtype = attachment.content_type.split("/", 1)
        message.add_attachment(
            attachment.content,
            maintype=maintype,
            subtype=subtype,
            filename=attachment.filename,
        )
    return message


def _classify_smtp_send_error(
    exc: Exception,
) -> tuple[SendStatus, str, tuple[str, ...]]:
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return (
            SendStatus.RECIPIENT_REJECTED,
            "所有收件地址均被邮件服务器拒绝",
            tuple(str(address) for address in exc.recipients),
        )
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return SendStatus.AUTH_FAILED, "SMTP 鉴权失败，请检查密码、授权码或 OAuth 授权", ()
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return SendStatus.BLOCKED, "邮件服务器拒绝使用当前账号发件", ()
    if isinstance(exc, TimeoutError):
        return SendStatus.TIMEOUT, "SMTP 连接超时", ()
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return SendStatus.NETWORK_ERROR, "SMTP 连接意外断开", ()
    if isinstance(exc, smtplib.SMTPResponseException):
        code = int(exc.smtp_code)
        if code in {421, 450, 451, 452}:
            return SendStatus.RATE_LIMITED, "邮件服务器暂时限制发件，请稍后重试", ()
        if code in {530, 534, 535, 538}:
            return SendStatus.AUTH_FAILED, "SMTP 鉴权失败，请检查账号发件权限", ()
        if code in {552}:
            return SendStatus.ATTACHMENT_TOO_LARGE, "邮件或附件超过服务器允许的大小", ()
        if code in {550, 551, 553}:
            return SendStatus.RECIPIENT_REJECTED, "收件地址被邮件服务器拒绝", ()
        if code >= 500:
            return SendStatus.BLOCKED, "邮件服务器拒绝了本次发件", ()
        return SendStatus.PROVIDER_ERROR, "邮件服务器未能接受本次发件", ()
    if isinstance(exc, OSError):
        return SendStatus.NETWORK_ERROR, "无法连接 SMTP 邮件服务器", ()
    if isinstance(exc, (TypeError, ValueError)):
        return SendStatus.VALIDATION_ERROR, "发件内容格式不正确", ()
    if isinstance(exc, smtplib.SMTPException):
        return SendStatus.PROVIDER_ERROR, "SMTP 邮件服务器返回异常", ()
    return SendStatus.UNKNOWN_ERROR, "发件过程中发生未知错误", ()
