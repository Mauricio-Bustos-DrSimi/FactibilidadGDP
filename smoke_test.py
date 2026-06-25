"""End-to-end integration test of the authenticated, multi-layer review API."""
import os
import tempfile

os.environ["SITE_SWIPER_DB"] = os.path.join(tempfile.gettempdir(), "ss_smoke.db")
if os.path.exists(os.environ["SITE_SWIPER_DB"]):
    os.remove(os.environ["SITE_SWIPER_DB"])
os.environ["SESSION_SECRET"] = "smoke-secret"
os.environ["SYSADMIN_EMAIL"] = "admin@smoke"
os.environ["SYSADMIN_PASSWORD"] = "adminpw"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def login(client: TestClient, email: str, password: str):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


with TestClient(app) as admin:
    login(admin, "admin@smoke", "adminpw")

    # --- sysadmin creates the three reviewers ---
    for role in ("coordinator", "manager", "director"):
        r = admin.post("/users", json={
            "email": f"{role}@smoke", "name": role.title(),
            "password": f"{role}pw", "role": role,
        })
        assert r.status_code == 200, r.text
    assert len(admin.get("/users").json()) == 4  # 3 + sysadmin
    print("created 3 reviewers + sysadmin")

    # --- create project + ingest candidates (sysadmin only) ---
    pid = admin.post("/projects", json={"name": "Demo"}).json()["project_id"]
    with open("data/sample_candidates.csv", "rb") as f:
        r = admin.post(f"/projects/{pid}/ingest",
                       files={"file": ("sample_candidates.csv", f, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["candidates_created"] == 12
    print("ingested 12 candidates")

    # --- a reviewer cannot ingest (403) ---
    coord = TestClient(app)
    login(coord, "coordinator@smoke", "coordinatorpw")
    with open("data/sample_candidates.csv", "rb") as f:
        assert coord.post(f"/projects/{pid}/ingest",
                          files={"file": ("x.csv", f, "text/csv")}).status_code == 403
    print("reviewer blocked from ingest -> 403")

# Separate clients keep separate session cookies per reviewer.
coord = TestClient(app); login(coord, "coordinator@smoke", "coordinatorpw")
mgr = TestClient(app); login(mgr, "manager@smoke", "managerpw")
director = TestClient(app); login(director, "director@smoke", "directorpw")
admin = TestClient(app); login(admin, "admin@smoke", "adminpw")

# --- coordinator queue has all 12; sysadmin has none ---
q = coord.get("/queue").json()
assert q["stage"] == "coordinator" and q["remaining"] == 12, q
assert admin.get("/queue").json()["candidate"] is None
first = q["candidate"]
assert "current_stage" in first and first["status"] == "pending"
cid = first["id"]
print("coordinator queue: 12 pending, first =", cid)

# --- skip keeps it in coordinator, pushes to back ---
coord.post(f"/candidates/{cid}/review", json={"action": "skip", "note": "later"})
after = coord.get("/queue").json()
assert after["remaining"] == 12 and after["candidate"]["id"] != cid, after
print("skip: still 12 in queue, now serving", after["candidate"]["id"])

# --- coordinator stars cid -> advances to manager + priority ---
r = coord.post(f"/candidates/{cid}/review", json={"action": "star", "note": "prime corner"})
assert r.status_code == 200 and r.json()["current_stage"] == "manager"
assert r.json()["priority"] is True
assert coord.get("/queue").json()["remaining"] == 11
print("star: advanced to manager, coordinator queue now 11")

# --- coordinator cannot review a manager-stage candidate (409) ---
assert coord.post(f"/candidates/{cid}/review", json={"action": "accept"}).status_code == 409

# --- manager rejects, then reopens (resumes at manager) ---
assert mgr.get("/queue").json()["remaining"] == 1
mgr.post(f"/candidates/{cid}/review", json={"action": "reject", "note": "rent high"})
reopened = mgr.post(f"/candidates/{cid}/reopen", json={"note": "renegotiated"}).json()
assert reopened["status"] == "returned" and reopened["current_stage"] == "manager"
print("manager reject + reopen: back at manager/returned")

# --- manager accepts -> director; director sends back one step -> manager ---
mgr.post(f"/candidates/{cid}/review", json={"action": "accept"})
assert director.get("/queue").json()["remaining"] == 1
sb = director.post(f"/candidates/{cid}/send-back", json={"note": "confirm parking"}).json()
assert sb["current_stage"] == "manager" and sb["status"] == "returned"
# coordinator cannot send back (first layer) -> 409
nc = coord.get("/queue").json()["candidate"]["id"]
assert coord.post(f"/candidates/{nc}/send-back", json={}).status_code == 409
print("send-back: director -> manager; coordinator send-back blocked")

# --- manager re-accepts, director approves -> final ---
mgr.post(f"/candidates/{cid}/review", json={"action": "accept"})
fin = director.post(f"/candidates/{cid}/review", json={"action": "accept"}).json()
assert fin["current_stage"] == "done" and fin["status"] == "approved_final"
print("final: candidate approved_final / done")

# --- audit trail captured the whole journey ---
actions = [r["action"] for r in admin.get(f"/candidates/{cid}/reviews").json()]
assert actions == ["skip", "star", "reject", "reopen", "accept",
                   "send_back", "accept", "accept"], actions
# reviewer identity is attached
roles = {r["reviewer_role"] for r in admin.get(f"/candidates/{cid}/reviews").json()}
assert roles == {"coordinator", "manager", "director"}, roles
print("audit trail:", actions)

# --- export (sysadmin) reflects workflow state ---
res = admin.get(f"/projects/{pid}/results")
assert res.status_code == 200 and "text/csv" in res.headers["content-type"]
header = res.text.splitlines()[0]
assert "status" in header and "coordinator_action" in header and "director_action" in header
assert coord.get(f"/projects/{pid}/results").status_code == 403  # reviewer can't export
print("export ok; reviewer export blocked -> 403")

# --- business ingest (sysadmin) + reviewer can read ---
with open("data/sample_business_locations.csv", "rb") as f:
    rb = admin.post("/business/ingest",
                    files={"file": ("biz.csv", f, "text/csv")}, data={"replace": "true"})
assert rb.status_code == 200 and rb.json()["locations_created"] == 12
assert len(coord.get("/business").json()) == 12
print("business: 12 ingested, readable by reviewer")

print("\nALL SMOKE TESTS PASSED")
