from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QProxyStyle,
    QStyle,
    QStyleOption,
    QWidget,
)

_CHECK_PRIMITIVES = {
    QStyle.PrimitiveElement.PE_IndicatorCheckBox,
    QStyle.PrimitiveElement.PE_IndicatorItemViewItemCheck,
    QStyle.PrimitiveElement.PE_IndicatorMenuCheckMark,
}


class MailDeskProxyStyle(QProxyStyle):
    """Keep native widget behaviour while drawing consistent check indicators."""

    def __init__(self) -> None:
        super().__init__("Fusion")

    def drawPrimitive(
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        if element in _CHECK_PRIMITIVES:
            self._draw_check_indicator(element, option, painter, widget)
            return
        super().drawPrimitive(element, option, painter, widget)

    def pixelMetric(
        self,
        metric: QStyle.PixelMetric,
        option: QStyleOption | None = None,
        widget: QWidget | None = None,
    ) -> int:
        if metric in {
            QStyle.PixelMetric.PM_IndicatorWidth,
            QStyle.PixelMetric.PM_IndicatorHeight,
        }:
            return 17
        return super().pixelMetric(metric, option, widget)

    @staticmethod
    def _draw_check_indicator(
        element: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None,
    ) -> None:
        del widget
        state = option.state
        checked = bool(state & QStyle.StateFlag.State_On)
        partial = bool(state & QStyle.StateFlag.State_NoChange)
        enabled = bool(state & QStyle.StateFlag.State_Enabled)
        hovered = bool(state & QStyle.StateFlag.State_MouseOver)
        application = QApplication.instance()
        dark = bool(
            application is not None
            and application.property("maildeskDarkTheme") is True
        )

        size = min(17.0, float(option.rect.width()), float(option.rect.height()))
        bounds = QRectF(
            option.rect.center().x() - size / 2,
            option.rect.center().y() - size / 2,
            size,
            size,
        ).adjusted(0.75, 0.75, -0.75, -0.75)
        accent = QColor("#3b82f6" if dark else "#2563eb")
        surface = QColor("#182230" if dark else "#ffffff")
        border = QColor("#526177" if dark else "#b8c5d6")
        if hovered and not (checked or partial):
            border = QColor("#60a5fa" if dark else "#3b82f6")
            surface = QColor("#172a44" if dark else "#eff6ff")
        fill = accent if checked or partial else surface
        if not enabled:
            fill.setAlpha(120)
            border.setAlpha(120)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(accent if checked or partial else border, 1.2))
        painter.setBrush(fill)
        painter.drawRoundedRect(bounds, 4.2, 4.2)

        if checked:
            tick = QPainterPath()
            tick.moveTo(bounds.left() + bounds.width() * 0.24, bounds.center().y())
            tick.lineTo(
                bounds.left() + bounds.width() * 0.43,
                bounds.top() + bounds.height() * 0.69,
            )
            tick.lineTo(
                bounds.left() + bounds.width() * 0.77,
                bounds.top() + bounds.height() * 0.31,
            )
            pen = QPen(QColor("#ffffff"), 1.9)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(tick)
        elif partial:
            pen = QPen(QColor("#ffffff"), 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(
                bounds.left() + bounds.width() * 0.28,
                bounds.center().y(),
                bounds.right() - bounds.width() * 0.28,
                bounds.center().y(),
            )
        painter.restore()


def install_modern_style(application: QApplication) -> None:
    """Install the shared indicator style once for the whole application."""

    if isinstance(application.style(), MailDeskProxyStyle):
        return
    application.setStyle(MailDeskProxyStyle())
