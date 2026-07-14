from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

from mailbox_manager.domain.models import EmailAccount

SECURITY_CONSENT_SCOPES = (
    "offline_access "
    "https://graph.microsoft.com/Mail.Read "
    "https://graph.microsoft.com/MailboxSettings.Read"
)


class DeviceAuthorizationError(RuntimeError):
    pass


class DeviceAuthorizationCancelled(DeviceAuthorizationError):
    pass


@dataclass(frozen=True, slots=True)
class DeviceCodeChallenge:
    user_code: str
    verification_uri: str
    verification_uri_complete: str = ""
    expires_in: int = 900
    interval: int = 5
    device_code: str = field(default="", repr=False)


class GraphDeviceAuthorizationService:
    def __init__(
        self,
        *,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout), transport=transport, follow_redirects=False
        )
        self._sleep = sleeper
        self._clock = clock

    def request_challenge(self, account: EmailAccount) -> DeviceCodeChallenge:
        if not account.client_id:
            raise DeviceAuthorizationError("账号缺少 Microsoft Client ID")
        tenant = quote(account.tenant or "common", safe="")
        response = self._client.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode",
            data={"client_id": account.client_id, "scope": SECURITY_CONSENT_SCOPES},
        )
        if response.status_code >= 400:
            raise DeviceAuthorizationError(
                "该 Client ID 不支持设备码授权，请使用已启用公共客户端流程的应用"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise DeviceAuthorizationError("Microsoft 未返回有效授权信息")
        device_code = payload.get("device_code")
        user_code = payload.get("user_code")
        verification_uri = payload.get("verification_uri")
        required_values = (device_code, user_code, verification_uri)
        if not all(isinstance(value, str) and value for value in required_values):
            raise DeviceAuthorizationError("Microsoft 未返回有效设备验证码")
        return DeviceCodeChallenge(
            device_code=device_code,
            user_code=user_code,
            verification_uri=verification_uri,
            verification_uri_complete=str(payload.get("verification_uri_complete") or ""),
            expires_in=_bounded_int(payload.get("expires_in"), 900, 60, 1800),
            interval=_bounded_int(payload.get("interval"), 5, 1, 30),
        )

    def wait_for_refresh_token(
        self,
        account: EmailAccount,
        challenge: DeviceCodeChallenge,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> str:
        tenant = quote(account.tenant or "common", safe="")
        token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
        deadline = self._clock() + challenge.expires_in
        interval = challenge.interval
        while self._clock() < deadline:
            if cancelled and cancelled():
                raise DeviceAuthorizationCancelled("已取消 Microsoft 重新授权")
            self._sleep(interval)
            if cancelled and cancelled():
                raise DeviceAuthorizationCancelled("已取消 Microsoft 重新授权")
            response = self._client.post(
                token_url,
                data={
                    "client_id": account.client_id,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": challenge.device_code,
                },
            )
            payload = _json_object(response)
            if response.status_code < 400:
                refresh_token = payload.get("refresh_token")
                if isinstance(refresh_token, str) and refresh_token:
                    return refresh_token
                raise DeviceAuthorizationError("Microsoft 未返回 Refresh Token")
            error = str(payload.get("error", "")).casefold()
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval = min(30, interval + 5)
                continue
            if error == "authorization_declined":
                raise DeviceAuthorizationCancelled("用户拒绝了 Microsoft 授权")
            if error in {"expired_token", "bad_verification_code"}:
                raise DeviceAuthorizationError("Microsoft 设备验证码已过期，请重新尝试")
            if error in {"invalid_client", "unauthorized_client"}:
                raise DeviceAuthorizationError("该 Client ID 未启用公共客户端设备码流程")
            raise DeviceAuthorizationError("Microsoft 无法完成设备码授权")
        raise DeviceAuthorizationError("Microsoft 设备验证码已过期，请重新尝试")

    def close(self) -> None:
        self._client.close()


def _json_object(response: httpx.Response) -> dict[str, object]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))
