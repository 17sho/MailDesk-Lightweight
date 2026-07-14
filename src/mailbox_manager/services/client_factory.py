from __future__ import annotations

import threading
from dataclasses import dataclass

from mailbox_manager.domain.models import EmailAccount, ProtocolType, ProxyConfig
from mailbox_manager.protocols.imap_client import ImapClient
from mailbox_manager.protocols.oauth import OAuthTokenProvider
from mailbox_manager.protocols.outlook_graph import OutlookGraphClient
from mailbox_manager.protocols.pop3_client import Pop3Client
from mailbox_manager.services.proxy_service import proxy_url
from mailbox_manager.storage.enterprise_repositories import ProxyRepository, SettingsRepository


class ProxyRouteError(ConnectionError):
    """A fixed proxy route cannot be honored without leaking to direct access."""


@dataclass(frozen=True, slots=True)
class ProxyRoute:
    """A proxy decision that can be shared by throttling and client creation."""

    proxy: ProxyConfig | None

    @property
    def identity(self) -> str:
        if self.proxy is None:
            return "direct"
        return f"proxy:{self.proxy.identity}"


class ProtocolClientFactory:
    """Create protocol clients with an account's optional fixed proxy binding."""

    def __init__(
        self,
        proxies: ProxyRepository,
        settings: SettingsRepository | None = None,
    ) -> None:
        self._proxies = proxies
        self._settings = settings
        self._proxy_index = 0
        self._proxy_lock = threading.Lock()

    def __call__(self, account: EmailAccount):
        return self.create_for_route(account, self.resolve_route(account))

    def resolve_route(self, account: EmailAccount) -> ProxyRoute:
        """Choose the account's route exactly once before any throttle wait."""

        return ProxyRoute(self._proxy_for(account))

    def create_for_route(self, account: EmailAccount, route: ProxyRoute):
        """Create a protocol client without rotating or resolving the route again."""

        proxy = route.proxy
        http_proxy = proxy_url(proxy) if proxy is not None else None
        if account.protocol is ProtocolType.GRAPH:
            return OutlookGraphClient(account, proxy=http_proxy)
        if account.protocol is ProtocolType.POP3:
            return Pop3Client(account, proxy=proxy)
        token = ""
        if account.refresh_token and account.client_id:
            provider = OAuthTokenProvider(proxy=http_proxy)
            try:
                token = provider.access_token(account)
            finally:
                provider.close()
        return ImapClient(
            account,
            oauth_access_token=token,
            proxy=proxy,
        )

    def _proxy_for(self, account: EmailAccount):
        if account.proxy_id is not None:
            proxy = self._proxies.get(account.proxy_id)
            if proxy is None:
                raise ProxyRouteError("账号绑定的固定代理不存在，请重新绑定或切换为直连")
            if not proxy.enabled:
                raise ProxyRouteError("账号绑定的固定代理已停用，请启用代理或切换为直连")
            return proxy
        if not self._global_proxy_enabled():
            return None
        enabled = [proxy for proxy in self._proxies.list_all() if proxy.enabled]
        if not enabled:
            return None
        with self._proxy_lock:
            proxy = enabled[self._proxy_index % len(enabled)]
            self._proxy_index += 1
        return proxy

    def _global_proxy_enabled(self) -> bool:
        if self._settings is None:
            return False
        values = self._settings.get("enterprise_ui", {})
        return bool(
            isinstance(values, dict) and values.get("proxy_fetch_enabled", False)
        )
