from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from mailbox_manager.domain.models import (
    AuditEvent,
    AutomationRule,
    DashboardOverview,
    DashboardStats,
    Group,
    PostAction,
    ProxyConfig,
    ProxyType,
    ScheduleConfig,
    Tag,
    WebhookConfig,
)
from mailbox_manager.domain.status import AccountStatus
from mailbox_manager.observability.logging_config import redact_text
from mailbox_manager.storage.crypto import CredentialCipher
from mailbox_manager.storage.database import Database


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class GroupRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def create(self, group: Group) -> int:
        name = group.name.strip()
        if not name or len(name) > 100:
            raise ValueError("分组名称必须为 1 到 100 个字符")
        with self._database.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO groups(parent_id, name, created_at) VALUES (?, ?, ?)",
                (group.parent_id, name, _now().isoformat()),
            )
            return int(cursor.lastrowid)

    def list_all(self) -> list[Group]:
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT id, parent_id, name FROM groups ORDER BY id"
            ).fetchall()
        return [
            Group(group_id=row["id"], parent_id=row["parent_id"], name=row["name"])
            for row in rows
        ]

    def descendant_ids(self, group_id: int) -> list[int]:
        groups = self.list_all()
        children: dict[int | None, list[int]] = {}
        for group in groups:
            if group.group_id is not None:
                children.setdefault(group.parent_id, []).append(group.group_id)
        result: list[int] = []
        pending = list(children.get(group_id, []))
        while pending:
            current = pending.pop(0)
            result.append(current)
            pending.extend(children.get(current, []))
        return result

    def rename(self, group_id: int, name: str) -> None:
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 100:
            raise ValueError("分组名称必须为 1 到 100 个字符")
        with self._database.connect() as connection:
            connection.execute("UPDATE groups SET name = ? WHERE id = ?", (clean_name, group_id))

    def delete(self, group_id: int) -> None:
        with self._database.connect() as connection:
            connection.execute("DELETE FROM groups WHERE id = ?", (group_id,))


class TagRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def create(self, tag: Tag) -> int:
        name = tag.name.strip()
        if not name or len(name) > 50:
            raise ValueError("标签名称必须为 1 到 50 个字符")
        with self._database.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO tags(name, color) VALUES (?, ?)", (name, tag.color)
            )
            return int(cursor.lastrowid)

    def list_all(self) -> list[Tag]:
        with self._database.connect() as connection:
            rows = connection.execute("SELECT id, name, color FROM tags ORDER BY name").fetchall()
        return [Tag(tag_id=row["id"], name=row["name"], color=row["color"]) for row in rows]

    def update(self, tag_id: int, name: str, color: str) -> None:
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 50:
            raise ValueError("标签名称必须为 1 到 50 个字符")
        with self._database.connect() as connection:
            connection.execute(
                "UPDATE tags SET name = ?, color = ? WHERE id = ?",
                (clean_name, color, tag_id),
            )

    def delete(self, tag_id: int) -> None:
        with self._database.connect() as connection:
            connection.execute("DELETE FROM tags WHERE id = ?", (tag_id,))

    def assign(self, account_id: int, tag_id: int) -> None:
        with self._database.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO account_tags(account_id, tag_id) VALUES (?, ?)",
                (account_id, tag_id),
            )

    def unassign(self, account_id: int, tag_id: int) -> None:
        with self._database.connect() as connection:
            connection.execute(
                "DELETE FROM account_tags WHERE account_id = ? AND tag_id = ?",
                (account_id, tag_id),
            )

    def for_account(self, account_id: int) -> list[Tag]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT t.id, t.name, t.color
                FROM tags t JOIN account_tags at ON at.tag_id = t.id
                WHERE at.account_id = ? ORDER BY t.name
                """,
                (account_id,),
            ).fetchall()
        return [Tag(tag_id=row["id"], name=row["name"], color=row["color"]) for row in rows]


class ProxyRepository:
    def __init__(self, database: Database, cipher: CredentialCipher) -> None:
        self._database = database
        self._cipher = cipher

    def add(self, proxy: ProxyConfig) -> int:
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO proxies(
                    proxy_type, host, port, username, password_ciphertext, enabled, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proxy.proxy_type.value,
                    proxy.host.casefold(),
                    proxy.port,
                    proxy.username,
                    self._cipher.encrypt_text(proxy.password),
                    int(proxy.enabled),
                    _now().isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def get(self, proxy_id: int) -> ProxyConfig | None:
        with self._database.connect() as connection:
            row = connection.execute("SELECT * FROM proxies WHERE id = ?", (proxy_id,)).fetchone()
        return self._from_row(row) if row else None

    def list_all(self) -> list[ProxyConfig]:
        with self._database.connect() as connection:
            rows = connection.execute("SELECT * FROM proxies ORDER BY id").fetchall()
        return [self._from_row(row) for row in rows]

    def _from_row(self, row: object) -> ProxyConfig:
        return ProxyConfig(
            proxy_id=row["id"],  # type: ignore[index]
            proxy_type=ProxyType(row["proxy_type"]),  # type: ignore[index]
            host=row["host"],  # type: ignore[index]
            port=row["port"],  # type: ignore[index]
            username=row["username"],  # type: ignore[index]
            password=self._cipher.decrypt_text(row["password_ciphertext"]),  # type: ignore[index]
            enabled=bool(row["enabled"]),  # type: ignore[index]
        )


class WebhookRepository:
    def __init__(self, database: Database, cipher: CredentialCipher) -> None:
        self._database = database
        self._cipher = cipher

    def add(self, webhook: WebhookConfig) -> int:
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO webhooks(name, url, secret_ciphertext, enabled, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    webhook.name.strip(),
                    webhook.url.strip(),
                    self._cipher.encrypt_text(webhook.secret),
                    int(webhook.enabled),
                    _now().isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def get(self, webhook_id: int) -> WebhookConfig | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM webhooks WHERE id = ?", (webhook_id,)
            ).fetchone()
        if not row:
            return None
        return WebhookConfig(
            webhook_id=row["id"],
            name=row["name"],
            url=row["url"],
            secret=self._cipher.decrypt_text(row["secret_ciphertext"]),
            enabled=bool(row["enabled"]),
        )

    def list_all(self) -> list[WebhookConfig]:
        with self._database.connect() as connection:
            ids = [row["id"] for row in connection.execute("SELECT id FROM webhooks ORDER BY id")]
        return [item for webhook_id in ids if (item := self.get(webhook_id)) is not None]


class ScheduleRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def upsert(self, schedule: ScheduleConfig) -> int:
        now = _now()
        next_run = schedule.next_run_at or now + timedelta(minutes=schedule.interval_minutes)
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT id FROM schedules WHERE group_id IS ?", (schedule.group_id,)
            ).fetchone()
            if row:
                connection.execute(
                    """
                    UPDATE schedules SET interval_minutes = ?, enabled = ?, next_run_at = ?
                    WHERE id = ?
                    """,
                    (
                        schedule.interval_minutes,
                        int(schedule.enabled),
                        next_run.isoformat(),
                        row["id"],
                    ),
                )
                return int(row["id"])
            cursor = connection.execute(
                """
                INSERT INTO schedules(
                    group_id, interval_minutes, enabled, last_run_at, next_run_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    schedule.group_id,
                    schedule.interval_minutes,
                    int(schedule.enabled),
                    schedule.last_run_at.isoformat() if schedule.last_run_at else None,
                    next_run.isoformat(),
                    now.isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def list_all(self) -> list[ScheduleConfig]:
        with self._database.connect() as connection:
            rows = connection.execute("SELECT * FROM schedules ORDER BY id").fetchall()
        return [
            ScheduleConfig(
                schedule_id=row["id"],
                group_id=row["group_id"],
                interval_minutes=row["interval_minutes"],
                enabled=bool(row["enabled"]),
                last_run_at=_parse_time(row["last_run_at"]),
                next_run_at=_parse_time(row["next_run_at"]),
            )
            for row in rows
        ]

    def due(self, at_time: datetime | None = None) -> list[ScheduleConfig]:
        timestamp = (at_time or _now()).isoformat()
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT id FROM schedules WHERE enabled = 1 AND next_run_at <= ?", (timestamp,)
            ).fetchall()
        schedules = {item.schedule_id: item for item in self.list_all()}
        return [schedules[row["id"]] for row in rows]

    def mark_run(self, schedule: ScheduleConfig, at_time: datetime | None = None) -> None:
        if schedule.schedule_id is None:
            raise ValueError("调度任务尚未保存")
        now = at_time or _now()
        next_run = now + timedelta(minutes=schedule.interval_minutes)
        with self._database.connect() as connection:
            connection.execute(
                "UPDATE schedules SET last_run_at = ?, next_run_at = ? WHERE id = ?",
                (now.isoformat(), next_run.isoformat(), schedule.schedule_id),
            )


class AutomationRuleRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def add(self, rule: AutomationRule) -> int:
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO automation_rules(
                    name, pattern, action, target_folder, webhook_id, forward_to,
                    enabled, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule.name.strip(),
                    rule.pattern,
                    rule.action.value,
                    rule.target_folder,
                    rule.webhook_id,
                    rule.forward_to.casefold(),
                    int(rule.enabled),
                    _now().isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def list_all(self, enabled_only: bool = False) -> list[AutomationRule]:
        query = "SELECT * FROM automation_rules"
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY id"
        with self._database.connect() as connection:
            rows = connection.execute(query).fetchall()
        return [
            AutomationRule(
                rule_id=row["id"],
                name=row["name"],
                pattern=row["pattern"],
                action=PostAction(row["action"]),
                target_folder=row["target_folder"],
                webhook_id=row["webhook_id"],
                forward_to=row["forward_to"],
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]


class SettingsRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def set(self, key: str, value: object) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO settings(key, value_json) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json
                """,
                (key, payload),
            )

    def get(self, key: str, default: object = None) -> object:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT value_json FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return json.loads(row["value_json"]) if row else default


class AuditRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def record(
        self, action: str, outcome: str, detail: str = "", account_id: int | None = None
    ) -> int:
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO audit_events(occurred_at, action, account_id, outcome, detail_redacted)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    _now().isoformat(),
                    action[:100],
                    account_id,
                    outcome[:50],
                    redact_text(detail)[:2000],
                ),
            )
            return int(cursor.lastrowid)

    def list_recent(self, limit: int = 1000) -> list[AuditEvent]:
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (max(1, min(limit, 5000)),)
            ).fetchall()
        return [
            AuditEvent(
                event_id=row["id"],
                occurred_at=datetime.fromisoformat(row["occurred_at"]),
                action=row["action"],
                account_id=row["account_id"],
                outcome=row["outcome"],
                detail_redacted=row["detail_redacted"],
            )
            for row in rows
        ]


class StatisticsRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def dashboard(self) -> DashboardStats:
        with self._database.connect() as connection:
            status_rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM accounts GROUP BY status"
            ).fetchall()
            message_rows = connection.execute(
                """
                SELECT substr(created_at, 1, 13) AS hour, COUNT(*) AS count
                FROM messages GROUP BY hour ORDER BY hour DESC LIMIT 24
                """
            ).fetchall()
        status_counts = {AccountStatus(row["status"]): row["count"] for row in status_rows}
        points = tuple(
            (datetime.fromisoformat(row["hour"] + ":00:00+00:00"), row["count"])
            for row in reversed(message_rows)
            if row["hour"]
        )
        return DashboardStats(status_counts=status_counts, messages_per_hour=points)

    def overview(self) -> DashboardOverview:
        with self._database.connect() as connection:
            account_row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS healthy,
                    SUM(CASE WHEN status NOT IN (?, ?, ?) THEN 1 ELSE 0 END) AS abnormal
                FROM accounts
                """,
                (
                    AccountStatus.SUCCESS.value,
                    AccountStatus.SUCCESS.value,
                    AccountStatus.DISCONNECTED.value,
                    AccountStatus.CONNECTING.value,
                ),
            ).fetchone()
            message_row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(
                        CASE WHEN lower(folder) IN (
                            'junk', 'spam', 'trash', 'deleted items', 'deleted'
                        ) THEN 1 ELSE 0 END
                    ) AS special
                FROM messages
                """
            ).fetchone()
            proxy_row = connection.execute(
                "SELECT COUNT(*) AS count FROM proxies WHERE enabled = 1"
            ).fetchone()
        return DashboardOverview(
            total_accounts=int(account_row["total"] or 0),
            healthy_accounts=int(account_row["healthy"] or 0),
            abnormal_accounts=int(account_row["abnormal"] or 0),
            total_messages=int(message_row["total"] or 0),
            special_folder_messages=int(message_row["special"] or 0),
            enabled_proxies=int(proxy_row["count"] or 0),
        )
