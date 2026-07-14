from __future__ import annotations

from mailbox_manager.domain.status import AccountStatus


class MailDeskError(Exception):
    """Base application exception with a stable status code."""

    status = AccountStatus.UNKNOWN_ERROR


class ConfigurationError(MailDeskError):
    status = AccountStatus.CONFIG_ERROR


class AuthenticationError(MailDeskError):
    status = AccountStatus.AUTH_FAILED


class ConnectionTimeoutError(MailDeskError):
    status = AccountStatus.TIMEOUT


class RateLimitedError(MailDeskError):
    status = AccountStatus.RATE_LIMITED


class NetworkError(MailDeskError):
    status = AccountStatus.NETWORK_ERROR


class CancelledError(MailDeskError):
    status = AccountStatus.CANCELLED


class ImportValidationError(MailDeskError):
    status = AccountStatus.CONFIG_ERROR


class StorageError(MailDeskError):
    pass

