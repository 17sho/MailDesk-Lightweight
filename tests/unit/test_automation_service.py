from __future__ import annotations

from mailbox_manager.domain.models import (
    AutomationRule,
    EmailAccount,
    MailMessage,
    PostAction,
    ProtocolType,
    WebhookConfig,
)
from mailbox_manager.services.automation_service import AutomationService
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.enterprise_repositories import (
    AuditRepository,
    AutomationRuleRepository,
    SettingsRepository,
    WebhookRepository,
)
from mailbox_manager.storage.repositories import AccountRepository


class ActionClient:
    def __init__(self) -> None:
        self.actions: list[tuple[PostAction, str, bool]] = []

    def apply_action(self, _message, action, target_folder="", *, confirmed=False):
        self.actions.append((action, target_folder, confirmed))
        return True


def test_automation_rule_triggers_action_webhook_and_confirmed_forward(tmp_path) -> None:
    database = Database(tmp_path / "automation.db")
    database.initialize()
    cipher = CredentialCipher.from_raw_key(b"J" * 32)
    rules = AutomationRuleRepository(database)
    webhooks = WebhookRepository(database, cipher)
    settings = SettingsRepository(database)
    audits = AuditRepository(database)
    webhook_id = webhooks.add(
        WebhookConfig(name="hook", url="https://hooks.example.com/mail", secret="secret")
    )
    rules.add(
        AutomationRule(
            name="验证码规则",
            pattern="验证码",
            action=PostAction.MARK_READ,
            webhook_id=webhook_id,
            forward_to="archive@example.com",
        )
    )
    settings.set("enterprise_ui", {"confirm_actions": True})
    settings.set("webhook_allowed_hosts", ["hooks.example.com"])
    webhook_calls: list[dict[str, object]] = []
    forward_calls: list[str] = []
    service = AutomationService(
        rules,
        webhooks,
        settings,
        audits,
        webhook_sender=lambda _hook, payload, _hosts: webhook_calls.append(payload),
        forward_sender=lambda _account, _message, target: forward_calls.append(target),
    )
    account = EmailAccount(
        email="owner@example.com",
        provider="custom",
        protocol=ProtocolType.IMAP,
        host="imap.example.com",
        port=993,
        username="owner@example.com",
        secret="secret",
    )
    account_repository = AccountRepository(database, cipher)
    account_repository.add_many([account])
    account = account_repository.list_all()[0]
    message = MailMessage(
        provider_message_id="mail-1",
        transport_id="42",
        folder="INBOX",
        subject="登录验证码",
        sender="security@example.com",
        matched_values=("123456",),
        raw_eml=b"Subject: code\r\n\r\n123456",
    )
    client = ActionClient()

    count = service.process(account, message, client)

    assert count == 1
    assert client.actions == [(PostAction.MARK_READ, "", True)]
    assert webhook_calls[0]["code"] == "123456"
    assert forward_calls == ["archive@example.com"]
    assert audits.list_recent()[0].outcome == "success"
