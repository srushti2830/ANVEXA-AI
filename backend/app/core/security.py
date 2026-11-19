from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import re
import secrets
import threading
from typing import Any
import uuid

import argon2
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)
from fastapi import HTTPException, status
import jwt

from backend.app.core.config import Settings, get_settings

# Argon2id password hasher configuration (OWASP recommended minimums)
_password_hasher = argon2.PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

# Password strength regexes
_UPPERCASE_RE = re.compile(r"[A-Z]")
_LOWERCASE_RE = re.compile(r"[a-z]")
_DIGIT_RE = re.compile(r"[0-9]")
_SPECIAL_RE = re.compile(r"""[!@#$%^&*()_+\-=\[\]{}|;:,.<>?/~`"'\\]""")


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2id hash."""
    if not hashed_password:
        return False
    try:
        return _password_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError, TypeError):
        return False


def validate_password_strength(password: str) -> None:
    """Validate password complexity.

    Requires:
    - Minimum 8 characters
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 numeric digit
    - At least 1 special character
    """
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if len(password) > 128:
        raise ValueError("Password must not exceed 128 characters.")
    if not _UPPERCASE_RE.search(password):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not _LOWERCASE_RE.search(password):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not _DIGIT_RE.search(password):
        raise ValueError("Password must contain at least one number.")
    if not _SPECIAL_RE.search(password):
        raise ValueError(
            "Password must contain at least one special character (!@#$%^&*...)."
        )


def generate_refresh_token() -> str:
    """Generate a high-entropy cryptographically secure raw refresh token."""
    return secrets.token_urlsafe(64)


def hash_token(raw_token: str) -> str:
    """Generate SHA-256 hash of a raw token for safe database persistence."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_access_token(
    user_id: uuid.UUID,
    email: str,
    role: str,
    expires_delta: timedelta | None = None,
    settings: Settings | None = None,
) -> str:
    """Create a signed JWT access token."""
    app_settings = settings or get_settings()
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(minutes=app_settings.access_token_expire_minutes)
    )

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    return jwt.encode(
        payload,
        app_settings.jwt_secret_key.get_secret_value(),
        algorithm=app_settings.jwt_algorithm,
    )


def decode_access_token(
    token: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Decode and validate a JWT access token."""
    app_settings = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            app_settings.jwt_secret_key.get_secret_value(),
            algorithms=[app_settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat"]},
        )
    except jwt.ExpiredSignatureError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from err
    except jwt.InvalidTokenError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from err

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


class InMemoryRateLimiter:
    """Thread-safe rate limiter for authentication endpoints."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failed_attempts: dict[str, list[datetime]] = {}

    def check_rate_limit(
        self,
        key: str,
        max_attempts: int,
        lockout_seconds: int,
    ) -> None:
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(seconds=lockout_seconds)

        with self._lock:
            attempts = self._failed_attempts.get(key, [])
            valid_attempts = [t for t in attempts if t > threshold]
            self._failed_attempts[key] = valid_attempts

            if len(valid_attempts) >= max_attempts:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many failed login attempts. Please try again later.",
                )

    def record_failed_attempt(self, key: str) -> None:
        now = datetime.now(timezone.utc)
        with self._lock:
            if key not in self._failed_attempts:
                self._failed_attempts[key] = []
            self._failed_attempts[key].append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._failed_attempts.pop(key, None)

    def reset_all(self) -> None:
        """Utility for tests to reset state."""
        with self._lock:
            self._failed_attempts.clear()


rate_limiter = InMemoryRateLimiter()
