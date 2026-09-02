from __future__ import annotations

from types import SimpleNamespace


def test_identity_service_centralizes_factibility_access_policy():
    from app.identity import IdentityService

    identity = IdentityService()
    users = (
        SimpleNamespace(role="sysadmin", email="anyone@example.test"),
        SimpleNamespace(
            role="coordinador",
            email="  ADMJENNIFER@PORUNPAISMEJOR.COM.MX  ",
        ),
        SimpleNamespace(role="coordinador", email="other@example.test"),
    )

    assert tuple(identity.can_access_factibility(user) for user in users) == (
        True,
        True,
        False,
    )
