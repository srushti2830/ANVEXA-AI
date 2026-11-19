from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user
from backend.app.database.session import get_db
from backend.app.models.user import User
from backend.app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)
from backend.app.schemas.user import UserResponse, UserUpdate
from backend.app.services.auth_service import (
    authenticate_user,
    change_user_password,
    create_user_tokens,
    register_user,
    revoke_refresh_token,
    rotate_refresh_token,
    update_user_profile,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user account",
)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
) -> User:
    """Create a new standard user account.

    Public registration always assigns the base USER role.
    """
    return register_user(db=db, request=request)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and obtain tokens",
)
def login(
    request: LoginRequest,
    http_request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate with email and password to receive JWT access and refresh tokens."""
    client_ip = http_request.client.host if http_request.client else None
    user = authenticate_user(db=db, request=request, client_ip=client_ip)
    return create_user_tokens(db=db, user=user)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate refresh token and get new token pair",
)
def refresh(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Exchange a valid refresh token for a new access token and rotated refresh token."""
    return rotate_refresh_token(db=db, raw_refresh_token=request.refresh_token)


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Invalidate refresh token and end session",
)
def logout(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Revoke a refresh token on logout."""
    revoke_refresh_token(db=db, raw_refresh_token=request.refresh_token)
    return MessageResponse(message="Successfully logged out.")


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
)
def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    """Return the profile information for the authenticated user."""
    return current_user


@router.put(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update current user profile",
)
def update_me(
    update_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Update profile fields (full name, email) for the authenticated user."""
    return update_user_profile(db=db, user=current_user, update_data=update_data)


@router.post(
    "/change-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Change user password",
)
def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Change password and invalidate all active sessions."""
    change_user_password(db=db, user=current_user, request=request)
    return MessageResponse(message="Password changed successfully.")
