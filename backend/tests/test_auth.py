from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Iterator
import uuid

import httpx
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.core.security import (
    create_access_token,
    hash_password,
    rate_limiter,
)
from app.database.base import Base
from app.database.session import get_db
from app.main import create_app
from app.models.enums import UserRole
from app.models.refresh_token import RefreshToken
from app.models.user import User


@pytest.fixture(autouse=True)
def setup_test_settings(monkeypatch):
    """Ensure consistent JWT secret and clean settings cache for all tests."""
    monkeypatch.setenv(
        "ANVEXA_JWT_SECRET_KEY",
        "test-secret-key-for-testing-purposes-only-32bytes!",
    )
    get_settings.cache_clear()
    rate_limiter.reset_all()
    yield
    get_settings.cache_clear()
    rate_limiter.reset_all()


@pytest.fixture
def auth_db_session() -> Iterator[Session]:
    """Provide an isolated in-memory SQLite database for authentication testing."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name != "embeddings"
    ]
    Base.metadata.create_all(engine, tables=tables)

    with Session(engine) as session:
        yield session

    engine.dispose()


def client_request(
    app,
    method: str,
    path: str,
    json: dict | None = None,
    headers: dict | None = None,
) -> httpx.Response:
    """Synchronous helper using httpx ASGITransport."""
    async def run_req() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(
                method, path, json=json, headers=headers
            )

    return asyncio.run(run_req())


@pytest.fixture
def test_client(auth_db_session: Session):
    """Create a FastAPI test client with an overridden database session."""
    application = create_app()

    def override_get_db():
        yield auth_db_session

    application.dependency_overrides[get_db] = override_get_db

    class ClientWrapper:
        def post(self, path: str, json=None, headers=None):
            return client_request(application, "POST", path, json, headers)

        def get(self, path: str, headers=None):
            return client_request(application, "GET", path, None, headers)

        def put(self, path: str, json=None, headers=None):
            return client_request(application, "PUT", path, json, headers)

        def patch(self, path: str, json=None, headers=None):
            return client_request(application, "PATCH", path, json, headers)

    return ClientWrapper()


# ---------------------------------------------------------------------------
# Registration Tests
# ---------------------------------------------------------------------------


def test_successful_registration(test_client, auth_db_session: Session) -> None:
    response = test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "researcher@university.edu",
            "full_name": "Dr. Marie Curie",
            "password": "Password123!",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "researcher@university.edu"
    assert data["full_name"] == "Dr. Marie Curie"
    assert data["role"] == "user"
    assert data["is_active"] is True
    assert data["is_verified"] is False
    assert "id" in data
    assert "hashed_password" not in data
    assert "password" not in data

    # Verify database persistence
    user = auth_db_session.query(User).filter_by(email="researcher@university.edu").first()
    assert user is not None
    assert user.hashed_password.startswith("$argon2id$")


def test_duplicate_email_registration(test_client) -> None:
    test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "duplicate@test.org",
            "full_name": "Original User",
            "password": "Password123!",
        },
    )

    # Duplicate registration with identical casing
    res2 = test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "duplicate@test.org",
            "full_name": "Another User",
            "password": "Password123!",
        },
    )
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"]

    # Duplicate registration with uppercase email (case-insensitive check)
    res3 = test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "DUPLICATE@TEST.ORG",
            "full_name": "Uppercase User",
            "password": "Password123!",
        },
    )
    assert res3.status_code == 409


def test_invalid_email(test_client) -> None:
    for invalid_email in ["not-an-email", "user@", "@domain.com", "plainaddress"]:
        response = test_client.post(
            "/api/v1/auth/register",
            json={
                "email": invalid_email,
                "full_name": "Test User",
                "password": "Password123!",
            },
        )
        assert response.status_code == 422


def test_weak_password_rejection(test_client) -> None:
    weak_passwords = [
        "short",             # < 8 chars
        "alllowercase1!",    # missing uppercase
        "ALLUPPERCASE1!",    # missing lowercase
        "NoDigitsHere!",     # missing digit
        "NoSpecialChars1",   # missing special char
    ]
    for pw in weak_passwords:
        response = test_client.post(
            "/api/v1/auth/register",
            json={
                "email": f"test_{uuid.uuid4().hex[:6]}@example.com",
                "full_name": "Weak Password User",
                "password": pw,
            },
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Login and Token Tests
# ---------------------------------------------------------------------------


def test_successful_login(test_client) -> None:
    test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "loginuser@test.org",
            "full_name": "Login User",
            "password": "CorrectPassword1!",
        },
    )

    response = test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "loginuser@test.org",
            "password": "CorrectPassword1!",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


def test_incorrect_password(test_client) -> None:
    test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "loginuser2@test.org",
            "full_name": "Login User",
            "password": "CorrectPassword1!",
        },
    )

    response = test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "loginuser2@test.org",
            "password": "WrongPassword999!",
        },
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


def test_login_nonexistent_user(test_client) -> None:
    response = test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "nobody@nowhere.com",
            "password": "Password123!",
        },
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


# ---------------------------------------------------------------------------
# JWT Validation Tests
# ---------------------------------------------------------------------------


def test_invalid_jwt(test_client) -> None:
    response = test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not.a.valid.jwt.token"},
    )
    assert response.status_code == 401


def test_expired_jwt(test_client, auth_db_session: Session) -> None:
    user = User(
        email="expired@test.org",
        full_name="Expired User",
        hashed_password=hash_password("Password123!"),
        role=UserRole.USER,
        is_active=True,
    )
    auth_db_session.add(user)
    auth_db_session.commit()

    expired_token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role.value,
        expires_delta=timedelta(seconds=-10),
    )

    response = test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert "Token has expired" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Refresh Token Rotation and Revocation
# ---------------------------------------------------------------------------


def test_refresh_token_rotation(test_client) -> None:
    test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "refresh@test.org",
            "full_name": "Refresh User",
            "password": "Password123!",
        },
    )
    login_res = test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "refresh@test.org",
            "password": "Password123!",
        },
    )
    first_refresh = login_res.json()["refresh_token"]

    # Rotate refresh token
    rotate_res = test_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first_refresh},
    )
    assert rotate_res.status_code == 200
    new_data = rotate_res.json()
    second_refresh = new_data["refresh_token"]
    assert second_refresh != first_refresh
    assert "access_token" in new_data

    # Old refresh token is now revoked; attempting to use it fails
    reuse_res = test_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first_refresh},
    )
    assert reuse_res.status_code == 401
    assert "revoked" in reuse_res.json()["detail"].lower()


def test_logout(test_client) -> None:
    test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "logout@test.org",
            "full_name": "Logout User",
            "password": "Password123!",
        },
    )
    login_res = test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "logout@test.org",
            "password": "Password123!",
        },
    )
    refresh_token = login_res.json()["refresh_token"]

    # Logout
    logout_res = test_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout_res.status_code == 200
    assert "logged out" in logout_res.json()["message"].lower()

    # Re-using the logged-out refresh token fails
    refresh_res = test_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_res.status_code == 401


# ---------------------------------------------------------------------------
# Current User and Profile Tests
# ---------------------------------------------------------------------------


def test_current_user_profile(test_client) -> None:
    test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "profile@test.org",
            "full_name": "Profile User",
            "password": "Password123!",
        },
    )
    login_res = test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "profile@test.org",
            "password": "Password123!",
        },
    )
    token = login_res.json()["access_token"]

    response = test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "profile@test.org"
    assert response.json()["full_name"] == "Profile User"


def test_update_profile(test_client) -> None:
    test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "update@test.org",
            "full_name": "Before Update",
            "password": "Password123!",
        },
    )
    login_res = test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "update@test.org",
            "password": "Password123!",
        },
    )
    token = login_res.json()["access_token"]

    update_res = test_client.put(
        "/api/v1/auth/me",
        json={"full_name": "After Update"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["full_name"] == "After Update"


def test_change_password(test_client) -> None:
    test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "changepw@test.org",
            "full_name": "Change PW User",
            "password": "OldPassword1!",
        },
    )
    login_res = test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "changepw@test.org",
            "password": "OldPassword1!",
        },
    )
    token = login_res.json()["access_token"]
    old_refresh = login_res.json()["refresh_token"]

    # Change password
    change_res = test_client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "OldPassword1!",
            "new_password": "NewPassword2@",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert change_res.status_code == 200

    # Old password no longer works
    fail_login = test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "changepw@test.org",
            "password": "OldPassword1!",
        },
    )
    assert fail_login.status_code == 401

    # New password works
    success_login = test_client.post(
        "/api/v1/auth/login",
        json={
            "email": "changepw@test.org",
            "password": "NewPassword2@",
        },
    )
    assert success_login.status_code == 200

    # Old refresh token was revoked by password change
    refresh_attempt = test_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert refresh_attempt.status_code == 401


# ---------------------------------------------------------------------------
# Authorization and Security Controls
# ---------------------------------------------------------------------------


def test_unauthorized_access(test_client) -> None:
    response = test_client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_role_permissions_and_admin_endpoints(test_client, auth_db_session: Session) -> None:
    # Create regular user
    user = User(
        email="standard@test.org",
        full_name="Standard User",
        hashed_password=hash_password("Password123!"),
        role=UserRole.USER,
        is_active=True,
    )
    # Create admin user
    admin = User(
        email="admin@test.org",
        full_name="Admin User",
        hashed_password=hash_password("Password123!"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    auth_db_session.add_all([user, admin])
    auth_db_session.commit()

    user_token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role.value,
    )
    admin_token = create_access_token(
        user_id=admin.id,
        email=admin.email,
        role=admin.role.value,
    )

    # Standard user cannot list users (Admin only)
    res_forbidden = test_client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert res_forbidden.status_code == 403

    # Admin user can list users
    res_allowed = test_client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_allowed.status_code == 200
    assert len(res_allowed.json()) >= 2

    # Admin can promote user to reviewer
    res_promote = test_client.patch(
        f"/api/v1/users/{user.id}/role",
        json={"role": "reviewer"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_promote.status_code == 200
    assert res_promote.json()["role"] == "reviewer"


def test_cross_user_access_protection(test_client, auth_db_session: Session) -> None:
    user1 = User(
        email="user1@test.org",
        full_name="User One",
        hashed_password=hash_password("Password123!"),
        role=UserRole.USER,
        is_active=True,
    )
    user2 = User(
        email="user2@test.org",
        full_name="User Two",
        hashed_password=hash_password("Password123!"),
        role=UserRole.USER,
        is_active=True,
    )
    auth_db_session.add_all([user1, user2])
    auth_db_session.commit()

    user1_token = create_access_token(
        user_id=user1.id,
        email=user1.email,
        role=user1.role.value,
    )

    # User 1 can view own record
    res_own = test_client.get(
        f"/api/v1/users/{user1.id}",
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert res_own.status_code == 200

    # User 1 CANNOT view User 2's record (IDOR protection)
    res_cross = test_client.get(
        f"/api/v1/users/{user2.id}",
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert res_cross.status_code == 403


def test_inactive_account(test_client, auth_db_session: Session) -> None:
    user = User(
        email="inactive@test.org",
        full_name="Inactive User",
        hashed_password=hash_password("Password123!"),
        role=UserRole.USER,
        is_active=False,
    )
    auth_db_session.add(user)
    auth_db_session.commit()

    # Login fails for inactive account
    res_login = test_client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@test.org", "password": "Password123!"},
    )
    assert res_login.status_code == 403
    assert "inactive" in res_login.json()["detail"].lower()

    # Even with a pre-existing token, access is forbidden
    token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role.value,
    )
    res_me = test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_me.status_code == 403


def test_login_rate_limiting(test_client) -> None:
    test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "brute@test.org",
            "full_name": "Brute Force Target",
            "password": "Password123!",
        },
    )

    # 5 failed attempts
    for _ in range(5):
        res = test_client.post(
            "/api/v1/auth/login",
            json={"email": "brute@test.org", "password": "WrongPassword!"},
        )
        assert res.status_code == 401

    # 6th attempt should be blocked by rate limiter with 429
    blocked = test_client.post(
        "/api/v1/auth/login",
        json={"email": "brute@test.org", "password": "Password123!"},
    )
    assert blocked.status_code == 429
    assert "too many" in blocked.json()["detail"].lower()
