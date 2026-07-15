from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mailbox_manager.domain.models import ProxyConfig, ProxyType
from mailbox_manager.gui.icons import line_icon


class AddProxyDialog(QDialog):
    """Add one encrypted HTTP or SOCKS5 proxy without using bulk text import."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.proxy: ProxyConfig | None = None
        self.setObjectName("settingsDialog")
        self.setWindowTitle("MailDesk · 添加代理")
        self.setMinimumSize(560, 510)
        self.resize(640, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        content = QWidget()
        content.setObjectName("settingsPage")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(26, 22, 26, 24)
        layout.setSpacing(14)

        self.name_input = self._field(layout, "名称", "例如：香港节点 1")
        layout.addLayout(self._type_row())

        address = QGridLayout()
        address.setHorizontalSpacing(16)
        address.setVerticalSpacing(7)
        self.host_input = QLineEdit()
        self.host_input.setClearButtonEnabled(True)
        self.host_input.setPlaceholderText("127.0.0.1 或 proxy.example.com")
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(1080)
        self.port_input.setAlignment(Qt.AlignmentFlag.AlignLeft)
        address.addWidget(self._label("主机"), 0, 0)
        address.addWidget(self._label("端口"), 0, 1)
        address.addWidget(self.host_input, 1, 0)
        address.addWidget(self.port_input, 1, 1)
        address.setColumnStretch(0, 2)
        address.setColumnStretch(1, 1)
        layout.addLayout(address)

        credentials = QGridLayout()
        credentials.setHorizontalSpacing(16)
        credentials.setVerticalSpacing(7)
        self.username_input = QLineEdit()
        self.username_input.setClearButtonEnabled(True)
        self.username_input.setPlaceholderText("用户名（可选）")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("密码（可选）")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setClearButtonEnabled(True)
        credentials.addWidget(self._label("用户名（可选）"), 0, 0)
        credentials.addWidget(self._label("密码（可选）"), 0, 1)
        credentials.addWidget(self.username_input, 1, 0)
        credentials.addWidget(self.password_input, 1, 1)
        credentials.setColumnStretch(0, 1)
        credentials.setColumnStretch(1, 1)
        layout.addLayout(credentials)

        self.default_proxy = QCheckBox("设为默认代理（全局代理池会优先从这里开始）")
        layout.addWidget(self.default_proxy)
        hint = QLabel("代理密码只会以本机密钥加密后保存，不会写入普通设置或日志。")
        hint.setObjectName("settingsCardCaption")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        root.addWidget(content, 1)
        root.addWidget(self._build_footer())

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("settingsHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(26, 20, 26, 18)
        layout.setSpacing(13)
        icon = QLabel()
        icon.setObjectName("settingsHeaderIcon")
        icon.setFixedSize(42, 42)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(line_icon("globe", "#2563eb", 22).pixmap(22, 22))
        copy = QVBoxLayout()
        copy.setSpacing(2)
        title = QLabel("添加代理")
        title.setObjectName("settingsTitle")
        subtitle = QLabel("单独保存一个 HTTP 或 SOCKS5 代理")
        subtitle.setObjectName("settingsSubtitle")
        copy.addWidget(title)
        copy.addWidget(subtitle)
        layout.addWidget(icon)
        layout.addLayout(copy)
        layout.addStretch(1)
        return header

    def _type_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(18)
        row.addWidget(self._label("类型"))
        self.socks_radio = QRadioButton("SOCKS5")
        self.http_radio = QRadioButton("HTTP / HTTPS")
        self.socks_radio.setChecked(True)
        self.type_group = QButtonGroup(self)
        self.type_group.addButton(self.socks_radio)
        self.type_group.addButton(self.http_radio)
        row.addWidget(self.socks_radio)
        row.addWidget(self.http_radio)
        row.addStretch(1)
        return row

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("settingsFieldLabel")
        return label

    def _field(self, layout: QVBoxLayout, label: str, placeholder: str) -> QLineEdit:
        layout.addWidget(self._label(label))
        editor = QLineEdit()
        editor.setPlaceholderText(placeholder)
        editor.setClearButtonEnabled(True)
        layout.addWidget(editor)
        return editor

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("settingsFooter")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.addStretch(1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        save = buttons.button(QDialogButtonBox.StandardButton.Save)
        save.setText("保存代理")
        save.setObjectName("primaryButton")
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setText("取消")
        cancel.setObjectName("secondaryButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        return footer

    def accept(self) -> None:
        name = self.name_input.text().strip()
        host = self.host_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not name:
            self.name_input.setFocus()
            QMessageBox.warning(self, "缺少代理名称", "请填写便于识别的代理名称。")
            return
        if not host or len(host) > 253 or re.search(r"[\s/:]", host):
            self.host_input.setFocus()
            QMessageBox.warning(
                self,
                "代理主机无效",
                "请填写不带协议和端口的 IP 地址或主机名。",
            )
            return
        if bool(username) != bool(password):
            QMessageBox.warning(
                self,
                "代理认证不完整",
                "用户名和密码必须同时填写，或同时留空。",
            )
            return
        proxy_type = ProxyType.SOCKS5 if self.socks_radio.isChecked() else ProxyType.HTTP
        try:
            self.proxy = ProxyConfig(
                name=name,
                proxy_type=proxy_type,
                host=host,
                port=self.port_input.value(),
                username=username,
                password=password,
                is_default=self.default_proxy.isChecked(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "代理设置无效", str(exc))
            return
        super().accept()
