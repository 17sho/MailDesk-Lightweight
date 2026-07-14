from __future__ import annotations

import csv
import threading
import zipfile
from datetime import UTC, datetime, timedelta

from mailbox_manager.domain.models import Group, ScheduleConfig
from mailbox_manager.services import throttle as throttle_module
from mailbox_manager.services.audit_report import AuditReportService
from mailbox_manager.services.scheduler_service import ScheduleRunner
from mailbox_manager.services.throttle import ComplianceThrottle
from mailbox_manager.storage.database import Database
from mailbox_manager.storage.enterprise_repositories import (
    AuditRepository,
    GroupRepository,
    ScheduleRepository,
)


def test_schedule_runner_invokes_due_group_and_advances_next_run(tmp_path) -> None:
    database = Database(tmp_path / "schedule.db")
    database.initialize()
    schedules = ScheduleRepository(database)
    due_time = datetime(2026, 7, 14, 0, 0, tzinfo=UTC)
    group_id = GroupRepository(database).create(Group(name="项目A"))
    schedule_id = schedules.upsert(
        ScheduleConfig(
            group_id=group_id,
            interval_minutes=5,
            next_run_at=due_time - timedelta(seconds=1),
        )
    )
    called: list[int | None] = []
    runner = ScheduleRunner(schedules, called.append)

    count = runner.run_due(due_time)

    assert count == 1
    assert called == [group_id]
    updated = schedules.list_all()[0]
    assert updated.schedule_id == schedule_id
    assert updated.last_run_at == due_time
    assert updated.next_run_at == due_time + timedelta(minutes=5)


def test_compliance_throttle_limits_same_identity_concurrency() -> None:
    throttle = ComplianceThrottle(max_concurrency_per_identity=1)
    entered: list[str] = []
    release = threading.Event()

    def first() -> None:
        with throttle.slot("proxy-1", "account-1"):
            entered.append("first")
            release.wait(1)

    def second() -> None:
        with throttle.slot("proxy-1", "account-2"):
            entered.append("second")

    thread_one = threading.Thread(target=first)
    thread_two = threading.Thread(target=second)
    thread_one.start()
    thread_two.start()
    thread_one.join(0.05)

    assert entered == ["first"]
    release.set()
    thread_one.join(1)
    thread_two.join(1)
    assert entered == ["first", "second"]


def test_compliance_throttle_spaces_different_accounts_on_same_identity(
    monkeypatch,
) -> None:
    now = [100.0]
    sleeps: list[float] = []
    monkeypatch.setattr(throttle_module.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(throttle_module.random, "uniform", lambda _low, _high: 2.0)

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(throttle_module.time, "sleep", fake_sleep)
    throttle = ComplianceThrottle(
        max_concurrency_per_identity=2,
        min_account_interval=2,
        max_account_interval=4,
    )

    with throttle.slot("direct", "account-1"):
        pass
    with throttle.slot("direct", "account-2"):
        pass

    assert sleeps == [2.0]


def test_audit_report_contains_redacted_csv_and_diagnostics(tmp_path) -> None:
    database = Database(tmp_path / "audit.db")
    database.initialize()
    audits = AuditRepository(database)
    audits.record("fetch", "failed", "owner@example.com password=secret")
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "app.log").write_text("owner@example.com refresh_token=token", encoding="utf-8")
    target = tmp_path / "report.zip"

    AuditReportService(audits, logs).export(target)

    with zipfile.ZipFile(target) as archive:
        assert {"audit.csv", "diagnostics.json", "app.log"} <= set(archive.namelist())
        audit_text = archive.read("audit.csv").decode("utf-8-sig")
        log_text = archive.read("app.log").decode("utf-8")
    rows = list(csv.DictReader(audit_text.splitlines()))
    assert rows[0]["action"] == "fetch"
    assert "owner@example.com" not in audit_text
    assert "secret" not in audit_text
    assert "=token" not in log_text
