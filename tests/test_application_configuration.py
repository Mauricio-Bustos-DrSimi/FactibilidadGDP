from __future__ import annotations

from pathlib import Path

from app.config import Settings


def test_settings_from_env_exposes_application_identity_and_shell_configuration(
    monkeypatch,
    tmp_path: Path,
):
    documents_dir = tmp_path / "projection-documents"
    environment = {
        "PROJECTION_DOCUMENTS_DIR": str(documents_dir),
        "PROJECTION_ATTACHMENT_MAX_BYTES": "2048",
        "PROJECTION_ATTACHMENT_MAX_FILES": "7",
        "POSTGRES_SYNC_INTERVAL_SECONDS": "90",
        "POSTGRES_CANDIDATE_SYNC_INTERVAL_SECONDS": "3",
        "POSTGRES_AUTO_SYNC": "true",
        "POSTGRES_SYNC_PROJECT_NAME": "Mirror test",
        "APPROVAL_NOTIFICATION_FROM": "sender@example.test",
        "APPROVAL_NOTIFICATION_TO": "one@example.test;two@example.test",
        "APPROVAL_NOTIFICATION_CC": "copy@example.test",
        "APPROVAL_NOTIFICATION_BASE_URL": "https://example.test/base/",
        "SESSION_SECRET": "stable-session-secret",
        "GOOGLE_MAPS_API_KEY": "maps-key",
        "SYSADMIN_EMAIL": "sysadmin@example.test",
        "SYSADMIN_PASSWORD": "sysadmin-password",
        "SHADOW_MODE": "false",
        "EMAIL_DELIVERY_ENABLED": "false",
        "LEGACY_SYNC_ENABLED": "false",
        "REPLICATION_MODE": "disabled",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    settings = Settings.from_env()

    assert {
        "documents_dir": settings.projection_documents_dir,
        "attachment_bytes": settings.projection_attachment_max_bytes,
        "attachment_files": settings.projection_attachment_max_files,
        "sync_interval": settings.postgres_sync_interval_seconds,
        "candidate_sync_interval": settings.postgres_candidate_sync_interval_seconds,
        "auto_sync": settings.postgres_auto_sync,
        "sync_project": settings.postgres_sync_project_name,
        "notification_from": settings.approval_notification_from,
        "notification_to": settings.approval_notification_to,
        "notification_cc": settings.approval_notification_cc,
        "notification_url": settings.approval_notification_base_url,
        "session_secret": settings.session_secret,
        "maps_key": settings.google_maps_api_key,
        "sysadmin_email": settings.sysadmin_email,
        "sysadmin_password": settings.sysadmin_password,
    } == {
        "documents_dir": documents_dir.resolve(),
        "attachment_bytes": 2048,
        "attachment_files": 7,
        "sync_interval": 90,
        "candidate_sync_interval": 3,
        "auto_sync": True,
        "sync_project": "Mirror test",
        "notification_from": "sender@example.test",
        "notification_to": ("one@example.test", "two@example.test"),
        "notification_cc": ("copy@example.test",),
        "notification_url": "https://example.test/base",
        "session_secret": "stable-session-secret",
        "maps_key": "maps-key",
        "sysadmin_email": "sysadmin@example.test",
        "sysadmin_password": "sysadmin-password",
    }
