from __future__ import annotations

from pathlib import Path

from mailbox_manager.domain.models import (
    AccountStatus,
    EmailAccount,
    FetchRequest,
    FetchResult,
    MailMessage,
    ProtocolType,
    SecurityMode,
)
from mailbox_manager.services.eml_store import EmlStore
from mailbox_manager.services.fetch_service import FetchService
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.enterprise_repositories import AuditRepository
from mailbox_manager.storage.repositories import AccountRepository, MessageRepository


class RawClient:
    def fetch_messages(self, _request: FetchRequest) -> FetchResult:
        return FetchResult(
            AccountStatus.SUCCESS,
            (
                MailMessage(
                    provider_message_id="<unsafe/id@example.com>",
                    folder="INBOX",
                    subject="验证码",
                    raw_eml=b"Subject: code\r\n\r\n123456",
                ),
            ),
        )

    def close(self) -> None:
        return None


def test_fetch_service_saves_raw_eml_and_records_redacted_audit(tmp_path) -> None:
    database = Database(tmp_path / "maildesk.db")
    database.initialize()
    accounts = AccountRepository(database, CredentialCipher.from_raw_key(b"I" * 32))
    accounts.add_many(
        [
            EmailAccount(
                email="owner@example.com",
                provider="custom",
                protocol=ProtocolType.IMAP,
                host="imap.example.com",
                port=993,
                security=SecurityMode.SSL,
                username="owner@example.com",
                secret="secret",
            )
        ]
    )
    account = accounts.list_all()[0]
    messages = MessageRepository(database)
    audits = AuditRepository(database)
    service = FetchService(
        accounts,
        messages,
        client_factory=lambda _account: RawClient(),
        eml_store=EmlStore(tmp_path / "eml"),
        audit_repository=audits,
    )

    result = service.fetch_account(account, FetchRequest())

    eml_path = result.messages[0].eml_path
    assert eml_path.endswith(".eml")
    assert (tmp_path / "eml" / str(account.account_id)) in Path(eml_path).parents
    assert Path(eml_path).read_bytes().endswith(b"123456")
    persisted = messages.list_for_account(account.account_id)[0]  # type: ignore[arg-type]
    assert persisted.eml_path == eml_path
    audit = audits.list_recent()[0]
    assert audit.action == "fetch"
    assert "owner@example.com" not in audit.detail_redacted


def test_eml_store_deletes_only_the_requested_account_directory(tmp_path) -> None:
    store = EmlStore(tmp_path / "eml")
    first = store.root / "1"
    second = store.root / "2"
    first.mkdir()
    second.mkdir()
    (first / "mail.eml").write_bytes(b"one")
    (second / "mail.eml").write_bytes(b"two")

    assert store.delete_account(1) is True
    assert first.exists() is False
    assert (second / "mail.eml").read_bytes() == b"two"
