from __future__ import annotations

import httpx
import pytest

from mailbox_manager.domain.models import EmailAccount, ProtocolType
from mailbox_manager.services.security_audit import (
    GraphSecurityAuditService,
    SecurityAuditPermissionError,
)
from mailbox_manager.services.security_authorization import (
    GraphDeviceAuthorizationService,
)


def test_graph_security_audit_reports_forward_redirect_and_delete_rules() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2" in request.url.path:
            assert b"MailboxSettings.Read" in request.content
            return httpx.Response(200, json={"access_token": "access"})
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": "rule-1",
                        "displayName": "Suspicious",
                        "actions": {
                            "forwardTo": [
                                {"emailAddress": {"address": "outside@example.net"}}
                            ],
                            "delete": True,
                        },
                    }
                ]
            },
        )

    account = EmailAccount(
        email="owner@outlook.com",
        provider="outlook",
        protocol=ProtocolType.GRAPH,
        username="owner@outlook.com",
        refresh_token="refresh",
        client_id="00000000-0000-0000-0000-000000000001",
    )
    service = GraphSecurityAuditService(account, transport=httpx.MockTransport(handler))

    findings = service.audit_forwarding_rules()
    service.close()

    assert {finding.finding_type for finding in findings} == {"forward", "delete"}
    assert findings[0].rule_id == "rule-1"


def test_graph_security_audit_classifies_missing_permission() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2" in request.url.path:
            return httpx.Response(200, json={"access_token": "access"})
        return httpx.Response(403, json={"error": {"code": "ErrorAccessDenied"}})

    account = EmailAccount(
        email="owner@outlook.com",
        provider="outlook",
        protocol=ProtocolType.GRAPH,
        refresh_token="refresh",
        client_id="00000000-0000-0000-0000-000000000001",
    )
    service = GraphSecurityAuditService(account, transport=httpx.MockTransport(handler))

    with pytest.raises(SecurityAuditPermissionError):
        service.audit_forwarding_rules()
    service.close()


def test_device_code_authorization_returns_refresh_token_without_exposing_it() -> None:
    token_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.path.endswith("/devicecode"):
            assert b"Mail.Read" in request.content
            assert b"MailboxSettings.Read" in request.content
            return httpx.Response(
                200,
                json={
                    "device_code": "device-secret",
                    "user_code": "ABCD-EFGH",
                    "verification_uri": "https://microsoft.com/devicelogin",
                    "expires_in": 900,
                    "interval": 1,
                },
            )
        token_calls += 1
        if token_calls == 1:
            return httpx.Response(400, json={"error": "authorization_pending"})
        return httpx.Response(
            200,
            json={"access_token": "access-secret", "refresh_token": "rotated-refresh"},
        )

    account = EmailAccount(
        email="owner@outlook.com",
        provider="outlook",
        protocol=ProtocolType.GRAPH,
        client_id="00000000-0000-0000-0000-000000000001",
    )
    service = GraphDeviceAuthorizationService(
        transport=httpx.MockTransport(handler), sleeper=lambda _seconds: None
    )

    challenge = service.request_challenge(account)
    refresh_token = service.wait_for_refresh_token(account, challenge)
    service.close()

    assert challenge.user_code == "ABCD-EFGH"
    assert "device-secret" not in repr(challenge)
    assert refresh_token == "rotated-refresh"
