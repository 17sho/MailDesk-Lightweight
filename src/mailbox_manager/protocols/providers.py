from __future__ import annotations

from dataclasses import dataclass

from mailbox_manager.domain.models import SecurityMode


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    name: str
    imap_host: str
    imap_port: int = 993
    security: SecurityMode = SecurityMode.SSL
    requires_app_password: bool = True
    pop_host: str = ""
    pop_port: int = 995
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_security: SecurityMode = SecurityMode.SSL


PROVIDERS: dict[str, ProviderConfig] = {
    "qq.com": ProviderConfig(
        "QQ 邮箱", "imap.qq.com", pop_host="pop.qq.com", smtp_host="smtp.qq.com"
    ),
    "163.com": ProviderConfig(
        "163 邮箱", "imap.163.com", pop_host="pop.163.com", smtp_host="smtp.163.com"
    ),
    "126.com": ProviderConfig(
        "126 邮箱", "imap.126.com", pop_host="pop.126.com", smtp_host="smtp.126.com"
    ),
    "yeah.net": ProviderConfig(
        "网易邮箱", "imap.yeah.net", pop_host="pop.yeah.net", smtp_host="smtp.yeah.net"
    ),
    "88.com": ProviderConfig(
        "88 邮箱", "imap.88.com", pop_host="pop.88.com", smtp_host="smtp.88.com"
    ),
    "sina.com": ProviderConfig(
        "新浪邮箱", "imap.sina.com", pop_host="pop.sina.com", smtp_host="smtp.sina.com"
    ),
    "gmail.com": ProviderConfig(
        "Gmail", "imap.gmail.com", pop_host="pop.gmail.com", smtp_host="smtp.gmail.com"
    ),
    "outlook.com": ProviderConfig(
        "Outlook",
        "outlook.office365.com",
        pop_host="outlook.office365.com",
        smtp_host="smtp.office365.com",
        smtp_port=587,
        smtp_security=SecurityMode.STARTTLS,
    ),
    "hotmail.com": ProviderConfig(
        "Outlook",
        "outlook.office365.com",
        pop_host="outlook.office365.com",
        smtp_host="smtp.office365.com",
        smtp_port=587,
        smtp_security=SecurityMode.STARTTLS,
    ),
    "live.com": ProviderConfig(
        "Outlook",
        "outlook.office365.com",
        pop_host="outlook.office365.com",
        smtp_host="smtp.office365.com",
        smtp_port=587,
        smtp_security=SecurityMode.STARTTLS,
    ),
    "foxmail.com": ProviderConfig(
        "Foxmail", "imap.qq.com", pop_host="pop.qq.com", smtp_host="smtp.qq.com"
    ),
}


def provider_for_email(email: str) -> ProviderConfig | None:
    domain = email.rsplit("@", 1)[-1].casefold()
    return PROVIDERS.get(domain)
