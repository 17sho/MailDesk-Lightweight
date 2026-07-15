from __future__ import annotations

from build import should_include_qt_payload


def test_qt_payload_filter_removes_webengine_debug_and_devtools_resources() -> None:
    assert (
        should_include_qt_payload(
            "PySide6/resources/qtwebengine_resources.debug.pak"
        )
        is False
    )
    assert (
        should_include_qt_payload(
            "PySide6/resources/qtwebengine_devtools_resources.pak"
        )
        is False
    )
    assert should_include_qt_payload("PySide6/resources/qtwebengine_resources.pak")
    assert should_include_qt_payload("PySide6/resources/icudtl.dat")


def test_qt_payload_filter_keeps_only_supported_webengine_locales() -> None:
    for locale in ("en-US.pak", "zh-CN.pak"):
        assert should_include_qt_payload(
            f"PySide6/translations/qtwebengine_locales/{locale}"
        )
    for locale in ("en-GB.pak", "zh-TW.pak", "fr.pak"):
        assert not should_include_qt_payload(
            f"PySide6/translations/qtwebengine_locales/{locale}"
        )
    assert should_include_qt_payload("certifi/cacert.pem")
