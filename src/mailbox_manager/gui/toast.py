from __future__ import annotations

from typing import ClassVar

from PySide6.QtCore import QPoint, Qt, QTimer, QVariantAnimation
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from mailbox_manager.gui.icons import line_icon
from mailbox_manager.gui.motion import (
    FadeSlideEffect,
    ease_out_curve,
    reduced_motion_enabled,
)


class BottomToast(QFrame):
    """A compact, non-blocking notification anchored above the status bar."""

    _ICONS: ClassVar[dict[str, str]] = {
        "success": "check",
        "warning": "warning",
        "info": "info",
    }

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("bottomToast")
        self.setProperty("tone", "success")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setMinimumWidth(280)
        self.setMaximumWidth(640)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 16, 10)
        layout.setSpacing(10)
        self.icon_label = QLabel()
        self.icon_label.setObjectName("bottomToastIcon")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setFixedSize(22, 22)
        self.message_label = QLabel()
        self.message_label.setObjectName("bottomToastText")
        self.message_label.setWordWrap(True)
        self.message_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.message_label, 1)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.dismiss)
        self._motion_effect = FadeSlideEffect(self)
        self.setGraphicsEffect(self._motion_effect)
        self._motion_animation = QVariantAnimation(self)
        self._motion_animation.setEasingCurve(ease_out_curve())
        self._motion_animation.valueChanged.connect(self._motion_value_changed)
        self._motion_animation.finished.connect(self._motion_finished)
        self._motion_progress = 0.0
        self._motion_target = 0.0
        self._motion_duration = 0
        self._base_position = QPoint()
        self.hide()

    @property
    def motion_progress(self) -> float:
        return self._motion_progress

    @property
    def motion_target(self) -> float:
        return self._motion_target

    @property
    def motion_duration(self) -> int:
        return self._motion_duration

    @property
    def base_position(self) -> QPoint:
        return QPoint(self._base_position)

    def show_message(
        self,
        message: str,
        *,
        tone: str = "success",
        duration: int = 2400,
    ) -> None:
        tone = tone if tone in self._ICONS else "info"
        self.setProperty("tone", tone)
        self.icon_label.setPixmap(
            line_icon(self._ICONS[tone], "#ffffff", 14).pixmap(14, 14)
        )
        self.message_label.setText(message)
        self.style().unpolish(self)
        self.style().polish(self)
        self.adjustSize()
        parent = self.parentWidget()
        if parent is not None:
            width = min(max(self.sizeHint().width(), 280), parent.width() - 48)
            self.resize(width, self.sizeHint().height())
        was_visible = self.isVisible()
        self.reposition()
        self.show()
        self.raise_()
        if was_visible:
            self._motion_animation.stop()
            self._motion_progress = 1.0
            self._motion_target = 1.0
            self._apply_motion_progress()
        else:
            self._motion_progress = 0.0
            self._apply_motion_progress()
            self._animate_to(1.0, 170)
        self._hide_timer.start(max(800, duration))

    def dismiss(self) -> None:
        self._hide_timer.stop()
        if self.isVisible():
            self._animate_to(0.0, 130)

    def _animate_to(self, target: float, duration: int) -> None:
        self._motion_animation.stop()
        self._motion_target = max(0.0, min(1.0, target))
        distance = abs(self._motion_target - self._motion_progress)
        effective_duration = min(100, duration) if reduced_motion_enabled() else duration
        self._motion_duration = max(1, round(effective_duration * distance))
        self._motion_animation.setStartValue(self._motion_progress)
        self._motion_animation.setEndValue(self._motion_target)
        self._motion_animation.setDuration(self._motion_duration)
        self._motion_animation.start()

    def _motion_value_changed(self, value: object) -> None:
        self._motion_progress = max(0.0, min(1.0, float(value)))
        self._apply_motion_progress()

    def _motion_finished(self) -> None:
        self._motion_progress = self._motion_target
        self._apply_motion_progress()
        if self._motion_target == 0.0:
            self.hide()

    def _apply_motion_progress(self) -> None:
        travel = 0 if reduced_motion_enabled() else 8
        self._motion_effect.set_motion(self._motion_progress, travel)
        self.move(self._base_position)

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        status_height = 0
        status_bar_getter = getattr(parent, "statusBar", None)
        if callable(status_bar_getter):
            status_bar = status_bar_getter()
            status_height = status_bar.height() if status_bar.isVisible() else 0
        x = max(16, (parent.width() - self.width()) // 2)
        y = max(16, parent.height() - status_height - self.height() - 18)
        self._base_position = QPoint(x, y)
        self._apply_motion_progress()
