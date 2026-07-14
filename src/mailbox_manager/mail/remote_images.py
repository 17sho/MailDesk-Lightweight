from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx

from mailbox_manager.mail.parser import remote_image_urls, sanitize_email_html
from mailbox_manager.mail.web_document import (
    sanitize_email_web_source,
    web_remote_image_urls,
)

MAX_REMOTE_IMAGES = 20
MAX_REMOTE_IMAGE_SIZE = 3 * 1024 * 1024
MAX_REMOTE_TOTAL_SIZE = 12 * 1024 * 1024
_ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
_REDIRECT_CODES = {301, 302, 303, 307, 308}


def _is_public_host(hostname: str) -> bool:
    lowered = hostname.casefold().rstrip(".")
    if not lowered or lowered == "localhost" or lowered.endswith(".localhost"):
        return False
    try:
        addresses = [ipaddress.ip_address(lowered)]
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(lowered, None, type=socket.SOCK_STREAM)
            }
        except (OSError, ValueError):
            return False
    return bool(addresses) and all(address.is_global for address in addresses)


def _is_safe_url(url: str) -> bool:
    if not url or len(url) > 4096 or any(ord(character) < 32 for character in url):
        return False
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError:
        return False
    return bool(
        parsed.scheme.casefold() in {"http", "https"}
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
        and (port is None or 1 <= port <= 65535)
        and _is_public_host(parsed.hostname)
    )


def _download_image(client: httpx.Client, url: str) -> tuple[str, bytes] | None:
    current = url
    for _ in range(4):
        if not _is_safe_url(current):
            return None
        try:
            with client.stream("GET", current, headers={"Accept": "image/*"}) as response:
                if response.status_code in _REDIRECT_CODES:
                    location = response.headers.get("location", "")
                    if not location:
                        return None
                    current = urljoin(current, location)
                    continue
                if response.status_code != 200:
                    return None
                content_type = response.headers.get("content-type", "").split(";", 1)[0]
                content_type = content_type.casefold().strip()
                if content_type not in _ALLOWED_CONTENT_TYPES:
                    return None
                declared_length = response.headers.get("content-length", "")
                if declared_length.isdigit() and int(declared_length) > MAX_REMOTE_IMAGE_SIZE:
                    return None
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_REMOTE_IMAGE_SIZE:
                        return None
                    chunks.append(chunk)
                payload = b"".join(chunks)
                return (content_type, payload) if payload else None
        except httpx.HTTPError:
            return None
    return None


def load_remote_images(html_body: str) -> tuple[str, int, int]:
    """Download bounded public images after an explicit user action.

    Returns rendered HTML, successfully loaded count, and total remote image count.
    """

    urls = remote_image_urls(html_body)
    images = _download_images(urls)
    rendered = sanitize_email_html(
        html_body,
        remote_images=images,
        remote_policy="embed",
    )
    return rendered, len(images), len(urls)


def _download_images(urls: tuple[str, ...]) -> dict[str, tuple[str, bytes]]:
    images: dict[str, tuple[str, bytes]] = {}
    total_size = 0
    with httpx.Client(
        timeout=httpx.Timeout(10.0, connect=5.0),
        follow_redirects=False,
        headers={"User-Agent": "MailDesk/1.0 (email image viewer)"},
    ) as client:
        for url in urls[:MAX_REMOTE_IMAGES]:
            downloaded = _download_image(client, url)
            if downloaded is None:
                continue
            if total_size + len(downloaded[1]) > MAX_REMOTE_TOTAL_SIZE:
                break
            images[url] = downloaded
            total_size += len(downloaded[1])
    return images


def load_remote_images_for_web(html_body: str) -> tuple[str, int, int]:
    """Download bounded public images and retain the email's safe visual layout."""

    urls = web_remote_image_urls(html_body)
    images = _download_images(urls)
    rendered = sanitize_email_web_source(
        html_body,
        remote_images=images,
        remote_policy="embed",
    )
    return rendered, len(images), len(urls)
