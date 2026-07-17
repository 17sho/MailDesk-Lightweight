from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx
from PySide6.QtCore import (
    QObject,
    QPoint,
    QRunnable,
    Qt,
    QThreadPool,
    QUrl,
    Signal,
)
from PySide6.QtGui import QCloseEvent, QImage, QTextDocument
from PySide6.QtWidgets import QApplication, QMenu, QTextBrowser, QWidget

MAX_REMOTE_IMAGES = 48
MAX_REMOTE_IMAGE_BYTES = 8 * 1024 * 1024
_REMOTE_IMAGE_MIMES = {
    "image/gif",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}
RemoteImageLoader = Callable[[str], bytes]


class _RemoteImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "img" or len(self.urls) >= MAX_REMOTE_IMAGES:
            return
        values = {name.casefold(): (value or "") for name, value in attrs}
        source = values.get("src", "").strip()
        url = QUrl(source)
        if url.scheme().casefold() != "https" or not url.host() or url.userInfo():
            return
        if _declared_tracking_pixel(values):
            return
        if source not in self.urls:
            self.urls.append(source)


def _declared_tracking_pixel(values: dict[str, str]) -> bool:
    style = values.get("style", "")
    for name, value in re.findall(
        r"(?i)(?:^|;)\s*(width|height)\s*:\s*(\d+(?:\.\d+)?)\s*(?:px)?\b",
        style,
    ):
        values.setdefault(name.casefold(), value)

    def dimension(name: str) -> int | None:
        raw = values.get(name, "").strip().casefold().removesuffix("px").strip()
        try:
            return int(float(raw))
        except ValueError:
            return None

    width = dimension("width")
    height = dimension("height")
    return width is not None and height is not None and width <= 2 and height <= 2


def remote_image_urls(html: str) -> tuple[str, ...]:
    """Return unique public HTTPS image references declared by an email body."""

    parser = _RemoteImageParser()
    parser.feed(html)
    parser.close()
    return tuple(parser.urls)


def _is_public_https_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        return False
    if (
        parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        return False
    try:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    except OSError:
        return False
    return bool(addresses) and all(
        ipaddress.ip_address(address[4][0].split("%", 1)[0]).is_global
        for address in addresses
    )


def _download_remote_image(url: str) -> bytes:
    current = url
    timeout = httpx.Timeout(12.0, connect=6.0)
    with httpx.Client(follow_redirects=False, timeout=timeout, trust_env=False) as client:
        for _redirect in range(4):
            if not _is_public_https_url(current):
                return b""
            with client.stream(
                "GET",
                current,
                headers={
                    "Accept": "image/webp,image/png,image/jpeg,image/gif",
                    "User-Agent": "MailDesk/0.4 remote-image-reader",
                },
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location", "")
                    if not location:
                        return b""
                    current = urljoin(current, location)
                    continue
                if response.status_code != 200:
                    return b""
                mime = response.headers.get("content-type", "").split(";", 1)[0].casefold()
                if mime not in _REMOTE_IMAGE_MIMES:
                    return b""
                declared_size = response.headers.get("content-length", "")
                if declared_size.isdigit() and int(declared_size) > MAX_REMOTE_IMAGE_BYTES:
                    return b""
                chunks: list[bytes] = []
                received = 0
                for chunk in response.iter_bytes():
                    received += len(chunk)
                    if received > MAX_REMOTE_IMAGE_BYTES:
                        return b""
                    chunks.append(chunk)
                return b"".join(chunks)
    return b""


class _RemoteImageTask(QObject, QRunnable):
    loaded = Signal(object, int, str, bytes)

    def __init__(self, generation: int, url: str, loader: RemoteImageLoader) -> None:
        QObject.__init__(self)
        QRunnable.__init__(self)
        self.setAutoDelete(False)
        self.generation = generation
        self.url = url
        self.loader = loader

    def run(self) -> None:
        try:
            payload = self.loader(self.url)
        except Exception:
            payload = b""
        self.loaded.emit(self, self.generation, self.url, payload)


class _RemoteImageRegistry(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.tasks: set[_RemoteImageTask] = set()

    def start(self, task: _RemoteImageTask) -> None:
        self.tasks.add(task)
        task.loaded.connect(self._release)
        QThreadPool.globalInstance().start(task)

    def _release(
        self,
        task: _RemoteImageTask,
        _generation: int,
        _url: str,
        _payload: bytes,
    ) -> None:
        self.tasks.discard(task)


_REMOTE_IMAGE_REGISTRY = _RemoteImageRegistry()


class EmailBodyView(QTextBrowser):
    """Lightweight HTML mail reader implemented by Qt's rich-text engine.

    This deliberately avoids QtWebEngine/Chromium. It renders the extracted static
    HTML, CID/data images and common table markup, and loads bounded public HTTPS
    images in worker threads without adding a browser runtime.
    """

    feedbackRequested = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        remote_image_loader: RemoteImageLoader | None = None,
    ) -> None:
        super().__init__(parent)
        self._remote_image_loader = remote_image_loader or _download_remote_image
        self._remote_image_generation = 0
        self._remote_image_tasks: set[_RemoteImageTask] = set()
        self._remote_image_document = ""
        self._remote_image_cache: dict[str, QImage] = {}
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setAcceptRichText(True)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def setHtml(self, text: str) -> None:
        self._remote_image_generation += 1
        generation = self._remote_image_generation
        self._remote_image_tasks.clear()
        if text != self._remote_image_document:
            self._remote_image_cache.clear()
            self._remote_image_document = text
        super().setHtml(text)
        for url in remote_image_urls(text):
            cached = self._remote_image_cache.get(url)
            if cached is not None:
                self._install_image_resource(url, cached)
                continue
            task = _RemoteImageTask(generation, url, self._remote_image_loader)
            task.loaded.connect(self._remote_image_loaded)
            self._remote_image_tasks.add(task)
            _REMOTE_IMAGE_REGISTRY.start(task)

    def _remote_image_loaded(
        self,
        task: _RemoteImageTask,
        generation: int,
        url: str,
        payload: bytes,
    ) -> None:
        self._remote_image_tasks.discard(task)
        if generation == self._remote_image_generation and payload:
            self.install_remote_image(url, payload)

    def install_remote_image(self, url: str, payload: bytes) -> bool:
        """Install validated image bytes into the current rich-text document."""

        if url not in remote_image_urls(self._remote_image_document):
            return False
        image = QImage.fromData(payload)
        if image.isNull() or (image.width() <= 2 and image.height() <= 2):
            return False
        if image.width() * image.height() > 20_000_000:
            return False
        self._remote_image_cache[url] = image
        self._install_image_resource(url, image)
        return True

    def _install_image_resource(self, url: str, image: QImage) -> None:
        self.document().addResource(
            QTextDocument.ResourceType.ImageResource,
            QUrl(url),
            image,
        )
        self.document().markContentsDirty(0, self.document().characterCount())
        self.viewport().update()

    def shutdown(self) -> None:
        """Keep the former reader lifecycle API without a helper process to stop."""

        self._remote_image_generation += 1
        self._remote_image_tasks.clear()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.shutdown()
        super().closeEvent(event)

    def _show_context_menu(self, position: QPoint) -> None:
        link = QUrl(self.anchorAt(position))
        is_link = link.scheme().casefold() in {"http", "https", "mailto"}
        menu = QMenu(self)
        copy_link = menu.addAction("复制链接")
        copy_link.setEnabled(is_link)
        open_link = menu.addAction("打开链接")
        open_link.setEnabled(is_link)
        menu.addSeparator()
        copy_text = menu.addAction("复制选中文字")
        copy_text.setEnabled(self.textCursor().hasSelection())
        select_all = menu.addAction("全选正文")
        selected = menu.exec(self.mapToGlobal(position))
        if selected is copy_link:
            QApplication.clipboard().setText(link.toString())
            self.feedbackRequested.emit("链接已复制")
        elif selected is open_link:
            self.anchorClicked.emit(link)
        elif selected is copy_text:
            self.copy()
            self.feedbackRequested.emit("文字已复制")
        elif selected is select_all:
            self.selectAll()
