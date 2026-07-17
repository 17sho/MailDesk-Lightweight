from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice, QUrl
from PySide6.QtGui import QImage, QTextDocument
from PySide6.QtWidgets import QTextBrowser

from mailbox_manager.gui.email_body_view import EmailBodyView, remote_image_urls
from mailbox_manager.mail.web_document import prepare_email_web_document


def _test_png() -> bytes:
    image = QImage(8, 8, QImage.Format.Format_ARGB32)
    image.fill(0xFF24A88B)
    buffer = QBuffer()
    assert buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    return bytes(buffer.data())


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


def test_remote_image_urls_keep_https_content_but_skip_tracking_pixels() -> None:
    document = """
    <img src="https://cdn.example.com/logo.png" width="560" height="168">
    <img src="https://track.example.com/open.gif" width="1" height="1">
    <img src="https://track.example.com/style.gif" style="width:1px;height:1px">
    <img src="http://cdn.example.com/insecure.png">
    <img src="cid:brand-logo">
    <img src="https://cdn.example.com/logo.png">
    """

    assert remote_image_urls(document) == ("https://cdn.example.com/logo.png",)


def test_email_body_view_can_install_a_downloaded_image_resource(qtbot) -> None:
    view = EmailBodyView(remote_image_loader=lambda _url: b"")
    qtbot.addWidget(view)
    url = "https://cdn.example.com/logo.gif"
    view.setHtml(f'<p>Logo</p><img src="{url}">')

    assert view.install_remote_image(url, _test_png()) is True

    resource = view.document().resource(
        QTextDocument.ResourceType.ImageResource,
        QUrl(url),
    )
    assert isinstance(resource, QImage)
    assert resource.isNull() is False


def test_email_body_view_loads_remote_images_without_a_browser_engine(qtbot) -> None:
    requested: list[str] = []

    def load_image(url: str) -> bytes:
        requested.append(url)
        return _test_png()

    view = EmailBodyView(remote_image_loader=load_image)
    qtbot.addWidget(view)
    url = "https://cdn.example.com/remote-logo.png"
    view.setHtml(f'<p>Remote logo</p><img src="{url}" width="80" height="40">')

    def installed() -> bool:
        resource = view.document().resource(
            QTextDocument.ResourceType.ImageResource,
            QUrl(url),
        )
        return isinstance(resource, QImage) and not resource.isNull()

    qtbot.waitUntil(installed, timeout=3_000)
    assert requested == [url]

    view.setHtml(f'<p>Remote logo</p><img src="{url}" width="80" height="40">')
    qtbot.waitUntil(installed, timeout=3_000)
    assert requested == [url]
