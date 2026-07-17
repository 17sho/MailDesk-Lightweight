from __future__ import annotations

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mailbox_manager.domain.models import (
    AccountStatus,
    EmailAccount,
    FetchRequest,
    FetchResult,
    MailMessage,
    ProtocolType,
)
from mailbox_manager.gui.workers import (
    DeepSearchWorker,
    FetchWorker,
    UpdateCheckWorker,
    UpdateDownloadWorker,
)


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


def test_deep_search_worker_reports_matches_and_progress(qtbot) -> None:
    class SearchService:
        def search_account(self, _account, query, _request):
            assert query == "验证码"
            return FetchResult(
                AccountStatus.SUCCESS,
                messages=(
                    MailMessage("match", "INBOX", text_body="验证码 123456"),
                ),
            )

    worker = DeepSearchWorker(
        SearchService(),  # type: ignore[arg-type]
        [_graph_account()],
        "验证码",
        FetchRequest(),
        threading.Event(),
    )
    summaries: list[dict[str, object]] = []
    progress: list[tuple[int, int, str]] = []
    worker.signals.result.connect(summaries.append)
    worker.signals.progress.connect(
        lambda done, total, email: progress.append((done, total, email))
    )

    with qtbot.waitSignal(worker.signals.finished, timeout=1000):
        worker.run()

    assert summaries[0]["matches"] == 1
    assert summaries[0]["errors"] == ()
    assert progress[-1][:2] == (1, 1)


class FakeUpdateService:
    def __init__(self) -> None:
        self.update = object()
        self.downloaded = object()
        self.staged = object()

    def check_for_update(self):
        return self.update

    def download_update(self, update, *, progress, cancelled):
        assert update is self.update
        assert cancelled() is False
        progress(25, 100)
        progress(100, 100)
        return self.downloaded

    def stage_update(self, downloaded, *, cancelled):
        assert downloaded is self.downloaded
        assert cancelled() is False
        return self.staged


def test_update_check_worker_returns_available_update(qtbot) -> None:
    service = FakeUpdateService()
    worker = UpdateCheckWorker(service)  # type: ignore[arg-type]
    results: list[tuple[object, object]] = []
    worker.signals.result.connect(lambda update, error: results.append((update, error)))

    with qtbot.waitSignal(worker.signals.finished, timeout=1000):
        worker.run()

    assert results == [(service.update, None)]


def test_update_download_worker_reports_progress_and_stages(qtbot) -> None:
    service = FakeUpdateService()
    worker = UpdateDownloadWorker(  # type: ignore[arg-type]
        service,
        service.update,
        "operation-1",
    )
    progress: list[tuple[int, int | None]] = []
    statuses: list[str] = []
    results: list[tuple[object, object]] = []
    worker.signals.progress.connect(
        lambda operation, received, total: progress.append((received, total))
    )
    worker.signals.status.connect(lambda operation, status: statuses.append(status))
    worker.signals.result.connect(
        lambda operation, staged, error: results.append((staged, error))
    )

    with qtbot.waitSignal(
        worker.signals.finished,
        timeout=1000,
        check_params_cb=lambda operation: operation == "operation-1",
    ):
        worker.run()

    assert progress == [(25, 100), (100, 100)]
    assert statuses == ["正在下载并校验更新包…", "下载完成，正在安全解压…"]
    assert results == [(service.staged, None)]
