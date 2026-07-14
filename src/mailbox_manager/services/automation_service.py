from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from mailbox_manager.domain.models import (
    EmailAccount,
    MailMessage,
    PostAction,
    WebhookConfig,
)
from mailbox_manager.mail.parser import extract_matches
from mailbox_manager.protocols.oauth import OAuthTokenProvider
from mailbox_manager.protocols.smtp_client import SmtpClient
from mailbox_manager.services.webhook_service import WebhookService
from mailbox_manager.storage.enterprise_repositories import (
    AuditRepository,
    AutomationRuleRepository,
    SettingsRepository,
    WebhookRepository,
)


class ActionClient(Protocol):
    def apply_action(
        self,
        message: MailMessage,
        action: PostAction,
        target_folder: str = "",
        *,
        confirmed: bool = False,
    ) -> bool: ...


WebhookSender = Callable[[WebhookConfig, dict[str, object], set[str]], None]
ForwardSender = Callable[[EmailAccount, MailMessage, str], None]


def _send_webhook(
    webhook: WebhookConfig, payload: dict[str, object], allowed_hosts: set[str]
) -> None:
    service = WebhookService(allowed_hosts=allowed_hosts)
    try:
        service.send(webhook, payload)
    finally:
        service.close()


def _forward_message(account: EmailAccount, message: MailMessage, target: str) -> None:
    raw = message.raw_eml
    if not raw and message.eml_path:
        path = Path(message.eml_path)
        if path.is_file() and path.stat().st_size <= 25 * 1024 * 1024:
            raw = path.read_bytes()
    if not raw:
        raise ValueError("匹配邮件没有可转发的 EML 原件")
    token = ""
    provider = None
    client = None
    try:
        if account.refresh_token and account.client_id:
            provider = OAuthTokenProvider()
            token = provider.access_token(account)
        client = SmtpClient(account, oauth_access_token=token)
        client.forward_message(raw, target, confirmed_forwarding=True)
    finally:
        if client is not None:
            client.close()
        if provider is not None:
            provider.close()


class AutomationService:
    def __init__(
        self,
        rules: AutomationRuleRepository,
        webhooks: WebhookRepository,
        settings: SettingsRepository,
        audits: AuditRepository,
        *,
        webhook_sender: WebhookSender = _send_webhook,
        forward_sender: ForwardSender = _forward_message,
    ) -> None:
        self._rules = rules
        self._webhooks = webhooks
        self._settings = settings
        self._audits = audits
        self._webhook_sender = webhook_sender
        self._forward_sender = forward_sender

    def process(
        self, account: EmailAccount, message: MailMessage, client: ActionClient
    ) -> int:
        values = self._settings.get("enterprise_ui", {})
        values = values if isinstance(values, dict) else {}
        confirmed = bool(values.get("confirm_actions", False))
        allowed_value = self._settings.get("webhook_allowed_hosts", [])
        allowed_hosts = {
            str(host).casefold()
            for host in (allowed_value if isinstance(allowed_value, list) else [])
        }
        text = f"{message.subject}\n{message.text_body}"
        completed = 0
        for rule in self._rules.list_all(enabled_only=True):
            try:
                matches = extract_matches(text, keywords=(), custom_pattern=rule.pattern)
                if not matches:
                    continue
                if rule.action is not PostAction.NONE:
                    if not confirmed:
                        raise ValueError("自动化邮件操作尚未获得用户确认")
                    client.apply_action(
                        message,
                        rule.action,
                        rule.target_folder,
                        confirmed=True,
                    )
                if rule.webhook_id is not None:
                    webhook = self._webhooks.get(rule.webhook_id)
                    if webhook is not None:
                        self._webhook_sender(
                            webhook,
                            {
                                "account": account.email,
                                "sender": message.sender,
                                "code": _best_code(message.matched_values),
                                "matches": list(message.matched_values),
                                "extractedAt": datetime.now(UTC).isoformat(),
                            },
                            allowed_hosts,
                        )
                if rule.forward_to:
                    if not confirmed:
                        raise ValueError("自动转发尚未获得用户确认")
                    self._forward_sender(account, message, rule.forward_to)
                self._audits.record(
                    "automation_rule",
                    "success",
                    f"rule={rule.name} account={account.email}",
                    account.account_id,
                )
                completed += 1
            except Exception as exc:
                self._audits.record(
                    "automation_rule",
                    "failed",
                    f"rule={rule.name} account={account.email} error={exc}",
                    account.account_id,
                )
        return completed


def _best_code(values: tuple[str, ...]) -> str:
    return next((value for value in values if value.isdigit()), values[0] if values else "")

