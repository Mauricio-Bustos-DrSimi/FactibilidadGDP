"""Authentication & authorization.

Password hashing (bcrypt), the logged-in-user dependency (backed by a signed
session cookie via Starlette's SessionMiddleware), a role-guard dependency
factory, and a one-time sysadmin seeder.
"""
from __future__ import annotations

import os
import secrets

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import models
from app.database import get_db

SESSION_USER_KEY = "user_id"
SESSION_USER_SNAPSHOT_KEY = "user_snapshot"
SYSADMIN_ROLE = "sysadmin"
FACTIBILITY_USER_EMAIL = "admjennifer@porunpaismejor.com.mx"


# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------- #
# Current-user dependency
# --------------------------------------------------------------------------- #
def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> models.User:
    """Resolve the logged-in user from the session cookie, or 401."""
    uid = request.session.get(SESSION_USER_KEY)
    if not uid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        user = db.get(models.User, uid)
    except SQLAlchemyError:
        snapshot = request.session.get(SESSION_USER_SNAPSHOT_KEY) or {}
        if snapshot.get("id") == uid:
            return models.User(
                id=snapshot["id"],
                email=snapshot.get("email", ""),
                name=snapshot.get("name", "Usuario"),
                password_hash="",
                role=snapshot.get("role", ""),
                commercial_division=snapshot.get("commercial_division"),
                job_title=snapshot.get("job_title"),
                supervisor_emails=snapshot.get("supervisor_emails"),
                active=True,
            )
        raise
    if user is None or not user.active:
        # Stale or disabled account — drop the session.
        request.session.pop(SESSION_USER_KEY, None)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    return user


def require_role(*roles: str):
    """Dependency factory: allow only the given roles (sysadmin always passes)."""
    allowed = set(roles) | {SYSADMIN_ROLE}

    def _dep(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Requires role: {' or '.join(sorted(roles))}",
            )
        return user

    return _dep


def require_factibility_access(
    user: models.User = Depends(get_current_user),
) -> models.User:
    """Allow Factibilidad only to sysadmins and its explicitly assigned user."""
    email = str(user.email or "").strip().lower()
    if user.role != SYSADMIN_ROLE and email != FACTIBILITY_USER_EMAIL:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Acceso denegado, su usuario no tiene permiso para realizar esta acción.",
        )
    return user


# --------------------------------------------------------------------------- #
# Seeding
# --------------------------------------------------------------------------- #
def seed_sysadmin(db: Session) -> None:
    """Ensure at least one sysadmin exists.

    Uses SYSADMIN_EMAIL / SYSADMIN_PASSWORD from the environment if set;
    otherwise creates a default account and prints a one-time random password
    so a fresh install is usable but never ships a known credential.
    """
    existing = db.scalar(
        select(models.User)
        .where(models.User.role == SYSADMIN_ROLE)
        .where(models.User.active.is_(True))
        .where(models.User.deleted_at.is_(None))
    )
    if existing is not None:
        return

    email = os.environ.get("SYSADMIN_EMAIL", "admin@local")
    password = os.environ.get("SYSADMIN_PASSWORD")
    generated = password is None
    if generated:
        password = secrets.token_urlsafe(12)

    db.add(
        models.User(
            email=email,
            name="System Administrator",
            password_hash=hash_password(password),
            role=SYSADMIN_ROLE,
        )
    )
    db.commit()

    if generated:
        print(
            "\n" + "=" * 60 + "\n"
            f"  Seeded sysadmin account: {email}\n"
            f"  Temporary password: {password}\n"
            "  Set SYSADMIN_EMAIL / SYSADMIN_PASSWORD to control this,\n"
            "  and change the password after first login.\n"
            + "=" * 60 + "\n"
        )
    else:
        print(f"Seeded sysadmin account from env: {email}")
