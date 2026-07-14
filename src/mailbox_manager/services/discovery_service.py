from __future__ import annotations

import imaplib
import ssl
from collections.abc import Callable
from contextlib import suppress

from mailbox_manager.domain.models import SecurityMode

DiscoveryCandidate = tuple[str, int, SecurityMode]
Probe = Callable[[str, int, SecurityMode, str, str], bool]


def discovery_candidates(email: str) -> tuple[DiscoveryCandidate, ...]:
    if "@" not in email:
        raise ValueError("邮箱地址格式不正确")
    domain = email.rsplit("@", 1)[1].strip().casefold()
    if not domain or "." not in domain:
        raise ValueError("邮箱域名格式不正确")
    return (
        (f"imap.{domain}", 993, SecurityMode.SSL),
        (f"imap.{domain}", 143, SecurityMode.STARTTLS),
        (f"mail.{domain}", 993, SecurityMode.SSL),
        (f"mail.{domain}", 143, SecurityMode.STARTTLS),
    )


def _imap_probe(
    host: str,
    port: int,
    security: SecurityMode,
    email: str,
    secret: str,
    timeout: float = 8.0,
) -> bool:
    connection: imaplib.IMAP4 | None = None
    try:
        if security is SecurityMode.SSL:
            connection = imaplib.IMAP4_SSL(host, port, timeout=timeout)
        else:
            connection = imaplib.IMAP4(host, port, timeout=timeout)
            connection.starttls(ssl_context=ssl.create_default_context())
        status, _ = connection.login(email, secret)
        return status == "OK"
    except (imaplib.IMAP4.error, OSError, ssl.SSLError):
        return False
    finally:
        if connection is not None:
            with suppress(imaplib.IMAP4.error, OSError):
                connection.logout()


class DiscoveryService:
    """Explicit, bounded IMAP discovery for an account the user authorized."""

    def __init__(self, probe: Probe = _imap_probe) -> None:
        self._probe = probe

    def discover(self, email: str, secret: str) -> DiscoveryCandidate | None:
        if not secret:
            raise ValueError("自动发现需要用户提供授权码或应用专用密码")
        for host, port, security in discovery_candidates(email):
            if self._probe(host, port, security, email, secret):
                return host, port, security
        return None

