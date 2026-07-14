from __future__ import annotations

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mailbox_manager.domain.models import (
    AccountStatus,
    EmailAccount,
    FetchRequest,
    FetchResult,
    ProtocolType,
)
from mailbox_manager.gui.workers import FetchWorker


class FakeService:
    def fetch_account(self, _account, _request) -> FetchResult:
        return FetchResult(AccountStatus.SUCCESS, detail="ok")


def _graph_account() -> EmailAccount:
    return EmailAccount(
        account_id=7,
        email="owner@outlook.com",
        provider="outlook",
        protocol=ProtocolType.GRAPH,
        username="owner@outlook.com",
        refresh_token="refresh",
        client_id="00000000-0000-0000-0000-000000000001",
    )


def test_fetch_worker_emits_status_result_and_finished(qtbot) -> None:
    worker = FetchWorker(FakeService(), _graph_account(), FetchRequest(), threading.Event())
    statuses: list[AccountStatus] = []
    results: list[FetchResult] = []
    worker.signals.status.connect(lambda _id, status, _detail: statuses.append(status))
    worker.signals.result.connect(lambda _id, result: results.append(result))

    with qtbot.waitSignal(worker.signals.finished, timeout=1000):
        worker.run()

    assert statuses == [AccountStatus.CONNECTING, AccountStatus.SUCCESS]
    assert results[0].status is AccountStatus.SUCCESS


def test_fetch_worker_honors_stop_before_network_call(qtbot) -> None:
    stop = threading.Event()
    stop.set()
    worker = FetchWorker(FakeService(), _graph_account(), FetchRequest(), stop)
    statuses: list[AccountStatus] = []
    worker.signals.status.connect(lambda _id, status, _detail: statuses.append(status))

    with qtbot.waitSignal(worker.signals.finished, timeout=1000):
        worker.run()

    assert statuses == [AccountStatus.CANCELLED]

