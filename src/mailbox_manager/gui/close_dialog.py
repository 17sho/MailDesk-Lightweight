from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mailbox_manager.gui.icons import line_icon
from mailbox_manager.gui.window_geometry import configure_resizable_window

CLOSE_ACTION_ASK = "ask"
CLOSE_ACTION_TRAY = "tray"
CLOSE_ACTION_EXIT = "exit"
CLOSE_ACTIONS = frozenset({CLOSE_ACTION_ASK, CLOSE_ACTION_TRAY, CLOSE_ACTION_EXIT})


class CloseOptionButton(QPushButton):
    """Keyboard-accessible option card with independently styled text."""

    def __init__(
        self,
        title: str,
        description: str,
        icon_name: str,
        icon_color: str,
        object_name: str,
    ) -> None:
        super().__init__()
        self.setObjectName(object_name)
        self.setAccessibleName(title)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setMinimumHeight(74)

        row = QHBoxLayout(self)
        row.setContentsMargins(17, 12, 15, 12)
        row.setSpacing(13)

        icon = QLabel()
        icon.setObjectName("closeOptionIcon")
        icon.setFixedSize(34, 34)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(line_icon(icon_name, icon_color, 26).pixmap(26, 26))
        icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("closeOptionTitle")
        self.description_label = QLabel(description)
        self.description_label.setObjectName("closeOptionDescription")
        for label in (self.title_label, self.description_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        copy.addWidget(self.title_label)
        copy.addWidget(self.description_label)

        arrow = QLabel()
        arrow.setObjectName("closeOptionArrow")
        arrow.setFixedSize(22, 22)
        arrow.setPixmap(line_icon("chevron-right", "#94a3b8", 16).pixmap(16, 16))
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        row.addWidget(icon)
        row.addLayout(copy, 1)
        row.addWidget(arrow)

    def setDescription(self, description: str) -> None:
        self.description_label.setText(description)
        self.setToolTip(description)
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        hint = self.layout().sizeHint()
        return QSize(max(420, hint.width()), max(74, hint.height()))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()


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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        card = QFrame()
        card.setObjectName("closeDialogCard")
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 23, 28, 24)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("关闭窗口")
        title.setObjectName("closeDialogTitle")
        self.close_button = QPushButton()
        self.close_button.setObjectName("closeDialogDismiss")
        self.close_button.setFixedSize(30, 30)
        self.close_button.setIcon(line_icon("close", "#94a3b8", 18))
        self.close_button.setIconSize(QSize(18, 18))
        self.close_button.setToolTip("取消")
        self.close_button.setAccessibleName("取消关闭")
        self.close_button.clicked.connect(self.reject)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.close_button)
        layout.addLayout(header)

        subtitle = QLabel("请选择关闭窗口时的操作")
        subtitle.setObjectName("closeDialogSubtitle")
        layout.addWidget(subtitle)
        layout.addSpacing(2)

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
        self.tray_button.clicked.connect(lambda: self._choose(CLOSE_ACTION_TRAY))
        layout.addWidget(self.tray_button)

        self.exit_button = self._option(
            "退出应用",
            "完全关闭应用程序",
            "logout",
            "#ef4444",
            "closeExitOption",
        )
        self.exit_button.clicked.connect(lambda: self._choose(CLOSE_ACTION_EXIT))
        layout.addWidget(self.exit_button)

        layout.addSpacing(4)
        self.remember_checkbox = QCheckBox("记住我的选择，不再询问")
        self.remember_checkbox.setObjectName("closeRememberChoice")
        layout.addWidget(self.remember_checkbox)
        configure_resizable_window(
            self,
            preferred=QSize(520, max(380, self.sizeHint().height())),
            minimum=QSize(440, 320),
            screen_margin=32,
        )

    @staticmethod
    def _option(
        title: str,
        description: str,
        icon_name: str,
        icon_color: str,
        object_name: str,
    ) -> CloseOptionButton:
        return CloseOptionButton(
            title,
            description,
            icon_name,
            icon_color,
            object_name,
        )

    @property
    def remember_choice(self) -> bool:
        return self.remember_checkbox.isChecked()

    def _choose(self, action: str) -> None:
        self.selected_action = action
        self.accept()
