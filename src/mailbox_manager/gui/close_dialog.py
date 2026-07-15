from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QCommandLinkButton,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mailbox_manager.gui.icons import line_icon

CLOSE_ACTION_ASK = "ask"
CLOSE_ACTION_TRAY = "tray"
CLOSE_ACTION_EXIT = "exit"
CLOSE_ACTIONS = frozenset(
    {CLOSE_ACTION_ASK, CLOSE_ACTION_TRAY, CLOSE_ACTION_EXIT}
)


class CloseWindowDialog(QDialog):
    """Let the user choose whether closing hides or exits MailDesk."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        tray_available: bool = True,
    ) -> None:
        super().__init__(parent)
        self.selected_action: str | None = None
        self.setObjectName("closeWindowDialog")
        self.setWindowTitle("关闭窗口")
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(520, 430)
        self.resize(560, 450)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        card = QFrame()
        card.setObjectName("closeDialogCard")
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(34, 28, 34, 30)
        layout.setSpacing(18)

        header = QHBoxLayout()
        title = QLabel("关闭窗口")
        title.setObjectName("closeDialogTitle")
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("closeDialogDismiss")
        self.close_button.setFixedSize(34, 34)
        self.close_button.setToolTip("取消")
        self.close_button.clicked.connect(self.reject)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.close_button)
        layout.addLayout(header)

        subtitle = QLabel("请选择关闭窗口时的操作")
        subtitle.setObjectName("closeDialogSubtitle")
        layout.addWidget(subtitle)

        self.tray_button = self._option(
            "最小化到托盘",
            "应用将在后台继续运行",
            "minimize",
            "#2563eb",
            "closeTrayOption",
        )
        self.tray_button.setEnabled(tray_available)
        if not tray_available:
            self.tray_button.setDescription("当前系统没有可用的系统托盘")
        self.tray_button.clicked.connect(
            lambda: self._choose(CLOSE_ACTION_TRAY)
        )
        layout.addWidget(self.tray_button)

        self.exit_button = self._option(
            "退出应用",
            "完全关闭应用程序",
            "logout",
            "#ef4444",
            "closeExitOption",
        )
        self.exit_button.clicked.connect(
            lambda: self._choose(CLOSE_ACTION_EXIT)
        )
        layout.addWidget(self.exit_button)

        layout.addStretch(1)
        self.remember_checkbox = QCheckBox("记住我的选择，不再询问")
        self.remember_checkbox.setObjectName("closeRememberChoice")
        layout.addWidget(self.remember_checkbox)

    @staticmethod
    def _option(
        title: str,
        description: str,
        icon_name: str,
        icon_color: str,
        object_name: str,
    ) -> QCommandLinkButton:
        button = QCommandLinkButton(title, description)
        button.setObjectName(object_name)
        button.setIcon(line_icon(icon_name, icon_color, 34))
        button.setIconSize(QSize(42, 42))
        button.setFixedHeight(92)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    @property
    def remember_choice(self) -> bool:
        return self.remember_checkbox.isChecked()

    def _choose(self, action: str) -> None:
        self.selected_action = action
        self.accept()
