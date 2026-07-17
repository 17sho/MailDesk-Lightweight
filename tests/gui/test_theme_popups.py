from __future__ import annotations

import ast
import os
import re
import sys
from collections import Counter
from math import ceil
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QSize, qInstallMessageHandler
from PySide6.QtGui import QFont, QFontMetrics, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QComboBox, QMenu, QToolButton, QWidget

from mailbox_manager.gui.appearance import (
    THEME_DEFINITIONS,
    appearance_palette,
    apply_application_appearance,
    scaled_stylesheet,
)
from mailbox_manager.gui.settings_dialog import EnterpriseSettingsDialog
from mailbox_manager.gui.theme import DARK_THEME, LIGHT_THEME, theme_stylesheet


def _theme_rule(stylesheet: str, selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{([^}}]+)\}}", stylesheet)
    assert match is not None, f"Missing theme rule: {selector}"
    return match.group(1)


def _theme_property(rule: str, name: str) -> str:
    match = re.search(rf"{re.escape(name)}\s*:\s*([^;]+);", rule)
    assert match is not None, f"Missing theme property: {name}"
    return match.group(1).strip()


def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92
        if value <= 0.04045
        else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(foreground: str, background: str) -> float:
    foreground_luminance = _relative_luminance(foreground)
    background_luminance = _relative_luminance(background)
    lighter = max(foreground_luminance, background_luminance)
    darker = min(foreground_luminance, background_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def test_every_named_gui_surface_has_explicit_theme_coverage() -> None:
    root = Path(__file__).parents[2] / "src" / "mailbox_manager" / "gui"
    combined_theme = LIGHT_THEME + DARK_THEME
    missing: set[str] = set()
    for source in root.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "setObjectName"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                continue
            object_name = node.args[0].value
            if f"#{object_name}" not in combined_theme:
                missing.add(object_name)

    assert missing == set()


@pytest.mark.parametrize(
    "stylesheet",
    [LIGHT_THEME, DARK_THEME],
    ids=["light", "dark"],
)
def test_every_named_gui_surface_is_covered_in_each_theme(stylesheet: str) -> None:
    root = Path(__file__).parents[2] / "src" / "mailbox_manager" / "gui"
    missing: set[str] = set()
    for source in root.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "setObjectName"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                continue
            object_name = node.args[0].value
            if f"#{object_name}" not in stylesheet:
                missing.add(object_name)

    assert missing == set()


@pytest.mark.parametrize(
    "stylesheet",
    [LIGHT_THEME, DARK_THEME],
    ids=["light", "dark"],
)
def test_popup_styles_cover_interaction_states(stylesheet: str) -> None:
    required_rules = (
        "QComboBox QAbstractItemView::item:hover",
        "QComboBox QAbstractItemView::item:selected",
        "QComboBox QAbstractItemView::item:disabled",
        "QComboBox QAbstractItemView QScrollBar::handle:vertical:hover",
        "QMenu::item:selected",
        "QMenu::item:checked",
        "QMenu::item:disabled",
        "QMenu::indicator",
        "QMenu::separator",
        "QMenu::scroller",
        "QTabWidget#messageTabs > QTabBar::base",
    )

    for rule in required_rules:
        assert rule in stylesheet


@pytest.mark.parametrize(
    "stylesheet",
    [LIGHT_THEME, DARK_THEME],
    ids=["light", "dark"],
)
def test_settings_inline_actions_do_not_inherit_page_background(
    stylesheet: str,
) -> None:
    assert "QFrame#settingsInlineAction" in stylesheet
    assert "QLabel#settingsUpdateStatus" in stylesheet


@pytest.mark.parametrize(
    "stylesheet",
    [LIGHT_THEME, DARK_THEME],
    ids=["light", "dark"],
)
def test_settings_sidebar_small_text_remains_clear(stylesheet: str) -> None:
    sidebar_rule = _theme_rule(stylesheet, "QFrame#settingsSidebar")
    caption_rule = _theme_rule(stylesheet, "QLabel#settingsNavCaption")
    navigation_rule = _theme_rule(
        stylesheet,
        "QListWidget#settingsNavigation::item",
    )
    privacy_rule = _theme_rule(stylesheet, "QLabel#settingsPrivacyHint")

    sidebar_background = _theme_property(sidebar_rule, "background")
    caption_color = _theme_property(caption_rule, "color")
    navigation_color = _theme_property(navigation_rule, "color")
    privacy_color = _theme_property(privacy_rule, "color")
    privacy_background = _theme_property(privacy_rule, "background")

    assert _contrast_ratio(caption_color, sidebar_background) >= 4.5
    assert _contrast_ratio(navigation_color, sidebar_background) >= 4.5
    assert _contrast_ratio(privacy_color, privacy_background) >= 4.5
    assert int(_theme_property(caption_rule, "font-size").removesuffix("px")) >= 11
    assert int(_theme_property(privacy_rule, "font-size").removesuffix("px")) >= 11
    assert int(_theme_property(navigation_rule, "font-weight")) >= 500


@pytest.mark.parametrize(
    ("dark_theme", "stylesheet"),
    [
        (False, LIGHT_THEME),
        (True, DARK_THEME),
    ],
    ids=["light", "dark"],
)
def test_settings_navigation_icons_follow_theme_with_clear_contrast(
    qtbot,
    dark_theme: bool,
    stylesheet: str,
) -> None:
    app = QApplication.instance()
    assert app is not None
    previous_theme = app.property("maildeskDarkTheme")
    app.setProperty("maildeskDarkTheme", dark_theme)
    dialog = EnterpriseSettingsDialog()
    qtbot.addWidget(dialog)
    try:
        sidebar_background = _theme_property(
            _theme_rule(stylesheet, "QFrame#settingsSidebar"),
            "background",
        )
        selected_background = _theme_property(
            _theme_rule(
                stylesheet,
                "QListWidget#settingsNavigation::item:selected",
            ),
            "background",
        )
        icon = dialog.navigation.item(0).icon()

        def dominant_color(mode: QIcon.Mode) -> str:
            image = icon.pixmap(QSize(32, 32), mode, QIcon.State.Off).toImage()
            opaque_colors = Counter(
                image.pixelColor(x, y).name()
                for y in range(image.height())
                for x in range(image.width())
                if image.pixelColor(x, y).alpha() > 220
            )
            return opaque_colors.most_common(1)[0][0]

        icon_color = dominant_color(QIcon.Mode.Normal)
        selected_icon_color = dominant_color(QIcon.Mode.Selected)

        assert _contrast_ratio(icon_color, sidebar_background) >= 4.5
        assert _contrast_ratio(selected_icon_color, selected_background) >= 4.5
        assert selected_icon_color != icon_color
    finally:
        app.setProperty("maildeskDarkTheme", previous_theme)


@pytest.mark.parametrize("device_pixel_ratio", [1.25, 1.5, 1.75])
@pytest.mark.parametrize(
    "mode",
    [QIcon.Mode.Normal, QIcon.Mode.Selected],
    ids=["normal", "selected"],
)
def test_settings_navigation_icons_keep_native_fractional_dpi_pixmaps(
    qtbot,
    device_pixel_ratio: float,
    mode: QIcon.Mode,
) -> None:
    app = QApplication.instance()
    assert app is not None
    previous_theme = app.property("maildeskDarkTheme")
    app.setProperty("maildeskDarkTheme", False)
    dialog = EnterpriseSettingsDialog()
    qtbot.addWidget(dialog)
    try:
        logical_size = dialog.navigation.iconSize()
        assert logical_size == QSize(18, 18)
        pixmap = dialog.navigation.item(0).icon().pixmap(
            logical_size,
            device_pixel_ratio,
            mode,
            QIcon.State.Off,
        )

        assert pixmap.devicePixelRatio() == pytest.approx(device_pixel_ratio)
        assert pixmap.width() == ceil(logical_size.width() * device_pixel_ratio)
        assert pixmap.height() == ceil(
            logical_size.height() * device_pixel_ratio
        )
    finally:
        app.setProperty("maildeskDarkTheme", previous_theme)


@pytest.mark.parametrize(
    "stylesheet",
    [LIGHT_THEME, DARK_THEME],
    ids=["light", "dark"],
)
def test_specialized_buttons_have_press_and_keyboard_focus_feedback(
    stylesheet: str,
) -> None:
    required_rules = (
        "QPushButton:focus",
        "QToolButton:focus",
        "QPushButton#primaryButton:pressed",
        "QPushButton#ghostButton:pressed",
        "QPushButton#dangerButton:pressed",
        "QToolButton#primaryToolButton:pressed",
        "QToolButton#addAccountToolButton:pressed",
        "QToolButton#dashboardQuickAction:pressed",
        "QToolButton#dashboardMetricAction:pressed",
        "QToolButton#updateCloseButton:pressed",
        "QPushButton#attachmentActionButton:pressed",
        "QPushButton#closeDialogDismiss:pressed",
        "QPushButton#closeTrayOption:pressed",
        "QPushButton#closeExitOption:pressed",
    )

    for rule in required_rules:
        assert rule in stylesheet


def test_frequent_desktop_interactions_do_not_use_layout_animations() -> None:
    root = Path(__file__).parents[2] / "src" / "mailbox_manager" / "gui"
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in root.glob("*.py")
    )
    main_window_source = (root / "main_window.py").read_text(encoding="utf-8")
    motion_source = (root / "motion.py").read_text(encoding="utf-8")

    assert "QPropertyAnimation" not in source
    assert "QGraphicsDropShadowEffect" not in source
    assert "QGraphicsOpacityEffect" not in main_window_source
    assert "setMaximumHeight" not in motion_source
    assert "setMinimumHeight" not in motion_source


@pytest.mark.parametrize(
    "stylesheet",
    [LIGHT_THEME, DARK_THEME],
    ids=["light", "dark"],
)
def test_popup_styles_parse_and_provide_comfortable_rows(
    qtbot,
    stylesheet: str,
) -> None:
    app = QApplication.instance()
    assert app is not None
    previous_stylesheet = app.styleSheet()
    messages: list[str] = []

    def message_handler(_message_type, _context, message: str) -> None:
        messages.append(message)

    previous_handler = qInstallMessageHandler(message_handler)
    host = QWidget()
    combo = QComboBox(host)
    combo.addItems(["全部状态", "异常账号", "正常可用", "未连接", "连接中"])
    menu = QMenu(host)
    checked_action = menu.addAction("账号")
    checked_action.setCheckable(True)
    checked_action.setChecked(True)
    disabled_action = menu.addAction("暂不可用")
    disabled_action.setEnabled(False)
    menu.addSeparator()
    menu.addAction("导出审计报告")

    try:
        app.setStyleSheet(stylesheet)
        qtbot.addWidget(host)
        host.show()
        combo.ensurePolished()
        combo.showPopup()
        menu.ensurePolished()
        menu.popup(host.mapToGlobal(QPoint(0, host.height())))
        app.processEvents()

        assert combo.view().sizeHintForRow(0) >= 32
        assert menu.actionGeometry(checked_action).height() >= 30
    finally:
        menu.hide()
        combo.hidePopup()
        app.setStyleSheet(previous_stylesheet)
        qInstallMessageHandler(previous_handler)

    stylesheet_warnings = [
        message
        for message in messages
        if "stylesheet" in message.lower() or "unknown property" in message.lower()
    ]
    assert stylesheet_warnings == []


def test_font_scaling_updates_explicit_theme_font_sizes() -> None:
    scaled = scaled_stylesheet("QLabel { font-size: 10px; }", 14)

    assert "font-size: 14px" in scaled


def test_font_scaling_preserves_visual_hierarchy_without_oversizing_titles() -> None:
    scaled = scaled_stylesheet(
        "QLabel#title { font-size: 25px; } QLabel#caption { font-size: 11px; }",
        18,
    )

    assert "font-size: 33px" in scaled
    assert "font-size: 19px" in scaled
    assert "font-size: 45px" not in scaled


def test_font_weight_preference_reaches_all_base_controls() -> None:
    scaled = scaled_stylesheet(
        "QToolButton { font-weight: 500; } "
        "QToolButton#addAccount { font-weight: 600; } "
        "QLabel#title { font-weight: 700; }",
        10,
        600,
    )

    assert "QToolButton { font-weight: 600; }" in scaled
    assert "QToolButton#addAccount { font-weight: 600; }" in scaled
    assert "QLabel#title { font-weight: 700; }" in scaled


@pytest.mark.parametrize(
    "stylesheet",
    [LIGHT_THEME, DARK_THEME],
    ids=["light", "dark"],
)
def test_theme_uses_only_stable_qt_font_weights(stylesheet: str) -> None:
    import re

    weights = {
        int(match)
        for match in re.findall(r"font-weight\s*:\s*(\d+)", stylesheet)
    }

    assert weights <= {400, 500, 600, 700}
    assert "QToolButton {" in stylesheet
    assert "QMenu {" in stylesheet


def test_large_body_font_keeps_toolbar_and_menu_text_clear(qtbot) -> None:
    app = QApplication.instance()
    assert app is not None
    previous_font = app.font()
    previous_stylesheet = app.styleSheet()
    button = QToolButton()
    button.setText("批量导入")
    menu = QMenu()
    menu.addAction("从文件导入")
    try:
        apply_application_appearance(
            app,
            {
                "font_size": 18,
                "font_weight": 600,
                "dark_theme": False,
            },
        )
        app.setStyleSheet(scaled_stylesheet(LIGHT_THEME, 18, 600))
        qtbot.addWidget(button)
        button.ensurePolished()
        menu.ensurePolished()

        assert button.font().weight() == 600
        assert menu.font().weight() == 600
        if sys.platform == "win32":
            assert (
                app.font().hintingPreference()
                == QFont.HintingPreference.PreferFullHinting
            )
        assert button.sizeHint().width() > QFontMetrics(button.font()).horizontalAdvance(
            button.text()
        )
    finally:
        menu.deleteLater()
        app.setFont(previous_font)
        app.setStyleSheet(previous_stylesheet)


def test_dark_palette_covers_native_dialog_text_and_selection() -> None:
    palette = appearance_palette(True)

    assert palette.color(QPalette.ColorRole.Window).lightness() < 50
    assert palette.color(QPalette.ColorRole.WindowText).lightness() > 180
    assert palette.color(QPalette.ColorRole.Highlight).blue() > 180


def test_all_visual_themes_have_distinct_complete_stylesheets() -> None:
    stylesheets = {
        definition.theme_id: theme_stylesheet(definition.theme_id)
        for definition in THEME_DEFINITIONS
    }

    assert tuple(stylesheets) == (
        "midnight",
        "grass_gray",
        "twilight_yellow",
        "distant_green",
        "sky_blue",
        "cinnabar_red",
        "smoke_purple",
    )
    assert len(set(stylesheets.values())) == len(stylesheets)
    assert all("QMainWindow#mainWindow" in value for value in stylesheets.values())
