from __future__ import annotations

import csv
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
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

from mailbox_manager.domain.models import FetchRequest
from mailbox_manager.gui.icons import line_icon
from mailbox_manager.gui.workers import DeepSearchWorker
from mailbox_manager.services.content_filter import (
    ContentMatch,
    ContentMatchMode,
    extract_content_matches,
)
from mailbox_manager.services.fetch_service import FetchService
from mailbox_manager.storage.repositories import AccountRepository, MessageRepository


class ContentFilterDialog(QDialog):
    def __init__(
        self,
        messages: MessageRepository,
        *,
        current_account_id: int | None = None,
        current_account_email: str = "",
        accounts: AccountRepository | None = None,
        fetch_service: FetchService | None = None,
        fetch_request: FetchRequest | None = None,
        thread_pool: QThreadPool | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._messages = messages
        self._current_account_id = current_account_id
        self._accounts = accounts
        self._fetch_service = fetch_service
        self._fetch_request = fetch_request or FetchRequest()
        self._thread_pool = thread_pool
        self._deep_worker: DeepSearchWorker | None = None
        self._deep_stop_event = threading.Event()
        self._results: list[ContentMatch] = []
        self._coverage_total = 0
        self._coverage_loaded = 0
        self.setObjectName("contentFilterDialog")
        self.setWindowTitle("内容筛选与导出")
        self.resize(1080, 680)
        self.setMinimumSize(820, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("utilityDialogHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 18, 24, 17)
        header_layout.setSpacing(13)
        icon = QLabel()
        icon.setObjectName("utilityDialogIcon")
        icon.setFixedSize(42, 42)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(line_icon("filter", "#2563eb", 21).pixmap(21, 21))
        header_layout.addWidget(icon)
        title_copy = QVBoxLayout()
        title_copy.setSpacing(2)
        title = QLabel("筛选邮件中的指定文字或链接")
        title.setObjectName("utilityDialogTitle")
        help_label = QLabel(
            "只输出匹配的链接或文字片段，不导出整封邮件正文"
        )
        help_label.setObjectName("utilityDialogSubtitle")
        help_label.setWordWrap(True)
        title_copy.addWidget(title)
        title_copy.addWidget(help_label)
        header_layout.addLayout(title_copy, 1)
        root.addWidget(header)

        content = QWidget()
        content.setObjectName("utilityDialogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 17, 20, 17)
        layout.setSpacing(11)

        controls_card = QFrame()
        controls_card.setObjectName("filterControlCard")
        controls_layout = QVBoxLayout(controls_card)
        controls_layout.setContentsMargins(14, 12, 14, 13)
        controls_layout.setSpacing(9)
        controls_title = QLabel("筛选条件")
        controls_title.setObjectName("utilitySectionTitle")
        controls_layout.addWidget(controls_title)

        self.query_input = QLineEdit()
        self.query_input.setObjectName("contentFilterQuery")
        self.query_input.setPlaceholderText(
            "输入文字、域名或链接，例如 Reset Password、example.com、https://example.com/*"
        )
        self.query_input.setClearButtonEnabled(True)
        self.query_input.returnPressed.connect(self.run_filter)
        controls_layout.addWidget(self.query_input)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("contentFilterMode")
        self.mode_combo.addItem("精确包含", ContentMatchMode.LITERAL.value)
        self.mode_combo.addItem("通配符", ContentMatchMode.WILDCARD.value)
        self.mode_combo.addItem("正则表达式", ContentMatchMode.REGEX.value)
        self.mode_combo.setMinimumWidth(140)
        self.mode_combo.setMaximumWidth(180)
        controls.addWidget(self.mode_combo)
        self.scope_combo = QComboBox()
        self.scope_combo.setObjectName("contentFilterScope")
        if current_account_id is not None:
            label = current_account_email or f"账号 {current_account_id}"
            self.scope_combo.addItem(f"当前邮箱 · {label}", "current")
        self.scope_combo.addItem("全部邮箱", "all")
        self.scope_combo.setMaximumWidth(300)
        self.scope_combo.currentIndexChanged.connect(self._refresh_coverage_label)
        controls.addWidget(self.scope_combo)
        controls.addStretch(1)
        self.filter_button = QPushButton("开始筛选")
        self.filter_button.setObjectName("primaryButton")
        self.filter_button.setMinimumWidth(96)
        self.filter_button.setMaximumWidth(190)
        self.filter_button.clicked.connect(self.run_filter)
        controls.addWidget(self.filter_button)
        self.deep_filter_button = QPushButton("联网深度筛选")
        self.deep_filter_button.setMinimumWidth(118)
        self.deep_filter_button.setMaximumWidth(240)
        self.deep_filter_button.setToolTip(
            "由邮箱服务器搜索正文，只下载命中的邮件；POP3 邮箱需要逐封扫描"
        )
        self.deep_filter_button.setObjectName("secondaryButton")
        self.deep_filter_button.clicked.connect(self.run_deep_filter)
        controls.addWidget(self.deep_filter_button)
        controls_layout.addLayout(controls)
        guidance = QLabel(
            "精确包含适合普通文字和域名；通配符支持 * 和 ?；"
            "正则表达式适合订单号、验证码等固定格式。"
        )
        guidance.setObjectName("filterGuidance")
        guidance.setWordWrap(True)
        controls_layout.addWidget(guidance)
        layout.addWidget(controls_card)

        result_bar_frame = QFrame()
        result_bar_frame.setObjectName("filterResultBar")
        result_bar = QHBoxLayout(result_bar_frame)
        result_bar.setContentsMargins(2, 0, 2, 0)
        result_bar.setSpacing(8)
        result_title = QLabel("筛选结果")
        result_title.setObjectName("utilitySectionTitle")
        result_bar.addWidget(result_title)
        self.result_label = QLabel("尚未筛选")
        self.result_label.setObjectName("mutedLabel")
        result_bar.addWidget(self.result_label)
        result_bar.addStretch(1)
        layout.addWidget(result_bar_frame)

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
        root.addWidget(content, 1)

        footer = QFrame()
        footer.setObjectName("utilityDialogFooter")
        actions = QHBoxLayout(footer)
        actions.setContentsMargins(20, 13, 20, 13)
        actions.setSpacing(8)
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
        close_button.setObjectName("secondaryButton")
        close_button.clicked.connect(self.accept)
        actions.addWidget(close_button)
        root.addWidget(footer)
        self._refresh_coverage_label()
        self.query_input.textChanged.connect(self._refresh_deep_button)
        self.mode_combo.currentIndexChanged.connect(self._refresh_deep_button)
        self._refresh_deep_button()

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
            self._coverage_total = len(hits)
            self._coverage_loaded = sum(hit.message.body_loaded for hit in hits)
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
        coverage = (
            f"已搜索 {self._coverage_loaded}/{self._coverage_total} 封正文"
            if self._coverage_total
            else "当前范围没有本地邮件"
        )
        unloaded = max(0, self._coverage_total - self._coverage_loaded)
        pending = f"；另有 {unloaded} 封正文尚未加载" if unloaded else ""
        self.result_label.setText(
            f"共找到 {len(self._results)} 条匹配内容 · {coverage}{pending}"
        )
        enabled = bool(self._results)
        self.copy_button.setEnabled(enabled)
        self.export_csv_button.setEnabled(enabled)
        self.export_txt_button.setEnabled(enabled)

    def _refresh_coverage_label(self, _index: int = -1) -> None:
        account_id = (
            self._current_account_id
            if self.scope_combo.currentData() == "current"
            else None
        )
        self._coverage_total, self._coverage_loaded = self._messages.body_load_counts(
            account_id=account_id
        )
        unloaded = max(0, self._coverage_total - self._coverage_loaded)
        if not self._coverage_total:
            self.result_label.setText("当前范围没有本地邮件")
        elif unloaded:
            self.result_label.setText(
                f"当前范围 {self._coverage_total} 封邮件，已加载正文 "
                f"{self._coverage_loaded} 封，尚未加载 {unloaded} 封"
            )
        else:
            self.result_label.setText(
                f"当前范围 {self._coverage_total} 封邮件，正文均已加载"
            )
        self._refresh_deep_button()

    def _refresh_deep_button(self, _value: object = None) -> None:
        if self._deep_worker is not None:
            return
        available = (
            self._accounts is not None
            and self._fetch_service is not None
            and self._thread_pool is not None
            and self._coverage_loaded < self._coverage_total
            and bool(self.query_input.text().strip())
            and self.mode_combo.currentData() == ContentMatchMode.LITERAL.value
        )
        self.deep_filter_button.setEnabled(available)

    def run_deep_filter(self) -> None:
        if self._deep_worker is not None:
            self._deep_stop_event.set()
            self.deep_filter_button.setText("正在停止…")
            self.deep_filter_button.setEnabled(False)
            return
        query = self.query_input.text().strip()
        if not query:
            QMessageBox.warning(self, "深度筛选", "请先输入需要搜索的文字")
            return
        if self.mode_combo.currentData() != ContentMatchMode.LITERAL.value:
            QMessageBox.information(
                self,
                "深度筛选",
                "联网深度筛选当前只支持“精确包含”；通配符和正则仍筛选本地正文。",
            )
            return
        if self._accounts is None or self._fetch_service is None or self._thread_pool is None:
            return
        if self.scope_combo.currentData() == "current":
            account = (
                self._accounts.get(self._current_account_id)
                if self._current_account_id is not None
                else None
            )
            selected_accounts = [account] if account is not None else []
        else:
            selected_accounts = self._accounts.list_all()
        if not selected_accounts:
            QMessageBox.information(self, "深度筛选", "当前范围没有可搜索的邮箱账号")
            return
        answer = QMessageBox.question(
            self,
            "确认联网深度筛选",
            f"将连接 {len(selected_accounts)} 个邮箱，在服务器中搜索“{query[:80]}”。\n\n"
            "IMAP 和 Microsoft Graph 只下载命中的邮件；POP3 不支持服务端搜索，"
            "需要逐封扫描。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._deep_stop_event = threading.Event()
        worker = DeepSearchWorker(
            self._fetch_service,
            selected_accounts,
            query,
            self._fetch_request,
            self._deep_stop_event,
        )
        self._deep_worker = worker
        worker.signals.progress.connect(self._deep_search_progress)
        worker.signals.result.connect(self._deep_search_result)
        worker.signals.finished.connect(self._deep_search_finished)
        self.filter_button.setEnabled(False)
        self.deep_filter_button.setText("停止深度筛选")
        self.deep_filter_button.setEnabled(True)
        self._thread_pool.start(worker)

    def _deep_search_progress(self, completed: int, total: int, email: str) -> None:
        self.result_label.setText(
            f"联网深度筛选 {completed}/{total} · {email}"
        )

    def _deep_search_result(self, summary: object) -> None:
        values = summary if isinstance(summary, dict) else {}
        self._refresh_coverage_label()
        self.run_filter()
        errors = values.get("errors", ())
        suffix = f"；{len(errors)} 个账号失败" if errors else ""
        cancelled = "；任务已停止" if values.get("cancelled") else ""
        self.result_label.setText(
            self.result_label.text()
            + f" · 服务器命中 {int(values.get('matches', 0))} 封{suffix}{cancelled}"
        )

    def _deep_search_finished(self) -> None:
        self._deep_worker = None
        self.filter_button.setEnabled(True)
        self.deep_filter_button.setText("联网深度筛选")
        self._refresh_deep_button()

    def done(self, result: int) -> None:
        self._deep_stop_event.set()
        super().done(result)

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
