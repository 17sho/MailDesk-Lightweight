from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

DEFAULT_FONT_SIZE = 10
DEFAULT_FONT_WEIGHT = 500
MIN_FONT_SIZE = 9
MAX_FONT_SIZE = 18
SUPPORTED_FONT_WEIGHTS = (400, 500, 600)
DEFAULT_THEME = "grass_gray"


@dataclass(frozen=True, slots=True)
class ThemeDefinition:
    theme_id: str
    label: str
    dark: bool
    window: str
    surface: str
    panel: str
    border: str
    text: str
    muted: str
    accent: str
    accent_soft: str


THEME_DEFINITIONS = (
    ThemeDefinition(
        "midnight",
        "暗夜黑",
        True,
        "#0b0d10",
        "#111318",
        "#171a20",
        "#2a2f38",
        "#f4f7fb",
        "#9aa4b2",
        "#60a5fa",
        "#182b46",
    ),
    ThemeDefinition(
        "grass_gray",
        "草木灰",
        False,
        "#f5f7fa",
        "#ffffff",
        "#f8fafc",
        "#dfe5ed",
        "#172033",
        "#64748b",
        "#2563eb",
        "#dbeafe",
    ),
    ThemeDefinition(
        "twilight_yellow",
        "落晖黄",
        False,
        "#faf7f1",
        "#fffdf9",
        "#f5f0e7",
        "#dfd5c6",
        "#332b20",
        "#7f705d",
        "#98713d",
        "#f2e8d9",
    ),
    ThemeDefinition(
        "distant_green",
        "远山绿",
        False,
        "#f3f8f1",
        "#fbfef9",
        "#edf5e9",
        "#d3dfcd",
        "#203324",
        "#657765",
        "#3f8a4f",
        "#dcefdc",
    ),
    ThemeDefinition(
        "sky_blue",
        "天空蓝",
        False,
        "#f1f7fb",
        "#fbfdff",
        "#eaf4fa",
        "#cfe0ea",
        "#17303f",
        "#607786",
        "#1688b9",
        "#d9eef8",
    ),
    ThemeDefinition(
        "cinnabar_red",
        "朱砂红",
        False,
        "#fcf5f2",
        "#fffdfc",
        "#faece7",
        "#ead2ca",
        "#3a2520",
        "#826b64",
        "#c74736",
        "#f8ded7",
    ),
    ThemeDefinition(
        "smoke_purple",
        "烟墨紫",
        True,
        "#15101d",
        "#1b1525",
        "#231a2f",
        "#392b49",
        "#f4effa",
        "#afa2bd",
        "#a778ee",
        "#352150",
    ),
)
THEME_BY_ID = {definition.theme_id: definition for definition in THEME_DEFINITIONS}

_FONT_SIZE_PATTERN = re.compile(r"(font-size\s*:\s*)(\d+)(px)", re.IGNORECASE)
_FONT_WEIGHT_PATTERN = re.compile(r"(font-weight\s*:\s*)(\d+)", re.IGNORECASE)


def normalized_appearance(values: Mapping[str, object] | None) -> dict[str, object]:
    values = values or {}
    requested_theme = str(values.get("theme", "")).strip().casefold()
    if requested_theme not in THEME_BY_ID:
        requested_theme = "midnight" if bool(values.get("dark_theme", False)) else DEFAULT_THEME
    theme = THEME_BY_ID[requested_theme]
    try:
        font_size = int(values.get("font_size", DEFAULT_FONT_SIZE))
    except (TypeError, ValueError):
        font_size = DEFAULT_FONT_SIZE
    try:
        font_weight = int(values.get("font_weight", DEFAULT_FONT_WEIGHT))
    except (TypeError, ValueError):
        font_weight = DEFAULT_FONT_WEIGHT
    return {
        "theme": theme.theme_id,
        "dark_theme": theme.dark,
        "font_family": str(values.get("font_family", "")).strip()[:100],
        "font_size": max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, font_size)),
        "font_weight": (
            font_weight
            if font_weight in SUPPORTED_FONT_WEIGHTS
            else DEFAULT_FONT_WEIGHT
        ),
    }


def scaled_stylesheet(
    stylesheet: str,
    font_size: int,
    font_weight: int = DEFAULT_FONT_WEIGHT,
) -> str:
    """Adjust themed text by the user's base size and weight.

    Proportional scaling made a 25 px heading grow to 45 px when the base font
    was set to 18 pt.  Adding the base-size delta keeps the established visual
    hierarchy while allowing Qt's layouts and the application font to handle
    accessibility sizing once.
    """

    bounded_size = max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, int(font_size)))
    bounded_weight = (
        int(font_weight)
        if int(font_weight) in SUPPORTED_FONT_WEIGHTS
        else DEFAULT_FONT_WEIGHT
    )
    delta = bounded_size - DEFAULT_FONT_SIZE

    def replace(match: re.Match[str]) -> str:
        source = int(match.group(2))
        target = max(9, source + delta)
        return f"{match.group(1)}{target}{match.group(3)}"

    scaled = _FONT_SIZE_PATTERN.sub(replace, stylesheet)

    def replace_weight(match: re.Match[str]) -> str:
        source = int(match.group(2))
        target = max(source, bounded_weight)
        return f"{match.group(1)}{target}"

    return _FONT_WEIGHT_PATTERN.sub(replace_weight, scaled)


def appearance_palette(theme: str | bool) -> QPalette:
    theme_id = (
        "midnight" if theme is True else DEFAULT_THEME if theme is False else str(theme)
    )
    definition = THEME_BY_ID.get(theme_id, THEME_BY_ID[DEFAULT_THEME])
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: definition.window,
        QPalette.ColorRole.WindowText: definition.text,
        QPalette.ColorRole.Base: definition.surface,
        QPalette.ColorRole.AlternateBase: definition.panel,
        QPalette.ColorRole.ToolTipBase: definition.text if definition.dark else definition.surface,
        QPalette.ColorRole.ToolTipText: definition.window if definition.dark else definition.text,
        QPalette.ColorRole.Text: definition.text,
        QPalette.ColorRole.Button: definition.panel,
        QPalette.ColorRole.ButtonText: definition.text,
        QPalette.ColorRole.BrightText: "#ffffff",
        QPalette.ColorRole.Link: definition.accent,
        QPalette.ColorRole.LinkVisited: definition.accent,
        QPalette.ColorRole.Highlight: definition.accent,
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.PlaceholderText: definition.muted,
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(definition.muted))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Base,
        QColor(definition.panel),
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
    font.setStyleStrategy(QFont.StyleStrategy.PreferQuality)
    if sys.platform == "win32":
        font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    elif sys.platform == "darwin":
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    application.setFont(font)
    application.setPalette(appearance_palette(str(normalized["theme"])))
    application.setProperty("maildeskTheme", str(normalized["theme"]))
    application.setProperty("maildeskDarkTheme", bool(normalized["dark_theme"]))
    application.setProperty("maildeskFontSize", int(normalized["font_size"]))
    application.setProperty("maildeskFontWeight", int(normalized["font_weight"]))
    return normalized
