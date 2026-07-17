from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QApplication, QTabWidget, QWidget

from mailbox_manager.domain.models import EmailAccount, ProtocolType
from mailbox_manager.gui.main_window import MainWindow
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.enterprise_repositories import (
    SettingsRepository,
    StatisticsRepository,
)
from mailbox_manager.storage.repositories import AccountRepository, MessageRepository

WINDOW_SIZES = (
    QSize(1080, 680),
    QSize(1280, 720),
    QSize(1600, 900),
)


def _window(qtbot, tmp_path) -> MainWindow:
    database = Database(tmp_path / "responsive-layout.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"R" * 32))
    accounts.add_many(
        [
            EmailAccount(
                email="responsive@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                secret="app-password",
            )
        ]
    )
    window = MainWindow(
        accounts,
        MessageRepository(database),
        settings=SettingsRepository(database),
        statistics=StatisticsRepository(database),
    )
    qtbot.addWidget(window)
    return window


def _settle(qtbot) -> None:
    qtbot.wait(20)


def _assert_fully_inside(widget: QWidget, window: MainWindow) -> None:
    assert widget.isVisibleTo(window), widget.objectName()
    assert widget.width() > 0 and widget.height() > 0
    position = widget.mapTo(window, QPoint(0, 0))
    geometry = QRect(position, widget.size())
    assert window.rect().contains(geometry), (
        f"{widget.objectName()} escaped the window: "
        f"widget={geometry.getRect()} window={window.rect().getRect()}"
    )


@pytest.mark.parametrize(
    "window_size",
    WINDOW_SIZES,
    ids=lambda size: f"{size.width()}x{size.height()}",
)
def test_main_window_keeps_toolbar_and_account_workspace_usable(
    qtbot, tmp_path, window_size: QSize
) -> None:
    window = _window(qtbot, tmp_path)
    window.resize(window_size)
    window.show()
    _settle(qtbot)

    assert window.size() == window_size
    assert window.main_toolbar.objectName() == "mainToolbar"
    theme_button = window.main_toolbar.widgetForAction(window.theme_action)
    assert theme_button is not None
    for control in (
        window.tools_menu_button,
        theme_button,
        window.settings_tool_button,
    ):
        _assert_fully_inside(control, window)

    compact = window_size.width() < 1320
    assert window.toolbar_more_button.isVisibleTo(window) is compact
    assert window._workspace_compact is compact
    if compact:
        assert window.toolbar_more_button.objectName() == "toolbarMoreButton"
        _assert_fully_inside(window.toolbar_more_button, window)
        assert window.import_menu_button.isVisibleTo(window) is False
        overflow_actions = set(window.toolbar_more_button.menu().actions())
        assert {
            window.add_account_action,
            window.import_action,
            window.paste_import_action,
            window.export_action,
            window.compose_action,
            window.theme_action,
            window.settings_action,
        }.issubset(overflow_actions)
    else:
        assert window.import_menu_button.isVisibleTo(window) is True

    window.main_tabs.setCurrentWidget(window.account_workspace)
    _settle(qtbot)

    filter_controls = (
        window.account_search,
        window.tag_filter,
        window.status_filter,
        window.group_move_combo,
        window.move_group_button,
    )
    for control in filter_controls:
        _assert_fully_inside(control, window)

    assert window.account_search.width() >= 140
    assert window.account_stack.currentWidget() is window.account_table
    assert window.account_table.viewport().width() >= 480
    assert window.account_table.viewport().height() >= 100

    details_panel = window.findChild(QWidget, "detailsPanel")
    assert details_panel is not None
    _assert_fully_inside(details_panel, window)
    assert details_panel.width() >= 600
    assert details_panel.height() >= 160
    assert window.message_list.viewport().width() >= 170
    assert window.message_list.viewport().height() >= 70
    assert window.message_body.width() >= 250
    assert window.message_body.height() >= 80
    message_tabs = window.findChild(QTabWidget, "messageTabs")
    assert message_tabs is not None
    assert message_tabs.tabBar().drawBase() is False


def test_large_font_reflows_top_toolbar_before_controls_are_clipped(
    qtbot, tmp_path
) -> None:
    application = QApplication.instance()
    assert application is not None
    previous_font = application.font()
    window = _window(qtbot, tmp_path)
    window.resize(1440, 760)
    window.show()
    _settle(qtbot)
    try:
        window._apply_appearance_preferences(
            {
                "theme": "grass_gray",
                "font_family": "",
                "font_size": 18,
                "font_weight": 600,
            },
            persist=False,
        )
        window.resize(1400, 760)
        _settle(qtbot)

        assert window._toolbar_compact is True
        for control in (
            window.toolbar_more_button,
            window.tools_menu_button,
            window.theme_tool_button,
            window.settings_tool_button,
        ):
            _assert_fully_inside(control, window)
        assert window.settings_tool_button.toolButtonStyle() is (
            Qt.ToolButtonStyle.ToolButtonIconOnly
        )

        window.resize(1080, 760)
        _settle(qtbot)
        for control in (
            window.toolbar_more_button,
            window.concurrency_box,
            window.tools_menu_button,
            window.theme_tool_button,
            window.settings_tool_button,
        ):
            _assert_fully_inside(control, window)

        window.resize(2300, 760)
        _settle(qtbot)
        assert window._toolbar_compact is False
        for control in (
            window.add_account_tool_button,
            window.import_menu_button,
            window.export_tool_button,
            window.compose_tool_button,
            window.start_tool_button,
            window.stop_tool_button,
            window.tools_menu_button,
            window.settings_tool_button,
        ):
            _assert_fully_inside(control, window)
            assert control.font().weight() >= 600
    finally:
        application.setFont(previous_font)


def test_dashboard_tab_return_and_resize_restore_both_scroll_origins(
    qtbot, tmp_path
) -> None:
    window = _window(qtbot, tmp_path)
    window.resize(WINDOW_SIZES[0])
    # Keep both axes genuinely scrollable at every tested top-level size.  This
    # exercises scroll restoration rather than passing because a bar has no range.
    window.dashboard.scroll_area.setWidgetResizable(False)
    window.dashboard.content.setMinimumSize(1800, 1200)
    window.dashboard.content.resize(1800, 1200)
    window.show()
    window.main_tabs.setCurrentWidget(window.dashboard)
    _settle(qtbot)
    vertical = window.dashboard.scroll_area.verticalScrollBar()
    horizontal = window.dashboard.scroll_area.horizontalScrollBar()
    assert vertical.maximum() > vertical.minimum()
    assert horizontal.maximum() > horizontal.minimum()

    vertical.setValue(vertical.maximum())
    horizontal.setValue(horizontal.maximum())
    window.main_tabs.setCurrentWidget(window.account_workspace)
    window.main_tabs.setCurrentWidget(window.dashboard)
    qtbot.waitUntil(
        lambda: vertical.value() == vertical.minimum()
        and horizontal.value() == horizontal.minimum()
    )

    for window_size in WINDOW_SIZES[1:]:
        vertical.setValue(vertical.maximum())
        horizontal.setValue(horizontal.maximum())
        window.resize(window_size)
        qtbot.waitUntil(
            lambda: vertical.value() == vertical.minimum()
            and horizontal.value() == horizontal.minimum()
        )
