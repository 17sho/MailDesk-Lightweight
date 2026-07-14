from __future__ import annotations

import logging

from mailbox_manager.observability.logging_config import RedactingFilter, redact_text


def test_redact_text_masks_email_and_common_secret_fields() -> None:
    value = "owner@example.com password=hunter2 refresh_token=token-value client_secret=abc"

    redacted = redact_text(value)

    assert "owner@example.com" not in redacted
    assert "hunter2" not in redacted
    assert "token-value" not in redacted
    assert "client_secret=abc" not in redacted
    assert "ow***@example.com" in redacted


def test_logging_filter_redacts_message_arguments() -> None:
    record = logging.LogRecord(
        "maildesk",
        logging.INFO,
        __file__,
        1,
        "login %s password=%s",
        ("owner@example.com", "secret"),
        None,
    )

    assert RedactingFilter().filter(record) is True
    rendered = record.getMessage()
    assert "owner@example.com" not in rendered
    assert "secret" not in rendered


def test_redact_text_masks_structured_tokens_proxy_credentials_and_user_paths() -> None:
    value = (
        'access_token="ey.private.token" api_key=live-key '
        "Authorization: Bearer bearer-secret "
        "proxy=socks5://proxy-user:proxy-pass@127.0.0.1:1080 "
        r"traceback=C:\Users\Alice Smith\MailDesk\app.py "
        "cache=/home/alice/.cache/maildesk"
    )

    redacted = redact_text(value)

    for secret in (
        "ey.private.token",
        "live-key",
        "bearer-secret",
        "proxy-user",
        "proxy-pass",
        "Alice Smith",
        "/home/alice",
    ):
        assert secret not in redacted
    assert "access_token=\"<redacted>\"" in redacted
    assert "Authorization: <redacted>" in redacted
    assert "socks5://<redacted>:<redacted>@127.0.0.1:1080" in redacted
    assert r"C:\Users\<redacted>\MailDesk\app.py" in redacted
    assert "/home/<redacted>/.cache/maildesk" in redacted
