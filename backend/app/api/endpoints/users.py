from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    require_role,
    verify_resource_ownership,
)
from app.database.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import (
    AdminRoleUpdate,
    AdminStatusUpdate,
    UserResponse,
)

router = APIRouter(prefix="/users", tags=["user-management"])


@router.get(
    "",
    response_model=list[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="List all users (Admin only)",
)
def list_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> list[User]:
    """Admin-only endpoint to list all registered users."""
    return list(
        db.execute(
            select(User)
            .order_by(User.created_at.desc())
            .offset(skip)
            .limit(limit)
        ).scalars().all()
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get user details by ID",
)
def get_user_by_id(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    """Retrieve user details. Allowed for the user themselves or an administrator."""
    verify_resource_ownership(user_id, current_user, allow_roles=(UserRole.ADMIN,))

    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.patch(
    "/{user_id}/role",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update user role (Admin only)",
)
def update_user_role(
    user_id: uuid.UUID,
    role_update: AdminRoleUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> User:
    """Admin-only endpoint to promote/demote user roles."""
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.role = role_update.role
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch(
    "/{user_id}/status",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update user status (Admin only)",
)
def update_user_status(
    user_id: uuid.UUID,
    status_update: AdminStatusUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
) -> User:
    """Admin-only endpoint to activate/deactivate or verify accounts."""
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if status_update.is_active is not None:
        user.is_active = status_update.is_active
    if status_update.is_verified is not None:
        user.is_verified = status_update.is_verified

    db.add(user)
    db.commit()
    db.refresh(user)
    return user
