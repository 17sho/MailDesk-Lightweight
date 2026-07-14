from __future__ import annotations

import json

from mailbox_manager.domain.models import ProtocolType
from mailbox_manager.importers.file_importer import import_file
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.repositories import AccountRepository


def test_txt_csv_and_json_batch_import_persist_encrypted_accounts(tmp_path) -> None:
    microsoft_client_id = "00000000-0000-0000-0000-000000000001"
    google_client_id = "123456789-example.apps.googleusercontent.com"
    txt_path = tmp_path / "accounts.txt"
    txt_path.write_text(
        "owner@qq.com----ignored-password----qq-auth-code\n"
        "owner@gmail.com----abcd efgh ijkl mnop\n"
        "custom@example.org----custom-secret----imap.example.org----993\n"
        "pop@example.org----pop-secret----pop.example.org----995\n"
        f"owner@outlook.com----microsoft-refresh-token----{microsoft_client_id}\n",
        encoding="utf-8",
    )
    csv_path = tmp_path / "accounts.csv"
    csv_path.write_text(
        "邮箱地址;RefreshToken;ClientID;OAuth提供商\n"
        f"owner@workspace.example;google-refresh-token;{google_client_id};google\n",
        encoding="utf-8-sig",
    )
    json_path = tmp_path / "accounts.json"
    json_path.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "email": "owner@163.com",
                        "password": "163-auth-code",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    previews = [import_file(path) for path in (txt_path, csv_path, json_path)]
    assert all(preview.error_count == 0 for preview in previews)
    imported = [account for preview in previews for account in preview.valid_accounts]

    database = Database(tmp_path / "maildesk.db")
    database.initialize()
    repository = AccountRepository(database, CredentialCipher.from_raw_key(b"I" * 32))
    result = repository.add_many(imported)
    loaded = {account.email: account for account in repository.list_all()}

    assert result.inserted == 7
    assert loaded["owner@gmail.com"].secret == "abcdefghijklmnop"
    assert loaded["owner@outlook.com"].protocol is ProtocolType.GRAPH
    assert loaded["owner@workspace.example"].oauth_provider == "google"
    assert loaded["pop@example.org"].protocol is ProtocolType.POP3
    raw_database = database.path.read_bytes()
    for sensitive_value in (
        b"qq-auth-code",
        b"abcdefghijklmnop",
        b"custom-secret",
        b"pop-secret",
        b"microsoft-refresh-token",
        b"google-refresh-token",
        b"163-auth-code",
    ):
        assert sensitive_value not in raw_database

    duplicate = repository.add_many(imported)
    assert duplicate.duplicates == 7
