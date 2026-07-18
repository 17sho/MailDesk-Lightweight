from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mailbox_manager.domain.models import (
    EmailAccount,
    ImportPreview,
    ProtocolType,
    SecurityMode,
)
from mailbox_manager.gui.add_account_dialog import AddAccountDialog
from mailbox_manager.gui.close_dialog import CloseWindowDialog
from mailbox_manager.gui.compose_dialog import ComposeDialog
from mailbox_manager.gui.content_filter_dialog import ContentFilterDialog
from mailbox_manager.gui.import_dialog import ImportPreviewDialog
from mailbox_manager.gui.mail_viewer_dialog import MailViewerDialog
from mailbox_manager.gui.main_window import MainWindow
from mailbox_manager.gui.proxy_dialog import AddProxyDialog
from mailbox_manager.gui.settings_dialog import EnterpriseSettingsDialog
from mailbox_manager.gui.update_dialog import UpdateDialog
from mailbox_manager.gui.usage_guide import UsageGuideDialog
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.repositories import AccountRepository, MessageRepository


def _account() -> EmailAccount:
    return EmailAccount(
        account_id=1,
        email="owner@example.com",
        provider="custom",
        protocol=ProtocolType.IMAP,
        host="imap.example.com",
        port=993,
        security=SecurityMode.SSL,
        username="owner@example.com",
        secret="app-password",
    )


def test_every_secondary_dialog_is_resizable_and_bounded_to_the_screen(qtbot, tmp_path) -> None:
    database = Database(tmp_path / "dialog-sizing.db")
    database.initialize()
    messages = MessageRepository(database)
    dialogs = (
        AddAccountDialog(),
        CloseWindowDialog(),
        ComposeDialog([_account()]),
        ContentFilterDialog(messages),
        ImportPreviewDialog(ImportPreview(())),
        MailViewerDialog(_account(), []),
        AddProxyDialog(),
        EnterpriseSettingsDialog(),
        UpdateDialog("0.4.8", "0.4.9"),
        UsageGuideDialog(),
    )

    for dialog in dialogs:
        qtbot.addWidget(dialog)
        available = dialog.screen().availableGeometry()
        assert dialog.isSizeGripEnabled() is True, type(dialog).__name__
        assert dialog.minimumWidth() <= available.width(), type(dialog).__name__
        assert dialog.minimumHeight() <= available.height(), type(dialog).__name__
        assert dialog.width() <= available.width(), type(dialog).__name__
        assert dialog.height() <= available.height(), type(dialog).__name__


def test_main_window_initial_geometry_fits_the_active_screen(qtbot, tmp_path) -> None:
    database = Database(tmp_path / "main-window-sizing.db")
    database.initialize()
    window = MainWindow(
        AccountRepository(database, CredentialCipher.from_raw_key(b"S" * 32)),
        MessageRepository(database),
    )
    qtbot.addWidget(window)
    available = window.screen().availableGeometry()

    assert window.minimumWidth() <= available.width()
    assert window.minimumHeight() <= available.height()
    assert window.width() <= available.width()
    assert window.height() <= available.height()
