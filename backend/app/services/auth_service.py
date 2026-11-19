from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    rate_limiter,
    validate_password_strength,
    verify_password,
)
from app.models.enums import UserRole
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserUpdate


def register_user(
    db: Session,
    request: RegisterRequest,
) -> User:
    """Register a new user account.

    Enforces:
    - Normalization of email.
    - Password complexity validation.
    - Uniqueness of email address.
    - Strict default role of USER (cannot self-assign elevated roles).
    """
    normalized_email = request.email.strip().lower()

    # Validate password complexity before touching DB
    try:
        validate_password_strength(request.password)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(err),
        ) from err

    existing_user = db.execute(
        select(User).where(User.email == normalized_email)
    ).scalar_one_or_none()

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=normalized_email,
        full_name=request.full_name.strip(),
        hashed_password=hash_password(request.password),
        role=UserRole.USER,
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(
    db: Session,
    request: LoginRequest,
    client_ip: str | None = None,
    settings: Settings | None = None,
) -> User:
    """Authenticate a user using email and password with brute-force protection."""
    app_settings = settings or get_settings()
    normalized_email = request.email.strip().lower()
    rate_limit_key = f"{client_ip or 'unknown'}:{normalized_email}"

    # Rate limiting protection
    rate_limiter.check_rate_limit(
        rate_limit_key,
        max_attempts=app_settings.auth_rate_limit_max_attempts,
        lockout_seconds=app_settings.auth_rate_limit_lockout_seconds,
    )

    user = db.execute(
        select(User).where(User.email == normalized_email)
    ).scalar_one_or_none()

    if user is None or not verify_password(request.password, user.hashed_password):
        rate_limiter.record_failed_attempt(rate_limit_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Please contact support.",
        )

    # Reset failed attempts upon successful login
    rate_limiter.clear(rate_limit_key)
    return user


def create_user_tokens(
    db: Session,
    user: User,
    settings: Settings | None = None,
) -> TokenResponse:
    """Create a new access token and a hashed refresh token for the user."""
    app_settings = settings or get_settings()

    access_token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role.value,
        settings=app_settings,
    )

    raw_refresh_token = generate_refresh_token()
    token_hash = hash_token(raw_refresh_token)
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=app_settings.refresh_token_expire_days
    )

    refresh_token_record = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(refresh_token_record)
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        token_type="bearer",
        expires_in=app_settings.access_token_expire_minutes * 60,
    )


def rotate_refresh_token(
    db: Session,
    raw_refresh_token: str,
    settings: Settings | None = None,
) -> TokenResponse:
    """Rotate an existing refresh token for a new token pair.

    Implements token rotation and reuse detection.
    """
    app_settings = settings or get_settings()
    token_hash = hash_token(raw_refresh_token)

    token_record = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    ).scalar_one_or_none()

    if token_record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unrecognized refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Token reuse detection: if revoked token presented, revoke ALL user tokens as a precaution
    if token_record.revoked_at is not None:
        revoke_all_user_tokens(db, token_record.user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Expiration check
    now = datetime.now(timezone.utc)
    # Ensure timezone aware comparison
    expires_at = token_record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= now:
        token_record.revoked_at = now
        db.add(token_record)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check user account
    user = db.execute(
        select(User).where(User.id == token_record.user_id)
    ).scalar_one_or_none()

    if user is None or not user.is_active:
        token_record.revoked_at = now
        db.add(token_record)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Invalidate previous refresh token
    token_record.revoked_at = now
    db.add(token_record)
    db.commit()

    # Issue new pair
    return create_user_tokens(db, user, settings=app_settings)


def revoke_refresh_token(
    db: Session,
    raw_refresh_token: str,
) -> None:
    """Revoke a refresh token (logout)."""
    token_hash = hash_token(raw_refresh_token)
    token_record = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    ).scalar_one_or_none()

    if token_record is not None and token_record.revoked_at is None:
        token_record.revoked_at = datetime.now(timezone.utc)
        db.add(token_record)
        db.commit()


def revoke_all_user_tokens(
    db: Session,
    user_id: uuid.UUID,
) -> None:
    """Revoke all refresh tokens belonging to a user."""
    now = datetime.now(timezone.utc)
    tokens = db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
    ).scalars().all()

    for token in tokens:
        token.revoked_at = now
        db.add(token)
    db.commit()


def update_user_profile(
    db: Session,
    user: User,
    update_data: UserUpdate,
) -> User:
    """Update profile information for the current user."""
    if update_data.full_name is not None:
        user.full_name = update_data.full_name.strip()

    if update_data.email is not None:
        normalized_email = update_data.email.strip().lower()
        if normalized_email != user.email:
            existing = db.execute(
                select(User).where(User.email == normalized_email)
            ).scalar_one_or_none()
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This email address is already in use.",
                )
            user.email = normalized_email

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def change_user_password(
    db: Session,
    user: User,
    request: ChangePasswordRequest,
) -> None:
    """Change the user's password and invalidate all active sessions."""
    if not verify_password(request.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    if request.current_password == request.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password.",
        )

    try:
        validate_password_strength(request.new_password)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(err),
        ) from err

    user.hashed_password = hash_password(request.new_password)
    db.add(user)

    # Invalidate all active refresh tokens on password change
    revoke_all_user_tokens(db, user.id)
    db.commit()
