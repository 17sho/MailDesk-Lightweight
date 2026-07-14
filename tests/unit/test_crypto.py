from __future__ import annotations

import platform

import pytest

from mailbox_manager.storage.crypto import CredentialCipher, WindowsDpapiProtector


class PrefixProtector:
    def protect(self, data: bytes) -> bytes:
        return b"protected:" + data[::-1]

    def unprotect(self, data: bytes) -> bytes:
        assert data.startswith(b"protected:")
        return data.removeprefix(b"protected:")[::-1]


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


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows DPAPI only")
def test_windows_dpapi_protector_returns_bytes_and_round_trips() -> None:
    protector = WindowsDpapiProtector()

    protected = protector.protect(b"test-master-key")

    assert isinstance(protected, bytes)
    assert protected != b"test-master-key"
    assert protector.unprotect(protected) == b"test-master-key"
