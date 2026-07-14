from __future__ import annotations

import socket

from mailbox_manager.domain.models import ProxyConfig, ProxyType


def create_proxy_socket(
    proxy: ProxyConfig,
    destination: tuple[str, int],
    timeout: float | None,
) -> socket.socket:
    try:
        import socks
    except ImportError as exc:
        raise RuntimeError("使用 IMAP/POP3 代理需要安装 PySocks") from exc
    proxy_kind = socks.SOCKS5 if proxy.proxy_type is ProxyType.SOCKS5 else socks.HTTP
    return socks.create_connection(
        destination,
        timeout=timeout,
        proxy_type=proxy_kind,
        proxy_addr=proxy.host,
        proxy_port=proxy.port,
        proxy_username=proxy.username or None,
        proxy_password=proxy.password or None,
    )

