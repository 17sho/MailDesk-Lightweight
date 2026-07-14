from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from mailbox_manager.domain.models import EmailAccount, ImportPreview


class ImportPreviewDialog(QDialog):
    def __init__(self, preview: ImportPreview, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("importPreviewDialog")
        self._preview = preview
        self.setWindowTitle("导入映射预览")
        self.resize(1050, 560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(10)
        valid_count = len(preview.valid_accounts)
        title = QLabel("确认导入账号")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        summary = QLabel(
            f"已识别 {valid_count} 个账号，错误 {preview.error_count} 行。"
            "请确认认证方式，取消勾选不需要导入的记录。"
        )
        summary.setObjectName("sectionCaption")
        layout.addWidget(summary)
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
                {"high": "高", "medium": "中", "low": "低"}.get(
                    row.confidence, row.confidence
                ),
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
                        item.setForeground(QColor("#dc2626"))
                elif row.warnings and column == 7:
                    item.setForeground(QColor("#d97706"))
                if column == 7 and value:
                    item.setToolTip(value)
                self.table.setItem(row_index, column, item)
        self.table.blockSignals(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
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
        layout.addWidget(self.buttons)

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
