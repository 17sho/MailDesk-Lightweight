from __future__ import annotations

from mailbox_manager.domain.models import MailMessage, MessageSearchHit
from mailbox_manager.services.content_filter import (
    ContentMatchMode,
    extract_content_matches,
)


def _hit(message: MailMessage) -> MessageSearchHit:
    return MessageSearchHit("owner@example.com", message)


def test_link_filter_exports_matching_link_without_full_body() -> None:
    message = MailMessage(
        message_id=1,
        provider_message_id="link",
        folder="INBOX",
        subject="Your order",
        text_body="Unrelated private paragraph that must not be exported.",
        html_body=(
            '<p>Open order</p><a href="https://example.com/orders/ABC-123?source=mail">'
            "View</a>"
        ),
    )

    results = extract_content_matches(
        [_hit(message)],
        "https://example.com/orders/*",
        ContentMatchMode.WILDCARD,
    )

    assert [result.matched_content for result in results] == [
        "https://example.com/orders/ABC-123?source=mail"
    ]
    assert "private paragraph" not in results[0].matched_content


def test_literal_filter_returns_bounded_context_not_complete_message() -> None:
    message = MailMessage(
        message_id=2,
        provider_message_id="text",
        folder="INBOX",
        subject="Notice",
        text_body="A" * 500 + " Reset Password " + "B" * 500,
    )

    results = extract_content_matches(
        [_hit(message)], "Reset Password", ContentMatchMode.LITERAL
    )

    assert len(results) == 1
    assert "Reset Password" in results[0].matched_content
    assert len(results[0].matched_content) <= 280
    assert results[0].matched_content != message.text_body


def test_regex_filter_exports_only_the_matched_value() -> None:
    message = MailMessage(
        message_id=3,
        provider_message_id="regex",
        folder="INBOX",
        text_body="Internal order reference ORD-847291 belongs to customer Alice.",
    )

    results = extract_content_matches(
        [_hit(message)], r"ORD-\d{6}", ContentMatchMode.REGEX
    )

    assert [result.matched_content for result in results] == ["ORD-847291"]
