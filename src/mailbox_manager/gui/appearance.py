from __future__ import annotations

import re
from collections.abc import Mapping

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

DEFAULT_FONT_SIZE = 10
DEFAULT_FONT_WEIGHT = 500
MIN_FONT_SIZE = 9
MAX_FONT_SIZE = 18
SUPPORTED_FONT_WEIGHTS = (400, 500, 600)

_FONT_SIZE_PATTERN = re.compile(r"(font-size\s*:\s*)(\d+)(px)", re.IGNORECASE)


def normalized_appearance(values: Mapping[str, object] | None) -> dict[str, object]:
    values = values or {}
    try:
        font_size = int(values.get("font_size", DEFAULT_FONT_SIZE))
    except (TypeError, ValueError):
        font_size = DEFAULT_FONT_SIZE
    try:
        font_weight = int(values.get("font_weight", DEFAULT_FONT_WEIGHT))
    except (TypeError, ValueError):
        font_weight = DEFAULT_FONT_WEIGHT
    return {
        "dark_theme": bool(values.get("dark_theme", False)),
        "font_family": str(values.get("font_family", "")).strip()[:100],
        "font_size": max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, font_size)),
        "font_weight": (
            font_weight
            if font_weight in SUPPORTED_FONT_WEIGHTS
            else DEFAULT_FONT_WEIGHT
        ),
    }


def scaled_stylesheet(stylesheet: str, font_size: int) -> str:
    """Adjust themed text by the user's base-size delta.

    Proportional scaling made a 25 px heading grow to 45 px when the base font
    was set to 18 pt.  Adding the base-size delta keeps the established visual
    hierarchy while allowing Qt's layouts and the application font to handle
    accessibility sizing once.
    """

    bounded = max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, int(font_size)))
    delta = bounded - DEFAULT_FONT_SIZE

    def replace(match: re.Match[str]) -> str:
        source = int(match.group(2))
        target = max(9, source + delta)
        return f"{match.group(1)}{target}{match.group(3)}"

    return _FONT_SIZE_PATTERN.sub(replace, stylesheet)


def appearance_palette(dark: bool) -> QPalette:
    if not dark:
        application = QApplication.instance()
        return application.style().standardPalette() if application else QPalette()

    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: "#0f1520",
        QPalette.ColorRole.WindowText: "#e8edf5",
        QPalette.ColorRole.Base: "#111925",
        QPalette.ColorRole.AlternateBase: "#172130",
        QPalette.ColorRole.ToolTipBase: "#e8edf5",
        QPalette.ColorRole.ToolTipText: "#0f1520",
        QPalette.ColorRole.Text: "#e5eaf2",
        QPalette.ColorRole.Button: "#192332",
        QPalette.ColorRole.ButtonText: "#e5eaf2",
        QPalette.ColorRole.BrightText: "#ffffff",
        QPalette.ColorRole.Link: "#7db7ff",
        QPalette.ColorRole.LinkVisited: "#c4b5fd",
        QPalette.ColorRole.Highlight: "#2563eb",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.PlaceholderText: "#77859a",
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#69768a"))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Base,
        QColor("#121a26"),
    )
    return palette


def apply_application_appearance(
    application: QApplication,
    values: Mapping[str, object],
) -> dict[str, object]:
    normalized = normalized_appearance(values)
    family = str(normalized["font_family"])
    if not family:
        family = str(
            application.property("maildeskBaseFontFamily")
            or application.font().family()
        )
    font = QFont(family)
    font.setPointSize(int(normalized["font_size"]))
    font.setWeight(QFont.Weight(int(normalized["font_weight"])))
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    application.setFont(font)
    application.setPalette(appearance_palette(bool(normalized["dark_theme"])))
    application.setProperty("maildeskDarkTheme", bool(normalized["dark_theme"]))
    application.setProperty("maildeskFontSize", int(normalized["font_size"]))
    application.setProperty("maildeskFontWeight", int(normalized["font_weight"]))
    return normalized
