"""Typed runtime configuration for the blue/green Factibilidad deployment.

Secrets are read exclusively from the process environment.  This module never
logs complete database URLs because they may contain credentials.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)


DEFAULT_APPROVAL_NOTIFICATION_TO = (
    "dcastro@farmaciasdoctorsimi.cl",
    "mcasanova@porunpaismejor.com.mx",
    "admjennifer@porunpaismejor.com.mx",
    "lalbornoz@farmaciasdoctorsimi.cl",
)
DEFAULT_APPROVAL_NOTIFICATION_CC = (
    "mbustos@farmaciasdoctorsimi.cl",
    "rmalave@farmaciasdoctorsimi.cl",
)


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _addresses(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name, ";".join(default))
    return tuple(
        address.strip()
        for address in raw.replace(",", ";").split(";")
        if address.strip()
    )


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    legacy_database_url: str | None
    source_database_url: str | None
    cdc_database_url: str | None
    shadow_mode: bool
    gestor_test_mode: bool
    legacy_sync_enabled: bool
    email_delivery_enabled: bool
    session_cookie_name: str
    replication_mode: str
    replication_poll_seconds: int
    replication_lag_alert_seconds: int
    alembic_managed_schema: bool
    projection_documents_dir: Path
    projection_attachment_max_bytes: int
    projection_attachment_max_files: int
    postgres_sync_interval_seconds: int
    postgres_candidate_sync_interval_seconds: int
    postgres_auto_sync: bool
    postgres_sync_project_name: str
    approval_notification_from: str
    approval_notification_to: tuple[str, ...]
    approval_notification_cc: tuple[str, ...]
    approval_notification_base_url: str
    session_secret: str | None
    google_maps_api_key: str
    sysadmin_email: str
    sysadmin_password: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        replication_mode = os.getenv("REPLICATION_MODE", "polling").strip().lower()
        if replication_mode not in {"cdc", "polling", "disabled"}:
            raise RuntimeError("REPLICATION_MODE must be cdc, polling or disabled")
        shadow_mode = _boolean("SHADOW_MODE", True)
        attachment_max_bytes = os.getenv(
            "PROJECTION_ATTACHMENT_MAX_BYTES",
            os.getenv("PROJECTION_IMAGE_MAX_BYTES", str(15 * 1024 * 1024)),
        )
        attachment_max_files = os.getenv(
            "PROJECTION_ATTACHMENT_MAX_FILES",
            os.getenv("PROJECTION_IMAGE_MAX_FILES", "12"),
        )
        settings = cls(
            database_url=os.getenv("DATABASE_URL"),
            legacy_database_url=os.getenv("LEGACY_DATABASE_URL"),
            source_database_url=os.getenv("SOURCE_DATABASE_URL"),
            cdc_database_url=os.getenv("CDC_DATABASE_URL"),
            shadow_mode=shadow_mode,
            gestor_test_mode=_boolean("GESTOR_TEST_MODE", False),
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
            projection_documents_dir=Path(
                os.getenv(
                    "PROJECTION_DOCUMENTS_DIR",
                    str(PROJECT_ROOT / "DocumentosProyeccion"),
                )
            ).expanduser().resolve(),
            projection_attachment_max_bytes=int(attachment_max_bytes),
            projection_attachment_max_files=int(attachment_max_files),
            postgres_sync_interval_seconds=int(
                os.getenv("POSTGRES_SYNC_INTERVAL_SECONDS", "1800")
            ),
            postgres_candidate_sync_interval_seconds=max(
                2,
                int(os.getenv("POSTGRES_CANDIDATE_SYNC_INTERVAL_SECONDS", "10")),
            ),
            postgres_auto_sync=(
                _boolean("POSTGRES_AUTO_SYNC", False) and not shadow_mode
            ),
            postgres_sync_project_name=os.getenv(
                "POSTGRES_SYNC_PROJECT_NAME", "Postgres Sync"
            ),
            approval_notification_from=os.getenv(
                "APPROVAL_NOTIFICATION_FROM",
                "mbustos@farmaciasdoctorsimi.cl",
            ),
            approval_notification_to=_addresses(
                "APPROVAL_NOTIFICATION_TO", DEFAULT_APPROVAL_NOTIFICATION_TO
            ),
            approval_notification_cc=_addresses(
                "APPROVAL_NOTIFICATION_CC", DEFAULT_APPROVAL_NOTIFICATION_CC
            ),
            approval_notification_base_url=os.getenv(
                "APPROVAL_NOTIFICATION_BASE_URL",
                "http://172.23.1.128:8002",
            ).rstrip("/"),
            session_secret=os.getenv("SESSION_SECRET"),
            google_maps_api_key=os.getenv("GOOGLE_MAPS_API_KEY", ""),
            sysadmin_email=os.getenv("SYSADMIN_EMAIL", "admin@local"),
            sysadmin_password=os.getenv("SYSADMIN_PASSWORD"),
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

    def session_secret_or_ephemeral(self) -> tuple[str, bool]:
        """Return the configured session secret or one process-local fallback."""
        if self.session_secret:
            return self.session_secret, False
        return secrets.token_urlsafe(32), True


settings = Settings.from_env()
