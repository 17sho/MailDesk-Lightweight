from __future__ import annotations

from abc import ABC, abstractmethod

from mailbox_manager.domain.models import (
    ConnectionResult,
    FetchRequest,
    FetchResult,
    MailFolder,
    MailMessage,
    PostAction,
)


class EmailClientBase(ABC):
    """Uniform contract implemented by mailbox transports."""

    @abstractmethod
    def test_connection(self) -> ConnectionResult:
        """Authenticate and report a stable connection status."""

    @abstractmethod
    def list_folders(self) -> list[MailFolder]:
        """Return folders visible to the authenticated account."""

    @abstractmethod
    def fetch_messages(self, request: FetchRequest) -> FetchResult:
        """Fetch a bounded collection of messages."""

    @abstractmethod
    def close(self) -> None:
        """Release network resources; safe to call more than once."""

    def apply_action(
        self,
        message: MailMessage,
        action: PostAction,
        target_folder: str = "",
        *,
        confirmed: bool = False,
    ) -> bool:
        """Apply an explicitly confirmed provider action when supported."""
        return False

    def __enter__(self) -> EmailClientBase:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
