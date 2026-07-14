from __future__ import annotations

import os
from datetime import UTC, datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy

from mailbox_manager.domain.models import DashboardOverview, DashboardStats
from mailbox_manager.gui.dashboard import (
    DEFAULT_QUICK_ACTION_IDS,
    DashboardWidget,
    configured_quick_action_ids,
    normalize_quick_action_ids,
)


class _Statistics:
    def dashboard(self) -> DashboardStats:
        return DashboardStats(status_counts={}, messages_per_hour=())

    def overview(self) -> DashboardOverview:
        return DashboardOverview(
            total_accounts=12,
            healthy_accounts=9,
            abnormal_accounts=3,
            total_messages=48,
            special_folder_messages=2,
            enabled_proxies=4,
        )


class _Messages:
    @staticmethod
    def list_with_accounts(*, limit: int):
        assert limit == 6
        return []


class _SinglePointStatistics(_Statistics):
    def dashboard(self) -> DashboardStats:
        return DashboardStats(
            status_counts={},
            messages_per_hour=((datetime(2026, 7, 14, 12, tzinfo=UTC), 4),),
        )


def _dashboard(qtbot, **kwargs) -> DashboardWidget:
    dashboard = DashboardWidget(_Statistics(), _Messages(), **kwargs)
    qtbot.addWidget(dashboard)
    dashboard.resize(1280, 820)
    dashboard.show()
    return dashboard


def test_quick_action_ids_are_normalized_and_safe() -> None:
    assert normalize_quick_action_ids(None) == DEFAULT_QUICK_ACTION_IDS
    assert normalize_quick_action_ids([]) == DEFAULT_QUICK_ACTION_IDS
    assert normalize_quick_action_ids(["abnormal", "accounts", "accounts", "bad-id"]) == (
        "abnormal_accounts",
        "accounts",
    )
    assert configured_quick_action_ids(
        ["abnormal", "accounts", "accounts", "bad-id"]
    ) == (
        "abnormal_accounts",
        "accounts",
        "fetch",
        "add_account",
    )


def test_dashboard_rebuilds_shortcuts_and_keeps_legacy_signals(qtbot) -> None:
    dashboard = _dashboard(
        qtbot,
        quick_action_ids=["abnormal_accounts", "accounts", "add_account"],
    )
    generic_spy = QSignalSpy(dashboard.quickActionRequested)
    abnormal_spy = QSignalSpy(dashboard.abnormalAccountsRequested)
    accounts_spy = QSignalSpy(dashboard.navigateAccountsRequested)
    import_spy = QSignalSpy(dashboard.importRequested)

    dashboard.quick_action_buttons["abnormal_accounts"].click()
    dashboard.quick_action_buttons["accounts"].click()
    dashboard.quick_action_buttons["add_account"].click()

    assert dashboard.quick_action_ids == (
        "abnormal_accounts",
        "accounts",
        "add_account",
    )
    assert [generic_spy.at(index)[0] for index in range(generic_spy.count())] == [
        "abnormal_accounts",
        "accounts",
        "add_account",
    ]
    assert abnormal_spy.count() == 1
    assert accounts_spy.count() == 1
    assert import_spy.count() == 1


def test_dashboard_abnormal_metric_opens_filtered_accounts(qtbot) -> None:
    dashboard = _dashboard(qtbot)
    generic_spy = QSignalSpy(dashboard.quickActionRequested)
    abnormal_spy = QSignalSpy(dashboard.abnormalAccountsRequested)

    assert dashboard.abnormal_button.isEnabled() is True
    assert dashboard.health_badge.text() == "3 个账号待处理"
    dashboard.abnormal_button.click()

    assert abnormal_spy.count() == 1
    assert generic_spy.count() == 1
    assert generic_spy.at(0)[0] == "abnormal_accounts"


def test_dashboard_proxy_toggle_has_explicit_state_and_request_signal(qtbot) -> None:
    dashboard = _dashboard(qtbot, proxy_enabled=False)
    proxy_spy = QSignalSpy(dashboard.proxyToggleRequested)

    assert dashboard.proxy_enabled is False
    assert dashboard.proxy_toggle_button.text() == "启动"
    assert "本地网络" in dashboard.proxy_card.hint_label.text()
    assert dashboard.proxy_card.value_label.text() == "4"

    dashboard.proxy_toggle_button.click()

    assert dashboard.proxy_enabled is False
    assert dashboard.proxy_toggle_button.text() == "启动"
    assert dashboard.proxy_toggle_button.isEnabled() is False
    assert proxy_spy.count() == 1
    assert proxy_spy.at(0)[0] is True

    dashboard.set_proxy_state(True)
    dashboard.set_proxy_toggle_enabled(True)
    assert dashboard.proxy_enabled is True
    assert dashboard.proxy_toggle_button.text() == "关闭"
    assert "代理取件已开启" in dashboard.proxy_card.hint_label.text()
    assert proxy_spy.count() == 1


def test_dashboard_fetch_state_survives_shortcut_reconfiguration(qtbot) -> None:
    dashboard = _dashboard(qtbot)
    dashboard.set_fetch_state("running")
    assert dashboard.fetch_button is not None
    assert dashboard.fetch_button.text() == "取件进行中"
    assert dashboard.fetch_button.isEnabled() is False

    dashboard.set_quick_actions(["accounts"])
    assert dashboard.fetch_button is None
    dashboard.set_quick_actions(["fetch", "accounts"])

    assert dashboard.fetch_button is not None
    assert dashboard.fetch_button.text() == "取件进行中"
    assert dashboard.fetch_button.isEnabled() is False


def test_dashboard_exposes_stable_theme_hooks(qtbot) -> None:
    dashboard = _dashboard(qtbot)

    assert dashboard.scroll_area.objectName() == "dashboardScrollArea"
    assert dashboard.content.objectName() == "dashboardContent"
    assert dashboard.metrics_container.objectName() == "dashboardMetrics"
    assert dashboard.quick_card.objectName() == "dashboardQuickPanel"
    assert dashboard.recent_card.objectName() == "dashboardRecentPanel"
    assert dashboard.health_chart.objectName() == "dashboardChartView"
    assert dashboard.rate_chart.property("chartId") == "trend"
    assert dashboard.rate_chart.chart().legend().isVisible() is False
    assert dashboard.quick_action_buttons["accounts"].property("actionId") == "accounts"


def test_dashboard_reflows_cards_and_panels_at_compact_width(qtbot) -> None:
    dashboard = _dashboard(qtbot)

    dashboard.resize(1000, 720)
    qtbot.wait(1)
    compact_metric_positions = [
        dashboard.metrics_layout.getItemPosition(
            dashboard.metrics_layout.indexOf(card)
        )[:2]
        for card in dashboard.metric_cards
    ]

    assert 640 <= dashboard.content.minimumWidth() < 920
    assert dashboard.content.minimumHeight() >= 720
    assert compact_metric_positions == [(0, 0), (0, 1), (1, 0), (1, 1)]
    assert dashboard.activity_layout.getItemPosition(
        dashboard.activity_layout.indexOf(dashboard.recent_card)
    )[:2] == (0, 1)

    dashboard.resize(800, 720)
    qtbot.wait(1)
    assert dashboard.activity_layout.getItemPosition(
        dashboard.activity_layout.indexOf(dashboard.recent_card)
    )[:2] == (1, 0)
    assert dashboard.insights_layout.getItemPosition(
        dashboard.insights_layout.indexOf(dashboard.rate_card)
    )[:2] == (1, 0)
    assert dashboard.activity_row.height() >= dashboard.activity_layout.minimumSize().height()
    assert dashboard.insights_row.height() >= dashboard.insights_layout.minimumSize().height()
    assert dashboard.quick_card.height() >= dashboard.quick_card.minimumSizeHint().height()
    assert dashboard.scroll_area.verticalScrollBar().maximum() > 0

    dashboard.resize(1280, 720)
    qtbot.wait(1)
    wide_metric_positions = [
        dashboard.metrics_layout.getItemPosition(
            dashboard.metrics_layout.indexOf(card)
        )[:2]
        for card in dashboard.metric_cards
    ]
    assert wide_metric_positions == [(0, 0), (0, 1), (0, 2), (0, 3)]


def test_dashboard_shortcuts_do_not_capture_scroll_focus(qtbot) -> None:
    dashboard = _dashboard(qtbot)

    assert all(
        button.focusPolicy() == Qt.FocusPolicy.NoFocus
        for button in dashboard.quick_action_buttons.values()
    )

    dashboard.set_quick_actions(["fetch", "accounts", "abnormal_accounts"])
    assert all(
        button.focusPolicy() == Qt.FocusPolicy.NoFocus
        for button in dashboard.quick_action_buttons.values()
    )


def test_dashboard_show_and_resize_restore_scroll_origin(qtbot) -> None:
    dashboard = _dashboard(qtbot)
    dashboard.resize(800, 420)
    qtbot.wait(1)
    vertical = dashboard.scroll_area.verticalScrollBar()
    horizontal = dashboard.scroll_area.horizontalScrollBar()

    assert vertical.maximum() > vertical.minimum()
    vertical.setValue(vertical.maximum())
    dashboard.resize(790, 421)
    qtbot.waitUntil(lambda: vertical.value() == vertical.minimum())
    assert horizontal.value() == horizontal.minimum()

    vertical.setValue(vertical.maximum())
    dashboard.hide()
    dashboard.show()
    qtbot.waitUntil(lambda: vertical.value() == vertical.minimum())


def test_dashboard_renders_single_hour_as_a_line_with_headroom(qtbot) -> None:
    dashboard = DashboardWidget(_SinglePointStatistics(), _Messages())
    qtbot.addWidget(dashboard)

    chart = dashboard.rate_chart.chart()
    series = chart.series()[0]
    vertical_axis = chart.axes(Qt.Orientation.Vertical)[0]

    assert series.count() == 2
    assert series.pointsVisible() is False
    assert vertical_axis.max() > 4
