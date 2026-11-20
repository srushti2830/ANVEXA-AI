from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_require_a_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANVEXA_JWT_SECRET_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_reject_short_jwt_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_secret_key="short")


def test_settings_accept_configured_jwt_secret() -> None:
    settings = Settings(
        _env_file=None,
        jwt_secret_key="a-private-test-key-with-at-least-32-chars",
    )

    assert len(settings.jwt_secret_key.get_secret_value()) >= 32
