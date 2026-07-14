from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from html.parser import HTMLParser

from mailbox_manager.domain.models import MailMessage, MessageSearchHit

MAX_QUERY_LENGTH = 500
MAX_SNIPPET_LENGTH = 280
MAX_RESULTS = 2000
_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_DOMAIN_QUERY_PATTERN = re.compile(r"^(?:https?://)?(?:[\w-]+\.)+[a-z]{2,}(?:[/:?].*)?$", re.I)
_UNSAFE_REGEX_PATTERN = re.compile(r"\([^)]*[+*][^)]*\)[+*{]|\\[1-9]")


class ContentMatchMode(StrEnum):
    LITERAL = "literal"
    WILDCARD = "wildcard"
    REGEX = "regex"


@dataclass(frozen=True, slots=True)
class ContentMatch:
    account_email: str
    subject: str
    sender: str
    matched_content: str
    received_at: datetime | None = None
    message_id: int | None = None


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        href = dict(attrs).get("href") or ""
        if href.casefold().startswith(("http://", "https://")):
            self.links.append(href)


def extract_content_matches(
    hits: list[MessageSearchHit],
    query: str,
    mode: ContentMatchMode = ContentMatchMode.LITERAL,
    *,
    max_results: int = MAX_RESULTS,
) -> list[ContentMatch]:
    value = query.strip()
    if not value or len(value) > MAX_QUERY_LENGTH:
        raise ValueError("筛选内容不能为空，且长度不能超过 500 个字符")
    matcher = _compile_matcher(value, mode)
    link_query = _looks_like_link_query(value, mode)
    results: list[ContentMatch] = []
    seen: set[tuple[int | None, str]] = set()
    bounded_results = max(1, min(max_results, MAX_RESULTS))
    for hit in hits:
        message = hit.message
        matched_values = (
            _matching_links(message, matcher)
            if link_query
            else _matching_text_snippets(
                hit, matcher, exact_match=mode is ContentMatchMode.REGEX
            )
        )
        for matched in matched_values:
            key = (message.message_id, matched.casefold())
            if key in seen:
                continue
            seen.add(key)
            results.append(
                ContentMatch(
                    account_email=hit.account_email,
                    subject=message.subject,
                    sender=message.sender,
                    matched_content=matched,
                    received_at=message.received_at,
                    message_id=message.message_id,
                )
            )
            if len(results) >= bounded_results:
                return results
    return results


def _compile_matcher(query: str, mode: ContentMatchMode) -> re.Pattern[str]:
    if mode is ContentMatchMode.LITERAL:
        pattern = re.escape(query)
    elif mode is ContentMatchMode.WILDCARD:
        if not query.replace("*", "").replace("?", "").strip():
            raise ValueError("通配符不能只包含 * 或 ?")
        pattern = re.escape(query).replace(r"\*", ".*?").replace(r"\?", ".")
    elif mode is ContentMatchMode.REGEX:
        if _UNSAFE_REGEX_PATTERN.search(query):
            raise ValueError("正则表达式包含高风险结构")
        pattern = query
    else:
        raise ValueError("不支持的筛选模式")
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise ValueError("筛选表达式格式不正确") from exc


def _looks_like_link_query(query: str, mode: ContentMatchMode) -> bool:
    sample = query.replace("*", "").replace("?", "") if mode is ContentMatchMode.WILDCARD else query
    return "://" in sample or bool(_DOMAIN_QUERY_PATTERN.fullmatch(sample.strip()))


def _message_links(message: MailMessage) -> tuple[str, ...]:
    extractor = _LinkExtractor()
    if message.html_body:
        extractor.feed(message.html_body)
    text = "\n".join((message.subject, message.text_body))
    extractor.links.extend(
        match.group(0).rstrip(".,;:!?)）]}") for match in _URL_PATTERN.finditer(text)
    )
    return tuple(dict.fromkeys(extractor.links))


def _matching_links(message: MailMessage, matcher: re.Pattern[str]) -> list[str]:
    return [link[:1000] for link in _message_links(message) if matcher.search(link)]


def _matching_text_snippets(
    hit: MessageSearchHit,
    matcher: re.Pattern[str],
    *,
    exact_match: bool,
) -> list[str]:
    message = hit.message
    source_lines = [
        hit.account_email,
        message.subject,
        message.sender,
        *message.recipients,
        *message.text_body.replace("\r\n", "\n").replace("\r", "\n").split("\n"),
    ]
    snippets: list[str] = []
    for raw_line in source_lines:
        line = " ".join(raw_line.split())
        if not line:
            continue
        for match in list(matcher.finditer(line[:10_000]))[:10]:
            if match.start() == match.end():
                continue
            snippets.append(
                match.group(0)[:MAX_SNIPPET_LENGTH]
                if exact_match
                else _snippet(line, match.start(), match.end())
            )
    return snippets


def _snippet(line: str, start: int, end: int) -> str:
    context = max(30, (MAX_SNIPPET_LENGTH - max(1, end - start)) // 2)
    left = max(0, start - context)
    right = min(len(line), end + context)
    value = line[left:right]
    if left:
        value = "…" + value
    if right < len(line):
        value += "…"
    return value[:MAX_SNIPPET_LENGTH]
