from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QCheckBox, QMenu, QStyle, QStyleOptionButton

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


def test_modern_style_draws_distinct_checked_indicator(qapp) -> None:
    style = MailDeskProxyStyle()
    unchecked = _render_checkbox(style, QStyle.StateFlag.State_Off)
    checked = _render_checkbox(style, QStyle.StateFlag.State_On)

    assert unchecked != checked
    center = checked.pixelColor(12, 12)
    assert center.blue() > center.red()


def test_modern_style_uses_consistent_indicator_metrics(qapp) -> None:
    style = MailDeskProxyStyle()
    checkbox = QCheckBox()
    menu = QMenu()

    assert style.pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth, widget=checkbox) == 17
    assert style.pixelMetric(QStyle.PixelMetric.PM_IndicatorHeight, widget=menu) == 17
