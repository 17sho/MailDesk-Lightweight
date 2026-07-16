from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QUrl, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMenu, QTextBrowser, QWidget


class EmailBodyView(QTextBrowser):
    """Lightweight HTML mail reader implemented by Qt's rich-text engine.

    This deliberately avoids QtWebEngine/Chromium. It renders the extracted static
    HTML, CID/data images and common table markup, but does not promise browser-level
    CSS compatibility or automatic HTTP image loading.
    """

    feedbackRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setAcceptRichText(True)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setStyleSheet("background:#ffffff; border:0;")

    def shutdown(self) -> None:
        """Keep the former reader lifecycle API without a helper process to stop."""

    def closeEvent(self, event: QCloseEvent) -> None:
        self.shutdown()
        super().closeEvent(event)

    def _show_context_menu(self, position: QPoint) -> None:
        link = QUrl(self.anchorAt(position))
        is_link = link.scheme().casefold() in {"http", "https", "mailto"}
        menu = QMenu(self)
        copy_link = menu.addAction("复制链接")
        copy_link.setEnabled(is_link)
        open_link = menu.addAction("打开链接")
        open_link.setEnabled(is_link)
        menu.addSeparator()
        copy_text = menu.addAction("复制选中文字")
        copy_text.setEnabled(self.textCursor().hasSelection())
        select_all = menu.addAction("全选正文")
        selected = menu.exec(self.mapToGlobal(position))
        if selected is copy_link:
            QApplication.clipboard().setText(link.toString())
            self.feedbackRequested.emit("链接已复制")
        elif selected is open_link:
            self.anchorClicked.emit(link)
        elif selected is copy_text:
            self.copy()
            self.feedbackRequested.emit("文字已复制")
        elif selected is select_all:
            self.selectAll()
