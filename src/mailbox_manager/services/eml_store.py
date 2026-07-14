from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from mailbox_manager.domain.models import MailMessage


class EmlStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, account_id: int, message: MailMessage) -> str:
        if account_id <= 0 or not message.raw_eml:
            return ""
        account_directory = self.root / str(account_id)
        account_directory.mkdir(parents=True, exist_ok=True)
        identity = f"{message.folder}\0{message.provider_message_id}".encode()
        filename = hashlib.sha256(identity).hexdigest() + ".eml"
        target = account_directory / filename
        if not target.exists():
            temporary = target.with_suffix(".eml.tmp")
            temporary.write_bytes(message.raw_eml)
            temporary.replace(target)
        return str(target)

    def export(self, message: MailMessage, target: Path) -> None:
        target = Path(target)
        if target.suffix.casefold() != ".eml":
            target = target.with_suffix(".eml")
        if message.eml_path and Path(message.eml_path).is_file():
            shutil.copy2(message.eml_path, target)
            return
        if message.raw_eml:
            target.write_bytes(message.raw_eml)
            return
        raise ValueError("该邮件没有可导出的原件")

    def delete_account(self, account_id: int) -> bool:
        if account_id <= 0:
            return False
        root = self.root.resolve()
        target = (root / str(account_id)).resolve()
        if target.parent != root or not target.is_dir():
            return False
        shutil.rmtree(target)
        return True
