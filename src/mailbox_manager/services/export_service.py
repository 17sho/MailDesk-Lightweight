from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from mailbox_manager.domain.models import EmailAccount, MailMessage

EXPORT_FIELDS = (
    "email",
    "provider",
    "protocol",
    "host",
    "port",
    "security",
    "status",
    "last_fetch_at",
)


def _safe_cell(value: object) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def _row(account: EmailAccount) -> dict[str, str]:
    return {
        "email": _safe_cell(account.email),
        "provider": _safe_cell(account.provider),
        "protocol": account.protocol.value,
        "host": _safe_cell(account.host),
        "port": str(account.port),
        "security": account.security.value,
        "status": account.status.value,
        "last_fetch_at": account.last_fetch_at.isoformat() if account.last_fetch_at else "",
    }


def export_accounts_csv(accounts: Iterable[EmailAccount], path: Path) -> None:
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=EXPORT_FIELDS)
        writer.writeheader()
        writer.writerows(_row(account) for account in accounts)


def export_accounts_txt(accounts: Iterable[EmailAccount], path: Path) -> None:
    lines = [
        "----".join(
            (
                _safe_cell(account.email),
                account.protocol.value,
                _safe_cell(account.host),
                str(account.port),
                account.status.value,
            )
        )
        for account in accounts
    ]
    Path(path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def export_messages_csv(messages: Iterable[MailMessage], path: Path) -> None:
    fields = (
        "folder",
        "subject",
        "sender",
        "recipients",
        "catch_all_recipient",
        "received_at",
        "matches",
    )
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for message in messages:
            writer.writerow(
                {
                    "folder": _safe_cell(message.folder),
                    "subject": _safe_cell(message.subject),
                    "sender": _safe_cell(message.sender),
                    "recipients": _safe_cell(";".join(message.recipients)),
                    "catch_all_recipient": _safe_cell(message.catch_all_recipient),
                    "received_at": (
                        message.received_at.isoformat() if message.received_at else ""
                    ),
                    "matches": _safe_cell(";".join(message.matched_values)),
                }
            )
