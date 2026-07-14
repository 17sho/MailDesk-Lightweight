from __future__ import annotations

from build import ensure_icon, validate_mode


def test_ensure_icon_renders_windows_ico_from_svg(tmp_path) -> None:
    source = tmp_path / "app.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
        '<rect width="64" height="64" fill="#176b87"/></svg>',
        encoding="utf-8",
    )
    target = tmp_path / "app.ico"

    ensure_icon(source, target)

    assert target.read_bytes().startswith(b"\x00\x00\x01\x00")


def test_validate_mode_accepts_only_supported_pyinstaller_modes() -> None:
    assert validate_mode("onefile") == "onefile"
    assert validate_mode("onedir") == "onedir"

