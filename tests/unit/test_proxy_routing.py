from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace

import pytest

from mailbox_manager.domain.models import (
    AccountStatus,
    EmailAccount,
    FetchRequest,
    FetchResult,
    ProtocolType,
    ProxyConfig,
    ProxyType,
)
from mailbox_manager.services import client_factory
from mailbox_manager.services.client_factory import ProtocolClientFactory, ProxyRouteError
from mailbox_manager.services.fetch_service import FetchService
from mailbox_manager.services.proxy_service import proxy_url


class _ProxyRepositoryStub:
    def __init__(self, proxies: list[ProxyConfig]) -> None:
        self.proxies = proxies

    def get(self, proxy_id: int) -> ProxyConfig | None:
        return next((item for item in self.proxies if item.proxy_id == proxy_id), None)

    def list_all(self) -> list[ProxyConfig]:
        return list(self.proxies)


class _SettingsStub:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def get(self, _key: str, _default=None):
        return {"proxy_fetch_enabled": self.enabled}


class _FetchClientStub:
    def __init__(self) -> None:
        self.closed = False

    def fetch_messages(self, _request: FetchRequest) -> FetchResult:
        return FetchResult(AccountStatus.SUCCESS)

    def close(self) -> None:
        self.closed = True


class _AccountRepositoryStub:
    def __init__(self) -> None:
        self.statuses: list[tuple[int, AccountStatus, str]] = []

    def update_status(
        self, account_id: int, status: AccountStatus, detail: str
    ) -> None:
        self.statuses.append((account_id, status, detail))


class _MessageRepositoryStub:
    def add_many(self, _account_id: int, _messages) -> None:
        raise AssertionError("the test client should not return messages")


class _RecordingThrottle:
    def __init__(self) -> None:
        self.identities: list[str] = []
        self.account_keys: list[str] = []

    def slot(self, identity: str, account_key: str):
        self.identities.append(identity)
        self.account_keys.append(account_key)
        return nullcontext()


def _account(*, proxy_id: int | None = None) -> EmailAccount:
    return EmailAccount(
        email="owner@example.com",
        provider="custom",
        protocol=ProtocolType.IMAP,
        host="imap.example.com",
        port=993,
        secret="app-password",
        proxy_id=proxy_id,
    )


def _proxy(proxy_id: int, *, enabled: bool = True) -> ProxyConfig:
    return ProxyConfig(
        proxy_id=proxy_id,
        proxy_type=ProxyType.SOCKS5,
        host=f"proxy-{proxy_id}.example.com",
        port=1080 + proxy_id,
        enabled=enabled,
    )


def _capture_imap_proxy(monkeypatch, repository, settings):
    monkeypatch.setattr(
        client_factory,
        "ImapClient",
        lambda _account, *, oauth_access_token, proxy: proxy,
    )
    return ProtocolClientFactory(repository, settings)


def test_proxy_routing_uses_direct_network_when_global_pool_is_off(
    monkeypatch,
) -> None:
    repository = _ProxyRepositoryStub([_proxy(1)])
    settings = _SettingsStub(False)
    factory = _capture_imap_proxy(monkeypatch, repository, settings)

    assert factory(_account()) is None


def test_proxy_routing_rotates_enabled_global_pool(monkeypatch) -> None:
    first = _proxy(1)
    second = _proxy(2)
    disabled = _proxy(3, enabled=False)
    repository = _ProxyRepositoryStub([first, disabled, second])
    factory = _capture_imap_proxy(monkeypatch, repository, _SettingsStub(True))

    assert [factory(_account()) for _ in range(3)] == [first, second, first]


def test_fixed_account_proxy_overrides_global_switch(monkeypatch) -> None:
    first = _proxy(1)
    fixed = _proxy(2)
    repository = _ProxyRepositoryStub([first, fixed])
    factory = _capture_imap_proxy(monkeypatch, repository, _SettingsStub(False))

    assert factory(_account(proxy_id=2)) is fixed


@pytest.mark.parametrize(
    ("proxies", "message"),
    [
        ([], "不存在"),
        ([_proxy(9, enabled=False)], "已停用"),
    ],
)
def test_fixed_proxy_never_silently_falls_back_to_local_network(
    monkeypatch,
    proxies: list[ProxyConfig],
    message: str,
) -> None:
    repository = _ProxyRepositoryStub(proxies)
    factory = _capture_imap_proxy(monkeypatch, repository, _SettingsStub(True))

    with pytest.raises(ProxyRouteError, match=message):
        factory(_account(proxy_id=9))


def test_fetch_throttle_uses_resolved_proxy_and_reuses_route_for_client(
    monkeypatch,
) -> None:
    first = _proxy(1)
    second = _proxy(2)
    repository = _ProxyRepositoryStub([first, second])
    factory = ProtocolClientFactory(repository, _SettingsStub(True))
    selected_proxies: list[ProxyConfig | None] = []

    def make_client(_account, *, oauth_access_token, proxy):
        assert oauth_access_token == ""
        selected_proxies.append(proxy)
        return _FetchClientStub()

    monkeypatch.setattr(client_factory, "ImapClient", make_client)
    throttle = _RecordingThrottle()
    accounts = _AccountRepositoryStub()
    service = FetchService(
        accounts,  # type: ignore[arg-type]
        _MessageRepositoryStub(),  # type: ignore[arg-type]
        client_factory=factory,
        throttle=throttle,  # type: ignore[arg-type]
    )

    for account_id in (1, 2, 3):
        result = service.fetch_account(
            replace(_account(), account_id=account_id), FetchRequest()
        )
        assert result.status is AccountStatus.SUCCESS

    first_identity = f"proxy:{first.identity}"
    second_identity = f"proxy:{second.identity}"
    assert throttle.identities == [first_identity, second_identity, first_identity]
    assert throttle.identities[0] != throttle.identities[1]
    assert throttle.identities[0] == throttle.identities[2]
    assert selected_proxies == [first, second, first]
    assert throttle.account_keys == ["1", "2", "3"]


def test_fetch_service_keeps_plain_callable_factory_compatibility() -> None:
    throttle = _RecordingThrottle()
    client = _FetchClientStub()
    service = FetchService(
        _AccountRepositoryStub(),  # type: ignore[arg-type]
        _MessageRepositoryStub(),  # type: ignore[arg-type]
        client_factory=lambda _account: client,
        throttle=throttle,  # type: ignore[arg-type]
    )

    result = service.fetch_account(
        replace(_account(proxy_id=9), account_id=4), FetchRequest()
    )

    assert result.status is AccountStatus.SUCCESS
    assert throttle.identities == ["proxy:9"]
    assert client.closed is True


def test_graph_client_receives_resolved_global_proxy(monkeypatch) -> None:
    proxy = _proxy(1)
    observed: list[str | None] = []
    sentinel = object()
    monkeypatch.setattr(
        client_factory,
        "OutlookGraphClient",
        lambda _account, *, proxy: observed.append(proxy) or sentinel,
    )
    factory = ProtocolClientFactory(
        _ProxyRepositoryStub([proxy]), _SettingsStub(True)
    )

    result = factory(replace(_account(), protocol=ProtocolType.GRAPH))

    assert result is sentinel
    assert observed == [proxy_url(proxy)]


def test_oauth_token_and_imap_client_share_resolved_global_proxy(monkeypatch) -> None:
    proxy = _proxy(1)
    http_proxies: list[str | None] = []
    imap_routes: list[tuple[str, ProxyConfig | None]] = []
    sentinel = object()

    class TokenProviderStub:
        def __init__(self, *, proxy: str | None = None) -> None:
            http_proxies.append(proxy)

        def access_token(self, _account: EmailAccount) -> str:
            return "access-token"

        def close(self) -> None:
            pass

    def make_imap(_account, *, oauth_access_token, proxy):
        imap_routes.append((oauth_access_token, proxy))
        return sentinel

    monkeypatch.setattr(client_factory, "OAuthTokenProvider", TokenProviderStub)
    monkeypatch.setattr(client_factory, "ImapClient", make_imap)
    factory = ProtocolClientFactory(
        _ProxyRepositoryStub([proxy]), _SettingsStub(True)
    )
    account = replace(
        _account(), refresh_token="refresh-token", client_id="client-id"
    )

    result = factory(account)

    assert result is sentinel
    assert http_proxies == [proxy_url(proxy)]
    assert imap_routes == [("access-token", proxy)]
