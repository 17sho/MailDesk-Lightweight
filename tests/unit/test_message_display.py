from __future__ import annotations

from email.message import EmailMessage

from mailbox_manager.domain.models import MailMessage
from mailbox_manager.mail.display import (
    select_message_display_content,
    select_stored_message_display_content,
)


def test_empty_sanitized_html_falls_back_to_plain_text() -> None:
    selected = select_message_display_content(
        "<html><head><style>body { display:none }</style></head>"
        "<body><script>hidden()</script><br>&nbsp;</body></html>",
        "可见的纯文本正文",
    )

    assert selected.uses_html is False
    assert selected.html_fragment == ""
    assert selected.plain_text == "可见的纯文本正文"


def test_visible_sanitized_html_remains_preferred() -> None:
    selected = select_message_display_content(
        "<p>HTML 正文 <b>482913</b></p>",
        "纯文本备用正文",
    )

    assert selected.uses_html is True
    assert "482913" in selected.html_fragment
    assert selected.plain_text == ""


def test_valid_embedded_image_counts_as_useful_html_without_text() -> None:
    selected = select_message_display_content(
        '<img src="data:image/png;base64,aGVsbG8=">',
        "不应使用的备用正文",
    )

    assert selected.uses_html is True
    assert "data:image/png;base64" in selected.html_fragment


def test_unresolved_inline_image_falls_back_to_plain_text() -> None:
    selected = select_message_display_content(
        '<img src="cid:missing-image">',
        "图片不可用时显示这段正文",
    )

    assert selected.uses_html is False
    assert selected.plain_text == "图片不可用时显示这段正文"


def test_legacy_empty_html_is_lazily_recovered_from_bounded_eml(tmp_path) -> None:
    source = EmailMessage()
    source["Subject"] = "Legacy inline image"
    source.set_content("原件中的纯文本")
    source.add_alternative('<p>原件 HTML 正文</p><img src="cid:hero">', subtype="html")
    source.get_payload()[1].add_related(
        b"small-png",
        maintype="image",
        subtype="png",
        cid="<hero>",
        disposition="inline",
    )
    eml = tmp_path / "legacy.eml"
    eml.write_bytes(source.as_bytes())
    stored = MailMessage(
        provider_message_id="legacy",
        folder="INBOX",
        html_body="      ",
        text_body="数据库中的纯文本备用正文",
        eml_path=str(eml),
    )

    selected = select_stored_message_display_content(stored)

    assert selected.uses_html is True
    assert "原件 HTML 正文" in selected.html_fragment
    assert "data:image/png;base64" in selected.html_fragment
    assert selected.source_html


def test_eml_recovery_rejects_non_eml_file_and_keeps_plain_fallback(tmp_path) -> None:
    source = tmp_path / "legacy.txt"
    source.write_text("not an eml", encoding="utf-8")
    stored = MailMessage(
        provider_message_id="legacy-invalid",
        folder="INBOX",
        html_body=" ",
        text_body="安全回退正文",
        eml_path=str(source),
    )

    selected = select_stored_message_display_content(stored)

    assert selected.uses_html is False
    assert selected.plain_text == "安全回退正文"
