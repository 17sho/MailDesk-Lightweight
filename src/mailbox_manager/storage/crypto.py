from __future__ import annotations

import base64
import os
import platform
from pathlib import Path
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken

from mailbox_manager.domain.errors import StorageError


class KeyProtector(Protocol):
    def protect(self, data: bytes) -> bytes: ...

    def unprotect(self, data: bytes) -> bytes: ...


class WindowsDpapiProtector:
    """Bind the local master key to the current Windows user via DPAPI."""

    def __init__(self) -> None:
        if platform.system() != "Windows":
            raise StorageError("生产凭据存储仅支持 Windows DPAPI")
        try:
            import win32crypt
        except ImportError as exc:
            raise StorageError("缺少 pywin32，无法使用 Windows DPAPI") from exc
        self._win32crypt = win32crypt

    def protect(self, data: bytes) -> bytes:
        protected = self._win32crypt.CryptProtectData(
            data, "MailDesk master key", None, None, None, 0
        )
        if not isinstance(protected, bytes):
            raise StorageError("Windows DPAPI 返回了无效密文")
        return protected

    def unprotect(self, data: bytes) -> bytes:
        try:
            return self._win32crypt.CryptUnprotectData(data, None, None, None, 0)[1]
        except Exception as exc:
            raise StorageError("无法解密本机主密钥，请使用创建数据库的 Windows 用户运行") from exc


class CredentialCipher:
    """Encrypt sensitive database fields using a DPAPI-protected Fernet key."""

    def __init__(self, fernet: Fernet) -> None:
        self._fernet = fernet

    @classmethod
    def from_raw_key(cls, raw_key: bytes) -> CredentialCipher:
        if len(raw_key) != 32:
            raise ValueError("Fernet 原始密钥必须为 32 字节")
        return cls(Fernet(base64.urlsafe_b64encode(raw_key)))

    @classmethod
    def load_or_create(
        cls, key_path: Path, protector: KeyProtector | None = None
    ) -> CredentialCipher:
        protector = protector or WindowsDpapiProtector()
        key_path = Path(key_path)
        key_path.parent.mkdir(parents=True, exist_ok=True)
        if key_path.exists():
            protected_key = key_path.read_bytes()
            if not protected_key:
                raise StorageError("本地主密钥文件为空")
            raw_key = protector.unprotect(protected_key)
        else:
            raw_key = os.urandom(32)
            protected_key = protector.protect(raw_key)
            temporary = key_path.with_suffix(key_path.suffix + ".tmp")
            temporary.write_bytes(protected_key)
            temporary.replace(key_path)
        return cls.from_raw_key(raw_key)

    def encrypt_text(self, value: str) -> str:
        if not value:
            return ""
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt_text(self, value: str) -> str:
        if not value:
            return ""
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeError, ValueError) as exc:
            raise StorageError("凭据密文损坏或不属于当前 Windows 用户") from exc
