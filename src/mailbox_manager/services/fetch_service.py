from __future__ import annotations

from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import replace
from typing import Protocol, runtime_checkable

from mailbox_manager.domain.models import (
    EmailAccount,
    FetchRequest,
    FetchResult,
    MailMessage,
    ProtocolType,
)
from mailbox_manager.domain.status import AccountStatus
from mailbox_manager.protocols.imap_client import ImapClient
from mailbox_manager.protocols.oauth import OAuthTokenProvider
from mailbox_manager.protocols.outlook_graph import OutlookGraphClient
from mailbox_manager.protocols.pop3_client import Pop3Client
from mailbox_manager.services.automation_service import AutomationService
from mailbox_manager.services.client_factory import ProxyRoute, ProxyRouteError
from mailbox_manager.services.eml_store import EmlStore
from mailbox_manager.services.throttle import ComplianceThrottle
from mailbox_manager.storage.enterprise_repositories import AuditRepository
from mailbox_manager.storage.repositories import AccountRepository, MessageRepository


class FetchClient(Protocol):
    def fetch_messages(self, request: FetchRequest) -> FetchResult: ...

    def fetch_message(self, message: MailMessage, request: FetchRequest) -> MailMessage: ...

    def close(self) -> None: ...


ClientFactory = Callable[[EmailAccount], FetchClient]


@runtime_checkable
class RouteAwareClientFactory(Protocol):
    """Factory contract for resolving a network route before throttling."""

    def resolve_route(self, account: EmailAccount) -> ProxyRoute: ...

    def create_for_route(
        self, account: EmailAccount, route: ProxyRoute
    ) -> FetchClient: ...


def default_client_factory(account: EmailAccount) -> FetchClient:
    if account.protocol is ProtocolType.GRAPH:
        return OutlookGraphClient(account)
    if account.protocol is ProtocolType.POP3:
        return Pop3Client(account)
    if account.refresh_token and account.client_id:
        provider = OAuthTokenProvider()
        try:
            token = provider.access_token(account)
        finally:
            provider.close()
        return ImapClient(account, oauth_access_token=token)
    return ImapClient(account)


class FetchService:
    """Run one bounded account fetch and persist its observable result."""

    def __init__(
        self,
        accounts: AccountRepository,
        messages: MessageRepository,
        *,
        client_factory: ClientFactory = default_client_factory,
        eml_store: EmlStore | None = None,
        audit_repository: AuditRepository | None = None,
        throttle: ComplianceThrottle | None = None,
        automation: AutomationService | None = None,
    ) -> None:
        self._accounts = accounts
        self._messages = messages
        self._client_factory = client_factory
        self._eml_store = eml_store
        self._audit = audit_repository
        self._throttle = throttle
        self._automation = automation

    def set_throttle(self, throttle: ComplianceThrottle | None) -> None:
        self._throttle = throttle

    def fetch_account(self, account: EmailAccount, request: FetchRequest) -> FetchResult:
        if account.account_id is None:
            raise ValueError("账号必须先保存后才能收件")
        account_key = str(account.account_id)
        client = None
        try:
            route_factory = (
                self._client_factory
                if isinstance(self._client_factory, RouteAwareClientFactory)
                else None
            )
            route = route_factory.resolve_route(account) if route_factory else None
            identity = (
                route.identity
                if route is not None
                else f"proxy:{account.proxy_id}" if account.proxy_id else "direct"
            )
            guard = (
                self._throttle.slot(identity, account_key)
                if self._throttle is not None
                else nullcontext()
            )
            with guard:
                if route_factory is not None and route is not None:
                    client = route_factory.create_for_route(account, route)
                else:
                    client = self._client_factory(account)
                known_lookup = getattr(self._messages, "known_transport_ids", None)
                known_transport_ids = (
                    known_lookup(account.account_id)
                    if callable(known_lookup)
                    else frozenset()
                )
                incremental_request = replace(
                    request,
                    known_transport_ids=known_transport_ids,
                )
                result = client.fetch_messages(incremental_request)
            if result.messages and self._eml_store is not None:
                stored_messages = tuple(
                    replace(
                        message,
                        eml_path=self._eml_store.save(account.account_id, message),
                    )
                    for message in result.messages
                    if message.body_loaded and message.raw_eml
                )
                stored_by_key = {
                    (message.folder, message.transport_id): message
                    for message in stored_messages
                }
                result = replace(
                    result,
                    messages=tuple(
                        stored_by_key.get((message.folder, message.transport_id), message)
                        for message in result.messages
                    ),
                )
            if self._automation is not None and result.messages and client is not None:
                for message in result.messages:
                    if message.body_loaded:
                        self._automation.process(account, message, client)
            if result.messages:
                self._messages.add_many(account.account_id, result.messages)
            self._accounts.update_status(account.account_id, result.status, result.detail)
            if self._audit is not None:
                self._audit.record(
                    "fetch",
                    result.status.value,
                    f"{account.email} messages={len(result.messages)} detail={result.detail}",
                    account.account_id,
                )
            return result
        except ProxyRouteError as exc:
            detail = str(exc)
            self._accounts.update_status(
                account.account_id, AccountStatus.NETWORK_ERROR, detail
            )
            if self._audit is not None:
                self._audit.record(
                    "fetch", "proxy_unavailable", detail, account.account_id
                )
            return FetchResult(AccountStatus.NETWORK_ERROR, detail=detail)
        except Exception as exc:
            detail = "收件任务异常，请检查账号配置或网络连接"
            self._accounts.update_status(account.account_id, AccountStatus.UNKNOWN_ERROR, detail)
            if self._audit is not None:
                self._audit.record(
                    "fetch", "exception", f"{account.email} {exc}", account.account_id
                )
            return FetchResult(AccountStatus.UNKNOWN_ERROR, detail=detail)
        finally:
            if client is not None:
                client.close()

    def load_message(
        self,
        account: EmailAccount,
        message: MailMessage,
        request: FetchRequest,
    ) -> MailMessage:
        """Load and persist one complete message selected from the header list."""

        if message.body_loaded:
            return message
        if account.account_id is None or message.message_id is None:
            raise ValueError("邮件必须先同步到本地列表后才能加载正文")
        client = None
        try:
            route_factory = (
                self._client_factory
                if isinstance(self._client_factory, RouteAwareClientFactory)
                else None
            )
            route = route_factory.resolve_route(account) if route_factory else None
            identity = (
                route.identity
                if route is not None
                else f"proxy:{account.proxy_id}" if account.proxy_id else "direct"
            )
            guard = (
                self._throttle.slot(identity, str(account.account_id))
                if self._throttle is not None
                else nullcontext()
            )
            with guard:
                if route_factory is not None and route is not None:
                    client = route_factory.create_for_route(account, route)
                else:
                    client = self._client_factory(account)
                loaded = client.fetch_message(message, request)
            if not loaded.body_loaded:
                raise RuntimeError("服务器未返回完整邮件正文")
            loaded = replace(
                loaded,
                provider_message_id=message.provider_message_id,
                transport_id=message.transport_id,
                folder=message.folder,
                message_id=message.message_id,
                account_id=account.account_id,
                body_loaded=True,
            )
            if self._eml_store is not None and loaded.raw_eml:
                loaded = replace(
                    loaded,
                    eml_path=self._eml_store.save(account.account_id, loaded),
                )
            if self._automation is not None and client is not None:
                self._automation.process(account, loaded, client)
            self._messages.add_many(account.account_id, (loaded,))
            persisted = self._messages.get(message.message_id)
            if self._audit is not None:
                self._audit.record(
                    "load_message",
                    "success",
                    f"{account.email} folder={message.folder}",
                    account.account_id,
                )
            return persisted or loaded
        except ProxyRouteError as exc:
            raise RuntimeError(str(exc)) from exc
        finally:
            if client is not None:
                client.close()
