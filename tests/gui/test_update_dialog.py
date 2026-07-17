from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QUrl, qInstallMessageHandler
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QMessageBox

from mailbox_manager.gui import update_dialog as update_dialog_module
from mailbox_manager.gui.motion import SmoothProgressBar
from mailbox_manager.gui.theme import DARK_THEME, LIGHT_THEME
from mailbox_manager.gui.update_dialog import UpdateDialog, UpdateDialogState

RELEASE_NOTES = """\
## 新增

- 支持后台下载更新
- 下载完成后确认重启安装
"""


def _dialog(qtbot) -> UpdateDialog:
    dialog = UpdateDialog("v0.2.0", "0.3.0", RELEASE_NOTES)
    qtbot.addWidget(dialog)
    dialog.show()
    return dialog


def test_available_state_displays_release_and_emits_download_request(qtbot) -> None:
    dialog = _dialog(qtbot)
    download_spy = QSignalSpy(dialog.downloadRequested)

    assert dialog.state is UpdateDialogState.AVAILABLE
    assert dialog.title_label.text() == "发现新版本"
    assert dialog.version_badge.text() == "v0.3.0"
    assert "v0.2.0" in dialog.summary_label.text()
    assert "后台下载更新" in dialog.notes_browser.toPlainText()
    assert dialog.progress_panel.isHidden()
    assert dialog.skip_button.isVisible()

    dialog.primary_button.click()

    assert download_spy.count() == 1
    assert download_spy.at(0)[0] == "0.3.0"
    assert dialog.state is UpdateDialogState.DOWNLOADING
    assert dialog.progress_panel.isVisible()
    assert dialog.primary_button.isEnabled() is False
    assert dialog.later_button.text() == "后台运行"


def test_skip_and_later_are_distinct_actions(qtbot) -> None:
    skipped = _dialog(qtbot)
    skip_spy = QSignalSpy(skipped.skipVersionRequested)
    later_spy = QSignalSpy(skipped.laterRequested)

    skipped.skip_button.click()

    assert skip_spy.count() == 1
    assert skip_spy.at(0)[0] == "0.3.0"
    assert later_spy.count() == 0
    assert skipped.isVisible() is False

    later = _dialog(qtbot)
    later_spy = QSignalSpy(later.laterRequested)
    skip_spy = QSignalSpy(later.skipVersionRequested)

    later.close_button.click()

    assert later_spy.count() == 1
    assert skip_spy.count() == 0
    assert later.isVisible() is False


def test_close_control_uses_a_font_independent_icon(qtbot) -> None:
    dialog = _dialog(qtbot)

    assert dialog.close_button.text() == ""
    assert dialog.close_button.icon().isNull() is False
    assert dialog.close_button.toolTip() == "稍后处理"


def test_download_progress_supports_sizes_clamping_and_indeterminate(qtbot) -> None:
    dialog = _dialog(qtbot)

    dialog.set_download_progress(
        37,
        received_bytes=3 * 1024 * 1024,
        total_bytes=8 * 1024 * 1024,
    )

    assert dialog.state is UpdateDialogState.DOWNLOADING
    assert dialog.progress_bar.minimum() == 0
    assert dialog.progress_bar.maximum() == 100
    qtbot.waitUntil(lambda: dialog.progress_bar.value() == 37, timeout=1000)
    assert dialog.progress_percent_label.text() == "37%"
    assert dialog.progress_detail_label.text() == "3.0 MB / 8.0 MB"

    dialog.set_download_bytes(1 * 1024 * 1024, 4 * 1024 * 1024)
    qtbot.waitUntil(lambda: dialog.progress_bar.value() == 25, timeout=1000)
    assert dialog.progress_detail_label.text() == "1.0 MB / 4.0 MB"

    dialog.set_download_status("正在校验并安全解压…")
    assert dialog.progress_status_label.text() == "正在校验并安全解压…"

    dialog.set_download_progress(120)
    qtbot.waitUntil(lambda: dialog.progress_bar.value() == 100, timeout=1000)
    assert dialog.progress_percent_label.text() == "100%"
    assert "安全校验" in dialog.progress_detail_label.text()

    dialog.set_download_progress(None)
    assert dialog.progress_bar.minimum() == 0
    assert dialog.progress_bar.maximum() == 0
    assert dialog.progress_percent_label.text() == "准备中"


def test_download_progress_retargets_from_current_presented_value(qtbot) -> None:
    dialog = _dialog(qtbot)

    dialog.set_download_progress(72)

    assert isinstance(dialog.progress_bar, SmoothProgressBar)
    assert dialog.progress_bar.motion_target == 72
    assert dialog.progress_bar.motion_running is True
    qtbot.waitUntil(lambda: dialog.progress_bar.value() == 72, timeout=1000)

    dialog.set_download_progress(95)
    qtbot.wait(40)
    presented_value = dialog.progress_bar.value()
    dialog.set_download_progress(48)

    assert dialog.progress_bar.motion_start == presented_value
    assert dialog.progress_bar.motion_target == 48
    assert dialog.progress_bar.motion_duration <= 160
    qtbot.waitUntil(lambda: dialog.progress_bar.value() == 48, timeout=1000)


def test_download_complete_prompts_for_restart_and_install(qtbot) -> None:
    dialog = _dialog(qtbot)
    install_spy = QSignalSpy(dialog.installRequested)
    state_spy = QSignalSpy(dialog.stateChanged)

    dialog.set_download_complete()

    assert dialog.state is UpdateDialogState.READY
    assert dialog.title_label.text() == "更新已准备就绪"
    assert dialog.progress_bar.value() == 100
    assert dialog.progress_percent_label.text() == "100%"
    assert dialog.primary_button.text() == "重启并安装"
    assert dialog.later_button.text() == "稍后重启"
    assert dialog.skip_button.isHidden()
    assert state_spy.count() == 1

    dialog.primary_button.click()

    assert install_spy.count() == 1
    assert install_spy.at(0)[0] == "0.3.0"
    assert dialog.primary_button.isEnabled() is True
    assert dialog.primary_button.text() == "重启并安装"

    dialog.set_install_status("正在校验安装文件")

    assert dialog.primary_button.isEnabled() is False
    assert dialog.primary_button.text() == "正在准备安装…"
    assert dialog.later_button.isEnabled() is False
    assert dialog.progress_status_label.text() == "正在校验安装文件"


def test_download_error_is_recoverable(qtbot) -> None:
    dialog = _dialog(qtbot)
    download_spy = QSignalSpy(dialog.downloadRequested)

    dialog.set_download_error("校验失败，请重新下载")

    assert dialog.state is UpdateDialogState.ERROR
    assert dialog.title_label.text() == "更新下载失败"
    assert dialog.progress_detail_label.text() == "校验失败，请重新下载"
    assert dialog.primary_button.text() == "重新下载"

    dialog.primary_button.click()

    assert download_spy.count() == 1
    assert dialog.state is UpdateDialogState.DOWNLOADING
    assert dialog.progress_bar.value() == 0


def test_set_release_reuses_dialog_and_restores_available_state(qtbot) -> None:
    dialog = _dialog(qtbot)
    dialog.set_download_complete()

    dialog.set_release("0.3.0", "v0.4.0", "- 新的发布说明")

    assert dialog.state is UpdateDialogState.AVAILABLE
    assert dialog.current_version == "0.3.0"
    assert dialog.latest_version == "v0.4.0"
    assert dialog.version_badge.text() == "v0.4.0"
    assert dialog.primary_button.isEnabled() is True
    assert dialog.primary_button.text() == "立即更新"
    assert dialog.skip_button.isHidden() is False
    assert "新的发布说明" in dialog.notes_browser.toPlainText()


def test_release_note_links_block_unsafe_schemes_and_confirm_external_hosts(
    qtbot, monkeypatch
) -> None:
    dialog = _dialog(qtbot)
    opened: list[str] = []
    warnings: list[bool] = []
    monkeypatch.setattr(
        update_dialog_module.QDesktopServices,
        "openUrl",
        lambda url: opened.append(url.toString()) or True,
    )
    monkeypatch.setattr(
        update_dialog_module.QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(True),
    )

    dialog._open_release_link(QUrl("file:///C:/Windows/System32/calc.exe"))

    assert opened == []
    assert warnings == [True]

    monkeypatch.setattr(
        update_dialog_module.QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    dialog._open_release_link(QUrl("https://example.com/release-notes"))
    assert opened == []

    dialog._open_release_link(QUrl("https://github.com/17sho/MailDesk"))
    assert opened == ["https://github.com/17sho/MailDesk"]


@pytest.mark.parametrize(
    "stylesheet",
    [LIGHT_THEME, DARK_THEME],
    ids=["light", "dark"],
)
def test_update_dialog_styles_parse_without_qt_warnings(qtbot, stylesheet: str) -> None:
    app = QApplication.instance()
    assert app is not None
    previous_stylesheet = app.styleSheet()
    messages: list[str] = []

    def message_handler(_message_type, _context, message: str) -> None:
        messages.append(message)

    previous_handler = qInstallMessageHandler(message_handler)
    try:
        app.setStyleSheet(stylesheet)
        dialog = _dialog(qtbot)
        dialog.ensurePolished()
        app.processEvents()

        assert dialog.card.styleSheet() == ""
        assert dialog.primary_button.height() >= 36
        assert dialog.notes_browser.viewport().isVisible()
    finally:
        app.setStyleSheet(previous_stylesheet)
        qInstallMessageHandler(previous_handler)

    stylesheet_warnings = [
        message
        for message in messages
        if "stylesheet" in message.lower() or "unknown property" in message.lower()
    ]
    assert stylesheet_warnings == []
