from __future__ import annotations

from enum import StrEnum

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mailbox_manager.gui.icons import line_icon
from mailbox_manager.gui.motion import SmoothProgressBar


class UpdateDialogState(StrEnum):
    """Visible states of :class:`UpdateDialog`."""

    AVAILABLE = "available"
    DOWNLOADING = "downloading"
    READY = "ready"
    ERROR = "error"


class UpdateDialog(QDialog):
    """Modern, service-agnostic UI for the application update workflow.

    The dialog deliberately does not perform network or installer work.  The
    owning window listens to the request signals and feeds progress or result
    state back through the public ``set_*`` methods.
    """

    downloadRequested = Signal(str)
    skipVersionRequested = Signal(str)
    installRequested = Signal(str)
    laterRequested = Signal()
    stateChanged = Signal(object)

    def __init__(
        self,
        current_version: str,
        latest_version: str,
        release_notes: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.current_version = current_version.strip()
        self.latest_version = latest_version.strip()
        self.release_notes = release_notes.strip()
        self._state = UpdateDialogState.AVAILABLE
        self._drag_offset = None

        self.setObjectName("updateDialog")
        self.setWindowTitle("发现新版本")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setMinimumSize(620, 540)
        self.resize(740, 650)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)

        self.card = QFrame()
        self.card.setObjectName("updateCard")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        self.header = self._build_header()
        card_layout.addWidget(self.header)
        card_layout.addWidget(self._build_content(), 1)
        card_layout.addWidget(self._build_footer())
        outer.addWidget(self.card)

        self._apply_state()

    @property
    def state(self) -> UpdateDialogState:
        return self._state

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("updateHeader")
        header.installEventFilter(self)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 22, 22, 20)
        layout.setSpacing(14)

        self.header_icon = QLabel()
        self.header_icon.setObjectName("updateHeaderIcon")
        self.header_icon.setFixedSize(46, 46)
        self.header_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_icon.setPixmap(line_icon("sparkles", "#ffffff", 23).pixmap(23, 23))
        layout.addWidget(self.header_icon)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        self.title_label = QLabel()
        self.title_label.setObjectName("updateTitle")
        self.title_label.setAccessibleName("更新状态")
        self.title_label.installEventFilter(self)
        self.header_subtitle = QLabel("MailDesk 在线升级")
        self.header_subtitle.setObjectName("updateHeaderSubtitle")
        self.header_subtitle.installEventFilter(self)
        title_layout.addWidget(self.title_label)
        title_layout.addWidget(self.header_subtitle)
        layout.addLayout(title_layout)
        layout.addStretch(1)

        self.close_button = QToolButton()
        self.close_button.setObjectName("updateCloseButton")
        self.close_button.setIcon(line_icon("close", "#94a3b8", 18))
        self.close_button.setIconSize(QSize(18, 18))
        self.close_button.setToolTip("稍后处理")
        self.close_button.setAccessibleName("关闭更新窗口")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setFixedSize(34, 34)
        self.close_button.clicked.connect(self._on_later)
        layout.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
        return header

    def _build_content(self) -> QWidget:
        content = QWidget()
        content.setObjectName("updateContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(12)

        self.version_badge = QLabel()
        self.version_badge.setObjectName("updateVersionBadge")
        self.version_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.version_badge.setMinimumHeight(28)
        self.version_badge.setMaximumWidth(180)
        layout.addWidget(self.version_badge)

        self.summary_label = QLabel()
        self.summary_label.setObjectName("updateSummary")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.summary_label)

        separator = QFrame()
        separator.setObjectName("updateSeparator")
        separator.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(separator)

        notes_title = QLabel("更新内容")
        notes_title.setObjectName("updateSectionTitle")
        layout.addWidget(notes_title)

        self.notes_browser = QTextBrowser()
        self.notes_browser.setObjectName("updateReleaseNotes")
        self.notes_browser.setAccessibleName("版本更新内容")
        self.notes_browser.setOpenExternalLinks(False)
        self.notes_browser.anchorClicked.connect(self._open_release_link)
        self.notes_browser.setReadOnly(True)
        self.notes_browser.document().setDocumentMargin(10)
        layout.addWidget(self.notes_browser, 1)

        self.progress_panel = QFrame()
        self.progress_panel.setObjectName("updateProgressPanel")
        progress_layout = QVBoxLayout(self.progress_panel)
        progress_layout.setContentsMargins(14, 11, 14, 12)
        progress_layout.setSpacing(7)
        progress_header = QHBoxLayout()
        progress_header.setSpacing(8)
        self.progress_status_label = QLabel()
        self.progress_status_label.setObjectName("updateProgressStatus")
        self.progress_percent_label = QLabel()
        self.progress_percent_label.setObjectName("updateProgressPercent")
        progress_header.addWidget(self.progress_status_label)
        progress_header.addStretch(1)
        progress_header.addWidget(self.progress_percent_label)
        progress_layout.addLayout(progress_header)

        self.progress_bar = SmoothProgressBar()
        self.progress_bar.setObjectName("updateProgressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setAccessibleName("更新下载进度")
        progress_layout.addWidget(self.progress_bar)

        self.progress_detail_label = QLabel()
        self.progress_detail_label.setObjectName("updateProgressDetail")
        self.progress_detail_label.setWordWrap(True)
        progress_layout.addWidget(self.progress_detail_label)
        layout.addWidget(self.progress_panel)
        return content

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("updateFooter")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(28, 16, 28, 18)
        layout.setSpacing(10)

        layout.addStretch(1)
        self.later_button = QPushButton("稍后")
        self.later_button.setObjectName("secondaryButton")
        self.later_button.setAccessibleName("稍后处理更新")
        self.later_button.clicked.connect(self._on_later)
        layout.addWidget(self.later_button)

        self.skip_button = QPushButton("跳过此版本")
        self.skip_button.setObjectName("secondaryButton")
        self.skip_button.setAccessibleName("跳过当前更新版本")
        self.skip_button.clicked.connect(self._on_skip)
        layout.addWidget(self.skip_button)

        self.primary_button = QPushButton()
        self.primary_button.setObjectName("primaryButton")
        self.primary_button.setAccessibleName("立即更新")
        self.primary_button.setIcon(line_icon("download", "#ffffff", 18))
        self.primary_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.primary_button.clicked.connect(self._on_primary)
        layout.addWidget(self.primary_button)
        return footer

    def set_release(
        self,
        current_version: str,
        latest_version: str,
        release_notes: str = "",
    ) -> None:
        """Replace the displayed release and return to the available state."""

        self.current_version = current_version.strip()
        self.latest_version = latest_version.strip()
        self.release_notes = release_notes.strip()
        self._set_state(UpdateDialogState.AVAILABLE)

    def set_downloading(self) -> None:
        """Show a determinate download starting at zero percent."""

        self._set_state(UpdateDialogState.DOWNLOADING)
        self.set_download_progress(0)

    def set_download_progress(
        self,
        percent: int | None,
        *,
        received_bytes: int | None = None,
        total_bytes: int | None = None,
    ) -> None:
        """Update progress; ``None`` represents an indeterminate download."""

        if self._state is not UpdateDialogState.DOWNLOADING:
            self._set_state(UpdateDialogState.DOWNLOADING)

        safe_percent: int | None = None
        if percent is None:
            self.progress_bar.stop_motion()
            self.progress_bar.setRange(0, 0)
            self.progress_percent_label.setText("准备中")
            self.primary_button.setText("正在准备下载")
        else:
            safe_percent = max(0, min(100, int(percent)))
            self.progress_bar.setRange(0, 100)
            self.progress_bar.set_animated_value(safe_percent)
            self.progress_percent_label.setText(f"{safe_percent}%")
            self.primary_button.setText(f"正在下载 {safe_percent}%")

        if received_bytes is not None and total_bytes is not None and total_bytes > 0:
            detail = f"{_format_bytes(received_bytes)} / {_format_bytes(total_bytes)}"
        elif received_bytes is not None:
            detail = f"已下载 {_format_bytes(received_bytes)}"
        elif safe_percent == 100:
            detail = "文件下载完成，正在执行安全校验…"
        else:
            detail = "可关闭此窗口，下载会继续在后台进行。"
        self.progress_detail_label.setText(detail)

    def set_download_bytes(self, received_bytes: int, total_bytes: int | None) -> None:
        """Update progress from worker byte counts and calculate the percentage."""

        percent = (
            round(received_bytes * 100 / total_bytes)
            if total_bytes is not None and total_bytes > 0
            else None
        )
        self.set_download_progress(
            percent,
            received_bytes=received_bytes,
            total_bytes=total_bytes,
        )

    def set_download_status(self, message: str) -> None:
        """Display a worker status such as verification or safe extraction."""

        if self._state is not UpdateDialogState.DOWNLOADING:
            self._set_state(UpdateDialogState.DOWNLOADING)
        self.progress_status_label.setText(message.strip() or "正在处理更新")

    def set_download_complete(self) -> None:
        """Show the final restart-and-install confirmation state."""

        self._set_state(UpdateDialogState.READY)

    def set_install_status(self, status: str, detail: str = "") -> None:
        """Show a responsive, non-cancellable installer hand-off state."""

        if self._state is not UpdateDialogState.READY:
            self._set_state(UpdateDialogState.READY)
        self.progress_status_label.setText(status.strip() or "正在准备安装")
        self.progress_detail_label.setText(
            detail.strip() or "正在校验安装文件，完成后将自动关闭并重新启动。"
        )
        self.primary_button.setEnabled(False)
        self.primary_button.setText("正在准备安装…")
        self.later_button.setEnabled(False)

    def set_download_error(self, message: str) -> None:
        """Show a recoverable error and offer a retry action."""

        self._set_state(UpdateDialogState.ERROR)
        self.progress_detail_label.setText(
            message.strip() or "下载未能完成，请检查网络后重试。"
        )

    def _set_state(self, state: UpdateDialogState) -> None:
        changed = state is not self._state
        self._state = state
        self._apply_state()
        if changed:
            self.stateChanged.emit(state)

    def _apply_state(self) -> None:
        self.card.setProperty("state", self._state.value)
        self.version_badge.setText(f"v{_plain_version(self.latest_version)}")
        notes = self.release_notes or "此版本未提供更新说明。"
        self.notes_browser.setMarkdown(notes)
        self.later_button.setEnabled(True)

        if self._state is UpdateDialogState.AVAILABLE:
            self.setWindowTitle("发现新版本")
            self.title_label.setText("发现新版本")
            self.summary_label.setText(
                f"当前版本 v{_plain_version(self.current_version)}，"
                f"新版本 v{_plain_version(self.latest_version)} 已可用。"
            )
            self.progress_panel.hide()
            self.skip_button.show()
            self.later_button.setText("稍后")
            self.primary_button.setText("立即更新")
            self.primary_button.setIcon(line_icon("download", "#ffffff", 18))
            self.primary_button.setAccessibleName("立即更新")
            self.primary_button.setEnabled(True)
        elif self._state is UpdateDialogState.DOWNLOADING:
            self.setWindowTitle("正在下载更新")
            self.title_label.setText("正在下载更新")
            self.summary_label.setText(
                f"MailDesk v{_plain_version(self.latest_version)} 正在后台下载，"
                "您可以继续使用其他功能。"
            )
            self.progress_panel.show()
            self.progress_status_label.setText("下载新版安装包")
            self.skip_button.hide()
            self.later_button.setText("后台运行")
            self.primary_button.setText("正在下载")
            self.primary_button.setIcon(line_icon("download", "#ffffff", 18))
            self.primary_button.setEnabled(False)
        elif self._state is UpdateDialogState.READY:
            self.setWindowTitle("更新已准备就绪")
            self.title_label.setText("更新已准备就绪")
            self.summary_label.setText(
                f"MailDesk v{_plain_version(self.latest_version)} 已下载，"
                "并通过发布者签名与完整性校验。"
            )
            self.progress_panel.show()
            self.progress_status_label.setText("安装包准备完成")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.progress_percent_label.setText("100%")
            self.progress_detail_label.setText(
                "确认后会再次复核官方发布状态，再重启并安全安装。"
            )
            self.skip_button.hide()
            self.later_button.setText("稍后重启")
            self.primary_button.setText("重启并安装")
            self.primary_button.setIcon(line_icon("refresh", "#ffffff", 18))
            self.primary_button.setAccessibleName("重启并安装更新")
            self.primary_button.setEnabled(True)
        else:
            self.setWindowTitle("更新下载失败")
            self.title_label.setText("更新下载失败")
            self.summary_label.setText("下载没有完成，当前版本不会受到影响。")
            self.progress_panel.show()
            self.progress_status_label.setText("下载中断")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_percent_label.setText("未完成")
            self.skip_button.hide()
            self.later_button.setText("关闭")
            self.primary_button.setText("重新下载")
            self.primary_button.setIcon(line_icon("refresh", "#ffffff", 18))
            self.primary_button.setAccessibleName("重新下载更新")
            self.primary_button.setEnabled(True)

        self.card.style().unpolish(self.card)
        self.card.style().polish(self.card)
        self.card.update()

    def _on_primary(self) -> None:
        if self._state in (UpdateDialogState.AVAILABLE, UpdateDialogState.ERROR):
            self.set_downloading()
            self.downloadRequested.emit(self.latest_version)
        elif self._state is UpdateDialogState.READY:
            self.installRequested.emit(self.latest_version)

    def _on_skip(self) -> None:
        self.skipVersionRequested.emit(self.latest_version)
        self.done(QDialog.DialogCode.Rejected)

    def _on_later(self) -> None:
        self.laterRequested.emit()
        self.done(QDialog.DialogCode.Rejected)

    def _open_release_link(self, url: QUrl) -> None:
        if url.scheme().casefold() != "https" or not url.host():
            QMessageBox.warning(
                self,
                "已阻止不安全链接",
                "更新说明只允许打开 HTTPS 链接。",
            )
            return
        host = url.host().casefold().rstrip(".")
        trusted_github = host == "github.com" or host.endswith(".github.com")
        if not trusted_github:
            answer = QMessageBox.question(
                self,
                "打开外部网站",
                f"此链接将离开 GitHub 并打开：\n{host}\n\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer is not QMessageBox.StandardButton.Yes:
                return
        QDesktopServices.openUrl(url)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        drag_targets = (
            getattr(self, "header", None),
            getattr(self, "title_label", None),
            getattr(self, "header_subtitle", None),
        )
        if watched in drag_targets:
            if event.type() == QEvent.Type.MouseButtonPress:
                mouse_event = event
                if isinstance(mouse_event, QMouseEvent) and (
                    mouse_event.button() == Qt.MouseButton.LeftButton
                ):
                    self._drag_offset = (
                        mouse_event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                    )
                    return True
            elif event.type() == QEvent.Type.MouseMove and self._drag_offset is not None:
                mouse_event = event
                if isinstance(mouse_event, QMouseEvent) and (
                    mouse_event.buttons() & Qt.MouseButton.LeftButton
                ):
                    self.move(mouse_event.globalPosition().toPoint() - self._drag_offset)
                    return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self._drag_offset = None
                return True
        return super().eventFilter(watched, event)


def _plain_version(version: str) -> str:
    value = version.strip()
    return value[1:] if value.lower().startswith("v") else value


def _format_bytes(size: int) -> str:
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return "0 B"
