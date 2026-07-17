from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from mailbox_manager.gui.motion import (
    AnimatedStackedWidget,
    AnimatedTabWidget,
    SnapshotTransition,
)
from mailbox_manager.gui.toast import BottomToast


def _snapshot(width: int = 160, height: int = 90) -> QPixmap:
    snapshot = QPixmap(width, height)
    snapshot.fill(QColor("#2563eb"))
    return snapshot


def test_snapshot_transition_does_not_move_or_resize_target(qtbot) -> None:
    target = QWidget()
    target.resize(160, 90)
    qtbot.addWidget(target)
    target.show()
    original_geometry = target.geometry()
    transition = SnapshotTransition(
        target,
        _snapshot(),
        duration=120,
        offset=QPoint(-6, 0),
    )
    finished = QSignalSpy(transition.finished)

    transition.start()

    assert transition.parentWidget() is target
    assert target.geometry() == original_geometry
    qtbot.waitUntil(lambda: finished.count() == 1, timeout=1000)
    assert target.geometry() == original_geometry


def test_snapshot_transition_respects_reduced_motion(qtbot) -> None:
    app = QApplication.instance()
    assert app is not None
    previous = app.property("maildeskReducedMotion")
    app.setProperty("maildeskReducedMotion", True)
    target = QWidget()
    target.resize(160, 90)
    qtbot.addWidget(target)
    try:
        transition = SnapshotTransition(
            target,
            _snapshot(),
            duration=220,
            offset=QPoint(8, 0),
        )

        assert transition.duration <= 100
        assert transition.offset == QPoint()
    finally:
        app.setProperty("maildeskReducedMotion", previous)


def test_animated_stacked_widget_switches_immediately_with_overlay(qtbot) -> None:
    stack = AnimatedStackedWidget(duration=160, distance=6)
    first = QLabel("工作台")
    second = QLabel("账号与邮件")
    stack.addWidget(first)
    stack.addWidget(second)
    stack.resize(420, 260)
    qtbot.addWidget(stack)
    stack.show()
    QApplication.processEvents()

    stack.setCurrentIndex(1)

    assert stack.currentWidget() is second
    assert stack.active_transition is not None


def test_stacked_page_overlay_is_visible_before_new_page_is_exposed(qtbot) -> None:
    stack = AnimatedStackedWidget(duration=140, distance=0)
    stack.addWidget(QLabel("工作台"))
    stack.addWidget(QLabel("账号与邮件"))
    stack.resize(900, 600)
    qtbot.addWidget(stack)
    stack.show()
    QApplication.processEvents()
    overlay_visible_when_page_changes: list[bool] = []
    stack.currentChanged.connect(
        lambda _index: overlay_visible_when_page_changes.append(
            stack.active_transition is not None
            and stack.active_transition.isVisible()
        )
    )

    stack.setCurrentIndex(1)

    assert overlay_visible_when_page_changes == [True]


def test_animated_tab_widget_skips_keyboard_navigation_motion(qtbot) -> None:
    tabs = AnimatedTabWidget(duration=160, distance=6)
    tabs.addTab(QLabel("工作台"), "工作台概览")
    tabs.addTab(QLabel("账号"), "账号与邮件")
    tabs.resize(480, 300)
    qtbot.addWidget(tabs)
    tabs.show()
    tabs.tabBar().setFocus()
    QApplication.processEvents()

    qtbot.keyClick(tabs.tabBar(), Qt.Key.Key_Right)

    assert tabs.currentIndex() == 1
    assert tabs.active_transition is None


def test_keyboard_event_without_navigation_does_not_suppress_next_mouse_motion(
    qtbot,
) -> None:
    tabs = AnimatedTabWidget(duration=160, distance=6)
    tabs.addTab(QLabel("工作台"), "工作台概览")
    tabs.addTab(QLabel("账号"), "账号与邮件")
    tabs.resize(480, 300)
    qtbot.addWidget(tabs)
    tabs.show()
    tabs.tabBar().setFocus()
    QApplication.processEvents()

    qtbot.keyClick(tabs.tabBar(), Qt.Key.Key_A)
    qtbot.mouseClick(
        tabs.tabBar(),
        Qt.MouseButton.LeftButton,
        pos=tabs.tabBar().tabRect(1).center(),
    )

    assert tabs.currentIndex() == 1
    assert tabs.active_transition is not None


def test_disabled_tab_does_not_stage_a_stuck_overlay(qtbot) -> None:
    tabs = AnimatedTabWidget(duration=130, distance=0)
    tabs.addTab(QLabel("工作台"), "工作台概览")
    tabs.addTab(QLabel("账号"), "账号与邮件")
    tabs.setTabEnabled(1, False)
    tabs.resize(480, 300)
    qtbot.addWidget(tabs)
    tabs.show()
    QApplication.processEvents()

    qtbot.mouseClick(
        tabs.tabBar(),
        Qt.MouseButton.LeftButton,
        pos=tabs.tabBar().tabRect(1).center(),
    )

    assert tabs.currentIndex() == 0
    assert tabs.active_transition is None


@pytest.mark.parametrize("target_index", [1, 0])
def test_animated_tab_widget_mouse_navigation_is_interruptible(
    qtbot,
    target_index: int,
) -> None:
    tabs = AnimatedTabWidget(duration=160, distance=6)
    tabs.addTab(QLabel("工作台"), "工作台概览")
    tabs.addTab(QLabel("账号"), "账号与邮件")
    tabs.resize(480, 300)
    qtbot.addWidget(tabs)
    tabs.show()
    tabs.setCurrentIndex(1 - target_index)
    QApplication.processEvents()

    qtbot.mouseClick(
        tabs.tabBar(),
        Qt.MouseButton.LeftButton,
        pos=tabs.tabBar().tabRect(target_index).center(),
    )

    assert tabs.currentIndex() == target_index
    assert tabs.active_transition is not None


def test_retargeted_page_motion_starts_from_current_presented_frame(qtbot) -> None:
    tabs = AnimatedTabWidget(duration=180, distance=8)
    first = QLabel("工作台")
    first.setStyleSheet("background: #ef4444;")
    second = QLabel("账号")
    second.setStyleSheet("background: #10b981;")
    tabs.addTab(first, "工作台概览")
    tabs.addTab(second, "账号与邮件")
    tabs.resize(480, 300)
    qtbot.addWidget(tabs)
    tabs.show()
    QApplication.processEvents()
    tabs.setCurrentIndex(1)
    qtbot.wait(50)
    page_host = second.parentWidget()
    assert page_host is not None
    presented_frame = page_host.grab(second.geometry()).toImage()

    tabs.setCurrentIndex(0)

    transition = tabs.active_transition
    assert transition is not None
    assert transition.snapshot.toImage() == presented_frame


def test_bottom_toast_enters_and_exits_on_the_same_short_path(qtbot) -> None:
    host = QWidget()
    host.resize(900, 600)
    toast = BottomToast(host)
    qtbot.addWidget(host)
    host.show()

    toast.show_message("设置已保存", duration=900)

    assert toast.isVisible() is True
    assert toast.motion_target == 1.0
    assert toast.motion_duration <= 170
    qtbot.waitUntil(lambda: toast.motion_progress == pytest.approx(1.0), timeout=800)
    settled_position = toast.pos()

    toast.dismiss()

    assert toast.motion_target == 0.0
    assert toast.motion_duration <= 130
    qtbot.waitUntil(toast.isHidden, timeout=800)
    assert toast.pos() == settled_position


def test_bottom_toast_reduced_motion_keeps_feedback_without_travel(qtbot) -> None:
    app = QApplication.instance()
    assert app is not None
    previous = app.property("maildeskReducedMotion")
    app.setProperty("maildeskReducedMotion", True)
    host = QWidget()
    host.resize(900, 600)
    toast = BottomToast(host)
    qtbot.addWidget(host)
    host.show()
    try:
        toast.show_message("已复制")

        assert toast.motion_duration <= 100
        assert toast.pos() == toast.base_position
    finally:
        app.setProperty("maildeskReducedMotion", previous)
