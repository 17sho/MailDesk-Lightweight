from __future__ import annotations

import binascii
import time

import pyotp


def current_totp(secret: str, *, at_time: int | float | None = None) -> str:
    normalized = secret.strip().replace(" ", "").upper()
    if not normalized or len(normalized) > 256:
        raise ValueError("TOTP 密钥格式不正确")
    try:
        generator = pyotp.TOTP(normalized)
        code = generator.at(at_time if at_time is not None else time.time())
    except (binascii.Error, ValueError, TypeError) as exc:
        raise ValueError("TOTP 密钥格式不正确") from exc
    if len(code) != 6 or not code.isdigit():
        raise ValueError("TOTP 动态码生成失败")
    return code

