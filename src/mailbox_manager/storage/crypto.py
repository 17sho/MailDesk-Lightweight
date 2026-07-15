from __future__ import annotations

import base64
import hashlib
import os
import platform
from pathlib import Path
from typing import Protocol, cast

from cryptography.fernet import Fernet, InvalidToken

from mailbox_manager.domain.errors import StorageError


class KeyProtector(Protocol):
    def protect(self, data: bytes) -> bytes: ...

    def unprotect(self, data: bytes) -> bytes: ...


class PasswordStore(Protocol):
    def set_password(self, service: str, username: str, password: str) -> None: ...

    def get_password(self, service: str, username: str) -> str | None: ...


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


class MacOSKeychainProtector:
    """Store the random master key in the current macOS user's Keychain."""

    SERVICE_NAME = "com.maildesk.credentials.master-key"
    MARKER_PREFIX = b"maildesk-keychain-v1:"

    def __init__(self, key_path: Path, backend: PasswordStore | None = None) -> None:
        if backend is None:
            if platform.system() != "Darwin":
                raise StorageError("macOS 钥匙串保护仅能在 macOS 上使用")
            try:
                from keyring.backends.macOS import Keyring
            except ImportError as exc:
                raise StorageError("缺少 keyring，无法使用 macOS 钥匙串") from exc
            backend = cast(PasswordStore, Keyring())
        normalized = str(Path(key_path).expanduser().resolve()).encode("utf-8")
        self._account = hashlib.sha256(normalized).hexdigest()
        self._backend = backend

    @property
    def marker(self) -> bytes:
        return self.MARKER_PREFIX + self._account.encode("ascii")

    def protect(self, data: bytes) -> bytes:
        encoded = base64.urlsafe_b64encode(data).decode("ascii")
        try:
            self._backend.set_password(self.SERVICE_NAME, self._account, encoded)
        except Exception as exc:
            raise StorageError("无法将主密钥保存到 macOS 钥匙串") from exc
        return self.marker

    def unprotect(self, data: bytes) -> bytes:
        if data != self.marker:
            raise StorageError("macOS 钥匙串主密钥标记无效")
        try:
            encoded = self._backend.get_password(self.SERVICE_NAME, self._account)
            if not encoded:
                raise StorageError("macOS 钥匙串中缺少 MailDesk 主密钥")
            return base64.b64decode(encoded, altchars=b"-_", validate=True)
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError("无法从 macOS 钥匙串读取主密钥") from exc


def default_key_protector(key_path: Path) -> KeyProtector:
    system = platform.system()
    if system == "Windows":
        return WindowsDpapiProtector()
    if system == "Darwin":
        return MacOSKeychainProtector(key_path)
    raise StorageError("生产凭据存储仅支持 Windows DPAPI 或 macOS 钥匙串")


class CredentialCipher:
    """Encrypt sensitive database fields using a system-protected Fernet key."""

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
        key_path = Path(key_path)
        protector = protector or default_key_protector(key_path)
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
            if os.name != "nt":
                temporary.chmod(0o600)
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
            raise StorageError("凭据密文损坏或不属于当前系统用户") from exc
