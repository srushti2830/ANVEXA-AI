from __future__ import annotations

from typing import Callable
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.security import decode_access_token
from backend.app.database.session import get_db
from backend.app.models.enums import UserRole
from backend.app.models.user import User

settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_prefix}/auth/login",
    auto_error=False,
)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Retrieve and validate the currently authenticated user from the JWT token."""
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = uuid.UUID(user_id_str)
    except (ValueError, TypeError) as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid subject identifier in token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from err

    user = db.execute(
        select(User).where(User.id == user_id)
    ).scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Helper dependency returning verified active user."""
    return current_user


def require_role(*allowed_roles: UserRole) -> Callable[[User], User]:
    """Factory creating an authorization dependency for allowed roles."""

    def role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this resource",
            )
        return current_user

    return role_checker


def verify_resource_ownership(
    resource_owner_id: uuid.UUID,
    current_user: User,
    allow_roles: tuple[UserRole, ...] = (UserRole.ADMIN,),
) -> None:
    """Validate resource ownership to prevent Insecure Direct Object References (IDOR).

    Rejects request if the current user does not own the resource and does not possess
    one of the allowed override roles (e.g. ADMIN).
    """
    if current_user.role in allow_roles:
        return

    if current_user.id != resource_owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: you do not have permission to access this resource",
        )
