from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

EMAIL_RE = re.compile(r"(?P<local>[A-Z0-9._%+-]+)@(?P<domain>[A-Z0-9.-]+\.[A-Z]{2,})", re.I)
SECRET_RE = re.compile(
    r"(?i)(?P<prefix>\b(?:password|passwd|secret|client_secret|refresh_token|"
    r"access_token|id_token|api_key)\b[\"']?\s*[:=]\s*[\"']?)"
    r"(?P<value>[^\s,;\"'}]+)"
)
AUTHORIZATION_RE = re.compile(
    r"(?i)(?P<prefix>\bauthorization\b[\"']?\s*[:=]\s*[\"']?)"
    r"(?:(?:Bearer|Basic|Token)\s+)?[^\s,;\"'}]+"
)
BEARER_RE = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
URL_CREDENTIAL_RE = re.compile(
    r"(?i)(?P<scheme>https?|socks5h?)://[^/@\s:]+:[^/@\s]+@"
)
WINDOWS_USER_PATH_RE = re.compile(
    r"(?i)(?P<prefix>\b[A-Z]:[\\/]Users[\\/])[^\\/\r\n]+"
)
POSIX_USER_PATH_RE = re.compile(r"(?P<prefix>/(?:home|Users)/)[^/\s]+")


def redact_text(value: object) -> str:
    text = str(value)
    text = URL_CREDENTIAL_RE.sub(
        lambda match: f"{match.group('scheme')}://<redacted>:<redacted>@", text
    )
    text = AUTHORIZATION_RE.sub(
        lambda match: f"{match.group('prefix')}<redacted>", text
    )
    text = BEARER_RE.sub("Bearer <redacted>", text)
    text = SECRET_RE.sub(
        lambda match: f"{match.group('prefix')}<redacted>", text
    )
    text = WINDOWS_USER_PATH_RE.sub(
        lambda match: f"{match.group('prefix')}<redacted>", text
    )
    text = POSIX_USER_PATH_RE.sub(
        lambda match: f"{match.group('prefix')}<redacted>", text
    )

    def mask_email(match: re.Match[str]) -> str:
        local = match.group("local")
        return f"{local[:2]}***@{match.group('domain')}"

    return EMAIL_RE.sub(mask_email, text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage())
        record.args = ()
        return True


def configure_logging(log_directory: Path, level: int = logging.INFO) -> logging.Logger:
    log_directory = Path(log_directory)
    log_directory.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("maildesk")
    logger.setLevel(level)
    logger.propagate = False
    if logger.handlers:
        return logger
    handler = RotatingFileHandler(
        log_directory / "app.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.addFilter(RedactingFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    return logger
