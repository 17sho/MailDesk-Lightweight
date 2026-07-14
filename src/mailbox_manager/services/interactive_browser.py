from __future__ import annotations

import webbrowser

from mailbox_manager.domain.models import EmailAccount

OFFICIAL_WEBMAIL_URLS = {
    "gmail.com": "https://mail.google.com/",
    "outlook.com": "https://outlook.live.com/mail/",
    "hotmail.com": "https://outlook.live.com/mail/",
    "live.com": "https://outlook.live.com/mail/",
    "qq.com": "https://mail.qq.com/",
    "163.com": "https://mail.163.com/",
    "126.com": "https://mail.126.com/",
    "sina.com": "https://mail.sina.com.cn/",
}


def open_official_webmail(account: EmailAccount) -> bool:
    """Open a visible official login page; credentials and DOM remain user-controlled."""
    domain = account.email.rsplit("@", 1)[-1].casefold()
    url = OFFICIAL_WEBMAIL_URLS.get(domain)
    if not url:
        return False
    return webbrowser.open(url, new=2)

