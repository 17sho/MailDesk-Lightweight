from __future__ import annotations

import csv
import io
import json
import platform
import sys
import zipfile
from pathlib import Path

from mailbox_manager.observability.logging_config import redact_text
from mailbox_manager.storage.enterprise_repositories import AuditRepository


class AuditReportService:
    def __init__(self, audits: AuditRepository, log_directory: Path) -> None:
        self._audits = audits
        self._log_directory = Path(log_directory)

    def export(self, target: Path) -> None:
        target = Path(target)
        if target.suffix.casefold() != ".zip":
            target = target.with_suffix(".zip")
        audit_stream = io.StringIO(newline="")
        writer = csv.DictWriter(
            audit_stream,
            fieldnames=("occurred_at", "action", "account_id", "outcome", "detail"),
        )
        writer.writeheader()
        for event in self._audits.list_recent(5000):
            writer.writerow(
                {
                    "occurred_at": event.occurred_at.isoformat(),
                    "action": event.action,
                    "account_id": event.account_id or "",
                    "outcome": event.outcome,
                    "detail": redact_text(event.detail_redacted),
                }
            )
        diagnostics = {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "architecture": platform.machine(),
            "note": "Credentials and message bodies are intentionally excluded.",
        }
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("audit.csv", "\ufeff" + audit_stream.getvalue())
            archive.writestr(
                "diagnostics.json", json.dumps(diagnostics, ensure_ascii=False, indent=2)
            )
            log_file = self._log_directory / "app.log"
            if log_file.exists():
                content = log_file.read_text(encoding="utf-8", errors="replace")
                archive.writestr("app.log", redact_text(content))

