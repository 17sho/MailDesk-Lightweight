from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx

from mailbox_manager.domain.models import WebhookConfig

Resolver = Callable[..., list[tuple[object, ...]]]
MAX_WEBHOOK_PAYLOAD = 64 * 1024


def validate_webhook_url(
    raw_url: str,
    allowed_hosts: set[str],
    *,
    resolver: Resolver = socket.getaddrinfo,
) -> str:
    if len(raw_url) > 2048:
        raise ValueError("Webhook URL 过长")
    url = urlsplit(raw_url)
    if url.scheme != "https":
        raise ValueError("Webhook 仅允许 HTTPS")
    if not url.hostname or url.username or url.password or url.fragment:
        raise ValueError("Webhook URL 格式不正确")
    hostname = url.hostname.casefold().rstrip(".")
    normalized_allowed = {host.casefold().rstrip(".") for host in allowed_hosts}
    if hostname not in normalized_allowed:
        raise ValueError("Webhook 主机不在允许列表")
    try:
        addresses = resolver(hostname, url.port or 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("Webhook 主机无法解析") from exc
    resolved: set[str] = set()
    for address in addresses:
        socket_address = address[4]
        if isinstance(socket_address, tuple) and socket_address:
            resolved.add(str(socket_address[0]))
    if not resolved:
        raise ValueError("Webhook 主机没有可用地址")
    for address in resolved:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise ValueError("Webhook 主机返回无效地址") from exc
        if not ip.is_global:
            raise ValueError("Webhook 禁止访问私网、回环或保留地址")
    return raw_url


class WebhookService:
    def __init__(
        self,
        *,
        allowed_hosts: set[str],
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver = socket.getaddrinfo,
    ) -> None:
        self._allowed_hosts = allowed_hosts
        self._resolver = resolver
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout), transport=transport, follow_redirects=False
        )

    def send(self, webhook: WebhookConfig, payload: dict[str, object]) -> None:
        if not webhook.enabled:
            return
        url = validate_webhook_url(
            webhook.url, self._allowed_hosts, resolver=self._resolver
        )
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > MAX_WEBHOOK_PAYLOAD:
            raise ValueError("Webhook 数据不能超过 64 KiB")
        headers = {"Content-Type": "application/json", "User-Agent": "MailDesk/0.2"}
        if webhook.secret:
            digest = hmac.new(
                webhook.secret.encode("utf-8"), body, hashlib.sha256
            ).hexdigest()
            headers["X-MailDesk-Signature"] = f"sha256={digest}"
        response = self._client.post(url, content=body, headers=headers)
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"Webhook 推送失败，HTTP {response.status_code}")

    def close(self) -> None:
        self._client.close()

