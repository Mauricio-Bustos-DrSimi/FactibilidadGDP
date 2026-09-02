from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.config import Settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_replication_cli_exposes_operational_commands_without_connecting():
    environment = os.environ.copy()
    environment.update({
        "DATABASE_URL": "",
        "LEGACY_DATABASE_URL": "",
        "SOURCE_DATABASE_URL": "",
        "CDC_DATABASE_URL": "",
        "LEGACY_SYNC_ENABLED": "false",
        "REPLICATION_MODE": "disabled",
    })

    result = subprocess.run(
        [sys.executable, "-m", "app.replication.cli", "--help"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    for command in (
        "preflight",
        "migrate",
        "snapshot",
        "poll",
        "apply",
        "reconcile",
        "replay",
        "documents",
    ):
        assert command in result.stdout


def test_shadow_mode_rejects_real_email_delivery_configuration(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("SHADOW_MODE", "true")
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("LEGACY_SYNC_ENABLED", "false")
    monkeypatch.setenv("REPLICATION_MODE", "disabled")

    with pytest.raises(
        RuntimeError,
        match="EMAIL_DELIVERY_ENABLED must be false while SHADOW_MODE is true",
    ):
        Settings.from_env()
