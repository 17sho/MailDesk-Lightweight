from __future__ import annotations

from urllib.parse import quote

import httpx

from mailbox_manager.domain.models import EmailAccount, SecurityFinding

AUDIT_SCOPE = "https://graph.microsoft.com/MailboxSettings.Read"


class SecurityAuditError(RuntimeError):
    pass


class SecurityAuditPermissionError(SecurityAuditError):
    pass


class SecurityAuditAuthenticationError(SecurityAuditError):
    pass


class SecurityAuditTemporaryError(SecurityAuditError):
    pass


def _oauth_error(response: httpx.Response) -> tuple[str, str]:
    try:
        payload = response.json()
    except ValueError:
        return "", ""
    if not isinstance(payload, dict):
        return "", ""
    code = payload.get("error")
    description = payload.get("error_description")
    return (
        str(code).casefold() if code else "",
        str(description).casefold() if description else "",
    )


class GraphSecurityAuditService:
    """Read-only audit of Graph inbox rules; never modifies account security settings."""

    def __init__(
        self,
        account: EmailAccount,
        *,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._account = account
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout), transport=transport, follow_redirects=False
        )

    def _token(self) -> str:
        tenant = quote(self._account.tenant or "common", safe="")
        response = self._client.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            data={
                "client_id": self._account.client_id,
                "refresh_token": self._account.refresh_token,
                "grant_type": "refresh_token",
                "scope": f"{AUDIT_SCOPE} offline_access",
            },
        )
        if response.status_code >= 400:
            code, description = _oauth_error(response)
            if code in {"invalid_scope", "consent_required", "interaction_required"} or any(
                marker in description for marker in ("aadsts65001", "consent", "permission")
            ):
                raise SecurityAuditPermissionError("安全审计需要额外 Microsoft 授权")
            if code in {"invalid_grant", "invalid_client", "unauthorized_client"}:
                raise SecurityAuditAuthenticationError("Microsoft 授权已失效或客户端不兼容")
            raise SecurityAuditTemporaryError("Microsoft 授权服务暂时不可用")
        payload = response.json()
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise SecurityAuditAuthenticationError("Microsoft 未返回有效 Access Token")
        return token

    def audit_forwarding_rules(self) -> list[SecurityFinding]:
        response = self._client.get(
            "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messageRules",
            headers={"Authorization": f"Bearer {self._token()}"},
        )
        if response.status_code == 403:
            raise SecurityAuditPermissionError("安全审计缺少 MailboxSettings.Read 权限")
        if response.status_code == 401:
            raise SecurityAuditAuthenticationError("Microsoft 安全审计授权已失效")
        if response.status_code == 429 or response.status_code >= 500:
            raise SecurityAuditTemporaryError("Microsoft Graph 暂时无法完成安全审计")
        if response.status_code >= 400:
            raise SecurityAuditError("无法读取 Outlook 收件规则")
        payload = response.json()
        rules = payload.get("value", []) if isinstance(payload, dict) else []
        findings: list[SecurityFinding] = []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            rule_id = str(rule.get("id", ""))
            rule_name = str(rule.get("displayName", "未命名规则"))
            actions = rule.get("actions")
            if not isinstance(actions, dict):
                continue
            for field, finding_type in (("forwardTo", "forward"), ("redirectTo", "redirect")):
                targets = actions.get(field)
                if isinstance(targets, list) and targets:
                    findings.append(
                        SecurityFinding(
                            rule_id,
                            rule_name,
                            finding_type,
                            ", ".join(_target_address(target) for target in targets),
                        )
                    )
            if actions.get("delete") is True:
                findings.append(SecurityFinding(rule_id, rule_name, "delete", "规则会删除邮件"))
        return findings

    def close(self) -> None:
        self._client.close()


def _target_address(value: object) -> str:
    if not isinstance(value, dict):
        return "未知目标"
    email_address = value.get("emailAddress")
    if not isinstance(email_address, dict):
        return "未知目标"
    return str(email_address.get("address", "未知目标")).casefold()
