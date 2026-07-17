from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QButtonGroup,
    QGridLayout,
    QWidget,
)

from mailbox_manager.gui.appearance import (
    DEFAULT_THEME,
    THEME_BY_ID,
    THEME_DEFINITIONS,
    ThemeDefinition,
)


class ThemeOptionButton(QAbstractButton):
    """Accessible, code-rendered preview for one application theme."""

    def __init__(self, definition: ThemeDefinition, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.definition = definition
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(f"界面主题：{definition.label}")
        self.setToolTip(f"切换为{definition.label}主题")
        self.setMinimumSize(116, 126)

    def sizeHint(self) -> QSize:
        return QSize(128, 134)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        theme = self.definition
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = self.rect().adjusted(2, 2, -2, -2)
        hovered = self.underMouse() and self.isEnabled()
        application = QApplication.instance()
        current_theme_id = str(
            application.property("maildeskTheme") if application is not None else ""
        )
        current_theme = THEME_BY_ID.get(current_theme_id, THEME_BY_ID[DEFAULT_THEME])
        selected_fill = QColor(theme.accent_soft)
        selected_fill.setAlpha(150 if theme.dark else 125)
        outer_fill = selected_fill if self.isChecked() else QColor(0, 0, 0, 0)
        border = QColor(theme.accent if self.isChecked() else current_theme.border)
        if hovered and not self.isChecked():
            border = QColor(current_theme.accent)
            border.setAlpha(150)
        painter.setPen(QPen(border, 1.5 if self.isChecked() else 1.0))
        painter.setBrush(outer_fill)
        painter.drawRoundedRect(bounds, 14, 14)

        pressed_offset = 1 if self.isDown() else 0
        preview = bounds.adjusted(10, 10 + pressed_offset, -10, -42 + pressed_offset)
        painter.setPen(QPen(QColor(theme.border), 1))
        painter.setBrush(QColor(theme.surface))
        painter.drawRoundedRect(preview, 11, 11)

        sidebar_width = max(22, round(preview.width() * 0.26))
        sidebar = preview.adjusted(0, 0, -(preview.width() - sidebar_width), 0)
        sidebar_color = QColor(theme.panel)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(sidebar_color)
        painter.drawRoundedRect(sidebar, 10, 10)
        painter.drawRect(
            sidebar.right() - 9,
            sidebar.top(),
            10,
            sidebar.height(),
        )

        accent = QColor(theme.accent)
        painter.setBrush(accent)
        painter.drawRoundedRect(
            sidebar.left() + 7,
            sidebar.top() + 10,
            max(12, sidebar_width - 14),
            5,
            2,
            2,
        )
        muted = QColor(theme.muted)
        muted.setAlpha(90)
        painter.setBrush(muted)
        for row, width_ratio in enumerate((0.72, 0.55, 0.66)):
            painter.drawRoundedRect(
                sidebar.left() + 7,
                sidebar.top() + 23 + row * 9,
                max(10, round((sidebar_width - 14) * width_ratio)),
                3,
                1,
                1,
            )

        content_left = sidebar.right() + 10
        content_width = preview.right() - content_left - 8
        painter.setBrush(QColor(theme.panel))
        painter.drawRoundedRect(content_left, preview.top() + 10, content_width, 7, 3, 3)
        painter.drawRoundedRect(
            content_left,
            preview.top() + 25,
            max(14, round(content_width * 0.58)),
            5,
            2,
            2,
        )
        painter.setBrush(QColor(theme.window))
        painter.drawRoundedRect(
            content_left,
            preview.top() + 38,
            content_width,
            max(12, preview.bottom() - preview.top() - 47),
            4,
            4,
        )

        label_font = QFont(self.font())
        minimum_weight = (
            QFont.Weight.DemiBold if self.isChecked() else QFont.Weight.Normal
        )
        label_font.setWeight(
            QFont.Weight(max(int(label_font.weight()), int(minimum_weight)))
        )
        painter.setFont(label_font)
        painter.setPen(QColor(current_theme.text))
        label_rect = bounds.adjusted(4, bounds.height() - 34, -4, -5)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, theme.label)

        if self.isChecked():
            center = bounds.topRight() + QPoint(-7, 9)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme.accent))
            painter.drawEllipse(center, 10, 10)
            painter.setPen(QPen(QColor("#ffffff"), 1.8))
            painter.drawLine(center.x() - 4, center.y(), center.x() - 1, center.y() + 3)
            painter.drawLine(center.x() - 1, center.y() + 3, center.x() + 5, center.y() - 4)


class ThemePicker(QWidget):
    themeChanged = Signal(str)

    def __init__(self, theme_id: str = DEFAULT_THEME, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, ThemeOptionButton] = {}
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)
        for index, definition in enumerate(THEME_DEFINITIONS):
            button = ThemeOptionButton(definition)
            self._buttons[definition.theme_id] = button
            self._group.addButton(button, index)
            layout.addWidget(button, index // 4, index % 4)
            button.toggled.connect(
                lambda checked, selected=definition.theme_id: (
                    self.themeChanged.emit(selected) if checked else None
                )
            )
        layout.setColumnStretch(4, 1)
        self.set_current_theme(theme_id)

    def current_theme(self) -> str:
        checked = self._group.checkedButton()
        if isinstance(checked, ThemeOptionButton):
            return checked.definition.theme_id
        return DEFAULT_THEME

    def set_current_theme(self, theme_id: str) -> None:
        normalized = theme_id if theme_id in THEME_BY_ID else DEFAULT_THEME
        self._buttons[normalized].setChecked(True)
