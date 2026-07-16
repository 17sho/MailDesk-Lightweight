from __future__ import annotations

import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from mailbox_manager.domain.models import (
    Group,
    PostAction,
    ScheduleConfig,
    WebhookConfig,
)
from mailbox_manager.gui.main_window import MainWindow
from mailbox_manager.gui.settings_dialog import EnterpriseSettingsDialog
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.enterprise_repositories import (
    AutomationRuleRepository,
    GroupRepository,
    ProxyRepository,
    ScheduleRepository,
    SettingsRepository,
    WebhookRepository,
)
from mailbox_manager.storage.repositories import AccountRepository, MessageRepository


def _window_with_automation_repositories(tmp_path):
    database = Database(tmp_path / "settings-integration.db")
    database.initialize()
    cipher = CredentialCipher.from_raw_key(b"W" * 32)
    webhooks = WebhookRepository(database, cipher)
    rules = AutomationRuleRepository(database)
    window = MainWindow(
        AccountRepository(database, cipher),
        MessageRepository(database),
        webhooks=webhooks,
        rules=rules,
    )
    return window, webhooks, rules


def _fill_rule(dialog: EnterpriseSettingsDialog, *, name: str = "验证码规则") -> None:
    dialog.rule_name.setText(name)
    dialog.rule_pattern.setText(r"\b\d{6}\b")
    dialog.rule_action.setCurrentIndex(
        dialog.rule_action.findData(PostAction.NONE.value)
    )


def test_new_webhook_id_is_written_to_new_rule(qtbot, tmp_path) -> None:
    window, webhooks, rules = _window_with_automation_repositories(tmp_path)
    qtbot.addWidget(window)
    dialog = EnterpriseSettingsDialog()
    qtbot.addWidget(dialog)
    dialog.webhook_name.setText("新端点")
    dialog.webhook_url.setText("https://hooks.example.com/mail")
    dialog.webhook_hosts.setText("hooks.example.com")
    _fill_rule(dialog)
    dialog.rule_webhook.setCurrentIndex(dialog.rule_webhook.findData("new"))

    window._save_enterprise_settings(dialog.values())

    stored_webhooks = webhooks.list_all()
    stored_rules = rules.list_all()
    assert len(stored_webhooks) == 1
    assert len(stored_rules) == 1
    assert stored_webhooks[0].webhook_id is not None
    assert stored_rules[0].webhook_id == stored_webhooks[0].webhook_id


def test_existing_webhook_selection_is_written_to_new_rule(qtbot, tmp_path) -> None:
    window, webhooks, rules = _window_with_automation_repositories(tmp_path)
    qtbot.addWidget(window)
    first_id = webhooks.add(
        WebhookConfig(name="第一个端点", url="https://first.example.com/mail")
    )
    selected_id = webhooks.add(
        WebhookConfig(name="选中的端点", url="https://selected.example.com/mail")
    )
    options = [
        (item.webhook_id, item.name)
        for item in webhooks.list_all()
        if item.webhook_id is not None
    ]
    dialog = EnterpriseSettingsDialog(webhook_options=options)
    qtbot.addWidget(dialog)
    _fill_rule(dialog, name="已有端点规则")
    dialog.rule_webhook.setCurrentIndex(dialog.rule_webhook.findData(selected_id))

    window._save_enterprise_settings(dialog.values())

    stored_rules = rules.list_all()
    assert first_id != selected_id
    assert dialog.values()["rule_webhook_id"] == selected_id
    assert len(webhooks.list_all()) == 2
    assert len(stored_rules) == 1
    assert stored_rules[0].webhook_id == selected_id


def test_update_check_from_settings_waits_until_modal_dialog_closes(
    qtbot, tmp_path, monkeypatch
) -> None:
    window, _webhooks, _rules = _window_with_automation_repositories(tmp_path)
    qtbot.addWidget(window)
    original_dialog = EnterpriseSettingsDialog
    check_calls: list[tuple[bool, bool]] = []
    state = {"inside_exec": False}

    class AutoUpdateSettingsDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, values, parent=None, *, webhook_options=None) -> None:
            self._dialog = original_dialog(
                values,
                parent,
                webhook_options=webhook_options,
            )
            self.addProxyRequested = self._dialog.addProxyRequested
            self.updateCheckRequested = self._dialog.updateCheckRequested
            self._accepted = False

        def accept(self) -> None:
            self._accepted = True

        def exec(self):
            state["inside_exec"] = True
            self.updateCheckRequested.emit()
            assert check_calls == []
            state["inside_exec"] = False
            return self.DialogCode.Accepted if self._accepted else self.DialogCode.Rejected

        def values(self):
            return self._dialog.values()

    monkeypatch.setattr(
        "mailbox_manager.gui.main_window.EnterpriseSettingsDialog",
        AutoUpdateSettingsDialog,
    )
    monkeypatch.setattr(
        window,
        "check_for_updates",
        lambda *, manual=True: check_calls.append((manual, state["inside_exec"])),
    )

    window.show_settings()
    qtbot.waitUntil(lambda: check_calls == [(True, False)])


def test_show_settings_keeps_one_shot_credentials_out_of_plain_settings(
    qtbot, tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "settings-secrets.db"
    database = Database(database_path)
    database.initialize()
    cipher = CredentialCipher.from_raw_key(b"P" * 32)
    settings = SettingsRepository(database)
    proxies = ProxyRepository(database, cipher)
    webhooks = WebhookRepository(database, cipher)
    rules = AutomationRuleRepository(database)
    window = MainWindow(
        AccountRepository(database, cipher),
        MessageRepository(database),
        proxies=proxies,
        settings=settings,
        webhooks=webhooks,
        rules=rules,
    )
    qtbot.addWidget(window)
    original_dialog = EnterpriseSettingsDialog
    opened_with: list[dict[str, object]] = []

    class AutoAcceptSettingsDialog:
        DialogCode = QDialog.DialogCode

        def __init__(
            self,
            values,
            parent=None,
            *,
            webhook_options=None,
        ) -> None:
            opened_with.append(dict(values))
            self._dialog = original_dialog(
                values,
                parent,
                webhook_options=webhook_options,
            )
            if len(opened_with) == 1:
                self._dialog.proxy_text.setPlainText(
                    "127.0.0.1:18080:audit-user:audit-password"
                )
                self._dialog.webhook_name.setText("audit-hook")
                self._dialog.webhook_url.setText("https://hooks.example.com/mail")
                self._dialog.webhook_secret.setText("audit-webhook-secret")
                self._dialog.webhook_hosts.setText("hooks.example.com")
                self._dialog.rule_name.setText("audit-rule")
                self._dialog.rule_pattern.setText(r"\b\d{6}\b")
                self._dialog.rule_webhook.setCurrentIndex(
                    self._dialog.rule_webhook.findData("new")
                )

        def exec(self):
            return self.DialogCode.Accepted

        def values(self):
            values = self._dialog.values()
            self._dialog.close()
            self._dialog.deleteLater()
            return values

    monkeypatch.setattr(
        "mailbox_manager.gui.main_window.EnterpriseSettingsDialog",
        AutoAcceptSettingsDialog,
    )

    window.show_settings()
    window.show_settings()

    assert len(proxies.list_all()) == 1
    assert proxies.list_all()[0].password == "audit-password"
    assert len(webhooks.list_all()) == 1
    assert webhooks.list_all()[0].secret == "audit-webhook-secret"
    assert len(rules.list_all()) == 1
    assert len(opened_with) == 2
    persisted = settings.get("enterprise_ui", {})
    one_shot_keys = {
        "proxy_text",
        "webhook_name",
        "webhook_url",
        "webhook_secret",
        "rule_name",
        "rule_pattern",
        "rule_action",
        "rule_target",
        "rule_webhook_id",
        "rule_forward",
    }
    assert one_shot_keys.isdisjoint(persisted)
    assert one_shot_keys.isdisjoint(opened_with[1])

    connection = sqlite3.connect(database_path)
    try:
        raw_settings = connection.execute(
            "SELECT value_json FROM settings WHERE key = 'enterprise_ui'"
        ).fetchone()[0]
        encrypted_proxy_password = connection.execute(
            "SELECT password_ciphertext FROM proxies"
        ).fetchone()[0]
        encrypted_webhook_secret = connection.execute(
            "SELECT secret_ciphertext FROM webhooks"
        ).fetchone()[0]
    finally:
        connection.close()
    for plain_value in (
        "audit-user",
        "audit-password",
        "audit-webhook-secret",
    ):
        assert plain_value not in raw_settings
    assert "audit-password" not in str(encrypted_proxy_password)
    assert "audit-webhook-secret" not in str(encrypted_webhook_secret)


def test_main_window_removes_legacy_one_shot_credentials_from_settings(
    qtbot, tmp_path
) -> None:
    database = Database(tmp_path / "legacy-settings-secrets.db")
    database.initialize()
    cipher = CredentialCipher.from_raw_key(b"L" * 32)
    settings = SettingsRepository(database)
    settings.set(
        "enterprise_ui",
        {
            "proxy_fetch_enabled": True,
            "proxy_text": "127.0.0.1:1080:legacy-user:legacy-password",
            "webhook_url": "https://hooks.example.com/private-token",
            "webhook_secret": "legacy-webhook-secret",
            "rule_pattern": r"\b\d{6}\b",
        },
    )

    window = MainWindow(
        AccountRepository(database, cipher),
        MessageRepository(database),
        settings=settings,
    )
    qtbot.addWidget(window)

    assert settings.get("enterprise_ui", {}) == {"proxy_fetch_enabled": True}
    assert window._proxy_fetch_enabled is True


def test_appearance_controls_round_trip_and_preview(qtbot) -> None:
    dialog = EnterpriseSettingsDialog(
        {
            "dark_theme": True,
            "font_family": "Microsoft YaHei UI",
            "font_size": 13,
            "font_weight": 600,
        }
    )
    qtbot.addWidget(dialog)

    assert dialog.font_size.value() == 13
    assert dialog.font_weight.currentData() == 600
    assert dialog.values()["dark_theme"] is True
    assert dialog.values()["font_size"] == 13
    assert dialog.values()["font_weight"] == 600
    assert dialog.font_preview.font().pointSize() == 13
    assert dialog.font_preview.font().weight() == QFont.Weight.DemiBold


def test_theme_toggle_preserves_saved_font_preferences(qtbot, tmp_path) -> None:
    database = Database(tmp_path / "appearance-settings.db")
    database.initialize()
    cipher = CredentialCipher.from_raw_key(b"A" * 32)
    settings = SettingsRepository(database)
    settings.set(
        "ui_preferences",
        {
            "dark_theme": False,
            "font_family": "",
            "font_size": 12,
            "font_weight": 500,
        },
    )
    window = MainWindow(
        AccountRepository(database, cipher),
        MessageRepository(database),
        settings=settings,
    )
    qtbot.addWidget(window)

    window.toggle_theme()

    saved = settings.get("ui_preferences", {})
    assert saved == {
        "dark_theme": True,
        "font_family": "",
        "font_size": 12,
        "font_weight": 500,
    }
    app = QApplication.instance()
    assert app is not None
    assert app.font().pointSize() == 12
    assert app.font().weight() == QFont.Weight.Medium


def test_open_settings_uses_schedule_for_current_group(
    qtbot, tmp_path, monkeypatch
) -> None:
    database = Database(tmp_path / "group-schedule-settings.db")
    database.initialize()
    cipher = CredentialCipher.from_raw_key(b"G" * 32)
    groups = GroupRepository(database)
    schedules = ScheduleRepository(database)
    first_group_id = groups.create(Group(name="项目 A"))
    selected_group_id = groups.create(Group(name="项目 B"))
    schedules.upsert(
        ScheduleConfig(group_id=first_group_id, interval_minutes=11, enabled=False)
    )
    schedules.upsert(
        ScheduleConfig(group_id=selected_group_id, interval_minutes=37, enabled=True)
    )
    window = MainWindow(
        AccountRepository(database, cipher),
        MessageRepository(database),
        groups=groups,
        schedules=schedules,
    )
    qtbot.addWidget(window)
    selected_item = window._find_group_item("group", selected_group_id)
    assert selected_item is not None
    window.group_tree.setCurrentItem(selected_item)
    captured: list[dict[str, object]] = []

    class CapturingSettingsDialog:
        DialogCode = QDialog.DialogCode

        def __init__(
            self,
            values,
            _parent=None,
            *,
            webhook_options=None,
        ) -> None:
            del webhook_options
            captured.append(dict(values))

        def exec(self):
            return self.DialogCode.Rejected

    monkeypatch.setattr(
        "mailbox_manager.gui.main_window.EnterpriseSettingsDialog",
        CapturingSettingsDialog,
    )

    window.show_settings()

    assert window._selected_group_id() == selected_group_id
    assert captured == [
        {
            "dark_theme": False,
            "font_family": "",
            "font_size": 10,
            "font_weight": 500,
            "schedule_enabled": True,
            "schedule_interval": 37,
        }
    ]


def test_invalid_webhook_keeps_settings_dialog_open(qtbot, monkeypatch) -> None:
    dialog = EnterpriseSettingsDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )
    dialog.webhook_name.setText("无效端点")
    dialog.webhook_url.setText("http://hooks.example.com/mail")
    dialog.webhook_hosts.setText("hooks.example.com")

    dialog.accept()

    assert dialog.isVisible() is True
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.navigation.currentRow() == 3
    assert dialog.webhook_url.text() == "http://hooks.example.com/mail"
    assert warnings == [
        ("Webhook 地址无效", "Webhook 必须使用包含有效主机名的 HTTPS 地址。")
    ]


def test_invalid_rule_regex_keeps_settings_dialog_open(qtbot, monkeypatch) -> None:
    dialog = EnterpriseSettingsDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )
    dialog.rule_name.setText("损坏的正则")
    dialog.rule_pattern.setText("([")

    dialog.accept()

    assert dialog.isVisible() is True
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.navigation.currentRow() == 4
    assert dialog.rule_pattern.text() == "(["
    assert warnings
    assert warnings[0][0] == "匹配表达式无效"
