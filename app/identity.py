"""Identity, signed-session and authorization boundary for the application."""
from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import Settings, settings
from app.database import get_db


SESSION_USER_KEY = "user_id"
SESSION_USER_SNAPSHOT_KEY = "user_snapshot"
SYSADMIN_ROLE = "sysadmin"
FACTIBILITY_USER_EMAIL = "admjennifer@porunpaismejor.com.mx"
FACTIBILITY_ACCESS_DENIED = (
    "Acceso denegado, su usuario no tiene permiso para realizar esta acción."
)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


class IdentityService:
    """Own authentication, session snapshots and module-access policy."""

    def authenticate(
        self,
        db: Session,
        email: str,
        password: str,
    ) -> models.User | None:
        user = db.scalar(select(models.User).where(models.User.email == email))
        if user is None or not user.active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    def begin_session(
        self,
        request: Request,
        user: models.User,
        *,
        started_at: datetime | None = None,
    ) -> None:
        request.session[SESSION_USER_KEY] = user.id
        request.session[SESSION_USER_SNAPSHOT_KEY] = {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "commercial_division": user.commercial_division,
            "job_title": user.job_title,
            "supervisor_emails": user.supervisor_emails,
        }
        request.session["review_session_started_at"] = (
            started_at or datetime.now(timezone.utc)
        ).isoformat()

    def end_session(self, request: Request) -> None:
        request.session.pop(SESSION_USER_KEY, None)

    def current_user(self, request: Request, db: Session) -> models.User:
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
            request.session.pop(SESSION_USER_KEY, None)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
        return user

    def can_access_factibility(self, user: models.User) -> bool:
        email = str(user.email or "").strip().lower()
        return user.role == SYSADMIN_ROLE or email == FACTIBILITY_USER_EMAIL


identity_service = IdentityService()


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> models.User:
    return identity_service.current_user(request, db)


def require_role(*roles: str):
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
    if not identity_service.can_access_factibility(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, FACTIBILITY_ACCESS_DENIED)
    return user


def seed_sysadmin(
    db: Session,
    runtime_settings: Settings | None = None,
) -> None:
    """Ensure one active sysadmin exists without embedding a known password."""
    existing = db.scalar(
        select(models.User)
        .where(models.User.role == SYSADMIN_ROLE)
        .where(models.User.active.is_(True))
        .where(models.User.deleted_at.is_(None))
    )
    if existing is not None:
        return

    configured = runtime_settings or settings
    email = configured.sysadmin_email
    password = configured.sysadmin_password
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


LoginSideEffect = Callable[[BackgroundTasks], None]


def create_identity_router(
    login_side_effect: LoginSideEffect | None = None,
    service: IdentityService = identity_service,
) -> APIRouter:
    """Create the existing identity HTTP surface with injectable side effects."""
    router = APIRouter()

    @router.post("/auth/login", response_model=schemas.UserOut)
    def login(
        payload: schemas.LoginRequest,
        request: Request,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
    ):
        user = service.authenticate(db, payload.email, payload.password)
        if user is None:
            raise HTTPException(401, "Invalid email or password")
        service.begin_session(request, user)
        if login_side_effect is not None:
            login_side_effect(background_tasks)
        return user

    @router.post("/auth/logout")
    def logout(request: Request):
        service.end_session(request)
        return {"ok": True}

    @router.get("/me", response_model=schemas.UserOut)
    def me(user: models.User = Depends(get_current_user)):
        return user

    return router


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
