"""End-to-end smoke test of the API using FastAPI's TestClient (in-memory DB)."""
import os
import tempfile

os.environ["SITE_SWIPER_DB"] = os.path.join(tempfile.gettempdir(), "ss_smoke.db")
# fresh db
if os.path.exists(os.environ["SITE_SWIPER_DB"]):
    os.remove(os.environ["SITE_SWIPER_DB"])

from fastapi.testclient import TestClient  # noqa: E402
from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
c = TestClient(app)

# 1. create project
p = c.post("/projects", json={"name": "Demo", "project_url": "http://x"}).json()
pid = p["project_id"]
assert pid and p["name"] == "Demo", p
print("created project", pid)

# 2. ingest candidates
with open("data/sample_candidates.csv", "rb") as f:
    r = c.post(f"/projects/{pid}/ingest", files={"file": ("sample_candidates.csv", f, "text/csv")})
assert r.status_code == 200, r.text
ing = r.json()
print("ingest:", ing)
assert ing["candidates_created"] == 12
assert ing["map_column"] == "maps"
assert ing["parsed_coordinates"] == 12, ing

# 3. next
nx = c.get(f"/projects/{pid}/next").json()
assert nx["total"] == 12 and nx["decided"] == 0 and nx["remaining"] == 12
first_id = nx["candidate"]["id"]
assert nx["candidate"]["lat"] is not None
print("next candidate:", first_id, nx["candidate"]["display_data"].get("name"))

# 4. decisions (accept, then re-decide same -> upsert/idempotent)
d = c.post(f"/projects/{pid}/decisions", json={"candidate_id": first_id, "verdict": "accept"})
assert d.status_code == 200, d.text
d2 = c.post(f"/projects/{pid}/decisions", json={"candidate_id": first_id, "verdict": "star"})
assert d2.json()["id"] == d.json()["id"], "decision should upsert, not duplicate"
print("decision upsert ok, verdict now:", d2.json()["verdict"])

# advance differs
nx2 = c.get(f"/projects/{pid}/next").json()
assert nx2["decided"] == 1 and nx2["remaining"] == 11
assert nx2["candidate"]["id"] != first_id
print("advanced to", nx2["candidate"]["id"])

# decide the rest with a mix
ids = [first_id]
while True:
    n = c.get(f"/projects/{pid}/next").json()
    if not n["candidate"]:
        break
    cid = n["candidate"]["id"]
    verdict = ["accept", "reject", "star"][cid % 3]
    c.post(f"/projects/{pid}/decisions", json={"candidate_id": cid, "verdict": verdict})
    ids.append(cid)
fin = c.get(f"/projects/{pid}/next").json()
assert fin["remaining"] == 0 and fin["candidate"] is None
print("all decided:", fin)

# 5. business ingest + list
with open("data/sample_business_locations.csv", "rb") as f:
    rb = c.post("/business/ingest", files={"file": ("biz.csv", f, "text/csv")}, data={"replace": "true"})
assert rb.status_code == 200, rb.text
print("business ingest:", rb.json())
assert rb.json()["locations_created"] == 12
biz = c.get("/business").json()
assert len(biz) == 12 and biz[0]["lat"]
print("business list ok:", len(biz), "->", biz[0]["name"], biz[0]["attributes"])

# 6. results export CSV
res = c.get(f"/projects/{pid}/results")
assert res.status_code == 200 and "text/csv" in res.headers["content-type"]
lines = res.text.strip().splitlines()
assert lines[0].startswith("candidate_id,verdict,lat,lng,map_ref,note,decided_at")
assert len(lines) == 13  # header + 12
print("export header:", lines[0])
print("export rows:", len(lines) - 1)

# 7. config endpoint
cfg = c.get("/config").json()
assert "google_maps_api_key" in cfg
print("config ok (key present:", bool(cfg["google_maps_api_key"]), ")")

print("\nALL SMOKE TESTS PASSED")
