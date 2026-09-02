"""Compatibility facade for the extracted identity module."""
from app.identity import (
    FACTIBILITY_ACCESS_DENIED,
    FACTIBILITY_USER_EMAIL,
    IdentityService,
    SESSION_USER_KEY,
    SESSION_USER_SNAPSHOT_KEY,
    SYSADMIN_ROLE,
    create_identity_router,
    get_current_user,
    hash_password,
    identity_service,
    require_factibility_access,
    require_role,
    seed_sysadmin,
    verify_password,
)

__all__ = [
    "FACTIBILITY_ACCESS_DENIED",
    "FACTIBILITY_USER_EMAIL",
    "IdentityService",
    "SESSION_USER_KEY",
    "SESSION_USER_SNAPSHOT_KEY",
    "SYSADMIN_ROLE",
    "create_identity_router",
    "get_current_user",
    "hash_password",
    "identity_service",
    "require_factibility_access",
    "require_role",
    "seed_sysadmin",
    "verify_password",
]
