from __future__ import annotations

import logging
import mimetypes
import re
from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass, field
from email.errors import HeaderParseError
from email.headerregistry import Address
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx

from mailbox_manager.domain.models import EmailAccount, ProtocolType

_LOGGER = logging.getLogger("maildesk.services.send")

MAX_RECIPIENTS = 100
MAX_ATTACHMENT_COUNT = 20
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = 25 * 1024 * 1024
MAX_BODY_CHARACTERS = 2_000_000

_CONTENT_TYPE_PATTERN = re.compile(r"[\w!#$&^_.+-]+/[\w!#$&^_.+-]+", re.ASCII)


class SendStatus(StrEnum):
    """Stable, provider-independent outcome for an outgoing message."""

    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    VALIDATION_ERROR = "validation_error"
    AUTH_FAILED = "auth_failed"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    BLOCKED = "blocked"
    RECIPIENT_REJECTED = "recipient_rejected"
    ATTACHMENT_TOO_LARGE = "attachment_too_large"
    NETWORK_ERROR = "network_error"
    CONFIG_ERROR = "config_error"
    PROVIDER_ERROR = "provider_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass(frozen=True, slots=True)
class OutgoingAttachment:
    """An attachment whose bytes are already bounded and ready to send."""

    filename: str
    content_type: str
    content: bytes = field(repr=False)

    def __post_init__(self) -> None:
        filename = self.filename.strip().replace("\\", "/").rsplit("/", 1)[-1]
        if (
            not filename
            or len(filename) > 255
            or any(ord(character) < 32 for character in filename)
        ):
            raise ValueError("附件文件名不正确")
        content_type = self.content_type.strip().casefold()
        if not _CONTENT_TYPE_PATTERN.fullmatch(content_type):
            raise ValueError("附件 MIME 类型不正确")
        if not isinstance(self.content, bytes):
            raise TypeError("附件内容必须是 bytes")
        if len(self.content) > MAX_ATTACHMENT_BYTES:
            raise ValueError(
                f"单个附件不能超过 {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB"
            )
        object.__setattr__(self, "filename", filename)
        object.__setattr__(self, "content_type", content_type)

    @property
    def size(self) -> int:
        return len(self.content)

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        content_type: str = "",
    ) -> OutgoingAttachment:
        source = Path(path)
        if not source.is_file():
            raise ValueError("附件文件不存在或不是普通文件")
        size = source.stat().st_size
        if size > MAX_ATTACHMENT_BYTES:
            raise ValueError(
                f"单个附件不能超过 {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB"
            )
        guessed_type = mimetypes.guess_type(source.name)[0]
        return cls(
            filename=source.name,
            content_type=content_type or guessed_type or "application/octet-stream",
            content=source.read_bytes(),
        )


@dataclass(frozen=True, slots=True)
class OutgoingDraft:
    """Validated immutable message shared by SMTP and Microsoft Graph."""

    to: tuple[str, ...]
    subject: str = ""
    text_body: str = ""
    html_body: str = ""
    cc: tuple[str, ...] = ()
    bcc: tuple[str, ...] = ()
    attachments: tuple[OutgoingAttachment, ...] = ()
    save_to_sent: bool = True

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str)
            for value in (self.subject, self.text_body, self.html_body)
        ):
            raise TypeError("邮件主题和正文必须是字符串")
        to = _normalize_recipients(self.to)
        cc = _normalize_recipients(self.cc)
        bcc = _normalize_recipients(self.bcc)
        recipient_count = len(to) + len(cc) + len(bcc)
        if not recipient_count:
            raise ValueError("至少填写一个收件人")
        if recipient_count > MAX_RECIPIENTS:
            raise ValueError(f"单封邮件最多支持 {MAX_RECIPIENTS} 个收件地址")
        if "\r" in self.subject or "\n" in self.subject or len(self.subject) > 998:
            raise ValueError("邮件主题格式不正确或过长")
        if not self.text_body and not self.html_body:
            raise ValueError("邮件正文不能为空")
        if len(self.text_body) + len(self.html_body) > MAX_BODY_CHARACTERS:
            raise ValueError("邮件正文过大")
        attachments = tuple(self.attachments)
        if len(attachments) > MAX_ATTACHMENT_COUNT:
            raise ValueError(f"单封邮件最多支持 {MAX_ATTACHMENT_COUNT} 个附件")
        if not all(isinstance(item, OutgoingAttachment) for item in attachments):
            raise TypeError("附件列表包含无效项目")
        if sum(item.size for item in attachments) > MAX_TOTAL_ATTACHMENT_BYTES:
            raise ValueError(
                f"附件总大小不能超过 {MAX_TOTAL_ATTACHMENT_BYTES // (1024 * 1024)} MB"
            )
        object.__setattr__(self, "to", to)
        object.__setattr__(self, "cc", cc)
        object.__setattr__(self, "bcc", bcc)
        object.__setattr__(self, "attachments", attachments)

    @property
    def all_recipients(self) -> tuple[str, ...]:
        return self.to + self.cc + self.bcc

    @property
    def attachment_bytes(self) -> int:
        return sum(item.size for item in self.attachments)


@dataclass(frozen=True, slots=True)
class SendResult:
    status: SendStatus
    detail: str = ""
    tracking_id: str = ""
    rejected_recipients: tuple[str, ...] = ()

    @property
    def is_success(self) -> bool:
        return self.status in {SendStatus.SUCCESS, SendStatus.PARTIAL_SUCCESS}


@dataclass(frozen=True, slots=True)
class AccountSendResult:
    account_email: str
    result: SendResult


@dataclass(frozen=True, slots=True)
class BatchSendResult:
    results: tuple[AccountSendResult, ...]

    @property
    def success_count(self) -> int:
        return sum(item.result.is_success for item in self.results)

    @property
    def failure_count(self) -> int:
        return len(self.results) - self.success_count


class SendClient(Protocol):
    def send_message(self, draft: OutgoingDraft) -> SendResult: ...

    def close(self) -> None: ...


class AuditSink(Protocol):
    def record(
        self,
        action: str,
        outcome: str,
        detail: str = "",
        account_id: int | None = None,
    ) -> int: ...


SendClientFactory = Callable[[EmailAccount], SendClient]


class SmtpOAuthTokenProvider:
    """Exchange refresh tokens with an SMTP-specific Microsoft scope."""

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
        proxy: str | None = None,
    ) -> None:
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            transport=transport,
            follow_redirects=False,
            proxy=proxy,
        )

    def access_token(self, account: EmailAccount) -> str:
        if not account.refresh_token or not account.client_id:
            raise ValueError("OAuth2 账号缺少 Refresh Token 或 Client ID")
        provider = (
            account.oauth_provider or _oauth_provider_from_email(account.email)
        ).casefold()
        data = {
            "client_id": account.client_id,
            "refresh_token": account.refresh_token,
            "grant_type": "refresh_token",
        }
        if provider == "google":
            url = "https://oauth2.googleapis.com/token"
        elif provider in {"microsoft", "outlook", "office365"}:
            tenant = quote(account.tenant or "common", safe="")
            url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
            data["scope"] = "https://outlook.office.com/SMTP.Send offline_access"
        else:
            raise ValueError("暂不支持该 OAuth2 发件提供商")
        response = self._client.post(url, data=data)
        if response.status_code >= 400:
            raise RuntimeError("OAuth2 发件授权失败，请重新授权 SMTP.Send 权限")
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("OAuth2 服务返回了无效数据") from exc
        access_token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(access_token, str) or not access_token:
            raise RuntimeError("OAuth2 服务未返回有效 Access Token")
        return access_token

    def close(self) -> None:
        self._client.close()


def default_send_client_factory(account: EmailAccount) -> SendClient:
    """Create a sender while preserving refresh-token SMTP authentication."""

    if account.protocol is ProtocolType.GRAPH:
        from mailbox_manager.protocols.outlook_graph import OutlookGraphClient

        return OutlookGraphClient(account)

    from mailbox_manager.protocols.smtp_client import SmtpClient

    access_token = ""
    if account.refresh_token and account.client_id:
        provider = SmtpOAuthTokenProvider()
        try:
            access_token = provider.access_token(account)
        finally:
            provider.close()
    return SmtpClient(account, oauth_access_token=access_token)


class SendService:
    """Send through one or more user-selected accounts and isolate failures."""

    def __init__(
        self,
        *,
        client_factory: SendClientFactory = default_send_client_factory,
        audit_repository: AuditSink | None = None,
    ) -> None:
        self._client_factory = client_factory
        self._audit = audit_repository

    def send_account(self, account: EmailAccount, draft: OutgoingDraft) -> SendResult:
        account_id = account.account_id if account.account_id is not None else "unsaved"
        _LOGGER.info(
            "发件任务开始 account_id=%s protocol=%s recipients=%d attachments=%d "
            "attachment_bytes=%d",
            account_id,
            account.protocol.value,
            len(draft.all_recipients),
            len(draft.attachments),
            draft.attachment_bytes,
        )
        client: SendClient | None = None
        try:
            client = self._client_factory(account)
            result = client.send_message(draft)
        except ValueError as exc:
            result = SendResult(SendStatus.CONFIG_ERROR, str(exc))
        except httpx.TimeoutException:
            result = SendResult(SendStatus.TIMEOUT, "OAuth2 发件授权连接超时")
        except httpx.HTTPError:
            result = SendResult(SendStatus.NETWORK_ERROR, "无法连接 OAuth2 发件授权服务")
        except RuntimeError:
            result = SendResult(SendStatus.AUTH_FAILED, "OAuth2 发件授权失败，请重新授权")
        except Exception:
            result = SendResult(SendStatus.UNKNOWN_ERROR, "发件任务发生未知错误")
        finally:
            if client is not None:
                with suppress(Exception):
                    client.close()
        log_method = _LOGGER.info if result.is_success else _LOGGER.warning
        log_method(
            "发件任务完成 account_id=%s protocol=%s outcome=%s",
            account_id,
            account.protocol.value,
            result.status.value,
        )
        if self._audit is not None:
            with suppress(Exception):
                self._audit.record(
                    "send",
                    result.status.value,
                    (
                        f"{account.email} recipients={len(draft.all_recipients)} "
                        f"attachments={len(draft.attachments)}"
                    ),
                    account.account_id,
                )
        return result

    def send_batch(
        self,
        accounts: Iterable[EmailAccount],
        draft: OutgoingDraft,
        *,
        confirmed: bool,
    ) -> BatchSendResult:
        if not confirmed:
            _LOGGER.warning("批量发件已拒绝 reason=confirmation_required")
            raise ValueError("批量发件必须由用户显式确认")
        selected = tuple(accounts)
        if not selected:
            _LOGGER.warning("批量发件已拒绝 reason=no_accounts")
            raise ValueError("至少选择一个发件账号")
        _LOGGER.info(
            "批量发件开始 accounts=%d recipients=%d attachments=%d attachment_bytes=%d",
            len(selected),
            len(draft.all_recipients),
            len(draft.attachments),
            draft.attachment_bytes,
        )
        batch_result = BatchSendResult(
            tuple(
                AccountSendResult(account.email, self.send_account(account, draft))
                for account in selected
            )
        )
        _LOGGER.info(
            "批量发件完成 accounts=%d success=%d failed=%d",
            len(selected),
            batch_result.success_count,
            batch_result.failure_count,
        )
        return batch_result


def _normalize_recipients(values: Iterable[str]) -> tuple[str, ...]:
    recipients: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise TypeError("收件地址必须是字符串")
        candidate = value.strip()
        if (
            not candidate
            or len(candidate) > 320
            or any(character.isspace() for character in candidate)
        ):
            raise ValueError(f"收件地址格式不正确：{candidate or '(空)'}")
        try:
            address = Address(addr_spec=candidate)
        except (HeaderParseError, ValueError) as exc:
            raise ValueError(f"收件地址格式不正确：{candidate}") from exc
        if not address.username or not address.domain:
            raise ValueError(f"收件地址格式不正确：{candidate}")
        normalized = f"{address.username}@{address.domain.casefold()}"
        key = normalized.casefold()
        if key not in seen:
            seen.add(key)
            recipients.append(normalized)
    return tuple(recipients)


def _oauth_provider_from_email(email: str) -> str:
    domain = email.rsplit("@", 1)[-1].casefold()
    if domain == "gmail.com":
        return "google"
    if domain in {"outlook.com", "hotmail.com", "live.com"}:
        return "microsoft"
    return ""
