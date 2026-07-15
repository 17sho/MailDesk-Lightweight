from __future__ import annotations

import imaplib
import re
import socket
import ssl
from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace

from mailbox_manager.domain.models import (
    ConnectionResult,
    EmailAccount,
    FetchRequest,
    FetchResult,
    MailFolder,
    PostAction,
    ProxyConfig,
)
from mailbox_manager.domain.status import AccountStatus
from mailbox_manager.mail.parser import parse_email_message
from mailbox_manager.protocols.base import EmailClientBase
from mailbox_manager.protocols.proxy_socket import create_proxy_socket

ConnectionFactory = Callable[..., imaplib.IMAP4]
IMAP_FETCH_BATCH_SIZE = 25
UID_RESPONSE_PATTERN = re.compile(rb"\bUID\s+(\d+)\b", re.IGNORECASE)


class ImapClient(EmailClientBase):
    def __init__(
        self,
        account: EmailAccount,
        *,
        timeout: float = 20.0,
        oauth_access_token: str = "",
        connection_factory: ConnectionFactory | None = None,
        proxy: ProxyConfig | None = None,
    ) -> None:
        self._account = account
        self._timeout = timeout
        self._oauth_access_token = oauth_access_token
        self._factory = connection_factory
        self._connection: imaplib.IMAP4 | None = None
        self._proxy = proxy

    def _connect(self) -> imaplib.IMAP4:
        if self._connection is not None:
            return self._connection
        factory = self._factory
        if factory is None and self._proxy is not None:
            connection = _proxy_imap_connection(
                self._account.host,
                self._account.port,
                self._account.security.value == "ssl",
                self._proxy,
                self._timeout,
            )
            factory = None
        else:
            connection = None
        if factory is None and connection is None:
            factory = (
                imaplib.IMAP4_SSL
                if self._account.security.value == "ssl"
                else imaplib.IMAP4
            )
        if connection is None:
            connection = factory(
                self._account.host, self._account.port, timeout=self._timeout
            )
        if self._account.security.value == "starttls":
            connection.starttls(ssl_context=ssl.create_default_context())
        if self._oauth_access_token:
            auth = (
                f"user={self._account.username}\x01"
                f"auth=Bearer {self._oauth_access_token}\x01\x01"
            )
            connection.authenticate("XOAUTH2", lambda _challenge: auth.encode("utf-8"))
        else:
            connection.login(self._account.username or self._account.email, self._account.secret)
        self._connection = connection
        return connection

    def test_connection(self) -> ConnectionResult:
        try:
            self._connect()
            return ConnectionResult(AccountStatus.SUCCESS, "连接成功")
        except Exception as exc:
            status, detail = _classify_imap_error(exc)
            return ConnectionResult(status, detail)

    def list_folders(self) -> list[MailFolder]:
        try:
            status, rows = self._connect().list()
            if status != "OK":
                return []
            folders: list[MailFolder] = []
            for row in rows or []:
                decoded = (
                    row.decode("utf-8", errors="replace")
                    if isinstance(row, bytes)
                    else str(row)
                )
                folders.append(_parse_folder(decoded))
            return folders
        except Exception:
            return []

    def fetch_messages(self, request: FetchRequest) -> FetchResult:
        messages = []
        try:
            connection = self._connect()
            remaining: int | None = None if request.unlimited else request.max_messages
            folders = list(request.folders)
            if request.include_special_folders:
                existing = {folder.casefold() for folder in folders}
                for candidate in self.list_folders():
                    if _is_special_folder(candidate) and candidate.name.casefold() not in existing:
                        folders.append(candidate.name)
                        existing.add(candidate.name.casefold())
            for folder in folders:
                if remaining is not None and remaining <= 0:
                    break
                status, _ = connection.select(
                    folder, readonly=request.post_action is PostAction.NONE
                )
                if status != "OK":
                    continue
                status, search_data = connection.uid("search", None, "ALL")
                if status != "OK" or not search_data:
                    continue
                identifiers = search_data[0].split()
                if remaining is not None:
                    identifiers = identifiers[-remaining:]
                newest_first = list(reversed(identifiers))
                for offset in range(0, len(newest_first), IMAP_FETCH_BATCH_SIZE):
                    batch = newest_first[offset : offset + IMAP_FETCH_BATCH_SIZE]
                    for identifier, raw in _fetch_uid_messages(connection, batch):
                        message = parse_email_message(
                            raw,
                            folder=folder,
                            keywords=request.keywords,
                            custom_pattern=request.custom_pattern,
                        )
                        message = replace(
                            message,
                            transport_id=_uid_text(identifier),
                        )
                        if not request.include_raw:
                            message = replace(message, raw_eml=b"")
                        messages.append(message)
                        if (
                            message.matched_values
                            and request.post_action is not PostAction.NONE
                        ):
                            _apply_post_action(connection, identifier, request)
                        if remaining is not None:
                            remaining -= 1
                            if remaining <= 0:
                                break
                    if remaining is not None and remaining <= 0:
                        break
            return FetchResult(AccountStatus.SUCCESS, tuple(messages), "收取完成")
        except Exception as exc:
            status, detail = _classify_imap_error(exc)
            return FetchResult(status, tuple(messages), detail)

    def close(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            with suppress(imaplib.IMAP4.error, OSError):
                connection.logout()

    def apply_action(
        self,
        message,
        action: PostAction,
        target_folder: str = "",
        *,
        confirmed: bool = False,
    ) -> bool:
        if not confirmed or not message.transport_id or action is PostAction.NONE:
            return False
        connection = self._connect()
        status, _ = connection.select(message.folder, readonly=False)
        if status != "OK":
            return False
        request = FetchRequest(
            post_action=action,
            action_target_folder=target_folder,
            confirmed_actions=True,
        )
        _apply_post_action(connection, message.transport_id.encode("ascii"), request)
        return True


def _raw_from_fetch(fetch_data: object) -> bytes:
    if not isinstance(fetch_data, list):
        return b""
    for item in fetch_data:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
            return item[1]
    return b""


def _fetch_uid_messages(
    connection: imaplib.IMAP4, identifiers: list[bytes]
) -> list[tuple[bytes, bytes]]:
    """Fetch a small UID batch, falling back only for missing server responses."""

    if not identifiers:
        return []
    normalized = [_uid_bytes(identifier) for identifier in identifiers]
    sequence_set = b",".join(normalized)
    status, fetch_data = connection.uid("fetch", sequence_set, "(UID RFC822)")
    mapped = _raw_messages_by_uid(fetch_data) if status == "OK" else {}
    if len(normalized) == 1 and normalized[0] not in mapped:
        raw = _raw_from_fetch(fetch_data)
        if raw:
            mapped[normalized[0]] = raw

    for identifier in normalized:
        if identifier in mapped:
            continue
        status, individual_data = connection.uid(
            "fetch", identifier, "(UID RFC822)"
        )
        if status != "OK":
            continue
        individual = _raw_messages_by_uid(individual_data)
        raw = individual.get(identifier) or _raw_from_fetch(individual_data)
        if raw:
            mapped[identifier] = raw
    return [
        (identifier, mapped[identifier])
        for identifier in normalized
        if identifier in mapped
    ]


def _raw_messages_by_uid(fetch_data: object) -> dict[bytes, bytes]:
    messages: dict[bytes, bytes] = {}
    if not isinstance(fetch_data, list):
        return messages
    for item in fetch_data:
        if not (
            isinstance(item, tuple)
            and len(item) >= 2
            and isinstance(item[0], bytes)
            and isinstance(item[1], bytes)
        ):
            continue
        match = UID_RESPONSE_PATTERN.search(item[0])
        if match is not None:
            messages[match.group(1)] = item[1]
    return messages


def _uid_bytes(identifier: bytes | str) -> bytes:
    return (
        identifier.strip()
        if isinstance(identifier, bytes)
        else str(identifier).strip().encode("ascii", errors="ignore")
    )


def _uid_text(identifier: bytes | str) -> str:
    return (
        identifier.decode("ascii", errors="ignore")
        if isinstance(identifier, bytes)
        else str(identifier)
    )


FOLDER_PATTERN = re.compile(r"^\((?P<flags>[^)]*)\)\s+\S+\s+(?P<name>.+)$")


def _parse_folder(value: str) -> MailFolder:
    match = FOLDER_PATTERN.match(value.strip())
    if not match:
        name = value.rsplit(" ", 1)[-1].strip('"')
        return MailFolder(name=name, display_name=name)
    name = match.group("name").strip().strip('"')
    flags = tuple(flag for flag in match.group("flags").split() if flag)
    return MailFolder(name=name, display_name=name, flags=flags)


def _is_special_folder(folder: MailFolder) -> bool:
    special_flags = {"\\junk", "\\spam", "\\trash"}
    if any(flag.casefold() in special_flags for flag in folder.flags):
        return True
    normalized = folder.display_name.casefold()
    return any(token in normalized for token in ("junk", "spam", "trash", "垃圾", "废件"))


def _apply_post_action(
    connection: imaplib.IMAP4, identifier: bytes, request: FetchRequest
) -> None:
    if not request.confirmed_actions:
        return
    if request.post_action is PostAction.MARK_READ:
        connection.uid("store", identifier, "+FLAGS", "(\\Seen)")
    elif request.post_action is PostAction.MOVE:
        status, _ = connection.uid("copy", identifier, request.action_target_folder)
        if status == "OK":
            connection.uid("store", identifier, "+FLAGS", "(\\Deleted)")
            connection.expunge()
    elif request.post_action is PostAction.DELETE:
        connection.uid("store", identifier, "+FLAGS", "(\\Deleted)")
        connection.expunge()


def _classify_imap_error(exc: Exception) -> tuple[AccountStatus, str]:
    if isinstance(exc, imaplib.IMAP4.error):
        return AccountStatus.AUTH_FAILED, "邮箱鉴权失败，请检查授权码或应用专用密码"
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return AccountStatus.TIMEOUT, "连接邮箱服务器超时"
    if isinstance(exc, ssl.SSLError):
        return AccountStatus.NETWORK_ERROR, "TLS 连接失败，请检查服务器与加密模式"
    if isinstance(exc, OSError):
        return AccountStatus.NETWORK_ERROR, "无法连接邮箱服务器"
    return AccountStatus.UNKNOWN_ERROR, "收件时发生未知错误"


def _proxy_imap_connection(
    host: str,
    port: int,
    use_ssl: bool,
    proxy: ProxyConfig,
    timeout: float,
) -> imaplib.IMAP4:
    class ProxyImap(imaplib.IMAP4):
        def _create_socket(self, socket_timeout):
            return create_proxy_socket(proxy, (self.host, self.port), socket_timeout)

    class ProxyImapSsl(imaplib.IMAP4_SSL):
        def _create_socket(self, socket_timeout):
            raw = create_proxy_socket(proxy, (self.host, self.port), socket_timeout)
            return self.ssl_context.wrap_socket(raw, server_hostname=self.host)

    implementation = ProxyImapSsl if use_ssl else ProxyImap
    return implementation(host, port, timeout=timeout)
