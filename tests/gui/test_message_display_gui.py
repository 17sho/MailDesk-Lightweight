from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt

from mailbox_manager.domain.models import EmailAccount, MailMessage, ProtocolType
from mailbox_manager.gui.mail_viewer_dialog import MailViewerDialog
from mailbox_manager.gui.main_window import MainWindow
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


def test_main_message_detail_falls_back_when_sanitized_html_is_empty(
    qtbot, tmp_path
) -> None:
    database = Database(tmp_path / "main-display-fallback.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"D" * 32))
    accounts.add_many([_account()])
    messages = MessageRepository(database)
    messages.add_many(
        1,
        (
            MailMessage(
                provider_message_id="fallback-main",
                folder="INBOX",
                subject="正文回退",
                html_body=(
                    "<html><head><style>body{display:none}</style></head>"
                    "<body><script>hidden()</script><br>&nbsp;</body></html>"
                ),
                text_body="主界面应显示的纯文本正文",
            ),
        ),
    )
    window = MainWindow(accounts, messages)
    qtbot.addWidget(window)

    assert window.message_body.parentWidget().testAttribute(
        Qt.WidgetAttribute.WA_NativeWindow
    ) is True

    window._account_row_clicked(window.account_model.index(0, 1))

    assert "主界面应显示的纯文本正文" in window.message_body.toPlainText()
    assert "hidden()" not in window.message_body.toPlainText()
    assert window._rendered_html_fragment == ""


def test_mail_viewer_falls_back_when_html_has_no_valid_media(qtbot) -> None:
    message = MailMessage(
        provider_message_id="fallback-viewer",
        folder="INBOX",
        subject="阅读器正文回退",
        html_body='<div>&nbsp;</div><img src="cid:missing-image">',
        text_body="独立阅读器应显示的纯文本正文",
    )
    dialog = MailViewerDialog(_account(), [message])
    qtbot.addWidget(dialog)

    assert "独立阅读器应显示的纯文本正文" in dialog.body.toPlainText()


def test_mail_viewer_shows_sender_name_and_address_separately(qtbot) -> None:
    message = MailMessage(
        provider_message_id="sender-details",
        folder="INBOX",
        subject="发件人信息",
        sender_name="Security Team",
        sender="security@example.com",
        text_body="正文",
    )
    dialog = MailViewerDialog(_account(), [message])
    qtbot.addWidget(dialog)

    assert dialog.sender_label.text() == "发件人：Security Team"
    assert dialog.sender_address_label.text() == "邮箱：security@example.com"
    assert "Security Team <security@example.com>" in dialog.inbox_list.item(0).text()
