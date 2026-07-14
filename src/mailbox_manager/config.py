from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    root: Path
    database: Path
    key_file: Path
    logs: Path
    eml: Path

    @property
    def updates(self) -> Path:
        """Private staging area used by the verified-release updater."""

        return self.root / "updates"

    @classmethod
    def for_current_user(cls) -> AppPaths:
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        root = base / "MailDesk"
        return cls(
            root=root,
            database=root / "maildesk.db",
            key_file=root / "master.key.dpapi",
            logs=root / "logs",
            eml=root / "eml",
        )

    def ensure(self) -> None:
        for directory in (self.root, self.logs, self.eml, self.updates):
            directory.mkdir(parents=True, exist_ok=True)
