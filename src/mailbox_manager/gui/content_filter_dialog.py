from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mailbox_manager.services.content_filter import (
    ContentMatch,
    ContentMatchMode,
    extract_content_matches,
)
from mailbox_manager.storage.repositories import MessageRepository


class ContentFilterDialog(QDialog):
    def __init__(
        self,
        messages: MessageRepository,
        *,
        current_account_id: int | None = None,
        current_account_email: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._messages = messages
        self._current_account_id = current_account_id
        self._results: list[ContentMatch] = []
        self.setObjectName("contentFilterDialog")
        self.setWindowTitle("内容筛选与导出")
        self.resize(1080, 680)
        self.setMinimumSize(820, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        title = QLabel("筛选邮件中的指定文字或链接")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        help_label = QLabel(
            "只输出命中的链接或文字片段，不会复制、展示或导出整封邮件正文。"
            "通配符支持 * 和 ?，正则适合提取订单号、验证码等固定格式。"
        )
        help_label.setObjectName("sectionCaption")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.query_input = QLineEdit()
        self.query_input.setObjectName("contentFilterQuery")
        self.query_input.setPlaceholderText(
            "输入文字、域名或链接，例如 Reset Password、example.com、https://example.com/*"
        )
        self.query_input.setClearButtonEnabled(True)
        self.query_input.returnPressed.connect(self.run_filter)
        controls.addWidget(self.query_input, 1)
        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("contentFilterMode")
        self.mode_combo.addItem("精确包含", ContentMatchMode.LITERAL.value)
        self.mode_combo.addItem("通配符", ContentMatchMode.WILDCARD.value)
        self.mode_combo.addItem("正则表达式", ContentMatchMode.REGEX.value)
        self.mode_combo.setMaximumWidth(140)
        controls.addWidget(self.mode_combo)
        self.scope_combo = QComboBox()
        self.scope_combo.setObjectName("contentFilterScope")
        if current_account_id is not None:
            label = current_account_email or f"账号 {current_account_id}"
            self.scope_combo.addItem(f"当前邮箱 · {label}", "current")
        self.scope_combo.addItem("全部邮箱", "all")
        self.scope_combo.setMaximumWidth(300)
        controls.addWidget(self.scope_combo)
        self.filter_button = QPushButton("开始筛选")
        self.filter_button.setObjectName("primaryButton")
        self.filter_button.clicked.connect(self.run_filter)
        controls.addWidget(self.filter_button)
        layout.addLayout(controls)

        result_bar = QHBoxLayout()
        self.result_label = QLabel("尚未筛选")
        self.result_label.setObjectName("mutedLabel")
        result_bar.addWidget(self.result_label)
        result_bar.addStretch(1)
        layout.addLayout(result_bar)

        self.table = QTableWidget(0, 5)
        self.table.setObjectName("contentFilterResults")
        self.table.setHorizontalHeaderLabels(
            ("邮箱账号", "邮件主题", "发件人", "匹配内容", "收件时间")
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for column, width in enumerate((220, 240, 190, 390, 145)):
            header.resizeSection(column, width)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.copy_button = QPushButton("复制全部结果")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self.copy_results)
        actions.addWidget(self.copy_button)
        self.export_csv_button = QPushButton("导出 CSV")
        self.export_csv_button.setEnabled(False)
        self.export_csv_button.clicked.connect(lambda: self.export_results("csv"))
        actions.addWidget(self.export_csv_button)
        self.export_txt_button = QPushButton("导出 TXT")
        self.export_txt_button.setEnabled(False)
        self.export_txt_button.clicked.connect(lambda: self.export_results("txt"))
        actions.addWidget(self.export_txt_button)
        actions.addStretch(1)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.accept)
        actions.addWidget(close_button)
        layout.addLayout(actions)

    @property
    def results(self) -> tuple[ContentMatch, ...]:
        return tuple(self._results)

    def run_filter(self) -> None:
        query = self.query_input.text().strip()
        try:
            mode = ContentMatchMode(str(self.mode_combo.currentData()))
            account_id = (
                self._current_account_id
                if self.scope_combo.currentData() == "current"
                else None
            )
            hits = self._messages.list_with_accounts(account_id=account_id)
            self._results = extract_content_matches(hits, query, mode)
        except ValueError as exc:
            QMessageBox.warning(self, "筛选条件无效", str(exc))
            return
        self._populate_results()

    def _populate_results(self) -> None:
        self.table.setRowCount(len(self._results))
        for row, result in enumerate(self._results):
            received = (
                result.received_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
                if result.received_at
                else ""
            )
            values = (
                result.account_email,
                result.subject,
                result.sender,
                result.matched_content,
                received,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 3:
                    item.setToolTip(value)
                self.table.setItem(row, column, item)
        self.result_label.setText(f"共找到 {len(self._results)} 条匹配内容")
        enabled = bool(self._results)
        self.copy_button.setEnabled(enabled)
        self.export_csv_button.setEnabled(enabled)
        self.export_txt_button.setEnabled(enabled)

    def copy_results(self) -> None:
        if not self._results:
            return
        QApplication.clipboard().setText(self._tab_separated_results())
        self.result_label.setText(f"已复制 {len(self._results)} 条匹配内容")

    def export_results(self, file_type: str) -> None:
        if not self._results:
            return
        if file_type == "csv":
            path, _ = QFileDialog.getSaveFileName(
                self, "导出筛选内容", "邮件筛选结果.csv", "CSV (*.csv)"
            )
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "导出筛选内容", "邮件筛选结果.txt", "文本文件 (*.txt)"
            )
        if not path:
            return
        target = Path(path)
        if file_type == "csv":
            self._export_csv(target)
        else:
            target.write_text(self._tab_separated_results(), encoding="utf-8")
        self.result_label.setText(f"已导出到 {target}")

    def _tab_separated_results(self) -> str:
        rows = ["邮箱账号\t邮件主题\t发件人\t匹配内容\t收件时间"]
        for result in self._results:
            received = result.received_at.isoformat() if result.received_at else ""
            rows.append(
                "\t".join(
                    _flat_cell(value)
                    for value in (
                        result.account_email,
                        result.subject,
                        result.sender,
                        result.matched_content,
                        received,
                    )
                )
            )
        return "\n".join(rows)

    def _export_csv(self, path: Path) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("邮箱账号", "邮件主题", "发件人", "匹配内容", "收件时间"))
            for result in self._results:
                writer.writerow(
                    (
                        _safe_spreadsheet_cell(result.account_email),
                        _safe_spreadsheet_cell(result.subject),
                        _safe_spreadsheet_cell(result.sender),
                        _safe_spreadsheet_cell(result.matched_content),
                        result.received_at.isoformat() if result.received_at else "",
                    )
                )


def _flat_cell(value: str) -> str:
    return " ".join(value.replace("\t", " ").splitlines())


def _safe_spreadsheet_cell(value: str) -> str:
    flattened = _flat_cell(value)
    return "'" + flattened if flattened.startswith(("=", "+", "-", "@")) else flattened
