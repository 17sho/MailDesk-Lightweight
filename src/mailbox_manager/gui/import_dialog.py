from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mailbox_manager.domain.models import EmailAccount, ImportPreview
from mailbox_manager.gui.icons import line_icon
from mailbox_manager.gui.window_geometry import configure_resizable_window


class ImportPreviewDialog(QDialog):
    def __init__(self, preview: ImportPreview, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("importPreviewDialog")
        self._preview = preview
        self.setWindowTitle("导入映射预览")
        configure_resizable_window(
            self,
            preferred=QSize(1050, 560),
            minimum=QSize(700, 460),
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        valid_count = len(preview.valid_accounts)

        header = QFrame()
        header.setObjectName("utilityDialogHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 18, 24, 17)
        header_layout.setSpacing(13)
        icon = QLabel()
        icon.setObjectName("utilityDialogIcon")
        icon.setFixedSize(42, 42)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(line_icon("import", "#2563eb", 21).pixmap(21, 21))
        header_layout.addWidget(icon)
        title_copy = QVBoxLayout()
        title_copy.setSpacing(2)
        title = QLabel("确认导入账号")
        title.setObjectName("utilityDialogTitle")
        summary = QLabel(
            f"已识别 {valid_count} 个账号，错误 {preview.error_count} 行。"
            "请确认认证方式，取消勾选不需要导入的记录。"
        )
        summary.setObjectName("utilityDialogSubtitle")
        summary.setWordWrap(True)
        title_copy.addWidget(title)
        title_copy.addWidget(summary)
        header_layout.addLayout(title_copy, 1)
        root.addWidget(header)

        content = QWidget()
        content.setObjectName("utilityDialogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 17, 20, 17)
        layout.setSpacing(11)
        result_row = QHBoxLayout()
        result_title = QLabel("映射结果")
        result_title.setObjectName("utilitySectionTitle")
        result_row.addWidget(result_title)
        result_row.addStretch(1)
        self.summary_badge = QLabel(f"可导入 {valid_count} 个")
        self.summary_badge.setObjectName("utilityResultBadge")
        result_row.addWidget(self.summary_badge)
        layout.addLayout(result_row)
        self.table = QTableWidget(len(preview.rows), 8)
        self.table.setObjectName("importPreviewTable")
        self.table.setHorizontalHeaderLabels(
            ["导入", "行", "账号", "邮箱类型", "认证方式", "服务器", "置信度", "提示/错误"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.blockSignals(True)
        for row_index, row in enumerate(preview.rows):
            account = row.account
            if account is None:
                authentication = "—"
            elif account.protocol.value == "graph":
                authentication = "Microsoft Graph OAuth2"
            elif account.refresh_token and account.client_id:
                authentication = "IMAP OAuth2"
            else:
                authentication = "密码 / 授权码"
            values = (
                "",
                str(row.line_number),
                account.email if account else row.raw_masked,
                account.provider if account else "—",
                authentication,
                f"{account.host}:{account.port}" if account and account.host else "—",
                {"high": "高", "medium": "中", "low": "低"}.get(row.confidence, row.confidence),
                row.error or "；".join(row.warnings),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    flags = Qt.ItemFlag.ItemIsUserCheckable
                    if account is not None and not row.error:
                        flags |= Qt.ItemFlag.ItemIsEnabled
                    item.setFlags(flags)
                    item.setCheckState(
                        Qt.CheckState.Checked
                        if account is not None and not row.error
                        else Qt.CheckState.Unchecked
                    )
                if row.error:
                    item.setData(Qt.ItemDataRole.AccessibleDescriptionRole, "导入错误")
                    if column == 7:
                        item.setForeground(QColor("#ef4444"))
                elif row.warnings and column == 7:
                    item.setForeground(QColor("#f59e0b"))
                if column == 7 and value:
                    item.setToolTip(value)
                self.table.setItem(row_index, column, item)
        self.table.blockSignals(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        root.addWidget(content, 1)

        footer = QFrame()
        footer.setObjectName("utilityDialogFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(20, 13, 20, 13)
        footer_layout.setSpacing(10)
        footer_hint = QLabel("只有已勾选且校验通过的账号会被保存")
        footer_hint.setObjectName("utilityDialogFooterHint")
        footer_layout.addWidget(footer_hint)
        footer_layout.addStretch(1)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确认导入")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primaryButton")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.table.itemChanged.connect(self._refresh_accept_button)
        self._refresh_accept_button()
        footer_layout.addWidget(self.buttons)
        root.addWidget(footer)

    def _refresh_accept_button(self, *_args) -> None:
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            bool(self.valid_accounts)
        )

    @property
    def valid_accounts(self) -> tuple[EmailAccount, ...]:
        selected: list[EmailAccount] = []
        for row_index, row in enumerate(self._preview.rows):
            checkbox = self.table.item(row_index, 0)
            if (
                row.account is not None
                and not row.error
                and checkbox.checkState() == Qt.CheckState.Checked
            ):
                selected.append(row.account)
        return tuple(selected)
