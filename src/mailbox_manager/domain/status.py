from __future__ import annotations

from enum import StrEnum


class AccountStatus(StrEnum):
    """Stable machine-readable account and fetch status values."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    SUCCESS = "success"
    AUTH_FAILED = "auth_failed"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    BLOCKED = "blocked"
    NETWORK_ERROR = "network_error"
    CONFIG_ERROR = "config_error"
    CANCELLED = "cancelled"
    UNKNOWN_ERROR = "unknown_error"


STATUS_LABELS: dict[AccountStatus, str] = {
    AccountStatus.DISCONNECTED: "未连接",
    AccountStatus.CONNECTING: "连接中",
    AccountStatus.SUCCESS: "正常",
    AccountStatus.AUTH_FAILED: "鉴权失败",
    AccountStatus.TIMEOUT: "连接超时",
    AccountStatus.RATE_LIMITED: "服务限流",
    AccountStatus.BLOCKED: "服务拒绝",
    AccountStatus.NETWORK_ERROR: "网络错误",
    AccountStatus.CONFIG_ERROR: "配置错误",
    AccountStatus.CANCELLED: "已停止",
    AccountStatus.UNKNOWN_ERROR: "未知错误",
}

