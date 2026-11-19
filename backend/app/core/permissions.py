from __future__ import annotations

from enum import Enum

from app.models.enums import UserRole


class Permission(str, Enum):
    # User permissions
    PROFILE_MANAGE_OWN = "profile:manage_own"
    DOCUMENTS_UPLOAD_OWN = "documents:upload_own"
    DOCUMENTS_ACCESS_OWN = "documents:access_own"
    VERIFICATION_VIEW_OWN = "verification:view_own"

    # Reviewer permissions
    REVIEWS_ACCESS_ASSIGNED = "reviews:access_assigned"
    CLAIMS_REVIEW = "claims:review"
    REVIEWS_ADD_COMMENTS = "reviews:add_comments"
    VERDICTS_SUBMIT_HUMAN = "verdicts:submit_human"

    # Admin permissions
    USERS_MANAGE = "users:manage"
    ROLES_MANAGE = "roles:manage"
    ANALYTICS_VIEW_ADMIN = "analytics:view_admin"
    SETTINGS_MANAGE_SYSTEM = "settings:manage_system"


ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
    UserRole.USER: {
        Permission.PROFILE_MANAGE_OWN,
        Permission.DOCUMENTS_UPLOAD_OWN,
        Permission.DOCUMENTS_ACCESS_OWN,
        Permission.VERIFICATION_VIEW_OWN,
    },
    UserRole.REVIEWER: {
        # Inherits user capabilities
        Permission.PROFILE_MANAGE_OWN,
        Permission.DOCUMENTS_UPLOAD_OWN,
        Permission.DOCUMENTS_ACCESS_OWN,
        Permission.VERIFICATION_VIEW_OWN,
        # Reviewer capabilities
        Permission.REVIEWS_ACCESS_ASSIGNED,
        Permission.CLAIMS_REVIEW,
        Permission.REVIEWS_ADD_COMMENTS,
        Permission.VERDICTS_SUBMIT_HUMAN,
    },
    UserRole.ADMIN: {
        # Admin has all permissions
        Permission.PROFILE_MANAGE_OWN,
        Permission.DOCUMENTS_UPLOAD_OWN,
        Permission.DOCUMENTS_ACCESS_OWN,
        Permission.VERIFICATION_VIEW_OWN,
        Permission.REVIEWS_ACCESS_ASSIGNED,
        Permission.CLAIMS_REVIEW,
        Permission.REVIEWS_ADD_COMMENTS,
        Permission.VERDICTS_SUBMIT_HUMAN,
        Permission.USERS_MANAGE,
        Permission.ROLES_MANAGE,
        Permission.ANALYTICS_VIEW_ADMIN,
        Permission.SETTINGS_MANAGE_SYSTEM,
    },
}


def role_has_permission(role: UserRole, permission: Permission) -> bool:
    """Check if a given role grants a specific permission."""
    return permission in ROLE_PERMISSIONS.get(role, set())
