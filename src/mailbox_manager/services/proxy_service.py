from __future__ import annotations

from urllib.parse import quote

from mailbox_manager.domain.models import ProxyConfig, ProxyType


def parse_proxy_line(value: str, proxy_type: ProxyType = ProxyType.HTTP) -> ProxyConfig:
    parts = value.strip().split(":", 3)
    if len(parts) < 2:
        raise ValueError("代理格式必须为 IP:Port 或 IP:Port:User:Pass")
    host = parts[0].strip()
    try:
        port = int(parts[1])
    except ValueError as exc:
        raise ValueError("代理端口必须是数字") from exc
    username = parts[2].strip() if len(parts) >= 3 else ""
    password = parts[3] if len(parts) >= 4 else ""
    if bool(username) != bool(password):
        raise ValueError("代理用户名和密码必须同时提供")
    return ProxyConfig(
        proxy_type=proxy_type,
        host=host,
        port=port,
        username=username,
        password=password,
    )


def parse_proxy_text(value: str, proxy_type: ProxyType = ProxyType.HTTP) -> list[ProxyConfig]:
    proxies = [
        parse_proxy_line(line, proxy_type)
        for line in value.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if len(proxies) > 10_000:
        raise ValueError("单次最多导入 10,000 个代理")
    return proxies


def proxy_url(proxy: ProxyConfig) -> str:
    credentials = ""
    if proxy.username:
        credentials = f"{quote(proxy.username, safe='')}:{quote(proxy.password, safe='')}@"
    return f"{proxy.proxy_type.value}://{credentials}{proxy.host}:{proxy.port}"

