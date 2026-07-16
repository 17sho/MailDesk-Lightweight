from __future__ import annotations

from mailbox_manager.app import migrate_header_sync_settings
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.enterprise_repositories import SettingsRepository


def test_header_sync_migration_sets_existing_installation_to_unlimited_once(
    tmp_path,
) -> None:
    database = Database(tmp_path / "settings.db")
    database.initialize()
    settings = SettingsRepository(database)
    settings.set("fetch", {"folders": ["INBOX"], "max_messages": 20})

    assert migrate_header_sync_settings(settings) is True
    assert settings.get("fetch") == {"folders": ["INBOX"], "max_messages": 0}

    settings.set("fetch", {"folders": ["INBOX"], "max_messages": 50})
    assert migrate_header_sync_settings(settings) is False
    assert settings.get("fetch") == {"folders": ["INBOX"], "max_messages": 50}
