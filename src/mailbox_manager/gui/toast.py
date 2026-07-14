from __future__ import annotations

from typing import ClassVar

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from mailbox_manager.gui.icons import line_icon


class BottomToast(QFrame):
    """A compact, non-blocking notification anchored above the status bar."""

    _ICONS: ClassVar[dict[str, str]] = {
        "success": "check",
        "warning": "warning",
        "info": "info",
    }

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("bottomToast")
        self.setProperty("tone", "success")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setMinimumWidth(280)
        self.setMaximumWidth(640)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 16, 10)
        layout.setSpacing(10)
        self.icon_label = QLabel()
        self.icon_label.setObjectName("bottomToastIcon")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setFixedSize(22, 22)
        self.message_label = QLabel()
        self.message_label.setObjectName("bottomToastText")
        self.message_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.message_label, 1)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 7)
        shadow.setColor(QColor(15, 23, 42, 80))
        self.setGraphicsEffect(shadow)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self.hide()

    def show_message(
        self,
        message: str,
        *,
        tone: str = "success",
        duration: int = 2400,
    ) -> None:
        tone = tone if tone in self._ICONS else "info"
        self.setProperty("tone", tone)
        self.icon_label.setPixmap(
            line_icon(self._ICONS[tone], "#ffffff", 14).pixmap(14, 14)
        )
        self.message_label.setText(message)
        self.style().unpolish(self)
        self.style().polish(self)
        self.adjustSize()
        parent = self.parentWidget()
        if parent is not None:
            width = min(max(self.sizeHint().width(), 280), parent.width() - 48)
            self.resize(width, self.sizeHint().height())
        self.reposition()
        self.show()
        self.raise_()
        self._hide_timer.start(max(800, duration))

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        status_height = 0
        status_bar_getter = getattr(parent, "statusBar", None)
        if callable(status_bar_getter):
            status_bar = status_bar_getter()
            status_height = status_bar.height() if status_bar.isVisible() else 0
        x = max(16, (parent.width() - self.width()) // 2)
        y = max(16, parent.height() - status_height - self.height() - 18)
        self.move(x, y)
