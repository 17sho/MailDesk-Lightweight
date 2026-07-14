from __future__ import annotations

from urllib.parse import quote

import httpx

from mailbox_manager.domain.models import EmailAccount


class OAuthTokenProvider:
    """Exchange user-provided refresh tokens through official OAuth endpoints."""

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
        proxy: str | None = None,
    ) -> None:
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            transport=transport,
            follow_redirects=False,
            proxy=proxy,
        )

    def access_token(self, account: EmailAccount) -> str:
        if not account.refresh_token or not account.client_id:
            raise ValueError("OAuth2 账号缺少 Refresh Token 或 Client ID")
        provider = (account.oauth_provider or _provider_from_email(account.email)).casefold()
        if provider == "google":
            url = "https://oauth2.googleapis.com/token"
            data = {
                "client_id": account.client_id,
                "refresh_token": account.refresh_token,
                "grant_type": "refresh_token",
            }
        elif provider in {"microsoft", "outlook", "office365"}:
            tenant = quote(account.tenant or "common", safe="")
            url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
            data = {
                "client_id": account.client_id,
                "refresh_token": account.refresh_token,
                "grant_type": "refresh_token",
                "scope": "https://outlook.office.com/IMAP.AccessAsUser.All offline_access",
            }
        else:
            raise ValueError("暂不支持该 OAuth2 提供商")
        response = self._client.post(url, data=data)
        if response.status_code >= 400:
            raise RuntimeError("OAuth2 Token 换取失败，请检查授权范围或重新授权")
        payload = response.json()
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise RuntimeError("OAuth2 服务未返回有效 Access Token")
        return token

    def close(self) -> None:
        self._client.close()


def _provider_from_email(email: str) -> str:
    domain = email.rsplit("@", 1)[-1].casefold()
    if domain == "gmail.com":
        return "google"
    if domain in {"outlook.com", "hotmail.com", "live.com"}:
        return "microsoft"
    return ""
