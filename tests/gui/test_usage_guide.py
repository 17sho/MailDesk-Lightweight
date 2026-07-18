from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QFrame, QLabel

from mailbox_manager.gui.main_window import MainWindow
from mailbox_manager.gui.settings_dialog import EnterpriseSettingsDialog
from mailbox_manager.gui.usage_guide import UsageGuideDialog, UsageGuidePage
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
    assert dialog.navigation.count() == dialog.pages.count() == 9


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
    assert "账号、搜索、阅读器与发件" in text
    assert "系统更新" in text
    assert "数据与安全" in text


def test_usage_guide_is_text_only_with_spacious_sections(qtbot) -> None:
    page = UsageGuidePage()
    qtbot.addWidget(page)
    sections = [
        frame
        for frame in page.findChildren(QFrame)
        if frame.objectName() == "settingsCard"
    ]
    bodies = page.findChildren(QLabel, "guideBody")
    margins = page.widget().layout().contentsMargins()

    assert len(sections) >= 7
    assert bodies
    assert all(label.pixmap().isNull() for label in page.findChildren(QLabel))
    assert any("\n\n" in label.text() for label in bodies)
    assert page.widget().layout().spacing() >= 22
    assert margins.left() >= 38 and margins.right() >= 38


def test_usage_guide_images_are_not_packaged() -> None:
    root = Path(__file__).resolve().parents[2]

    assert not (root / "src" / "mailbox_manager" / "assets" / "guide").exists()
    for spec_name in ("mailbox-manager.spec", "mailbox-manager-macos.spec"):
        spec = (root / spec_name).read_text(encoding="utf-8")
        assert '"assets" / "guide"' not in spec


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
