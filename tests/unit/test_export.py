from __future__ import annotations

from mailbox_manager.domain.models import (
    EmailAccount,
    MailMessage,
    ProtocolType,
    SecurityMode,
)
from mailbox_manager.services.export_service import (
    export_accounts_csv,
    export_accounts_txt,
    export_messages_csv,
)


def _account() -> EmailAccount:
    return EmailAccount(
        email="=cmd@example.com",
        provider="custom",
        protocol=ProtocolType.IMAP,
        host="imap.example.com",
        port=993,
        security=SecurityMode.SSL,
        username="=cmd@example.com",
        secret="never-export-this",
        refresh_token="or-this",
    )


def test_csv_export_excludes_secrets_and_escapes_formula_cells(tmp_path) -> None:
    target = tmp_path / "accounts.csv"

    export_accounts_csv([_account()], target)
    content = target.read_text(encoding="utf-8-sig")

    assert "never-export-this" not in content
    assert "or-this" not in content
    assert "'=cmd@example.com" in content


def test_txt_export_contains_connection_metadata_only(tmp_path) -> None:
    target = tmp_path / "accounts.txt"

    export_accounts_txt([_account()], target)
    content = target.read_text(encoding="utf-8")

    assert "imap.example.com" in content
    assert "never-export-this" not in content


def test_message_result_export_contains_matches_but_not_body(tmp_path) -> None:
    target = tmp_path / "messages.csv"
    message = MailMessage(
        provider_message_id="mail-1",
        folder="INBOX",
        subject="=dangerous subject",
        sender="security@example.com",
        catch_all_recipient="alias@example.com",
        text_body="private body must not export",
        matched_values=("123456", "verification code"),
    )

    export_messages_csv([message], target)
    content = target.read_text(encoding="utf-8-sig")

    assert "123456" in content
    assert "private body must not export" not in content
    assert "'=dangerous subject" in content
