from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from mailbox_manager.domain.models import (
    AccountStatus,
    EmailAccount,
    FetchRequest,
    ProtocolType,
    SecurityMode,
)
from mailbox_manager.protocols.base import EmailClientBase


def test_fetch_request_supports_unlimited_and_rejects_negative_count() -> None:
    assert FetchRequest().unlimited is True
    assert FetchRequest(max_messages=0).unlimited is True
    assert FetchRequest(max_messages=201).unlimited is False

    with pytest.raises(ValueError, match="不能为负数"):
        FetchRequest(max_messages=-1)


def test_account_secret_is_not_exposed_in_repr() -> None:
    account = EmailAccount(
        email="owner@example.com",
        provider="custom",
        protocol=ProtocolType.IMAP,
        host="imap.example.com",
        port=993,
        security=SecurityMode.SSL,
        username="owner@example.com",
        secret="super-secret",
        status=AccountStatus.DISCONNECTED,
    )

    assert "super-secret" not in repr(account)
    with pytest.raises(FrozenInstanceError):
        account.port = 143  # type: ignore[misc]


def test_email_client_base_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        EmailClientBase()  # type: ignore[abstract]
