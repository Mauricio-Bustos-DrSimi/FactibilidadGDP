"""Independent connection pools for target, legacy, upstream and CDC."""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def _engine(url: str | None, name: str) -> Engine:
    if not url:
        raise RuntimeError(f"{name} is not configured")
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": 10},
        future=True,
    )


@lru_cache
def target_engine() -> Engine:
    return _engine(settings.database_url, "DATABASE_URL")


@lru_cache
def legacy_engine() -> Engine:
    return _engine(settings.legacy_database_url, "LEGACY_DATABASE_URL")


@lru_cache
def source_engine() -> Engine:
    return _engine(settings.source_database_url, "SOURCE_DATABASE_URL")


@lru_cache
def cdc_engine() -> Engine:
    return _engine(settings.cdc_database_url, "CDC_DATABASE_URL")


def target_session() -> Session:
    return sessionmaker(target_engine(), expire_on_commit=False, future=True)()
