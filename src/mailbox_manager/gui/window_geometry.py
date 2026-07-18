from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QDialog, QWidget


def configure_resizable_window(
    window: QWidget,
    *,
    preferred: QSize,
    minimum: QSize,
    screen_margin: int = 48,
) -> None:
    """Fit a window to its active screen while keeping user resizing enabled."""

    parent = window.parentWidget()
    screen = parent.screen() if parent is not None else window.screen()
    if screen is None:
        application = QApplication.instance()
        screen = application.primaryScreen() if application is not None else None
    if screen is None:
        window.setMinimumSize(minimum)
        window.resize(preferred)
    else:
        available = screen.availableGeometry().size()
        usable_width = max(1, available.width() - max(0, screen_margin))
        usable_height = max(1, available.height() - max(0, screen_margin))
        minimum_width = min(max(1, minimum.width()), usable_width)
        minimum_height = min(max(1, minimum.height()), usable_height)
        window.setMinimumSize(minimum_width, minimum_height)
        window.resize(
            min(max(minimum_width, preferred.width()), usable_width),
            min(max(minimum_height, preferred.height()), usable_height),
        )
    if isinstance(window, QDialog):
        window.setSizeGripEnabled(True)


def center_window_on_parent(window: QWidget) -> None:
    """Center a transient window on its owning software window and keep it visible."""

    parent = window.parentWidget()
    screen = parent.screen() if parent is not None else window.screen()
    available = screen.availableGeometry() if screen is not None else None
    target = parent.frameGeometry() if parent is not None and parent.isVisible() else available
    if target is None:
        return
    frame = window.frameGeometry()
    frame.moveCenter(target.center())
    if available is not None:
        frame.moveLeft(
            max(available.left(), min(frame.left(), available.right() - frame.width() + 1))
        )
        frame.moveTop(
            max(available.top(), min(frame.top(), available.bottom() - frame.height() + 1))
        )
    window.move(frame.topLeft())
