from __future__ import annotations

import re
from collections.abc import Iterable

import httpx

GOOGLE_TRANSLATE_ENDPOINT = "https://translate.googleapis.com/translate_a/single"
MAX_TRANSLATION_CHARACTERS = 100_000
MAX_TRANSLATION_CHUNK = 3_500
DEFAULT_TRANSLATION_LANGUAGE = "zh-CN"
TRANSLATION_LANGUAGES: tuple[tuple[str, str], ...] = (
    ("zh-CN", "简体中文"),
    ("zh-TW", "繁體中文"),
    ("en", "英语"),
    ("ja", "日语"),
    ("ko", "韩语"),
    ("es", "西班牙语"),
    ("fr", "法语"),
    ("de", "德语"),
    ("ru", "俄语"),
    ("pt", "葡萄牙语"),
    ("it", "意大利语"),
    ("ar", "阿拉伯语"),
    ("tr", "土耳其语"),
    ("th", "泰语"),
    ("vi", "越南语"),
    ("id", "印度尼西亚语"),
)
_LANGUAGE_CODES = frozenset(code for code, _label in TRANSLATION_LANGUAGES)
_BREAK_PATTERN = re.compile(r"(?:\n\n|\n|[。！？.!?]\s|\s)")


class TranslationError(RuntimeError):
    """A user-displayable translation failure with no provider response leakage."""


def translation_language_label(code: str) -> str:
    return next(
        (label for language, label in TRANSLATION_LANGUAGES if language == code),
        code,
    )


class TranslationService:
    """Explicit, bounded translation through Google's public translation endpoint."""

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        endpoint: str = GOOGLE_TRANSLATE_ENDPOINT,
    ) -> None:
        self._transport = transport
        self._endpoint = endpoint

    def translate(
        self,
        text: str,
        *,
        target_language: str,
        source_language: str = "auto",
    ) -> str:
        target = target_language.strip()
        if target not in _LANGUAGE_CODES:
            raise TranslationError("不支持所选的翻译语言")
        source = source_language.strip() or "auto"
        if source != "auto" and source not in _LANGUAGE_CODES:
            raise TranslationError("不支持指定的原文语言")
        normalized = text.replace("\x00", "").strip()
        if not normalized:
            raise TranslationError("当前邮件没有可翻译的正文")
        if len(normalized) > MAX_TRANSLATION_CHARACTERS:
            raise TranslationError("邮件正文超过 10 万字符，请先筛选需要翻译的内容")

        try:
            with httpx.Client(
                transport=self._transport,
                timeout=httpx.Timeout(20.0, connect=8.0),
                follow_redirects=False,
                headers={"User-Agent": "MailDesk/1.0 translation"},
            ) as client:
                translated = [
                    self._translate_chunk(client, chunk, source, target)
                    for chunk in _translation_chunks(normalized)
                ]
        except TranslationError:
            raise
        except httpx.TimeoutException as exc:
            raise TranslationError("翻译服务连接超时，请稍后重试") from exc
        except httpx.HTTPError as exc:
            raise TranslationError("无法连接翻译服务，请检查网络或代理设置") from exc
        return "".join(translated).strip()

    def _translate_chunk(
        self,
        client: httpx.Client,
        chunk: str,
        source: str,
        target: str,
    ) -> str:
        response = client.post(
            self._endpoint,
            params={"client": "gtx", "sl": source, "tl": target, "dt": "t"},
            data={"q": chunk},
        )
        if response.status_code == 429:
            raise TranslationError("翻译请求过于频繁，请稍后重试")
        if response.status_code < 200 or response.status_code >= 300:
            raise TranslationError("翻译服务暂时不可用，请稍后重试")
        try:
            payload = response.json()
            segments = payload[0]
            result = "".join(
                str(segment[0])
                for segment in segments
                if isinstance(segment, list) and segment and segment[0] is not None
            )
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise TranslationError("翻译服务返回了无法识别的结果") from exc
        if not result:
            raise TranslationError("翻译服务没有返回有效内容")
        return result


def _translation_chunks(text: str) -> Iterable[str]:
    start = 0
    while start < len(text):
        hard_end = min(len(text), start + MAX_TRANSLATION_CHUNK)
        end = hard_end
        if hard_end < len(text):
            window = text[start:hard_end]
            candidates = list(_BREAK_PATTERN.finditer(window))
            if candidates:
                preferred = candidates[-1].end()
                if preferred >= MAX_TRANSLATION_CHUNK // 2:
                    end = start + preferred
        yield text[start:end]
        start = end

