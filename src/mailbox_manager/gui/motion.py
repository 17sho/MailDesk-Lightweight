from __future__ import annotations

import ctypes
import sys
from functools import lru_cache

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSettings,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsEffect,
    QProgressBar,
    QStackedWidget,
    QTabWidget,
    QWidget,
)


def ease_out_curve() -> QEasingCurve:
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(
        QPointF(0.23, 1.0),
        QPointF(0.32, 1.0),
        QPointF(1.0, 1.0),
    )
    return curve


def crossfade_curve() -> QEasingCurve:
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(
        QPointF(0.77, 0.0),
        QPointF(0.175, 1.0),
        QPointF(1.0, 1.0),
    )
    return curve


@lru_cache(maxsize=1)
def _system_reduced_motion() -> bool:
    if sys.platform == "win32":
        animations_enabled = ctypes.c_int(1)
        success = ctypes.windll.user32.SystemParametersInfoW(  # type: ignore[attr-defined]
            0x1042,
            0,
            ctypes.byref(animations_enabled),
            0,
        )
        return bool(success) and not bool(animations_enabled.value)
    if sys.platform == "darwin":
        settings = QSettings("com.apple.universalaccess", "")
        return bool(settings.value("reduceMotion", False, type=bool))
    return False


def reduced_motion_enabled() -> bool:
    application = QApplication.instance()
    if application is not None:
        override = application.property("maildeskReducedMotion")
        if override is not None:
            return bool(override)
    return _system_reduced_motion()


class SnapshotTransition(QWidget):
    """Paint an outgoing snapshot above settled content without moving layout."""

    finished = Signal()

    def __init__(
        self,
        target: QWidget,
        snapshot: QPixmap,
        *,
        duration: int = 180,
        offset: QPoint | None = None,
        geometry: QRect | None = None,
    ) -> None:
        super().__init__(target)
        reduced = reduced_motion_enabled()
        self.duration = min(100, duration) if reduced else max(1, duration)
        self.offset = QPoint() if reduced or offset is None else QPoint(offset)
        self._snapshot = snapshot
        self._progress = 0.0
        self._has_painted = False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(target.rect() if geometry is None else geometry)

        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setDuration(self.duration)
        self._animation.setEasingCurve(crossfade_curve())
        self._animation.valueChanged.connect(self._set_progress)
        self._animation.finished.connect(self._finish)

    @property
    def is_running(self) -> bool:
        return self._animation.state() == QVariantAnimation.State.Running

    @property
    def snapshot(self) -> QPixmap:
        return self._snapshot

    @property
    def has_painted(self) -> bool:
        return self._has_painted

    def start(self) -> None:
        self.show()
        self.raise_()
        self._animation.start()

    def cancel(self) -> None:
        self._animation.stop()
        self.hide()
        self.deleteLater()

    def _set_progress(self, value: object) -> None:
        self._progress = max(0.0, min(1.0, float(value)))
        self.update()

    def _finish(self) -> None:
        self.hide()
        self.finished.emit()
        self.deleteLater()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        self._has_painted = True
        if self._snapshot.isNull():
            return
        painter = QPainter(self)
        painter.setOpacity(1.0 - self._progress)
        position = QPoint(
            round(self.offset.x() * self._progress),
            round(self.offset.y() * self._progress),
        )
        painter.drawPixmap(position, self._snapshot)


class FadeSlideEffect(QGraphicsEffect):
    """Translate and fade a small surface at paint time without moving it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._progress = 0.0
        self._travel = 0

    def set_motion(self, progress: float, travel: int) -> None:
        self._progress = max(0.0, min(1.0, float(progress)))
        self._travel = max(0, int(travel))
        self.updateBoundingRect()
        self.update()

    def boundingRectFor(self, source_rect: QRectF) -> QRectF:
        return source_rect.adjusted(0, 0, 0, self._travel)

    def draw(self, painter: QPainter) -> None:
        offset = QPoint()
        pixmap = self.sourcePixmap(
            Qt.CoordinateSystem.LogicalCoordinates,
            offset,
            QGraphicsEffect.PixmapPadMode.PadToEffectiveBoundingRect,
        )
        if pixmap.isNull() or self._progress <= 0.0:
            return
        painter.save()
        painter.setOpacity(self._progress)
        painter.translate(0, round((1.0 - self._progress) * self._travel))
        painter.drawPixmap(offset, pixmap)
        painter.restore()


class SmoothProgressBar(QProgressBar):
    """A progress bar that retargets from its current presented value."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._motion = QVariantAnimation(self)
        self._motion.setEasingCurve(ease_out_curve())
        self._motion.valueChanged.connect(self._present_motion_value)
        self._motion.finished.connect(self._finish_motion)
        self._motion_start = 0
        self._motion_target = 0
        self._motion_duration = 0

    @property
    def motion_start(self) -> int:
        return self._motion_start

    @property
    def motion_target(self) -> int:
        return self._motion_target

    @property
    def motion_duration(self) -> int:
        return self._motion_duration

    @property
    def motion_running(self) -> bool:
        return self._motion.state() == QVariantAnimation.State.Running

    def set_animated_value(self, value: int) -> None:
        target = max(self.minimum(), min(self.maximum(), int(value)))
        current = self.value()
        self._motion.stop()
        self._motion_start = current
        self._motion_target = target
        difference = abs(target - current)
        if difference == 0 or self.minimum() == self.maximum():
            QProgressBar.setValue(self, target)
            self._motion_duration = 0
            return
        duration = max(80, min(160, difference * 3))
        self._motion_duration = min(80, duration) if reduced_motion_enabled() else duration
        self._motion.setStartValue(current)
        self._motion.setEndValue(target)
        self._motion.setDuration(self._motion_duration)
        self._motion.start()

    def stop_motion(self) -> None:
        self._motion.stop()
        self._motion_start = self.value()
        self._motion_target = self.value()
        self._motion_duration = 0

    def setValue(self, value: int) -> None:
        self.stop_motion()
        QProgressBar.setValue(self, value)
        self._motion_start = self.value()
        self._motion_target = self.value()

    def _present_motion_value(self, value: object) -> None:
        QProgressBar.setValue(self, round(float(value)))

    def _finish_motion(self) -> None:
        QProgressBar.setValue(self, self._motion_target)


class _AnimatedPages:
    def _init_page_motion(self, duration: int, distance: int) -> None:
        self._motion_duration = duration
        self._motion_distance = distance
        self._active_transition: SnapshotTransition | None = None

    @property
    def active_transition(self) -> SnapshotTransition | None:
        return self._active_transition

    def _cancel_page_transition(self) -> None:
        if self._active_transition is not None:
            self._active_transition.cancel()
            self._active_transition = None

    def _stage_page_transition(
        self,
        page: QWidget | None,
        old_index: int,
        new_index: int,
    ) -> SnapshotTransition | None:
        if (
            page is None
            or not self.isVisible()
            or not page.isVisible()
            or old_index == new_index
        ):
            self._cancel_page_transition()
            return None
        host = page.parentWidget()
        if host is None:
            self._cancel_page_transition()
            return None
        page_geometry = page.geometry()
        # Capture the shared page host before cancelling an in-flight overlay.
        # This preserves the exact frame the user currently sees when retargeting.
        snapshot = host.grab(page_geometry)
        self._cancel_page_transition()
        if snapshot.isNull():
            return None
        direction = -1 if new_index > old_index else 1
        transition = SnapshotTransition(
            host,
            snapshot,
            duration=self._motion_duration,
            offset=QPoint(direction * self._motion_distance, 0),
            geometry=page_geometry,
        )
        self._active_transition = transition

        def clear_transition() -> None:
            if self._active_transition is transition:
                self._active_transition = None

        transition.finished.connect(clear_transition)
        # Paint the outgoing frame synchronously. The new page is switched only
        # after this guard is visible, preventing a one-frame flash on Windows.
        transition.show()
        transition.raise_()
        transition.repaint()
        return transition


class AnimatedStackedWidget(QStackedWidget, _AnimatedPages):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        duration: int = 170,
        distance: int = 6,
    ) -> None:
        super().__init__(parent)
        self._init_page_motion(duration, distance)

    def setCurrentIndex(self, index: int) -> None:
        old_index = self.currentIndex()
        if index == old_index:
            super().setCurrentIndex(index)
            return
        transition = self._stage_page_transition(
            self.currentWidget(),
            old_index,
            index,
        )
        super().setCurrentIndex(index)
        if transition is not None:
            transition.start()

    def setCurrentWidget(self, widget: QWidget) -> None:
        index = self.indexOf(widget)
        if index >= 0:
            self.setCurrentIndex(index)

class AnimatedTabWidget(QTabWidget, _AnimatedPages):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        duration: int = 160,
        distance: int = 6,
    ) -> None:
        super().__init__(parent)
        self._init_page_motion(duration, distance)
        self._pending_transition: SnapshotTransition | None = None
        self._pending_index = -1
        self._skip_next_transition = False
        self.tabBar().installEventFilter(self)
        self.currentChanged.connect(self._current_page_changed)

    def _prepare_page_transition(self, target_index: int) -> None:
        if not 0 <= target_index < self.count() or target_index == self.currentIndex():
            self._pending_transition = None
            self._pending_index = -1
            self._cancel_page_transition()
            return
        old_index = self.currentIndex()
        self._pending_transition = self._stage_page_transition(
            self.currentWidget(),
            old_index,
            target_index,
        )
        self._pending_index = old_index if self._pending_transition is not None else -1

    def setCurrentIndex(self, index: int) -> None:
        if index != self.currentIndex():
            self._prepare_page_transition(index)
        super().setCurrentIndex(index)

    def setCurrentWidget(self, widget: QWidget) -> None:
        index = self.indexOf(widget)
        if index >= 0:
            self.setCurrentIndex(index)

    def _clear_skip_transition(self) -> None:
        self._skip_next_transition = False

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self.tabBar():
            if event.type() == QEvent.Type.MouseButtonPress and isinstance(
                event, QMouseEvent
            ):
                # Native tab-bar clicks bypass the Python setCurrentIndex
                # override, so capture here after clearing any keyboard marker.
                self._skip_next_transition = False
                target_index = self.tabBar().tabAt(event.position().toPoint())
                if (
                    target_index >= 0
                    and target_index != self.currentIndex()
                    and self.isTabEnabled(target_index)
                ):
                    self._prepare_page_transition(target_index)
            elif event.type() in (QEvent.Type.KeyPress, QEvent.Type.Wheel):
                if isinstance(event, QKeyEvent) or event.type() == QEvent.Type.Wheel:
                    self._skip_next_transition = True
                    self._pending_transition = None
                    self._pending_index = -1
                    self._cancel_page_transition()
                    QTimer.singleShot(0, self._clear_skip_transition)
        return super().eventFilter(watched, event)

    def _current_page_changed(self, index: int) -> None:
        if self._skip_next_transition:
            self._skip_next_transition = False
            self._pending_transition = None
            self._pending_index = -1
            self._cancel_page_transition()
            return
        transition = self._pending_transition
        old_index = self._pending_index
        self._pending_transition = None
        self._pending_index = -1
        if transition is not None and old_index >= 0 and old_index != index:
            transition.start()
