from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from mailbox_manager.domain.models import EmailAccount, ProtocolType
from mailbox_manager.gui.main_window import MainWindow
from mailbox_manager.services.send_service import (
    OutgoingDraft,
    SendResult,
    SendService,
    SendStatus,
)
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.repositories import AccountRepository, MessageRepository


def _account() -> EmailAccount:
    return EmailAccount(
        email="owner@example.com",
        provider="custom",
        protocol=ProtocolType.IMAP,
        host="imap.example.com",
        port=993,
        secret="app-password",
    )


def test_send_lifecycle_is_visible_in_redacted_gui_log(qtbot, tmp_path, monkeypatch) -> None:
    database = Database(tmp_path / "send-log.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"S" * 32))
    accounts.add_many([_account()])

    class FakeClient:
        def __init__(self, _account: EmailAccount) -> None:
            pass

        def send_message(self, _draft: OutgoingDraft) -> SendResult:
            return SendResult(SendStatus.SUCCESS, "provider detail")

        def close(self) -> None:
            pass

    window = MainWindow(
        accounts,
        MessageRepository(database),
        send_service=SendService(client_factory=FakeClient),
    )
    qtbot.addWidget(window)
    draft = OutgoingDraft(
        to=("private-recipient@example.net",),
        text_body="private body text",
    )

    class AcceptedComposeDialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, _selected, _parent) -> None:
            self.draft = draft

        def exec(self):
            return self.DialogCode.Accepted

    monkeypatch.setattr(
        "mailbox_manager.gui.main_window.ComposeDialog", AcceptedComposeDialog
    )
    monkeypatch.setattr(window._pool, "start", lambda worker: worker.run())
    window.account_model.setData(
        window.account_model.index(0, 0),
        Qt.CheckState.Checked,
        Qt.ItemDataRole.CheckStateRole,
    )

    window.show_compose_dialog()

    log = window.log_view.toPlainText()
    assert "发件开始 · 账号 1 · 收件人 1 · 附件 0" in log
    assert "发件账号 1/1 · 成功 · success" in log
    assert "发件完成：成功 1，失败 0，共 1 个邮箱" in log
    assert "private-recipient@example.net" not in log
    assert "private body text" not in log
    assert "provider detail" not in log


def test_send_exception_adds_generic_redacted_log_entry(qtbot, tmp_path) -> None:
    database = Database(tmp_path / "send-error-log.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"E" * 32))
    window = MainWindow(accounts, MessageRepository(database))
    qtbot.addWidget(window)

    window._send_batch_result(
        None,
        RuntimeError("private-recipient@example.net private body text"),
    )

    log = window.log_view.toPlainText()
    assert "发件异常" in log
    assert "private-recipient@example.net" not in log
    assert "private body text" not in log
