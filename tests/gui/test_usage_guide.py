from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QLabel

from mailbox_manager.gui.main_window import MainWindow
from mailbox_manager.gui.settings_dialog import EnterpriseSettingsDialog
from mailbox_manager.gui.usage_guide import GuideScreenshot, UsageGuideDialog, UsageGuidePage
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.repositories import AccountRepository, MessageRepository


def _visible_text(widget) -> str:
    return "\n".join(label.text() for label in widget.findChildren(QLabel))


def test_usage_guide_is_not_embedded_in_system_settings(qtbot) -> None:
    dialog = EnterpriseSettingsDialog()
    qtbot.addWidget(dialog)

    labels = [dialog.navigation.item(row).text() for row in range(dialog.navigation.count())]

    assert "使用说明" not in labels
    assert dialog.navigation.count() == dialog.pages.count() == 10


def test_tools_menu_opens_the_usage_guide(qtbot, tmp_path) -> None:
    database = Database(tmp_path / "usage-guide.db")
    database.initialize()
    window = MainWindow(
        AccountRepository(database, CredentialCipher.from_raw_key(b"H" * 32)),
        MessageRepository(database),
    )
    qtbot.addWidget(window)
    window.show()

    assert window.usage_guide_action in window.tools_menu_button.menu().actions()
    assert window.usage_guide_action.shortcut().toString() == "F1"

    window.usage_guide_action.trigger()

    assert window._usage_guide_dialog is not None
    assert window._usage_guide_dialog.isVisible() is True


def test_usage_guide_dialog_is_resizable_and_contains_the_manual(qtbot) -> None:
    dialog = UsageGuideDialog()
    qtbot.addWidget(dialog)
    text = _visible_text(dialog)

    assert dialog.windowTitle() == "MailDesk · 使用说明"
    assert dialog.isSizeGripEnabled() is True
    assert "快速开始" in text
    assert "账号与邮件" in text
    assert "系统更新" in text
    assert "数据与安全" in text


def test_usage_guide_uses_real_annotated_application_screenshots(qtbot) -> None:
    page = UsageGuidePage()
    qtbot.addWidget(page)
    screenshots = page.findChildren(GuideScreenshot)

    assert len(screenshots) == 3
    assert all(item.accessibleName() for item in screenshots)
    assert all(item.source_path.is_file() for item in screenshots)
    assert all(not item.original_pixmap.isNull() for item in screenshots)
    assert all(item.original_pixmap.width() >= 1000 for item in screenshots)
    assert all("1" in item.legend_label.text() for item in screenshots)


def test_usage_guide_remains_scrollable_at_large_text_and_narrow_width(qtbot) -> None:
    page = UsageGuidePage()
    qtbot.addWidget(page)
    font = QFont(page.font())
    font.setPointSize(18)
    font.setWeight(QFont.Weight.DemiBold)
    page.setFont(font)
    page.resize(520, 620)
    page.show()
    QApplication.processEvents()

    assert page.widgetResizable() is True
    assert page.minimumSizeHint().width() <= 520
    assert page.widget().minimumSizeHint().width() <= page.viewport().width()
    assert all(
        label.wordWrap()
        for label in page.findChildren(QLabel)
        if label.objectName() in {"settingsPageCaption", "settingsCardCaption", "guideBody"}
    )
