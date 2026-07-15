from __future__ import annotations

import os
import platform
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
    def for_current_user(
        cls, *, system: str | None = None, home: Path | None = None
    ) -> AppPaths:
        system = system or platform.system()
        home = Path.home() if home is None else Path(home)
        explicit_root = os.environ.get("MAILDESK_DATA_DIR")
        if explicit_root:
            root = Path(explicit_root).expanduser()
        elif system == "Windows":
            local_app_data = os.environ.get("LOCALAPPDATA")
            base = Path(local_app_data) if local_app_data else home / "AppData" / "Local"
            root = base / "MailDesk"
        elif system == "Darwin":
            root = home / "Library" / "Application Support" / "MailDesk"
        else:
            data_home = os.environ.get("XDG_DATA_HOME")
            root = (Path(data_home) if data_home else home / ".local" / "share") / "MailDesk"
        key_name = "master.key.dpapi" if system == "Windows" else "master.key.keychain"
        return cls(
            root=root,
            database=root / "maildesk.db",
            key_file=root / key_name,
            logs=root / "logs",
            eml=root / "eml",
        )

    def ensure(self) -> None:
        for directory in (self.root, self.logs, self.eml, self.updates):
            directory.mkdir(parents=True, exist_ok=True)
