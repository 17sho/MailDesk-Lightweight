from __future__ import annotations

import json

import httpx
import pytest

from mailbox_manager.services import translation_service
from mailbox_manager.services.translation_service import (
    TranslationError,
    TranslationService,
)


def test_translation_service_translates_all_bounded_chunks(monkeypatch) -> None:
    monkeypatch.setattr(translation_service, "MAX_TRANSLATION_CHUNK", 12)
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        requests.append(body)
        return httpx.Response(
            200,
            content=json.dumps([[['译文', "source", None, None]]]).encode(),
            headers={"content-type": "application/json"},
            request=request,
        )

    result = TranslationService(transport=httpx.MockTransport(handler)).translate(
        "first paragraph. second paragraph. third paragraph.",
        target_language="zh-CN",
    )

    assert result == "译文" * len(requests)
    assert len(requests) >= 2
    assert all("q=" in request for request in requests)


def test_translation_service_rejects_unknown_language_and_oversized_input(
    monkeypatch,
) -> None:
    service = TranslationService(transport=httpx.MockTransport(lambda request: None))

    with pytest.raises(TranslationError, match="不支持"):
        service.translate("hello", target_language="unknown")

    monkeypatch.setattr(translation_service, "MAX_TRANSLATION_CHARACTERS", 3)
    with pytest.raises(TranslationError, match="10 万"):
        service.translate("hello", target_language="zh-CN")


def test_translation_service_redacts_provider_error_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            text="private-mail-body@example.com",
            request=request,
        )

    with pytest.raises(TranslationError) as captured:
        TranslationService(transport=httpx.MockTransport(handler)).translate(
            "private mail body",
            target_language="zh-CN",
        )

    assert "private" not in str(captured.value)

