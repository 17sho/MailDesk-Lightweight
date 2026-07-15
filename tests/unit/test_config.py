from __future__ import annotations

import os

import pytest

from mailbox_manager.app import report_update_health
from mailbox_manager.config import AppPaths


def test_app_paths_keep_runtime_data_outside_source_tree(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    paths = AppPaths.for_current_user(system="Windows", home=tmp_path)

    assert paths.root == tmp_path / "MailDesk"
    assert paths.database.parent == paths.root
    assert paths.key_file.name.endswith(".dpapi")
    assert paths.logs.parent == paths.root
    assert paths.updates == paths.root / "updates"


def test_macos_paths_use_application_support_and_keychain_marker(tmp_path) -> None:
    paths = AppPaths.for_current_user(system="Darwin", home=tmp_path)

    assert paths.root == tmp_path / "Library" / "Application Support" / "MailDesk"
    assert paths.key_file.name == "master.key.keychain"


def test_update_health_marker_is_restricted_to_update_staging(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    paths = AppPaths.for_current_user()
    paths.ensure()
    token = "a" * 32
    marker = paths.updates / (".health-" + "b" * 32)
    monkeypatch.setenv("MAILDESK_UPDATE_HEALTH_TOKEN", token)
    monkeypatch.setenv("MAILDESK_UPDATE_HEALTH_FILE", str(marker))

    assert report_update_health(paths) is True
    assert marker.read_text(encoding="utf-8") == token
    assert "MAILDESK_UPDATE_HEALTH_TOKEN" not in os.environ

    outside = tmp_path / "outside-health"
    monkeypatch.setenv("MAILDESK_UPDATE_HEALTH_TOKEN", token)
    monkeypatch.setenv("MAILDESK_UPDATE_HEALTH_FILE", str(outside))
    with pytest.raises(ValueError, match="路径无效"):
        report_update_health(paths)
    assert not outside.exists()
