from __future__ import annotations

import os
import platform

import pytest

from mailbox_manager.domain.errors import StorageError
from mailbox_manager.storage.crypto import (
    CredentialCipher,
    MacOSKeychainProtector,
    WindowsDpapiProtector,
)


class PrefixProtector:
    def protect(self, data: bytes) -> bytes:
        return b"protected:" + data[::-1]

    def unprotect(self, data: bytes) -> bytes:
        assert data.startswith(b"protected:")
        return data.removeprefix(b"protected:")[::-1]


class MemoryPasswordStore:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))


def test_cipher_persists_only_protected_key_and_round_trips_secret(tmp_path) -> None:
    key_file = tmp_path / "master.key.dpapi"
    cipher = CredentialCipher.load_or_create(key_file, PrefixProtector())

    ciphertext = cipher.encrypt_text("mail-password")

    assert ciphertext != "mail-password"
    assert b"mail-password" not in key_file.read_bytes()
    assert key_file.read_bytes().startswith(b"protected:")
    reloaded = CredentialCipher.load_or_create(key_file, PrefixProtector())
    assert reloaded.decrypt_text(ciphertext) == "mail-password"


def test_empty_secret_stays_empty() -> None:
    cipher = CredentialCipher.from_raw_key(b"A" * 32)

    assert cipher.encrypt_text("") == ""
    assert cipher.decrypt_text("") == ""


def test_macos_keychain_protector_persists_only_a_marker(tmp_path) -> None:
    store = MemoryPasswordStore()
    key_file = tmp_path / "master.key.keychain"
    protector = MacOSKeychainProtector(key_file, store)

    cipher = CredentialCipher.load_or_create(key_file, protector)

    assert key_file.read_bytes() == protector.marker
    if os.name != "nt":
        assert key_file.stat().st_mode & 0o777 == 0o600
    assert len(store.values) == 1
    reloaded = CredentialCipher.load_or_create(
        key_file, MacOSKeychainProtector(key_file, store)
    )
    encrypted = cipher.encrypt_text("mac-secret")
    assert reloaded.decrypt_text(encrypted) == "mac-secret"


def test_macos_keychain_protector_rejects_a_foreign_marker(tmp_path) -> None:
    store = MemoryPasswordStore()
    protector = MacOSKeychainProtector(tmp_path / "master.key.keychain", store)

    with pytest.raises(StorageError, match="标记无效"):
        protector.unprotect(b"maildesk-keychain-v1:foreign")


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows DPAPI only")
def test_windows_dpapi_protector_returns_bytes_and_round_trips() -> None:
    protector = WindowsDpapiProtector()

    protected = protector.protect(b"test-master-key")

    assert isinstance(protected, bytes)
    assert protected != b"test-master-key"
    assert protector.unprotect(protected) == b"test-master-key"
