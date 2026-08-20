"""Typed runtime configuration for the blue/green Factibilidad deployment.

Secrets are read exclusively from the process environment.  This module never
logs complete database URLs because they may contain credentials.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    legacy_database_url: str | None
    source_database_url: str | None
    cdc_database_url: str | None
    shadow_mode: bool
    legacy_sync_enabled: bool
    email_delivery_enabled: bool
    session_cookie_name: str
    replication_mode: str
    replication_poll_seconds: int
    replication_lag_alert_seconds: int
    alembic_managed_schema: bool

    @classmethod
    def from_env(cls) -> "Settings":
        replication_mode = os.getenv("REPLICATION_MODE", "polling").strip().lower()
        if replication_mode not in {"cdc", "polling", "disabled"}:
            raise RuntimeError("REPLICATION_MODE must be cdc, polling or disabled")
        settings = cls(
            database_url=os.getenv("DATABASE_URL"),
            legacy_database_url=os.getenv("LEGACY_DATABASE_URL"),
            source_database_url=os.getenv("SOURCE_DATABASE_URL"),
            cdc_database_url=os.getenv("CDC_DATABASE_URL"),
            shadow_mode=_boolean("SHADOW_MODE", True),
            legacy_sync_enabled=_boolean("LEGACY_SYNC_ENABLED", False),
            email_delivery_enabled=_boolean("EMAIL_DELIVERY_ENABLED", False),
            session_cookie_name=os.getenv(
                "SESSION_COOKIE_NAME", "factibilidad_session"
            ).strip(),
            replication_mode=replication_mode,
            replication_poll_seconds=max(
                1, int(os.getenv("REPLICATION_POLL_SECONDS", "5"))
            ),
            replication_lag_alert_seconds=max(
                1, int(os.getenv("REPLICATION_LAG_ALERT_SECONDS", "60"))
            ),
            alembic_managed_schema=_boolean("ALEMBIC_MANAGED_SCHEMA", False),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.session_cookie_name:
            raise RuntimeError("SESSION_COOKIE_NAME cannot be empty")
        if self.shadow_mode and self.email_delivery_enabled:
            raise RuntimeError(
                "EMAIL_DELIVERY_ENABLED must be false while SHADOW_MODE is true"
            )
        if self.legacy_sync_enabled and self.replication_mode != "disabled":
            if not self.legacy_database_url:
                raise RuntimeError(
                    "LEGACY_DATABASE_URL is required when legacy sync is enabled"
                )
            if self.replication_mode == "cdc" and not self.cdc_database_url:
                raise RuntimeError("CDC_DATABASE_URL is required for CDC mode")


settings = Settings.from_env()
