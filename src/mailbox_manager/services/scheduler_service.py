from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from mailbox_manager.storage.enterprise_repositories import ScheduleRepository


class ScheduleRunner:
    """Execute persisted due schedules; GUI QTimer calls this periodically."""

    def __init__(
        self, schedules: ScheduleRepository, fetch_group: Callable[[int | None], None]
    ) -> None:
        self._schedules = schedules
        self._fetch_group = fetch_group

    def run_due(self, at_time: datetime | None = None) -> int:
        due = self._schedules.due(at_time)
        for schedule in due:
            self._fetch_group(schedule.group_id)
            self._schedules.mark_run(schedule, at_time)
        return len(due)

