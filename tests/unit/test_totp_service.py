from __future__ import annotations

import pytest

from mailbox_manager.services.totp_service import current_totp


def test_current_totp_generates_six_digit_code_at_known_time() -> None:
    assert current_totp("JBSWY3DPEHPK3PXP", at_time=0) == "282760"


def test_current_totp_rejects_invalid_or_oversized_secret() -> None:
    with pytest.raises(ValueError, match="TOTP"):
        current_totp("not valid !!!")

    with pytest.raises(ValueError, match="TOTP"):
        current_totp("A" * 5000)

