from __future__ import annotations

import csv
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from mailbox_manager.domain.models import EmailAccount, ProtocolType, SecurityMode
from mailbox_manager.gui.import_dialog import ImportPreviewDialog
from mailbox_manager.importers.file_importer import import_file
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.repositories import AccountRepository

GOOGLE_CLIENT_ID = "123456789-maildesk.apps.googleusercontent.com"
MICROSOFT_CLIENT_ID = "00000000-0000-0000-0000-000000000123"


def _write_txt(path: Path) -> None:
    path.write_text(
        "\n".join(
            (
                "app@gmail.com----abcd efgh ijkl mnop",
                f"oauth@gmail.com----gmail-refresh-token----{GOOGLE_CLIENT_ID}",
                f"admin@workspace.example----workspace-refresh-token----{GOOGLE_CLIENT_ID}",
                "imap@custom.example----imap-password----imap.custom.example----143",
                "pop@custom.example----pop-password----pop.custom.example----995",
                f"graph@outlook.com----outlook-refresh-token----{MICROSOFT_CLIENT_ID}",
            )
        ),
        encoding="utf-8",
    )


def _records() -> list[dict[str, str]]:
    return [
        {
            "email": "app@gmail.com",
            "password": "abcd efgh ijkl mnop",
        },
        {
            "email": "oauth@gmail.com",
            "refresh_token": "gmail-refresh-token",
            "client_id": GOOGLE_CLIENT_ID,
        },
        {
            "email": "admin@workspace.example",
            "refresh_token": "workspace-refresh-token",
            "client_id": GOOGLE_CLIENT_ID,
        },
        {
            "email": "imap@custom.example",
            "password": "imap-password",
            "protocol": "imap",
            "host": "imap.custom.example",
            "port": "143",
            "security": "starttls",
            "smtp_host": "smtp.custom.example",
            "smtp_port": "587",
            "smtp_security": "starttls",
        },
        {
            "email": "pop@custom.example",
            "password": "pop-password",
            "protocol": "pop3",
            "host": "pop.custom.example",
            "port": "995",
            "security": "ssl",
        },
        {
            "email": "graph@outlook.com",
            "refresh_token": "outlook-refresh-token",
            "client_id": MICROSOFT_CLIENT_ID,
            "tenant": "organizations",
        },
    ]


def _write_csv(path: Path) -> None:
    fieldnames = tuple(dict.fromkeys(key for record in _records() for key in record))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(_records())


def _write_json(path: Path) -> None:
    path.write_text(
        json.dumps({"accounts": _records()}, ensure_ascii=False),
        encoding="utf-8",
    )


def _configuration(account: EmailAccount) -> tuple[object, ...]:
    return (
        account.email,
        account.provider,
        account.protocol,
        account.host,
        account.port,
        account.security,
        account.username,
        account.secret,
        account.refresh_token,
        account.client_id,
        account.tenant,
        account.oauth_provider,
        account.smtp_host,
        account.smtp_port,
        account.smtp_security,
        account.totp_secret,
    )


@pytest.mark.parametrize(
    ("suffix", "writer"),
    ((".txt", _write_txt), (".csv", _write_csv), (".json", _write_json)),
)
def test_file_preview_to_encrypted_database_preserves_all_authentication_fields(
    qtbot,
    tmp_path: Path,
    suffix: str,
    writer: Callable[[Path], None],
) -> None:
    source = tmp_path / f"accounts{suffix}"
    writer(source)

    preview = import_file(source)
    assert preview.error_count == 0
    assert len(preview.valid_accounts) == 6

    dialog = ImportPreviewDialog(preview)
    qtbot.addWidget(dialog)
    selected = dialog.valid_accounts
    assert tuple(map(_configuration, selected)) == tuple(
        map(_configuration, preview.valid_accounts)
    )

    database = Database(tmp_path / "import-pipeline.db")
    database.initialize()
    repository = AccountRepository(database, CredentialCipher.from_raw_key(b"I" * 32))
    result = repository.add_many(selected)

    assert result.inserted == 6
    stored = {account.email: account for account in repository.list_all()}
    assert tuple(map(_configuration, stored.values())) == tuple(
        map(_configuration, selected)
    )

    gmail_password = stored["app@gmail.com"]
    assert gmail_password.secret == "abcdefghijklmnop"
    assert gmail_password.host == "imap.gmail.com"
    assert gmail_password.smtp_host == "smtp.gmail.com"

    gmail_oauth = stored["oauth@gmail.com"]
    assert gmail_oauth.secret == ""
    assert gmail_oauth.oauth_provider == "google"
    assert gmail_oauth.protocol is ProtocolType.IMAP

    workspace = stored["admin@workspace.example"]
    assert workspace.provider == "Gmail"
    assert workspace.host == "imap.gmail.com"
    assert workspace.oauth_provider == "google"

    custom_imap = stored["imap@custom.example"]
    assert custom_imap.protocol is ProtocolType.IMAP
    assert custom_imap.security is SecurityMode.STARTTLS

    custom_pop = stored["pop@custom.example"]
    assert custom_pop.protocol is ProtocolType.POP3
    assert custom_pop.security is SecurityMode.SSL

    outlook = stored["graph@outlook.com"]
    assert outlook.protocol is ProtocolType.GRAPH
    assert outlook.secret == ""
    assert outlook.refresh_token == "outlook-refresh-token"
    assert outlook.client_id == MICROSOFT_CLIENT_ID
    assert outlook.oauth_provider == "microsoft"

    with database.connect() as connection:
        raw_rows = connection.execute(
            "SELECT email, secret_ciphertext, refresh_token_ciphertext FROM accounts"
        ).fetchall()
    for row in raw_rows:
        raw_secret = str(row["secret_ciphertext"]).encode("ascii")
        raw_token = str(row["refresh_token_ciphertext"]).encode("ascii")
        account = stored[str(row["email"])]
        if account.secret:
            assert account.secret.encode() not in raw_secret
        if account.refresh_token:
            assert account.refresh_token.encode() not in raw_token


def test_chinese_csv_columns_map_to_custom_imap_and_preserve_app_password(
    qtbot, tmp_path: Path
) -> None:
    source = tmp_path / "中文字段.csv"
    source.write_text(
        "账号,密码,协议,服务器,端口,加密方式\n"
        "owner@custom.example,mail password,imap,imap.custom.example,993,ssl\n",
        encoding="utf-8-sig",
    )

    preview = import_file(source)

    assert preview.error_count == 0
    dialog = ImportPreviewDialog(preview)
    qtbot.addWidget(dialog)
    account = dialog.valid_accounts[0]
    assert account.email == "owner@custom.example"
    assert account.secret == "mail password"
    assert account.host == "imap.custom.example"
    assert account.port == 993
    assert account.security is SecurityMode.SSL
