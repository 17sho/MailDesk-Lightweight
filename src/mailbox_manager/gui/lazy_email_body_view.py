from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from mailbox_manager.mail.parser import clean_message_text, html_to_text
from mailbox_manager.mail.web_document import prepare_plain_web_document


class _DocumentSnapshot:
    def __init__(self, owner: LazyEmailBodyView) -> None:
        self._owner = owner

    def toHtml(self) -> str:
        return self._owner._html


class LazyEmailBodyView(QWidget):
    """Delay QtWebEngine startup until an email body actually needs rendering."""

    anchorClicked = Signal(QUrl)
    feedbackRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._body_view = None
        self._plain_text = ""
        self._html = ""
        self._placeholder = ""
        self._mode = "empty"
        self._document_snapshot = _DocumentSnapshot(self)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._placeholder_label = QLabel()
        self._placeholder_label.setObjectName("emailBodyPlaceholder")
        self._placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder_label.setWordWrap(True)
        self._layout.addWidget(self._placeholder_label, 1)

    @property
    def is_initialized(self) -> bool:
        return self._body_view is not None

    @property
    def blocked_request_count(self) -> int:
        return self._body_view.blocked_request_count if self._body_view is not None else 0

    def setHtml(self, html: str) -> None:
        self._mode = "html"
        self._html = html
        self._plain_text = clean_message_text(html_to_text(html))
        self._ensure_body_view()

    def setPlainText(self, text: str) -> None:
        self._mode = "plain"
        self._plain_text = clean_message_text(text)
        self._html = prepare_plain_web_document(self._plain_text or self._placeholder)
        self._ensure_body_view()

    def setPlaceholderText(self, text: str) -> None:
        self._placeholder = text
        self._placeholder_label.setText(text)
        if self._mode == "empty":
            self._html = prepare_plain_web_document(text)
        if self._body_view is not None:
            self._body_view.setPlaceholderText(text)

    def toPlainText(self) -> str:
        return self._plain_text

    def document(self) -> _DocumentSnapshot:
        return self._document_snapshot

    def clear(self) -> None:
        self._mode = "empty"
        self._plain_text = ""
        self._html = prepare_plain_web_document(self._placeholder)
        if self._body_view is not None:
            self._body_view.clear()
        else:
            self._placeholder_label.setText(self._placeholder)
            self._placeholder_label.show()

    def copy(self) -> None:
        if self._body_view is not None:
            self._body_view.copy()

    def selectAll(self) -> None:
        if self._body_view is not None:
            self._body_view.selectAll()

    def shutdown(self) -> None:
        if self._body_view is not None:
            self._body_view.shutdown()
            self._body_view = None

    def closeEvent(self, event: QCloseEvent) -> None:
        self.shutdown()
        super().closeEvent(event)

    def _ensure_body_view(self) -> None:
        if self._body_view is not None:
            if self._mode == "html":
                self._body_view.setHtml(self._html)
            elif self._mode == "plain":
                self._body_view.setPlainText(self._plain_text)
            return

        # Importing and constructing QtWebEngine is the dominant startup cost.
        from mailbox_manager.gui.email_body_view import EmailBodyView

        body_view = EmailBodyView(self)
        body_view.setObjectName("emailBodyWebView")
        body_view.setPlaceholderText(self._placeholder)
        body_view.anchorClicked.connect(self.anchorClicked)
        body_view.feedbackRequested.connect(self.feedbackRequested)
        self._layout.replaceWidget(self._placeholder_label, body_view)
        self._placeholder_label.hide()
        self._body_view = body_view
        if self._mode == "html":
            body_view.setHtml(self._html)
        elif self._mode == "plain":
            body_view.setPlainText(self._plain_text)
        else:
            body_view.clear()
