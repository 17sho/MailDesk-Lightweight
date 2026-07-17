from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mailbox_manager.domain.status import STATUS_LABELS
from mailbox_manager.gui.appearance import DEFAULT_THEME, THEME_BY_ID
from mailbox_manager.gui.icons import line_icon
from mailbox_manager.storage.enterprise_repositories import StatisticsRepository
from mailbox_manager.storage.repositories import MessageRepository


@dataclass(frozen=True, slots=True)
class QuickActionDefinition:
    """Public metadata used by both the dashboard and the settings page."""

    action_id: str
    label: str
    icon: str
    description: str


QUICK_ACTION_DEFINITIONS = (
    QuickActionDefinition("accounts", "账号管理", "users", "查看、选择和管理全部邮箱账号"),
    QuickActionDefinition("fetch", "开始批量取件", "bolt", "立即为选中的账号批量收取邮件"),
    QuickActionDefinition("add_account", "添加邮箱", "mail-plus", "添加邮箱或打开批量导入"),
    QuickActionDefinition("content_filter", "筛选与导出", "filter", "按自定义内容筛选并导出结果"),
    QuickActionDefinition("abnormal_accounts", "异常账号", "warning", "只查看需要处理的异常账号"),
)
QUICK_ACTIONS_BY_ID = {
    definition.action_id: definition for definition in QUICK_ACTION_DEFINITIONS
}
DEFAULT_QUICK_ACTION_IDS = ("accounts", "fetch", "add_account", "content_filter")
CONFIGURED_QUICK_ACTION_COUNT = 4
MAX_QUICK_ACTIONS = 6
METRICS_COMPACT_BREAKPOINT = 1120
PANELS_STACK_BREAKPOINT = 840

_QUICK_ACTION_ALIASES = {
    "account_management": "accounts",
    "batch_fetch": "fetch",
    "import": "add_account",
    "filter_export": "content_filter",
    "abnormal": "abnormal_accounts",
}


def normalize_quick_action_ids(action_ids: Sequence[str] | None) -> tuple[str, ...]:
    """Return a safe, stable shortcut list and recover from damaged settings."""

    if action_ids is None:
        return DEFAULT_QUICK_ACTION_IDS
    normalized: list[str] = []
    for raw_action_id in action_ids:
        raw_value = str(raw_action_id).strip()
        action_id = _QUICK_ACTION_ALIASES.get(raw_value, raw_value)
        if action_id in QUICK_ACTIONS_BY_ID and action_id not in normalized:
            normalized.append(action_id)
        if len(normalized) >= MAX_QUICK_ACTIONS:
            break
    return tuple(normalized) or DEFAULT_QUICK_ACTION_IDS


def configured_quick_action_ids(action_ids: Sequence[str] | None) -> tuple[str, ...]:
    """Return the four unique actions represented by the settings page."""

    normalized = list(normalize_quick_action_ids(action_ids))
    for definition in QUICK_ACTION_DEFINITIONS:
        if definition.action_id not in normalized:
            normalized.append(definition.action_id)
        if len(normalized) >= CONFIGURED_QUICK_ACTION_COUNT:
            break
    return tuple(normalized[:CONFIGURED_QUICK_ACTION_COUNT])


class _MetricCard(QFrame):
    activated = Signal()

    def __init__(
        self,
        metric_id: str,
        title: str,
        hint: str,
        icon: str,
        color: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("dashboardMetricCard")
        self.setProperty("metricId", metric_id)
        self.setProperty("accent", color)
        self.setMinimumHeight(104)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(17, 15, 15, 15)
        layout.setSpacing(13)

        icon_label = QLabel()
        icon_label.setObjectName("dashboardMetricIcon")
        icon_label.setProperty("metricId", metric_id)
        icon_label.setFixedSize(48, 48)
        icon_label.setPixmap(line_icon(icon, color, 23).pixmap(23, 23))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        copy = QVBoxLayout()
        copy.setSpacing(0)
        title_label = QLabel(title)
        title_label.setObjectName("dashboardMetricLabel")
        self.value_label = QLabel("0")
        self.value_label.setObjectName("dashboardMetricValue")
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("dashboardMetricHint")
        copy.addWidget(title_label)
        copy.addWidget(self.value_label)
        copy.addWidget(self.hint_label)
        layout.addLayout(copy, 1)

        self.action_button = QToolButton()
        self.action_button.setObjectName("dashboardMetricAction")
        self.action_button.setProperty("metricId", metric_id)
        self.action_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.action_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_button.hide()
        self.action_button.clicked.connect(self.activated.emit)
        layout.addWidget(self.action_button, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_value(self, value: int) -> None:
        self.value_label.setText(f"{value:,}")

    def set_hint(self, hint: str) -> None:
        self.hint_label.setText(hint)

    def set_action(self, text: str, icon: str, color: str) -> QToolButton:
        self.action_button.setText(text)
        self.action_button.setIcon(line_icon(icon, color, 15))
        self.action_button.setIconSize(QSize(15, 15))
        self.action_button.show()
        return self.action_button


class _DashboardChart(QWidget):
    """Small native chart used instead of shipping the QtCharts runtime."""

    _COLORS = (
        "#10b981",
        "#ef4444",
        "#f59e0b",
        "#3b82f6",
        "#8b5cf6",
        "#64748b",
    )
    _HEALTH_COLOR_HINTS = (
        (("成功", "正常", "已连接"), "#10b981"),
        (("鉴权", "密码", "失效", "封禁"), "#ef4444"),
        (("超时", "限流", "等待"), "#f59e0b"),
        (("连接", "网络"), "#3b82f6"),
        (("取消", "停止"), "#8b5cf6"),
    )

    def __init__(self, chart_id: str) -> None:
        super().__init__()
        self.setObjectName("dashboardChartView")
        self.setProperty("chartId", chart_id)
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._chart_id = chart_id
        self._theme_id = DEFAULT_THEME
        self._dark = False
        self._health_segments: tuple[tuple[str, int, QColor], ...] = ()
        self._trend_points: tuple[tuple[object, int], ...] = ()

    @property
    def legend_visible(self) -> bool:
        return self._chart_id == "health"

    @property
    def points_visible(self) -> bool:
        return len(self._trend_points) > 1

    @property
    def rendered_point_count(self) -> int:
        return 2 if len(self._trend_points) == 1 else len(self._trend_points)

    @property
    def health_total(self) -> int:
        return sum(count for _label, count, _color in self._health_segments)

    @property
    def health_layout_mode(self) -> str:
        return "horizontal" if self.width() >= 430 and self.height() >= 150 else "stacked"

    @property
    def y_max(self) -> int:
        maximum = max((count for _timestamp, count in self._trend_points), default=0)
        return max(1, maximum + max(1, round(maximum * 0.15)))

    def set_theme(self, theme: str | bool) -> None:
        theme_id = (
            "midnight"
            if theme is True
            else DEFAULT_THEME if theme is False else str(theme)
        )
        self._theme_id = theme_id if theme_id in THEME_BY_ID else DEFAULT_THEME
        self._dark = THEME_BY_ID[self._theme_id].dark
        self.update()

    def set_health_data(self, values: Sequence[tuple[str, int]]) -> None:
        self._health_segments = tuple(
            (label, count, self._health_color(label, index))
            for index, (label, count) in enumerate(values)
            if count > 0
        )
        self.update()

    @classmethod
    def _health_color(cls, label: str, index: int) -> QColor:
        for hints, color in cls._HEALTH_COLOR_HINTS:
            if any(hint in label for hint in hints):
                return QColor(color)
        return QColor(cls._COLORS[index % len(cls._COLORS)])

    def set_trend_data(self, values: Sequence[tuple[object, int]]) -> None:
        self._trend_points = tuple(
            (timestamp, max(0, int(count))) for timestamp, count in values
        )
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._chart_id == "health":
            self._draw_health(painter)
        else:
            self._draw_trend(painter)

    def _draw_health(self, painter: QPainter) -> None:
        theme = THEME_BY_ID[self._theme_id]
        foreground = QColor(theme.text)
        muted = QColor(theme.muted)
        track = QColor(theme.border)
        panel = QColor(theme.panel)
        content = QRectF(self.rect()).adjusted(12, 9, -12, -9)
        if content.width() <= 40 or content.height() <= 40:
            return

        total = self.health_total
        horizontal = self.health_layout_mode == "horizontal"
        if horizontal:
            chart_width = min(content.width() * 0.43, 210.0)
            diameter = min(158.0, content.height() - 18, chart_width - 20)
            diameter = max(84.0, diameter)
            ring = QRectF(
                content.left() + (chart_width - diameter) / 2,
                content.center().y() - diameter / 2,
                diameter,
                diameter,
            )
            details_height = (
                138.0
                if not total
                else max(112.0, min(176.0, 40.0 + len(self._health_segments[:5]) * 26))
            )
            details_height = min(content.height() - 8, details_height)
            details = QRectF(
                content.left() + chart_width + 8,
                content.center().y() - details_height / 2,
                content.width() - chart_width - 8,
                details_height,
            )
        else:
            legend_height = min(58.0, content.height() * 0.32)
            diameter = max(
                72.0,
                min(132.0, content.width() * 0.46, content.height() - legend_height - 8),
            )
            ring = QRectF(
                content.center().x() - diameter / 2,
                content.top(),
                diameter,
                diameter,
            )
            details = QRectF(
                content.left(),
                ring.bottom() + 8,
                content.width(),
                max(34.0, content.bottom() - ring.bottom() - 8),
            )

        ring_width = max(11.0, min(18.0, diameter * 0.12))
        pen = QPen(track, ring_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(ring, 0, 360 * 16)

        start = 90 * 16
        if total:
            for _label, count, color in self._health_segments:
                span = -round(360 * 16 * count / total)
                painter.setPen(
                    QPen(
                        color,
                        ring_width,
                        Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap,
                    )
                )
                painter.drawArc(ring, start, span)
                start += span

        base_font = QFont(self.font())
        center_font = QFont(base_font)
        center_font.setBold(True)
        center_font.setPointSize(max(15, center_font.pointSize() + 5))
        painter.setFont(center_font)
        painter.setPen(foreground)
        number_rect = QRectF(ring.left(), ring.top() + ring.height() * 0.28, ring.width(), 30)
        painter.drawText(number_rect, Qt.AlignmentFlag.AlignCenter, f"{total:,}")
        label_font = QFont(base_font)
        label_font.setPointSize(max(8, label_font.pointSize() - 2))
        painter.setFont(label_font)
        painter.setPen(muted)
        painter.drawText(
            QRectF(ring.left(), number_rect.bottom() - 2, ring.width(), 20),
            Qt.AlignmentFlag.AlignCenter,
            "邮箱账号",
        )

        if horizontal:
            self._draw_horizontal_health_details(
                painter, details, foreground, muted, panel, total
            )
        else:
            self._draw_stacked_health_details(painter, details, muted, panel, total)

    def _draw_horizontal_health_details(
        self,
        painter: QPainter,
        details: QRectF,
        foreground: QColor,
        muted: QColor,
        panel: QColor,
        total: int,
    ) -> None:
        base_font = QFont(self.font())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(panel)
        painter.drawRoundedRect(details, 10, 10)
        inner = details.adjusted(14, 11, -14, -10)
        if not total:
            title_font = QFont(base_font)
            title_font.setBold(True)
            title_font.setPointSize(max(10, title_font.pointSize() + 1))
            painter.setFont(title_font)
            painter.setPen(foreground)
            painter.drawText(
                QRectF(inner.left(), inner.top() + 12, inner.width(), 24),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "还没有邮箱账号",
            )
            body_font = QFont(base_font)
            body_font.setPointSize(max(8, body_font.pointSize() - 1))
            painter.setFont(body_font)
            painter.setPen(muted)
            painter.drawText(
                QRectF(inner.left(), inner.top() + 43, inner.width(), 48),
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignTop
                | Qt.TextFlag.TextWordWrap,
                "添加邮箱并完成首次取件后，连接状态分布会显示在这里。",
            )
            return

        heading_font = QFont(base_font)
        heading_font.setBold(True)
        heading_font.setPointSize(max(9, heading_font.pointSize()))
        painter.setFont(heading_font)
        painter.setPen(foreground)
        painter.drawText(
            QRectF(inner.left(), inner.top(), inner.width(), 20),
            Qt.AlignmentFlag.AlignVCenter,
            "状态分布",
        )
        row_top = inner.top() + 25
        row_height = max(20.0, min(27.0, (inner.bottom() - row_top) / 5))
        label_font = QFont(base_font)
        label_font.setPointSize(max(8, label_font.pointSize() - 1))
        painter.setFont(label_font)
        metrics = QFontMetrics(label_font)
        for index, (label, count, color) in enumerate(self._health_segments[:5]):
            y = row_top + index * row_height
            if y + row_height > inner.bottom() + 2:
                break
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(inner.left() + 4, y + row_height / 2), 4, 4)
            painter.setPen(muted)
            text = metrics.elidedText(
                label,
                Qt.TextElideMode.ElideRight,
                max(30, int(inner.width() - 74)),
            )
            painter.drawText(
                QRectF(inner.left() + 14, y, inner.width() - 70, row_height),
                Qt.AlignmentFlag.AlignVCenter,
                text,
            )
            painter.setPen(foreground)
            painter.drawText(
                QRectF(inner.right() - 61, y, 61, row_height),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{count}  ·  {round(count * 100 / total)}%",
            )

    def _draw_stacked_health_details(
        self,
        painter: QPainter,
        details: QRectF,
        muted: QColor,
        panel: QColor,
        total: int,
    ) -> None:
        base_font = QFont(self.font())
        if not total:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(panel)
            empty = details.adjusted(6, 1, -6, -1)
            painter.drawRoundedRect(empty, 8, 8)
            painter.setPen(muted)
            painter.drawText(
                empty.adjusted(10, 0, -10, 0),
                Qt.AlignmentFlag.AlignCenter,
                "添加邮箱后显示连接状态分布",
            )
            return

        segments = self._health_segments[:6]
        column_width = details.width() / 2
        row_height = max(17.0, min(21.0, details.height() / 3))
        label_font = QFont(base_font)
        label_font.setPointSize(max(8, label_font.pointSize()))
        painter.setFont(label_font)
        metrics = QFontMetrics(label_font)
        for index, (label, count, color) in enumerate(segments[:6]):
            row, column = divmod(index, 2)
            x = details.left() + column * column_width
            y = details.top() + row * row_height
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(x + 4, y + row_height / 2), 4, 4)
            painter.setPen(muted)
            text = metrics.elidedText(
                f"{label}  {count}",
                Qt.TextElideMode.ElideRight,
                int(column_width - 18),
            )
            painter.drawText(
                QRectF(x + 13, y, column_width - 15, row_height),
                Qt.AlignmentFlag.AlignVCenter,
                text,
            )

    def _draw_trend(self, painter: QPainter) -> None:
        theme = THEME_BY_ID[self._theme_id]
        foreground = QColor(theme.text)
        muted = QColor(theme.muted)
        grid = QColor(theme.border)
        accent = QColor(theme.accent)
        plot = QRectF(self.rect()).adjusted(42, 10, -12, -27)
        if plot.width() <= 20 or plot.height() <= 20:
            return

        painter.setPen(QPen(grid, 1))
        for step in range(5):
            y = plot.bottom() - plot.height() * step / 4
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

        label_font = painter.font()
        label_font.setPointSize(max(8, label_font.pointSize() - 1))
        painter.setFont(label_font)
        painter.setPen(muted)
        y_max = self.y_max
        for step in (0, 2, 4):
            value = round(y_max * step / 4)
            y = plot.bottom() - plot.height() * step / 4
            painter.drawText(
                QRectF(0, y - 9, plot.left() - 7, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                str(value),
            )

        if not self._trend_points:
            painter.setPen(foreground)
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "暂无收件数据")
            return

        timestamps = [timestamp for timestamp, _count in self._trend_points]
        values = [count for _timestamp, count in self._trend_points]
        if len(values) == 1:
            y = plot.bottom() - plot.height() * values[0] / y_max
            points = (QPointF(plot.left(), y), QPointF(plot.right(), y))
        else:
            points = tuple(
                QPointF(
                    plot.left() + plot.width() * index / (len(values) - 1),
                    plot.bottom() - plot.height() * count / y_max,
                )
                for index, count in enumerate(values)
            )

        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        painter.setPen(
            QPen(
                accent,
                2.2,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        if self.points_visible:
            painter.setPen(QPen(accent, 1.5))
            painter.setBrush(QColor(theme.surface))
            for point in points:
                painter.drawEllipse(point, 3.2, 3.2)

        indices = sorted({0, len(timestamps) // 2, len(timestamps) - 1})
        metrics = QFontMetrics(label_font)
        for index in indices:
            timestamp = timestamps[index]
            text = (
                timestamp.strftime("%m-%d %H:%M")
                if hasattr(timestamp, "strftime")
                else str(timestamp)
            )
            width = metrics.horizontalAdvance(text) + 8
            ratio = index / max(1, len(timestamps) - 1)
            x = plot.left() + plot.width() * ratio
            x = max(plot.left(), min(plot.right() - width, x - width / 2))
            painter.setPen(muted)
            painter.drawText(
                QRectF(x, plot.bottom() + 5, width, 18),
                Qt.AlignmentFlag.AlignCenter,
                text,
            )


class DashboardWidget(QWidget):
    # The original signals remain available so existing MainWindow integrations keep working.
    navigateAccountsRequested = Signal()
    startFetchRequested = Signal()
    importRequested = Signal()
    contentFilterRequested = Signal()
    recentMessageRequested = Signal(int, int)

    # New generic/customizable dashboard actions.
    quickActionRequested = Signal(str)
    abnormalAccountsRequested = Signal()
    proxyToggleRequested = Signal(bool)

    def __init__(
        self,
        statistics: StatisticsRepository,
        messages: MessageRepository,
        parent=None,
        *,
        quick_action_ids: Sequence[str] | None = None,
        proxy_enabled: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("dashboard")
        self._statistics = statistics
        self._messages = messages
        self._theme_id = DEFAULT_THEME
        self._dark = False
        self._fetch_state = "idle"
        self._proxy_enabled = bool(proxy_enabled)
        self._proxy_count = 0
        self._quick_action_ids: tuple[str, ...] = ()
        self.quick_action_buttons: dict[str, QToolButton] = {}
        self.fetch_button: QToolButton | None = None
        self._metric_columns = 0
        self._panels_stacked: bool | None = None
        self._scroll_reset_pending = False

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("dashboardScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        root_layout.addWidget(self.scroll_area)

        self.content = QWidget()
        self.content.setObjectName("dashboardContent")
        # Compact windows should reflow instead of clipping the rightmost card.
        # Extremely small windows can still use the horizontal scrollbar.
        self.content.setMinimumSize(640, 720)
        self.scroll_area.setWidget(self.content)
        layout = QVBoxLayout(self.content)
        # Qt's SetMinimumSize constraint rewrites the widget minimum after
        # queued layout events (629 px on macOS). Keep the constraint manual so
        # the responsive floor remains deterministic on every platform.
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        layout.setContentsMargins(26, 22, 26, 26)
        layout.setSpacing(16)

        header = QFrame()
        header.setObjectName("dashboardHeader")
        title_row = QHBoxLayout(header)
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(12)
        title_copy = QVBoxLayout()
        title_copy.setSpacing(2)
        title = QLabel("工作台概览")
        title.setObjectName("dashboardTitle")
        title_copy.addWidget(title)
        self.summary_label = QLabel("账号健康、邮件活动与常用操作")
        self.summary_label.setObjectName("dashboardSubtitle")
        self.summary_label.setAccessibleName("账号和收件统计摘要")
        title_copy.addWidget(self.summary_label)
        title_row.addLayout(title_copy)
        title_row.addStretch(1)
        self.health_badge = QLabel("正在统计账号状态")
        self.health_badge.setObjectName("dashboardHealthBadge")
        title_row.addWidget(self.health_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        self.refresh_button = QToolButton()
        self.refresh_button.setObjectName("dashboardRefreshButton")
        self.refresh_button.setText("刷新数据")
        self.refresh_button.setIcon(line_icon("refresh", "#64748b", 17))
        self.refresh_button.setIconSize(QSize(17, 17))
        self.refresh_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh)
        title_row.addWidget(self.refresh_button, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(header)

        self.metrics_container = QWidget()
        self.metrics_container.setObjectName("dashboardMetrics")
        self.metrics_layout = QGridLayout(self.metrics_container)
        self.metrics_layout.setContentsMargins(0, 0, 0, 0)
        self.metrics_layout.setHorizontalSpacing(12)
        self.metrics_layout.setVerticalSpacing(12)
        self.total_card = _MetricCard(
            "accounts", "账号总数", "当前工作区", "users", "#3b82f6"
        )
        self.message_card = _MetricCard(
            "messages", "本地邮件", "已安全保存", "inbox", "#10b981"
        )
        self.abnormal_card = _MetricCard(
            "abnormal", "异常账号", "需要检查", "warning", "#f59e0b"
        )
        self.proxy_card = _MetricCard(
            "proxy", "代理取件", "当前使用本地网络", "globe", "#8b5cf6"
        )
        self.abnormal_button = self.abnormal_card.set_action(
            "查看", "warning", "#d97706"
        )
        self.abnormal_button.setAccessibleName("查看所有异常账号")
        self.abnormal_card.activated.connect(self._request_abnormal_accounts)
        self.proxy_toggle_button = self.proxy_card.set_action(
            "启动", "play", "#7c3aed"
        )
        self.proxy_toggle_button.setAccessibleName("启动代理取件")
        self.proxy_card.activated.connect(self._toggle_proxy)
        self.metric_cards = (
            self.total_card,
            self.message_card,
            self.abnormal_card,
            self.proxy_card,
        )
        for index, card in enumerate(self.metric_cards):
            self.metrics_layout.addWidget(card, 0, index)
        layout.addWidget(self.metrics_container)

        self.activity_row = QWidget()
        self.activity_row.setObjectName("dashboardActivityRow")
        self.activity_layout = QGridLayout(self.activity_row)
        self.activity_layout.setContentsMargins(0, 0, 0, 0)
        self.activity_layout.setHorizontalSpacing(12)
        self.activity_layout.setVerticalSpacing(12)

        self.quick_card = QFrame()
        self.quick_card.setObjectName("dashboardQuickPanel")
        self.quick_card.setProperty("dashboardPanel", True)
        quick_layout = QVBoxLayout(self.quick_card)
        quick_layout.setContentsMargins(17, 15, 17, 17)
        quick_layout.setSpacing(12)
        quick_header = QHBoxLayout()
        quick_header_copy = QVBoxLayout()
        quick_header_copy.setSpacing(1)
        quick_title = QLabel("快捷操作")
        quick_title.setObjectName("dashboardPanelTitle")
        quick_header_copy.addWidget(quick_title)
        quick_caption = QLabel("可在系统设置中调整显示和顺序")
        quick_caption.setObjectName("dashboardPanelCaption")
        quick_header_copy.addWidget(quick_caption)
        quick_header.addLayout(quick_header_copy)
        quick_header.addStretch(1)
        quick_layout.addLayout(quick_header)

        self.quick_grid_host = QWidget()
        self.quick_grid_host.setObjectName("dashboardQuickGrid")
        self.quick_grid = QGridLayout(self.quick_grid_host)
        self.quick_grid.setContentsMargins(0, 0, 0, 0)
        self.quick_grid.setHorizontalSpacing(10)
        self.quick_grid.setVerticalSpacing(10)
        self.quick_grid.setColumnStretch(0, 1)
        self.quick_grid.setColumnStretch(1, 1)
        quick_layout.addWidget(self.quick_grid_host, 1)
        self.activity_layout.addWidget(self.quick_card, 0, 0)

        self.recent_card = QFrame()
        self.recent_card.setObjectName("dashboardRecentPanel")
        self.recent_card.setProperty("dashboardPanel", True)
        recent_layout = QVBoxLayout(self.recent_card)
        recent_layout.setContentsMargins(17, 15, 17, 12)
        recent_layout.setSpacing(10)
        recent_header = QHBoxLayout()
        recent_header_copy = QVBoxLayout()
        recent_header_copy.setSpacing(1)
        recent_title = QLabel("最近邮件")
        recent_title.setObjectName("dashboardPanelTitle")
        recent_header_copy.addWidget(recent_title)
        recent_caption = QLabel("点击邮件可直接打开阅读")
        recent_caption.setObjectName("dashboardPanelCaption")
        recent_header_copy.addWidget(recent_caption)
        recent_header.addLayout(recent_header_copy)
        recent_header.addStretch(1)
        self.recent_count_label = QLabel("0 封")
        self.recent_count_label.setObjectName("dashboardCountBadge")
        recent_header.addWidget(self.recent_count_label)
        recent_layout.addLayout(recent_header)
        self.recent_list = QListWidget()
        self.recent_list.setObjectName("dashboardRecentList")
        self.recent_list.setWordWrap(True)
        self.recent_list.setSpacing(1)
        self.recent_list.itemClicked.connect(self._recent_activated)
        recent_layout.addWidget(self.recent_list, 1)
        self.activity_layout.addWidget(self.recent_card, 0, 1)
        self.activity_layout.setColumnStretch(0, 1)
        self.activity_layout.setColumnStretch(1, 2)
        self.activity_row.setMinimumHeight(290)
        layout.addWidget(self.activity_row, 1)

        self.insights_row = QWidget()
        self.insights_row.setObjectName("dashboardInsightsRow")
        self.insights_layout = QGridLayout(self.insights_row)
        self.insights_layout.setContentsMargins(0, 0, 0, 0)
        self.insights_layout.setHorizontalSpacing(12)
        self.insights_layout.setVerticalSpacing(12)
        self.health_card, self.health_chart = self._chart_card(
            "health", "账号健康度", "按最近连接结果统计"
        )
        self.rate_card, self.rate_chart = self._chart_card(
            "trend", "收件趋势", "最近 24 个有数据小时"
        )
        self.insights_layout.addWidget(self.health_card, 0, 0)
        self.insights_layout.addWidget(self.rate_card, 0, 1)
        self.insights_layout.setColumnStretch(0, 1)
        self.insights_layout.setColumnStretch(1, 2)
        self.insights_row.setMinimumHeight(270)
        layout.addWidget(self.insights_row, 1)

        # Establish the initial responsive floor after all children exist.
        self.content.setMinimumSize(640, 720)
        self._update_responsive_layout(self.width())
        self.set_quick_actions(quick_action_ids)
        self.set_proxy_state(proxy_enabled)
        self.refresh()

    @property
    def quick_action_ids(self) -> tuple[str, ...]:
        return self._quick_action_ids

    @property
    def proxy_enabled(self) -> bool:
        return self._proxy_enabled

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._update_responsive_layout(self.width())
        self._schedule_scroll_to_top()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_responsive_layout(event.size().width())
        if self.isVisible():
            self._schedule_scroll_to_top()

    def _update_responsive_layout(self, available_width: int) -> None:
        metric_columns = 2 if available_width < METRICS_COMPACT_BREAKPOINT else 4
        if metric_columns != self._metric_columns:
            for card in self.metric_cards:
                self.metrics_layout.removeWidget(card)
            for column in range(4):
                self.metrics_layout.setColumnStretch(
                    column, 1 if column < metric_columns else 0
                )
            self.metrics_layout.setRowStretch(0, 1)
            self.metrics_layout.setRowStretch(1, 1 if metric_columns == 2 else 0)
            for index, card in enumerate(self.metric_cards):
                self.metrics_layout.addWidget(
                    card,
                    index // metric_columns,
                    index % metric_columns,
                )
            self._metric_columns = metric_columns

        panels_stacked = available_width < PANELS_STACK_BREAKPOINT
        if panels_stacked != self._panels_stacked:
            for panel in (self.quick_card, self.recent_card):
                self.activity_layout.removeWidget(panel)
            for panel in (self.health_card, self.rate_card):
                self.insights_layout.removeWidget(panel)

            if panels_stacked:
                self.activity_layout.addWidget(self.quick_card, 0, 0)
                self.activity_layout.addWidget(self.recent_card, 1, 0)
                self.insights_layout.addWidget(self.health_card, 0, 0)
                self.insights_layout.addWidget(self.rate_card, 1, 0)
                activity_stretches = (1, 0)
                insight_stretches = (1, 0)
            else:
                self.activity_layout.addWidget(self.quick_card, 0, 0)
                self.activity_layout.addWidget(self.recent_card, 0, 1)
                self.insights_layout.addWidget(self.health_card, 0, 0)
                self.insights_layout.addWidget(self.rate_card, 0, 1)
                activity_stretches = (1, 2)
                insight_stretches = (1, 2)

            for column, stretch in enumerate(activity_stretches):
                self.activity_layout.setColumnStretch(column, stretch)
            for column, stretch in enumerate(insight_stretches):
                self.insights_layout.setColumnStretch(column, stretch)
            self.activity_layout.setRowStretch(0, 1)
            self.activity_layout.setRowStretch(1, 1 if panels_stacked else 0)
            self.insights_layout.setRowStretch(0, 1)
            self.insights_layout.setRowStretch(1, 1 if panels_stacked else 0)
            self._panels_stacked = panels_stacked

        self.metrics_layout.invalidate()
        self.activity_layout.invalidate()
        self.insights_layout.invalidate()
        self._sync_section_minimum_heights()
        self.content.updateGeometry()

    def _sync_section_minimum_heights(self) -> None:
        self.activity_layout.activate()
        self.insights_layout.activate()
        self.activity_row.setMinimumHeight(
            max(290, self.activity_layout.minimumSize().height())
        )
        self.insights_row.setMinimumHeight(
            max(270, self.insights_layout.minimumSize().height())
        )
        content_layout = self.content.layout()
        if content_layout is not None:
            content_layout.invalidate()
            content_layout.activate()
            layout_minimum = content_layout.minimumSize()
        else:
            layout_minimum = QSize(640, 720)
        # Preserve the vertical space needed by stacked panels while enforcing
        # the cross-platform compact-width contract ourselves.
        self.content.setMinimumSize(
            640,
            max(720, layout_minimum.height()),
        )

    def _schedule_scroll_to_top(self) -> None:
        if self._scroll_reset_pending:
            return
        self._scroll_reset_pending = True
        QTimer.singleShot(0, self._scroll_to_top)

    def _scroll_to_top(self) -> None:
        self._scroll_reset_pending = False
        vertical = self.scroll_area.verticalScrollBar()
        horizontal = self.scroll_area.horizontalScrollBar()
        vertical.setValue(vertical.minimum())
        horizontal.setValue(horizontal.minimum())

    def set_quick_actions(self, action_ids: Sequence[str] | None) -> tuple[str, ...]:
        """Rebuild the shortcuts without recreating the whole dashboard."""

        normalized = normalize_quick_action_ids(action_ids)
        while self.quick_grid.count():
            item = self.quick_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.quick_action_buttons.clear()
        self.fetch_button = None
        for row in range((MAX_QUICK_ACTIONS + 1) // 2):
            self.quick_grid.setRowStretch(row, 0)

        for index, action_id in enumerate(normalized):
            definition = QUICK_ACTIONS_BY_ID[action_id]
            button = QToolButton()
            button.setObjectName("dashboardQuickAction")
            button.setProperty("actionId", action_id)
            button.setText(definition.label)
            button.setToolTip(definition.description)
            button.setAccessibleName(definition.label)
            button.setAccessibleDescription(definition.description)
            button.setIcon(line_icon(definition.icon, "#3b82f6", 22))
            button.setIconSize(QSize(22, 22))
            button.setMinimumHeight(82)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            # Prevent QScrollArea from revealing a previously focused shortcut
            # when the dashboard tab is shown again.
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(partial(self._activate_quick_action, action_id))
            self.quick_action_buttons[action_id] = button
            if action_id == "fetch":
                self.fetch_button = button
            self.quick_grid.addWidget(button, index // 2, index % 2)

        rows = max(1, (len(normalized) + 1) // 2)
        for row in range(rows):
            self.quick_grid.setRowStretch(row, 1)
        self._quick_action_ids = normalized
        self._apply_fetch_state()
        self.quick_grid.invalidate()
        self._sync_section_minimum_heights()
        return normalized

    @staticmethod
    def _chart_card(
        chart_id: str, title: str, caption: str
    ) -> tuple[QFrame, _DashboardChart]:
        card = QFrame()
        card.setObjectName("dashboardChartPanel")
        card.setProperty("chartId", chart_id)
        card.setProperty("dashboardPanel", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(17, 14, 17, 10)
        card_layout.setSpacing(1)
        title_label = QLabel(title)
        title_label.setObjectName("dashboardPanelTitle")
        caption_label = QLabel(caption)
        caption_label.setObjectName("dashboardPanelCaption")
        chart_view = _DashboardChart(chart_id)
        card_layout.addWidget(title_label)
        card_layout.addWidget(caption_label)
        card_layout.addWidget(chart_view, 1)
        return card, chart_view

    def apply_theme(self, theme: str | bool) -> None:
        theme_id = (
            "midnight"
            if theme is True
            else DEFAULT_THEME if theme is False else str(theme)
        )
        self._theme_id = theme_id if theme_id in THEME_BY_ID else DEFAULT_THEME
        definition = THEME_BY_ID[self._theme_id]
        self._dark = definition.dark
        self.health_chart.set_theme(self._theme_id)
        self.rate_chart.set_theme(self._theme_id)
        self.refresh_button.setIcon(line_icon("refresh", definition.muted, 17))
        for action_id, button in self.quick_action_buttons.items():
            if action_id == "fetch":
                continue
            button.setIcon(
                line_icon(QUICK_ACTIONS_BY_ID[action_id].icon, definition.accent, 22)
            )
        self._apply_fetch_state()
        self._update_proxy_card()
        self.refresh()

    def set_fetch_state(self, state: str) -> None:
        self._fetch_state = state if state in {"idle", "running", "stopping"} else "idle"
        self._apply_fetch_state()

    def _apply_fetch_state(self) -> None:
        button = self.fetch_button
        if button is None:
            return
        if self._fetch_state == "running":
            button.setText("取件进行中")
            button.setEnabled(False)
            icon_name = "refresh"
        elif self._fetch_state == "stopping":
            button.setText("正在停止…")
            button.setEnabled(False)
            icon_name = "stop"
        else:
            button.setText(QUICK_ACTIONS_BY_ID["fetch"].label)
            button.setEnabled(True)
            icon_name = "bolt"
        button.setProperty("state", self._fetch_state)
        button.setIcon(
            line_icon(icon_name, THEME_BY_ID[self._theme_id].accent, 22)
        )
        button.style().unpolish(button)
        button.style().polish(button)

    def set_proxy_state(self, enabled: bool) -> None:
        """Reflect the persisted global proxy-fetch switch without emitting a request."""

        self._proxy_enabled = bool(enabled)
        self.proxy_card.setProperty("proxyEnabled", self._proxy_enabled)
        self._update_proxy_card()
        self.proxy_card.style().unpolish(self.proxy_card)
        self.proxy_card.style().polish(self.proxy_card)

    def set_proxy_toggle_enabled(self, enabled: bool) -> None:
        """Allow MainWindow to lock the switch while applying a state transition."""

        self.proxy_toggle_button.setEnabled(enabled)

    def _update_proxy_card(self) -> None:
        color = THEME_BY_ID[self._theme_id].accent
        if self._proxy_enabled:
            self.proxy_card.set_hint(f"代理取件已开启 · {self._proxy_count} 个可用")
            self.proxy_toggle_button.setText("关闭")
            self.proxy_toggle_button.setIcon(line_icon("stop", color, 15))
            self.proxy_toggle_button.setAccessibleName("关闭代理取件")
        else:
            self.proxy_card.set_hint(f"当前使用本地网络 · {self._proxy_count} 个可用")
            self.proxy_toggle_button.setText("启动")
            self.proxy_toggle_button.setIcon(line_icon("play", color, 15))
            self.proxy_toggle_button.setAccessibleName("启动代理取件")

    def _toggle_proxy(self) -> None:
        requested_state = not self._proxy_enabled
        # MainWindow owns persistence and is the only source of truth for this
        # switch.  Keep the rendered state unchanged until that write succeeds.
        self.set_proxy_toggle_enabled(False)
        self.proxyToggleRequested.emit(requested_state)

    def _request_abnormal_accounts(self) -> None:
        self.quickActionRequested.emit("abnormal_accounts")
        self.abnormalAccountsRequested.emit()

    def _activate_quick_action(self, action_id: str, _checked: bool = False) -> None:
        del _checked
        self.quickActionRequested.emit(action_id)
        signal = {
            "accounts": self.navigateAccountsRequested,
            "fetch": self.startFetchRequested,
            "add_account": self.importRequested,
            "content_filter": self.contentFilterRequested,
            "abnormal_accounts": self.abnormalAccountsRequested,
        }[action_id]
        signal.emit()

    def refresh(self) -> None:
        stats = self._statistics.dashboard()
        overview = self._statistics.overview()
        self.summary_label.setText(
            f"管理 {overview.total_accounts} 个账号 · 已保存 {overview.total_messages} 封邮件"
        )
        self.total_card.set_value(overview.total_accounts)
        self.message_card.set_value(overview.total_messages)
        self.abnormal_card.set_value(overview.abnormal_accounts)
        self.abnormal_button.setEnabled(overview.abnormal_accounts > 0)
        self.abnormal_card.set_hint(
            "点击查看并处理" if overview.abnormal_accounts else "全部账号状态正常"
        )
        self.health_badge.setProperty(
            "state", "warning" if overview.abnormal_accounts else "healthy"
        )
        self.health_badge.setText(
            f"{overview.abnormal_accounts} 个账号待处理"
            if overview.abnormal_accounts
            else "账号状态正常"
        )
        self.health_badge.style().unpolish(self.health_badge)
        self.health_badge.style().polish(self.health_badge)
        self._proxy_count = overview.enabled_proxies
        self.proxy_card.set_value(overview.enabled_proxies)
        self._update_proxy_card()
        self._refresh_recent_messages()

        trend_points = stats.messages_per_hour
        self.health_chart.set_health_data(
            tuple(
                (STATUS_LABELS[status], count)
                for status, count in stats.status_counts.items()
                if count
            )
        )
        self.rate_chart.set_trend_data(trend_points)

    def _refresh_recent_messages(self) -> None:
        hits = self._messages.list_with_accounts(limit=6)
        self.recent_list.clear()
        for hit in hits:
            message = hit.message
            received = (
                message.received_at.astimezone().strftime("%m-%d %H:%M")
                if message.received_at
                else ""
            )
            sender = message.sender_display or "未知发件人"
            item = QListWidgetItem(
                f"{message.subject or '(无主题)'}\n"
                f"{hit.account_email}  ·  {sender}  ·  {received}"
            )
            item.setData(
                Qt.ItemDataRole.UserRole,
                (message.account_id or 0, message.message_id or 0),
            )
            item.setToolTip(message.subject)
            self.recent_list.addItem(item)
        self.recent_count_label.setText(f"{len(hits)} 封")
        if not hits:
            empty_item = QListWidgetItem("暂无本地邮件，完成取件后会显示在这里")
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent_list.addItem(empty_item)

    def _recent_activated(self, item: QListWidgetItem) -> None:
        value = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(value, tuple) and len(value) == 2 and value[0]:
            self.recentMessageRequested.emit(int(value[0]), int(value[1]))
