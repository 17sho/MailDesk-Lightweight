from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from uuid import UUID

from mailbox_manager.domain.models import (
    EmailAccount,
    ImportPreview,
    ImportPreviewRow,
    ProtocolType,
    SecurityMode,
)
from mailbox_manager.protocols.providers import provider_for_email

EMAIL_PATTERN = re.compile(r"^[^\s@]{1,64}@[^\s@.]{1,253}(?:\.[^\s@.]{1,63})+$")
EMAIL_SEARCH = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PROXY_SEARCH = re.compile(r"(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}(?::[^\s|]+){0,2}")
MAX_LINES = 100_000

_IMPORT_KEY_ALIASES = {
    "email": "email",
    "emailaddress": "email",
    "mail": "email",
    "account": "email",
    "账号": "email",
    "邮箱": "email",
    "邮箱地址": "email",
    "username": "username",
    "用户名": "username",
    "登录名": "username",
    "password": "password",
    "passwd": "password",
    "pwd": "password",
    "secret": "password",
    "authcode": "password",
    "authorizationcode": "password",
    "apppassword": "password",
    "密码": "password",
    "授权码": "password",
    "应用专用密码": "password",
    "应用密码": "password",
    "客户端密码": "password",
    "host": "host",
    "server": "host",
    "imapserver": "host",
    "imaphost": "host",
    "收件服务器": "host",
    "imap服务器": "host",
    "服务器": "host",
    "pophost": "pop_host",
    "popserver": "pop_host",
    "pop3host": "pop_host",
    "pop3server": "pop_host",
    "pop服务器": "pop_host",
    "pop3服务器": "pop_host",
    "port": "port",
    "imapport": "port",
    "popport": "port",
    "pop3port": "port",
    "端口": "port",
    "protocol": "protocol",
    "协议": "protocol",
    "收件协议": "protocol",
    "security": "security",
    "encryption": "security",
    "连接加密": "security",
    "加密": "security",
    "加密方式": "security",
    "refreshtoken": "refresh_token",
    "刷新令牌": "refresh_token",
    "rt": "refresh_token",
    "clientid": "client_id",
    "客户端id": "client_id",
    "应用id": "client_id",
    "oauthprovider": "oauth_provider",
    "oauth提供商": "oauth_provider",
    "oauth类型": "oauth_provider",
    "tenant": "tenant",
    "租户": "tenant",
    "smtphost": "smtp_host",
    "smtpserver": "smtp_host",
    "smtp服务器": "smtp_host",
    "smtpport": "smtp_port",
    "smtp端口": "smtp_port",
    "smtpsecurity": "smtp_security",
    "smtp加密": "smtp_security",
    "smtp加密方式": "smtp_security",
    "totp": "totp_secret",
    "totpsecret": "totp_secret",
    "2fa": "totp_secret",
    "2fa密钥": "totp_secret",
    "provider": "provider",
    "mailboxtype": "provider",
    "emailtype": "provider",
    "邮箱类型": "provider",
    "服务商": "provider",
    "邮箱服务商": "provider",
}

_PROVIDER_HINT_DOMAINS = {
    "gmail": "gmail.com",
    "google": "gmail.com",
    "googleworkspace": "gmail.com",
    "谷歌": "gmail.com",
    "谷歌邮箱": "gmail.com",
    "qq": "qq.com",
    "qq邮箱": "qq.com",
    "foxmail": "foxmail.com",
    "163": "163.com",
    "163邮箱": "163.com",
    "126": "126.com",
    "126邮箱": "126.com",
    "yeah": "yeah.net",
    "yeahnet": "yeah.net",
    "88": "88.com",
    "88邮箱": "88.com",
    "sina": "sina.com",
    "新浪": "sina.com",
    "新浪邮箱": "sina.com",
    "outlook": "outlook.com",
    "microsoft": "outlook.com",
    "microsoft365": "outlook.com",
    "office365": "outlook.com",
}


def _compact_token(value: str) -> str:
    return re.sub(r"[\s_./\\-]+", "", value.strip().casefold())


def _canonical_import_key(value: str) -> str:
    compact = _compact_token(value)
    return _IMPORT_KEY_ALIASES.get(compact, value.strip().casefold())


def _security_mode(value: str, *, default: SecurityMode) -> SecurityMode:
    if not value.strip():
        return default
    compact = _compact_token(value)
    aliases = {
        "ssl": SecurityMode.SSL,
        "ssltls": SecurityMode.SSL,
        "implicittls": SecurityMode.SSL,
        "starttls": SecurityMode.STARTTLS,
        "explicittls": SecurityMode.STARTTLS,
        "plain": SecurityMode.PLAIN,
        "none": SecurityMode.PLAIN,
        "noencryption": SecurityMode.PLAIN,
        "无加密": SecurityMode.PLAIN,
    }
    if compact == "tls":
        return default
    try:
        return aliases[compact]
    except KeyError as exc:
        raise ValueError(f"不支持的连接加密方式：{value}") from exc


def _provider_from_hint(value: str):
    domain = _PROVIDER_HINT_DOMAINS.get(_compact_token(value))
    return provider_for_email(f"owner@{domain}") if domain else None


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except (ValueError, AttributeError):
        return False
    return True


def _oauth_provider_for_client_id(value: str) -> str:
    normalized = value.strip().casefold()
    if _is_uuid(normalized):
        return "microsoft"
    if normalized.endswith(".apps.googleusercontent.com") and len(normalized) <= 255:
        return "google"
    return ""


def _masked_source(email: str) -> str:
    if "@" not in email:
        return "<无法识别的导入行>"
    local, domain = email.split("@", 1)
    return f"{local[:2]}***@{domain}"


def _oauth_fields(parts: list[str]) -> tuple[str, str, str] | None:
    client_positions = [
        (index, _oauth_provider_for_client_id(value))
        for index, value in enumerate(parts[1:], 1)
        if _oauth_provider_for_client_id(value)
    ]
    if not client_positions:
        return None
    client_index, oauth_provider = client_positions[0]
    client_id = parts[client_index]
    candidates = [
        (index, value)
        for index, value in enumerate(parts[1:], 1)
        if index != client_index and value
    ]
    if not candidates:
        raise ValueError("OAuth 行缺少 Refresh Token")

    def token_score(candidate: tuple[int, str]) -> tuple[int, int, int]:
        index, value = candidate
        token_like = int(
            len(value) >= 80 or value.startswith(("0.", "1.", "M.")) or value.count(".") >= 2
        )
        adjacent_after = int(index == client_index + 1)
        adjacent_before = int(index == client_index - 1)
        return token_like, adjacent_after * 2 + adjacent_before, len(value)

    refresh_token = max(candidates, key=token_score)[1]
    return client_id, refresh_token, oauth_provider


class SmartAccountParser:
    def parse_text(self, text: str) -> ImportPreview:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) > MAX_LINES:
            raise ValueError(f"导入文本不能超过 {MAX_LINES} 行")
        rows = [self._parse_line(line, number) for number, line in enumerate(lines, 1)]
        return ImportPreview(tuple(rows))

    def parse_records(self, records: Iterable[Mapping[str, object]]) -> ImportPreview:
        rows: list[ImportPreviewRow] = []
        for number, record in enumerate(records, 1):
            normalized = {
                _canonical_import_key(str(key)): str(value or "").strip()
                for key, value in record.items()
            }
            email = normalized.get("email", "")
            try:
                account = self._account_from_mapping(normalized, email)
                rows.append(
                    ImportPreviewRow(number, account, "high", raw_masked=_masked_source(email))
                )
            except (ValueError, TypeError) as exc:
                rows.append(
                    ImportPreviewRow(
                        number,
                        None,
                        "low",
                        error=str(exc),
                        raw_masked=_masked_source(email),
                    )
                )
        return ImportPreview(tuple(rows))

    def _parse_line(self, line: str, number: int) -> ImportPreviewRow:
        if "----" not in line:
            return self._parse_freeform(line, number)
        parts = [part.strip() for part in line.split("----")]
        email = parts[0] if parts else ""
        try:
            if not EMAIL_PATTERN.fullmatch(email.casefold()):
                raise ValueError("邮箱地址格式不正确")
            account, confidence, warnings = self._account_from_parts(parts)
            return ImportPreviewRow(
                number,
                account,
                confidence,
                warnings,
                raw_masked=_masked_source(email),
            )
        except (ValueError, TypeError) as exc:
            return ImportPreviewRow(
                number,
                None,
                "low",
                error=str(exc),
                raw_masked=_masked_source(email),
            )

    def _parse_freeform(self, line: str, number: int) -> ImportPreviewRow:
        match = EMAIL_SEARCH.search(line)
        if not match:
            return ImportPreviewRow(
                number,
                None,
                "low",
                error="未找到邮箱地址",
                raw_masked="<无法识别的导入行>",
            )
        email = match.group(0).casefold()
        warnings: list[str] = []
        if PROXY_SEARCH.search(line):
            warnings.append("检测到代理字段；请在代理管理中确认后单独导入")
        remainder = line[match.end() :]
        tokens = [
            token.strip(":=()[]{}<>'\"")
            for token in re.split(r"[\s|,;]+", remainder)
            if token.strip(":=()[]{}<>'\"")
        ]
        tokens = [token for token in tokens if not PROXY_SEARCH.fullmatch(token)]
        client_id = next((token for token in tokens if _oauth_provider_for_client_id(token)), "")
        if client_id:
            try:
                oauth_fields = _oauth_fields([email, *tokens])
            except ValueError:
                oauth_fields = None
            if oauth_fields is None:
                return ImportPreviewRow(
                    number,
                    None,
                    "low",
                    tuple(warnings),
                    error="Outlook OAuth 行缺少 Refresh Token",
                    raw_masked=_masked_source(email),
                )
            client_id, refresh_token, oauth_provider = oauth_fields
            secret = next(
                (
                    token
                    for token in tokens
                    if token and token not in {client_id, refresh_token}
                ),
                "",
            )
            if oauth_provider == "google":
                gmail = provider_for_email("owner@gmail.com")
                account = EmailAccount(
                    email=email,
                    provider="Gmail",
                    protocol=ProtocolType.IMAP,
                    host="imap.gmail.com",
                    port=993,
                    username=email,
                    secret=secret,
                    refresh_token=refresh_token,
                    client_id=client_id,
                    oauth_provider="google",
                    smtp_host=gmail.smtp_host if gmail else "smtp.gmail.com",
                    smtp_port=gmail.smtp_port if gmail else 465,
                )
            else:
                account = EmailAccount(
                    email=email,
                    provider="Outlook",
                    protocol=ProtocolType.GRAPH,
                    username=email,
                    secret=secret,
                    refresh_token=refresh_token,
                    client_id=client_id,
                    oauth_provider="microsoft",
                )
            return ImportPreviewRow(
                number, account, "medium", tuple(warnings), raw_masked=_masked_source(email)
            )
        secret = tokens[0] if tokens else ""
        if not secret:
            return ImportPreviewRow(
                number,
                None,
                "low",
                tuple(warnings),
                error="邮箱附近未找到密码或授权码",
                raw_masked=_masked_source(email),
            )
        provider = provider_for_email(email)
        if provider:
            if provider.name == "Gmail":
                groups = tokens[:4]
                secret = (
                    "".join(groups)
                    if len(groups) == 4
                    and all(len(group) == 4 and group.isalnum() for group in groups)
                    else "".join(secret.split())
                )
            account = EmailAccount(
                email=email,
                provider=provider.name,
                protocol=ProtocolType.IMAP,
                host=provider.imap_host,
                port=provider.imap_port,
                security=provider.security,
                username=email,
                secret=secret,
                smtp_host=provider.smtp_host,
                smtp_port=provider.smtp_port,
                smtp_security=provider.smtp_security,
            )
            warnings.append("自由文本字段为启发式识别，请在预览中确认")
            confidence = "medium"
        else:
            domain = email.rsplit("@", 1)[1]
            account = EmailAccount(
                email=email,
                provider="custom",
                protocol=ProtocolType.IMAP,
                host=f"imap.{domain}",
                port=993,
                security=SecurityMode.SSL,
                username=email,
                secret=secret,
            )
            warnings.append("自定义域名使用自动发现候选配置，连接前请执行探测")
            confidence = "low"
        return ImportPreviewRow(
            number,
            account,
            confidence,
            tuple(warnings),
            raw_masked=_masked_source(email),
        )

    def _account_from_parts(self, parts: list[str]) -> tuple[EmailAccount, str, tuple[str, ...]]:
        email = parts[0].casefold()
        if len(parts) >= 4 and parts[3].isdigit():
            port = int(parts[3])
            host = parts[2].casefold()
            protocol = (
                ProtocolType.POP3
                if port in {110, 995} or host.startswith(("pop.", "pop3."))
                else ProtocolType.IMAP
            )
            account = EmailAccount(
                email=email,
                provider="custom",
                protocol=protocol,
                host=host,
                port=port,
                security=(SecurityMode.SSL if port in {993, 995} else SecurityMode.STARTTLS),
                username=email,
                secret=parts[1],
                totp_secret=parts[4] if len(parts) >= 5 else "",
            )
            return account, "high", ()
        oauth_fields = _oauth_fields(parts)
        if oauth_fields is not None:
            client_id, refresh_token, oauth_provider = oauth_fields
            secret = next(
                (value for value in parts[1:] if value and value not in {client_id, refresh_token}),
                "",
            )
            warnings = ("已识别并安全保存 OAuth 账号密码字段",) if secret else ()
            if oauth_provider == "google":
                gmail = provider_for_email("owner@gmail.com")
                return (
                    EmailAccount(
                        email=email,
                        provider="Gmail",
                        protocol=ProtocolType.IMAP,
                        host="imap.gmail.com",
                        port=993,
                        username=email,
                        secret=secret,
                        refresh_token=refresh_token,
                        client_id=client_id,
                        oauth_provider="google",
                        smtp_host=(gmail.smtp_host if gmail else "smtp.gmail.com"),
                        smtp_port=gmail.smtp_port if gmail else 465,
                    ),
                    "high",
                    warnings,
                )
            return (
                EmailAccount(
                    email=email,
                    provider="Outlook",
                    protocol=ProtocolType.GRAPH,
                    username=email,
                    secret=secret,
                    refresh_token=refresh_token,
                    client_id=client_id,
                    oauth_provider="microsoft",
                ),
                "high",
                warnings,
            )
        provider = provider_for_email(email)
        if len(parts) >= 4 and provider and provider.name == "Outlook":
            raise ValueError("疑似 Outlook OAuth 行，但未找到有效的 UUID Client ID")
        if len(parts) >= 2:
            if not provider:
                if len(parts) != 2:
                    raise ValueError("自定义域名邮箱需要提供 IMAP 服务器和端口")
                domain = email.rsplit("@", 1)[1]
                return (
                    EmailAccount(
                        email=email,
                        provider="custom",
                        protocol=ProtocolType.IMAP,
                        host=f"imap.{domain}",
                        port=993,
                        security=SecurityMode.SSL,
                        username=email,
                        secret=parts[1],
                    ),
                    "low",
                    ("自定义域名使用自动发现候选配置，连接前请执行探测",),
                )
            secret = parts[2] if len(parts) >= 3 else parts[1]
            if provider.name == "Gmail":
                secret = "".join(secret.split())
            warnings = ("已按邮箱服务商使用授权码/应用专用密码字段",) if len(parts) >= 3 else ()
            return (
                EmailAccount(
                    email=email,
                    provider=provider.name,
                    protocol=ProtocolType.IMAP,
                    host=provider.imap_host,
                    port=provider.imap_port,
                    security=provider.security,
                    username=email,
                    secret=secret,
                    smtp_host=provider.smtp_host,
                    smtp_port=provider.smtp_port,
                    smtp_security=provider.smtp_security,
                ),
                "medium" if warnings else "high",
                warnings,
            )
        raise ValueError("无法识别该行字段")

    def _account_from_mapping(self, record: Mapping[str, str], email: str) -> EmailAccount:
        email = email.casefold()
        if not EMAIL_PATTERN.fullmatch(email):
            raise ValueError("邮箱地址格式不正确")
        refresh_token = record.get("refresh_token", "")
        client_id = record.get("client_id", "")
        if bool(refresh_token) != bool(client_id):
            missing = "Client ID" if refresh_token else "Refresh Token"
            raise ValueError(f"OAuth 行缺少 {missing}")
        if refresh_token and client_id:
            secret = record.get("password", "")
            requested_provider = _compact_token(record.get("oauth_provider", ""))
            inferred_provider = _oauth_provider_for_client_id(client_id)
            oauth_provider = requested_provider or inferred_provider
            if not oauth_provider:
                oauth_provider = "google" if email.endswith("@gmail.com") else "microsoft"
            if oauth_provider in {"google", "gmail", "googleworkspace"}:
                provider = provider_for_email("owner@gmail.com")
                return EmailAccount(
                    email=email,
                    provider="Gmail",
                    protocol=ProtocolType.IMAP,
                    host="imap.gmail.com",
                    port=993,
                    username=email,
                    secret=secret,
                    refresh_token=refresh_token,
                    client_id=client_id,
                    oauth_provider="google",
                    smtp_host=provider.smtp_host if provider else "smtp.gmail.com",
                    smtp_port=provider.smtp_port if provider else 465,
                )
            if oauth_provider not in {"microsoft", "outlook", "office365"}:
                raise ValueError("OAuth 提供商必须是 google 或 microsoft")
            return EmailAccount(
                email=email,
                provider="Outlook",
                protocol=ProtocolType.GRAPH,
                username=email,
                secret=secret,
                refresh_token=refresh_token,
                client_id=client_id,
                tenant=record.get("tenant") or "common",
                oauth_provider="microsoft",
            )
        provider = provider_for_email(email) or _provider_from_hint(record.get("provider", ""))
        protocol_value = record.get("protocol", "").strip().casefold()
        host_hint = record.get("pop_host") or record.get("host", "")
        port_hint = record.get("port", "")
        if protocol_value in {"pop", ProtocolType.POP3.value}:
            protocol = ProtocolType.POP3
        elif protocol_value in {"imap", "imap4"}:
            protocol = ProtocolType.IMAP
        elif not protocol_value:
            protocol = (
                ProtocolType.POP3
                if record.get("pop_host")
                or host_hint.casefold().startswith(("pop.", "pop3."))
                or (port_hint.isdigit() and int(port_hint) in {110, 995})
                else ProtocolType.IMAP
            )
        else:
            raise ValueError("协议必须是 IMAP 或 POP3")
        if protocol is ProtocolType.POP3:
            host = (
                record.get("pop_host")
                or record.get("host")
                or (provider.pop_host if provider else "")
            )
            default_port = provider.pop_port if provider else 995
        else:
            host = record.get("host") or (provider.imap_host if provider else "")
            default_port = provider.imap_port if provider else 993
        if not host:
            raise ValueError("自定义域名邮箱需要提供 IMAP 服务器和端口")
        host = host.strip().casefold()
        port = int(record.get("port") or default_port)
        secret = record.get("password", "")
        if not secret:
            raise ValueError("缺少密码或授权码")
        if provider and provider.name == "Gmail":
            secret = "".join(secret.split())
        security = _security_mode(
            record.get("security", ""),
            default=(SecurityMode.SSL if port in {465, 993, 995} else SecurityMode.STARTTLS),
        )
        smtp_host = record.get("smtp_host") or (provider.smtp_host if provider else "")
        smtp_port = int(record.get("smtp_port") or (provider.smtp_port if provider else 0))
        smtp_security = _security_mode(
            record.get("smtp_security", ""),
            default=(
                provider.smtp_security
                if provider
                else SecurityMode.SSL
                if smtp_port in {0, 465}
                else SecurityMode.STARTTLS
            ),
        )
        return EmailAccount(
            email=email,
            provider=provider.name if provider else "custom",
            protocol=protocol,
            host=host,
            port=port,
            security=security,
            username=record.get("username") or email,
            secret=secret,
            smtp_host=smtp_host.strip().casefold(),
            smtp_port=smtp_port,
            smtp_security=smtp_security,
            totp_secret=record.get("totp_secret", ""),
        )
