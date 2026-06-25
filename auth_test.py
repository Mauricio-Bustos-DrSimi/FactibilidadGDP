"""Phase 2 auth test — login, session, role guard, logout."""
import os
import tempfile

os.environ["SITE_SWIPER_DB"] = os.path.join(tempfile.gettempdir(), "ss_auth.db")
if os.path.exists(os.environ["SITE_SWIPER_DB"]):
    os.remove(os.environ["SITE_SWIPER_DB"])
os.environ["SESSION_SECRET"] = "test-secret-fixed"
os.environ["SYSADMIN_EMAIL"] = "admin@test"
os.environ["SYSADMIN_PASSWORD"] = "supersecret"

from fastapi import Depends  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import auth, models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402


# A throwaway protected route to exercise the role guard.
@app.get("/_director_only")
def _director_only(user: models.User = Depends(auth.require_role("director"))):
    return {"id": user.id, "role": user.role}


# Using the client as a context manager runs the lifespan (init_db + seed).
with TestClient(app) as c:
    # Seed created the sysadmin from env.
    db = SessionLocal()
    admin = db.scalar(select(models.User).where(models.User.role == "sysadmin"))
    assert admin is not None and admin.email == "admin@test", admin
    print("seeded sysadmin:", admin.email)

    # Add a coordinator to test a non-sysadmin role.
    coord = models.User(
        email="coord@test", name="Coord",
        password_hash=auth.hash_password("coordpw"), role="coordinator",
    )
    db.add(coord)
    db.commit()
    db.close()

    # --- unauthenticated /me -> 401 ---
    assert c.get("/me").status_code == 401
    print("unauthenticated /me -> 401")

    # --- bad password -> 401 ---
    r = c.post("/auth/login", json={"email": "admin@test", "password": "wrong"})
    assert r.status_code == 401, r.text
    print("bad password -> 401")

    # --- good login -> 200 + /me works (cookie persisted by client) ---
    r = c.post("/auth/login", json={"email": "admin@test", "password": "supersecret"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "sysadmin"
    me = c.get("/me").json()
    assert me["email"] == "admin@test"
    print("sysadmin login + /me ok")

    # --- sysadmin bypasses the director-only guard ---
    assert c.get("/_director_only").status_code == 200
    print("sysadmin passes director-only guard (superuser bypass)")

    # --- logout clears the session ---
    assert c.post("/auth/logout").json()["ok"] is True
    assert c.get("/me").status_code == 401
    print("logout clears session")

    # --- coordinator is blocked from the director-only guard ---
    r = c.post("/auth/login", json={"email": "coord@test", "password": "coordpw"})
    assert r.status_code == 200
    assert c.get("/_director_only").status_code == 403
    print("coordinator blocked from director-only guard -> 403")

print("\nALL AUTH TESTS PASSED")
