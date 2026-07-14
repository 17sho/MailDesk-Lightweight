from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QMessageBox

from mailbox_manager.domain.models import AccountStatus, EmailAccount, ProtocolType
from mailbox_manager.gui.main_window import MainWindow
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.enterprise_repositories import (
    SettingsRepository,
    StatisticsRepository,
)
from mailbox_manager.storage.repositories import AccountRepository, MessageRepository


def _account(email: str) -> EmailAccount:
    return EmailAccount(
        email=email,
        provider="custom",
        protocol=ProtocolType.IMAP,
        host="imap.example.com",
        port=993,
        secret="app-password",
    )


def _window(qtbot, tmp_path, *, settings_values=None) -> MainWindow:
    database = Database(tmp_path / "dashboard-integration.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"V" * 32))
    accounts.add_many(
        [
            _account("healthy@example.com"),
            _account("broken@example.com"),
            _account("idle@example.com"),
        ]
    )
    stored = accounts.list_all()
    accounts.update_status(stored[0].account_id, AccountStatus.SUCCESS, "ok")
    accounts.update_status(
        stored[1].account_id,
        AccountStatus.AUTH_FAILED,
        "authentication failed",
    )
    settings = SettingsRepository(database)
    settings.set("enterprise_ui", dict(settings_values or {}))
    window = MainWindow(
        accounts,
        MessageRepository(database),
        settings=settings,
        statistics=StatisticsRepository(database),
    )
    qtbot.addWidget(window)
    return window


def test_dashboard_opens_all_abnormal_accounts_with_visible_filter(
    qtbot, tmp_path
) -> None:
    window = _window(qtbot, tmp_path)

    window.dashboard.abnormal_button.click()

    assert window.main_tabs.currentWidget() is window.account_workspace
    assert window.status_filter.currentData() == "abnormal"
    assert window.account_model.rowCount() == 1
    assert window.account_model.account_at(0).email == "broken@example.com"


def test_dashboard_proxy_switch_persists_and_can_be_turned_off(qtbot, tmp_path) -> None:
    window = _window(qtbot, tmp_path)
    settings = window._settings

    window.dashboard.proxy_toggle_button.click()
    assert settings.get("enterprise_ui", {})["proxy_fetch_enabled"] is True
    assert window.dashboard.proxy_toggle_button.text() == "关闭"

    window.dashboard.proxy_toggle_button.click()
    assert settings.get("enterprise_ui", {})["proxy_fetch_enabled"] is False
    assert window.dashboard.proxy_toggle_button.text() == "启动"


def test_dashboard_proxy_switch_rolls_back_when_persistence_fails(
    qtbot, tmp_path, monkeypatch
) -> None:
    window = _window(qtbot, tmp_path)
    stored_settings = window._settings
    warnings: list[tuple[str, str]] = []

    class FailingSettings:
        def get(self, key: str, default=None):
            return stored_settings.get(key, default)

        def set(self, key: str, value: object) -> None:
            if key == "enterprise_ui":
                raise OSError("settings database is read-only")
            stored_settings.set(key, value)

    window._settings = FailingSettings()
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )

    window.dashboard.proxy_toggle_button.click()

    assert window._proxy_fetch_enabled is False
    assert window.dashboard.proxy_enabled is False
    assert window.dashboard.proxy_toggle_button.text() == "启动"
    assert window.dashboard.proxy_toggle_button.isEnabled() is True
    assert stored_settings.get("enterprise_ui", {}) == {}
    assert warnings
    assert warnings[0][0] == "代理设置保存失败"


def test_dashboard_loads_persisted_custom_shortcuts(qtbot, tmp_path) -> None:
    actions = [
        "abnormal_accounts",
        "accounts",
        "add_account",
        "content_filter",
    ]
    window = _window(
        qtbot,
        tmp_path,
        settings_values={"dashboard_quick_actions": actions},
    )

    assert window.dashboard.quick_action_ids == tuple(actions)
    assert tuple(window.dashboard.quick_action_buttons) == tuple(actions)


def test_dashboard_repairs_incomplete_persisted_shortcuts(qtbot, tmp_path) -> None:
    window = _window(
        qtbot,
        tmp_path,
        settings_values={
            "dashboard_quick_actions": [
                "abnormal_accounts",
                "abnormal_accounts",
                "unknown-action",
            ]
        },
    )

    assert window.dashboard.quick_action_ids == (
        "abnormal_accounts",
        "accounts",
        "fetch",
        "add_account",
    )
