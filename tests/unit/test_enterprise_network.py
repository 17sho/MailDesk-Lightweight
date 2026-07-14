from __future__ import annotations

import socket

import httpx
import pytest

from mailbox_manager.domain.models import ProxyType, SecurityMode, WebhookConfig
from mailbox_manager.protocols.proxy_socket import create_proxy_socket
from mailbox_manager.services.discovery_service import DiscoveryService, discovery_candidates
from mailbox_manager.services.proxy_service import parse_proxy_line, proxy_url
from mailbox_manager.services.webhook_service import WebhookService, validate_webhook_url


def test_proxy_parser_supports_requested_colon_format_and_escaped_url() -> None:
    proxy = parse_proxy_line("127.0.0.1:1080:user@example.com:p@ss", ProxyType.SOCKS5)

    assert proxy.host == "127.0.0.1"
    assert proxy.port == 1080
    assert proxy.username == "user@example.com"
    assert proxy.password == "p@ss"
    assert proxy_url(proxy) == "socks5://user%40example.com:p%40ss@127.0.0.1:1080"


def test_proxy_socket_passes_fixed_binding_to_pysocks(monkeypatch) -> None:
    import socks

    proxy = parse_proxy_line("127.0.0.1:1080:user:pass", ProxyType.SOCKS5)
    captured: dict[str, object] = {}
    sentinel = object()

    def fake_create_connection(destination, **kwargs):
        captured["destination"] = destination
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(socks, "create_connection", fake_create_connection)

    result = create_proxy_socket(proxy, ("imap.example.com", 993), 10)

    assert result is sentinel
    assert captured["destination"] == ("imap.example.com", 993)
    assert captured["proxy_addr"] == "127.0.0.1"
    assert captured["proxy_username"] == "user"


def test_discovery_candidates_are_bounded_and_prioritize_tls() -> None:
    candidates = discovery_candidates("owner@example.org")

    assert candidates[0] == ("imap.example.org", 993, SecurityMode.SSL)
    assert ("mail.example.org", 143, SecurityMode.STARTTLS) in candidates
    assert len(candidates) <= 4


def test_discovery_service_stops_after_first_explicit_success() -> None:
    attempts: list[tuple[str, int]] = []

    def probe(host, port, _security, _email, _secret):
        attempts.append((host, port))
        return host == "mail.example.org" and port == 993

    result = DiscoveryService(probe=probe).discover("owner@example.org", "app-password")

    assert result == ("mail.example.org", 993, SecurityMode.SSL)
    assert attempts[-1] == ("mail.example.org", 993)


def test_webhook_validation_rejects_http_private_ip_and_unknown_host() -> None:
    def public_resolver(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]

    def private_resolver(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]

    with pytest.raises(ValueError, match="HTTPS"):
        validate_webhook_url(
            "http://hooks.example.com/mail", {"hooks.example.com"}, resolver=public_resolver
        )
    with pytest.raises(ValueError, match="私网"):
        validate_webhook_url(
            "https://hooks.example.com/mail", {"hooks.example.com"}, resolver=private_resolver
        )
    with pytest.raises(ValueError, match="允许列表"):
        validate_webhook_url(
            "https://evil.example/mail", {"hooks.example.com"}, resolver=public_resolver
        )


def test_webhook_service_posts_signed_bounded_payload_without_redirects() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(204)

    def resolver(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
    service = WebhookService(
        allowed_hosts={"hooks.example.com"},
        transport=httpx.MockTransport(handler),
        resolver=resolver,
    )

    service.send(
        WebhookConfig(
            name="业务回调", url="https://hooks.example.com/mail", secret="signing-secret"
        ),
        {"account": "owner@example.com", "code": "123456"},
    )

    request = captured["request"]
    assert request.headers["X-MailDesk-Signature"].startswith("sha256=")  # type: ignore[attr-defined]
    assert request.content.count(b"123456") == 1  # type: ignore[attr-defined]
