from __future__ import annotations

from mailbox_manager.config import AppPaths


def test_app_paths_keep_runtime_data_outside_source_tree(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    paths = AppPaths.for_current_user()

    assert paths.root == tmp_path / "MailDesk"
    assert paths.database.parent == paths.root
    assert paths.key_file.name.endswith(".dpapi")
    assert paths.logs.parent == paths.root

