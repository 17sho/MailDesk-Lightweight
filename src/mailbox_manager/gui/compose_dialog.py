from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from mailbox_manager.domain.models import EmailAccount
from mailbox_manager.gui.icons import line_icon
from mailbox_manager.gui.window_geometry import configure_resizable_window
from mailbox_manager.services.send_service import OutgoingAttachment, OutgoingDraft


class ComposeDialog(QDialog):
    def __init__(
        self,
        accounts: list[EmailAccount],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if not accounts:
            raise ValueError("至少需要一个发件账号")
        self._accounts = accounts
        self._attachment_paths: list[Path] = []
        self._draft: OutgoingDraft | None = None
        batch = len(accounts) > 1
        self.setObjectName("composeDialog")
        self.setWindowTitle("批量发件" if batch else "写邮件")
        configure_resizable_window(
            self,
            preferred=QSize(900, 720),
            minimum=QSize(680, 520),
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        content = QWidget()
        content.setObjectName("composeContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 18, 24, 18)
        content_layout.setSpacing(10)
        content_layout.addWidget(self._build_sender_card())
        recipients_card = QFrame()
        recipients_card.setObjectName("composeRecipientsCard")
        recipients_layout = QVBoxLayout(recipients_card)
        recipients_layout.setContentsMargins(14, 12, 14, 13)
        recipients_layout.setSpacing(9)
        self.to_input = self._field(recipients_layout, "收件人", "多个地址用逗号或分号分隔")
        self.cc_input = self._field(recipients_layout, "抄送", "可选")
        self.bcc_input = self._field(recipients_layout, "密送", "可选")
        self.subject_input = self._field(recipients_layout, "主题", "邮件主题")
        content_layout.addWidget(recipients_card)

        body_label = QLabel("正文")
        body_label.setObjectName("composeFieldLabel")
        content_layout.addWidget(body_label)
        self.body_editor = QTextEdit()
        self.body_editor.setObjectName("composeBody")
        self.body_editor.setAcceptRichText(True)
        self.body_editor.setPlaceholderText("输入邮件正文，可粘贴带格式的文字和链接…")
        content_layout.addWidget(self.body_editor, 1)
        content_layout.addWidget(self._build_attachment_card())
        if batch:
            self.batch_confirmation = QCheckBox(
                f"我确认使用所选 {len(accounts)} 个邮箱分别发送这封邮件"
            )
            self.batch_confirmation.setObjectName("composeConfirmation")
            content_layout.addWidget(self.batch_confirmation)
        else:
            self.batch_confirmation = None
        root.addWidget(content, 1)
        root.addWidget(self._build_footer())

    @property
    def accounts(self) -> list[EmailAccount]:
        return list(self._accounts)

    @property
    def draft(self) -> OutgoingDraft | None:
        return self._draft

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("composeHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(24, 18, 24, 16)
        layout.setSpacing(13)
        icon = QLabel()
        icon.setObjectName("composeHeaderIcon")
        icon.setFixedSize(42, 42)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(line_icon("mail", "#2563eb", 21).pixmap(21, 21))
        layout.addWidget(icon)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        title = QLabel("批量发件" if len(self._accounts) > 1 else "写邮件")
        title.setObjectName("composeTitle")
        subtitle = QLabel(
            f"将从 {len(self._accounts)} 个已选择邮箱分别发送"
            if len(self._accounts) > 1
            else f"发件邮箱：{self._accounts[0].email}"
        )
        subtitle.setObjectName("composeSubtitle")
        subtitle.setWordWrap(True)
        copy.addWidget(title)
        copy.addWidget(subtitle)
        layout.addLayout(copy)
        layout.addStretch(1)
        return header

    def _build_sender_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("composeSenderCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(3)
        label = QLabel("发件账号")
        label.setObjectName("composeFieldLabel")
        emails = "、".join(account.email for account in self._accounts[:8])
        if len(self._accounts) > 8:
            emails += f" 等 {len(self._accounts)} 个账号"
        value = QLabel(emails)
        value.setObjectName("composeSenderValue")
        value.setWordWrap(True)
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label)
        layout.addWidget(value)
        return card

    @staticmethod
    def _field(layout: QVBoxLayout, label_text: str, placeholder: str) -> QLineEdit:
        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setObjectName("composeFieldLabel")
        label.setMinimumWidth(68)
        editor = QLineEdit()
        editor.setPlaceholderText(placeholder)
        editor.setClearButtonEnabled(True)
        row.addWidget(label)
        row.addWidget(editor, 1)
        layout.addLayout(row)
        return editor

    def _build_attachment_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("composeAttachmentCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 9, 12, 10)
        layout.setSpacing(7)
        header = QHBoxLayout()
        self.attachment_summary = QLabel("附件 0 个")
        self.attachment_summary.setObjectName("composeFieldLabel")
        header.addWidget(self.attachment_summary)
        header.addStretch(1)
        add_button = QPushButton("添加附件")
        add_button.setObjectName("attachmentActionButton")
        add_button.clicked.connect(self._choose_attachments)
        header.addWidget(add_button)
        self.remove_attachment_button = QPushButton("移除选中")
        self.remove_attachment_button.setObjectName("attachmentActionButton")
        self.remove_attachment_button.setEnabled(False)
        self.remove_attachment_button.clicked.connect(self._remove_attachment)
        header.addWidget(self.remove_attachment_button)
        layout.addLayout(header)
        self.attachment_list = QListWidget()
        self.attachment_list.setObjectName("composeAttachmentList")
        self.attachment_list.setMaximumHeight(94)
        self.attachment_list.currentRowChanged.connect(
            lambda row: self.remove_attachment_button.setEnabled(row >= 0)
        )
        layout.addWidget(self.attachment_list)
        hint = QLabel("单个附件不超过 20 MB，总计不超过 25 MB；Graph 账号总计不超过 3 MB")
        hint.setObjectName("composeHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return card

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("composeFooter")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(24, 13, 24, 13)
        hint = QLabel("发送任务将在后台执行，单个账号失败不会中断其他账号")
        hint.setObjectName("composeHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        send_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        send_button.setText("确认发送")
        send_button.setObjectName("primaryButton")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        return footer

    def _choose_attachments(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择邮件附件")
        if not paths:
            return
        known = {str(path.resolve()).casefold() for path in self._attachment_paths}
        for raw_path in paths:
            path = Path(raw_path)
            try:
                resolved = str(path.resolve()).casefold()
                size = path.stat().st_size
            except OSError as exc:
                QMessageBox.warning(self, "无法添加附件", str(exc))
                continue
            if resolved in known:
                continue
            if size > 20 * 1024 * 1024:
                QMessageBox.warning(self, "附件过大", f"{path.name} 超过 20 MB")
                continue
            self._attachment_paths.append(path)
            known.add(resolved)
        self._refresh_attachments()

    def _remove_attachment(self) -> None:
        row = self.attachment_list.currentRow()
        if 0 <= row < len(self._attachment_paths):
            self._attachment_paths.pop(row)
            self._refresh_attachments()

    def _refresh_attachments(self) -> None:
        self.attachment_list.clear()
        total = 0
        for path in self._attachment_paths:
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            total += size
            self.attachment_list.addItem(QListWidgetItem(f"{path.name}    {_format_size(size)}"))
        self.attachment_summary.setText(
            f"附件 {len(self._attachment_paths)} 个 · {_format_size(total)}"
        )

    def accept(self) -> None:
        try:
            attachments = tuple(
                OutgoingAttachment.from_path(path) for path in self._attachment_paths
            )
            text_body = self.body_editor.toPlainText().strip()
            if not text_body:
                raise ValueError("邮件正文不能为空")
            self._draft = OutgoingDraft(
                to=_parse_recipients(self.to_input.text()),
                cc=_parse_recipients(self.cc_input.text()),
                bcc=_parse_recipients(self.bcc_input.text()),
                subject=self.subject_input.text().strip(),
                text_body=text_body,
                html_body=self.body_editor.toHtml(),
                attachments=attachments,
            )
            if self.batch_confirmation is not None and not self.batch_confirmation.isChecked():
                raise ValueError("批量发件前必须勾选确认")
        except (OSError, TypeError, ValueError) as exc:
            QMessageBox.warning(self, "无法发送", str(exc))
            return
        account_count = len(self._accounts)
        answer = QMessageBox.question(
            self,
            "确认发送邮件",
            f"将使用 {account_count} 个邮箱，向 {len(self._draft.all_recipients)} 个地址发送。\n"
            f"附件：{len(self._draft.attachments)} 个。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        super().accept()


def _parse_recipients(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in re.split(r"[,;，；\n]+", value) if item.strip())


def _format_size(size: int) -> str:
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return "0 B"
