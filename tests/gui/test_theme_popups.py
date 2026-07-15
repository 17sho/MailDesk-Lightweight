from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, qInstallMessageHandler
from PySide6.QtGui import QFontMetrics, QPalette
from PySide6.QtWidgets import QApplication, QComboBox, QMenu, QToolButton, QWidget

from mailbox_manager.gui.appearance import (
    appearance_palette,
    apply_application_appearance,
    scaled_stylesheet,
)
from mailbox_manager.gui.theme import DARK_THEME, LIGHT_THEME


@pytest.mark.parametrize(
    "stylesheet",
    [LIGHT_THEME, DARK_THEME],
    ids=["light", "dark"],
)
def test_popup_styles_cover_interaction_states(stylesheet: str) -> None:
    required_rules = (
        "QComboBox QAbstractItemView::item:hover",
        "QComboBox QAbstractItemView::item:selected",
        "QComboBox QAbstractItemView::item:disabled",
        "QComboBox QAbstractItemView QScrollBar::handle:vertical:hover",
        "QMenu::item:selected",
        "QMenu::item:checked",
        "QMenu::item:disabled",
        "QMenu::indicator",
        "QMenu::separator",
        "QMenu::scroller",
    )

    for rule in required_rules:
        assert rule in stylesheet


@pytest.mark.parametrize(
    "stylesheet",
    [LIGHT_THEME, DARK_THEME],
    ids=["light", "dark"],
)
def test_popup_styles_parse_and_provide_comfortable_rows(
    qtbot,
    stylesheet: str,
) -> None:
    app = QApplication.instance()
    assert app is not None
    previous_stylesheet = app.styleSheet()
    messages: list[str] = []

    def message_handler(_message_type, _context, message: str) -> None:
        messages.append(message)

    previous_handler = qInstallMessageHandler(message_handler)
    host = QWidget()
    combo = QComboBox(host)
    combo.addItems(["全部状态", "异常账号", "正常可用", "未连接", "连接中"])
    menu = QMenu(host)
    checked_action = menu.addAction("账号")
    checked_action.setCheckable(True)
    checked_action.setChecked(True)
    disabled_action = menu.addAction("暂不可用")
    disabled_action.setEnabled(False)
    menu.addSeparator()
    menu.addAction("导出审计报告")

    try:
        app.setStyleSheet(stylesheet)
        qtbot.addWidget(host)
        host.show()
        combo.ensurePolished()
        combo.showPopup()
        menu.ensurePolished()
        menu.popup(host.mapToGlobal(QPoint(0, host.height())))
        app.processEvents()

        assert combo.view().sizeHintForRow(0) >= 32
        assert menu.actionGeometry(checked_action).height() >= 30
    finally:
        menu.hide()
        combo.hidePopup()
        app.setStyleSheet(previous_stylesheet)
        qInstallMessageHandler(previous_handler)

    stylesheet_warnings = [
        message
        for message in messages
        if "stylesheet" in message.lower() or "unknown property" in message.lower()
    ]
    assert stylesheet_warnings == []


def test_font_scaling_updates_explicit_theme_font_sizes() -> None:
    scaled = scaled_stylesheet("QLabel { font-size: 10px; }", 14)

    assert "font-size: 14px" in scaled


def test_font_scaling_preserves_visual_hierarchy_without_oversizing_titles() -> None:
    scaled = scaled_stylesheet(
        "QLabel#title { font-size: 25px; } QLabel#caption { font-size: 11px; }",
        18,
    )

    assert "font-size: 33px" in scaled
    assert "font-size: 19px" in scaled
    assert "font-size: 45px" not in scaled


@pytest.mark.parametrize("stylesheet", [LIGHT_THEME, DARK_THEME])
def test_theme_uses_only_stable_qt_font_weights(stylesheet: str) -> None:
    import re

    weights = {
        int(match)
        for match in re.findall(r"font-weight\s*:\s*(\d+)", stylesheet)
    }

    assert weights <= {400, 500, 600, 700}
    assert "QToolButton {" in stylesheet
    assert "QMenu {" in stylesheet


def test_large_body_font_keeps_toolbar_and_menu_text_clear(qtbot) -> None:
    app = QApplication.instance()
    assert app is not None
    previous_font = app.font()
    previous_stylesheet = app.styleSheet()
    button = QToolButton()
    button.setText("批量导入")
    menu = QMenu()
    menu.addAction("从文件导入")
    try:
        apply_application_appearance(
            app,
            {
                "font_size": 18,
                "font_weight": 600,
                "dark_theme": False,
            },
        )
        app.setStyleSheet(scaled_stylesheet(LIGHT_THEME, 18))
        qtbot.addWidget(button)
        button.ensurePolished()
        menu.ensurePolished()

        assert button.font().weight() == 500
        assert menu.font().weight() == 400
        assert button.sizeHint().width() > QFontMetrics(button.font()).horizontalAdvance(
            button.text()
        )
    finally:
        menu.deleteLater()
        app.setFont(previous_font)
        app.setStyleSheet(previous_stylesheet)


def test_dark_palette_covers_native_dialog_text_and_selection() -> None:
    palette = appearance_palette(True)

    assert palette.color(QPalette.ColorRole.Window).lightness() < 50
    assert palette.color(QPalette.ColorRole.WindowText).lightness() > 180
    assert palette.color(QPalette.ColorRole.Highlight).blue() > 180
