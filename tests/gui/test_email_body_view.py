from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QTextBrowser

from mailbox_manager.gui.email_body_view import EmailBodyView
from mailbox_manager.mail.web_document import prepare_email_web_document


def test_email_body_view_uses_lightweight_qt_rich_text(qtbot) -> None:
    view = EmailBodyView()
    qtbot.addWidget(view)
    document = prepare_email_web_document(
        '<table><tr><td><b>完整正文</b></td></tr></table>'
    )

    view.setHtml(document)

    assert isinstance(view, QTextBrowser)
    assert "完整正文" in view.toPlainText()
    assert not hasattr(view, "_profile")
    assert view.openLinks() is False
    assert view.openExternalLinks() is False


def test_email_body_view_preserves_links_and_static_html(qtbot) -> None:
    view = EmailBodyView()
    qtbot.addWidget(view)
    view.setHtml(
        '<p>安全正文</p><a href="https://example.com/open">打开</a>'
        '<img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==">'
    )

    rendered = view.document().toHtml()

    assert "安全正文" in view.toPlainText()
    assert "https://example.com/open" in rendered
    assert "data:image/gif;base64" in rendered
