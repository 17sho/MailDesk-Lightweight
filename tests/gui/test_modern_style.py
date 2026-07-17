from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QCheckBox,
    QMenu,
    QRadioButton,
    QStyle,
    QStyleOptionButton,
)

from mailbox_manager.gui.modern_style import MailDeskProxyStyle


def _render_checkbox(style: MailDeskProxyStyle, state: QStyle.StateFlag) -> QImage:
    image = QImage(24, 24, QImage.Format.Format_ARGB32)
    image.fill(0)
    option = QStyleOptionButton()
    option.rect.setRect(3, 3, 18, 18)
    option.state = QStyle.StateFlag.State_Enabled | state
    painter = QPainter(image)
    style.drawPrimitive(
        QStyle.PrimitiveElement.PE_IndicatorCheckBox,
        option,
        painter,
    )
    painter.end()
    return image


def _render_radio(style: MailDeskProxyStyle, state: QStyle.StateFlag) -> QImage:
    image = QImage(24, 24, QImage.Format.Format_ARGB32)
    image.fill(0)
    option = QStyleOptionButton()
    option.rect.setRect(3, 3, 18, 18)
    option.state = QStyle.StateFlag.State_Enabled | state
    painter = QPainter(image)
    style.drawPrimitive(
        QStyle.PrimitiveElement.PE_IndicatorRadioButton,
        option,
        painter,
    )
    painter.end()
    return image


def test_modern_style_draws_distinct_checked_indicator(qapp) -> None:
    style = MailDeskProxyStyle()
    unchecked = _render_checkbox(style, QStyle.StateFlag.State_Off)
    checked = _render_checkbox(style, QStyle.StateFlag.State_On)

    assert unchecked != checked
    center = checked.pixelColor(12, 12)
    assert center.blue() > center.red()


def test_unchecked_hover_does_not_resemble_selected_state(qapp) -> None:
    style = MailDeskProxyStyle()
    hovered = _render_checkbox(
        style,
        QStyle.StateFlag.State_Off | QStyle.StateFlag.State_MouseOver,
    )

    vivid_blue_pixels = 0
    for y in range(hovered.height()):
        for x in range(hovered.width()):
            color = hovered.pixelColor(x, y)
            if (
                color.alpha() > 0
                and color.blue() > 180
                and color.blue() - color.red() > 70
            ):
                vivid_blue_pixels += 1

    assert vivid_blue_pixels == 0


def test_modern_style_draws_distinct_radio_indicator(qapp) -> None:
    style = MailDeskProxyStyle()
    unchecked = _render_radio(style, QStyle.StateFlag.State_Off)
    checked = _render_radio(style, QStyle.StateFlag.State_On)

    assert unchecked != checked
    center = checked.pixelColor(12, 12)
    assert center.blue() > center.red()


def test_modern_style_uses_consistent_indicator_metrics(qapp) -> None:
    style = MailDeskProxyStyle()
    checkbox = QCheckBox()
    radio = QRadioButton()
    menu = QMenu()

    assert style.pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth, widget=checkbox) == 18
    assert style.pixelMetric(QStyle.PixelMetric.PM_IndicatorHeight, widget=menu) == 18
    assert (
        style.pixelMetric(QStyle.PixelMetric.PM_ExclusiveIndicatorWidth, widget=radio)
        == 18
    )


def test_modern_style_preserves_checkbox_click_toggle(qapp) -> None:
    checkbox = QCheckBox("同时扫描垃圾邮件与已删除邮件")
    checkbox.setStyle(MailDeskProxyStyle())
    checkbox.show()
    qapp.processEvents()

    QTest.mouseClick(
        checkbox,
        Qt.MouseButton.LeftButton,
        pos=QPoint(9, checkbox.height() // 2),
    )

    assert checkbox.isChecked() is True
