"""Phase 1 workflow engine test — exercises every transition directly.

Runs against a throwaway SQLite file (no HTTP, no auth) to prove the
state machine in app/workflow.py is correct before wiring up the API.
"""
import os
import tempfile

os.environ["SITE_SWIPER_DB"] = os.path.join(tempfile.gettempdir(), "ss_workflow.db")
if os.path.exists(os.environ["SITE_SWIPER_DB"]):
    os.remove(os.environ["SITE_SWIPER_DB"])

from app import models, workflow  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402

init_db()
db = SessionLocal()


def mkuser(role: str) -> models.User:
    u = models.User(email=f"{role}@x.com", name=role.title(), password_hash="x", role=role)
    db.add(u)
    db.flush()
    return u


coord = mkuser("coordinator")
mgr = mkuser("manager")
director = mkuser("director")
sysadmin = mkuser("sysadmin")

# A project with a handful of candidates (all start at coordinator/pending).
proj = models.Project(name="WF Demo")
db.add(proj)
db.flush()
cands = []
for i in range(4):
    c = models.LocationCandidate(project_id=proj.project_id, lat=-33.4 - i, lng=-70.6, display_data={"n": i})
    db.add(c)
    cands.append(c)
db.flush()
db.commit()

A, B, C, D = cands
print("created", len(cands), "candidates at coordinator/pending")

# --- All start in the coordinator queue ---
assert db.scalars(workflow.queue_query("coordinator")).all(), "coordinator queue empty?"
first = workflow.next_for_role(db, "coordinator")
assert first.id == A.id, f"expected A first, got {first.id}"

# --- skip keeps it in this layer but pushes it to the back ---
workflow.submit_review(db, A, coord, "skip", note="come back later")
db.commit()
assert A.current_stage == "coordinator" and A.status == "pending", "skip changed state!"
after_skip = workflow.next_for_role(db, "coordinator")
assert after_skip.id != A.id, "skipped candidate should not be served first again"
print("skip: A stays coordinator/pending, queue now serves", after_skip.id, "first")

# --- star advances coordinator -> manager and flags priority ---
workflow.submit_review(db, B, coord, "star", note="great frontage")
db.commit()
assert B.current_stage == "manager" and B.status == "pending", (B.current_stage, B.status)
assert B.priority is True, "star should set priority"
print("star: B advanced to manager, priority =", B.priority)

# --- wrong-role guard: coordinator can't act on a manager-stage candidate ---
try:
    workflow.submit_review(db, B, coord, "accept")
    raise AssertionError("coordinator acting on manager stage should fail")
except workflow.WorkflowError:
    print("guard: coordinator blocked from manager-stage candidate")

# --- manager rejects B; reopen resumes at the SAME (manager) stage ---
workflow.submit_review(db, B, mgr, "reject", note="rent too high")
db.commit()
assert B.status == workflow.REJECTED, B.status
assert B.current_stage == "manager", "reject must not move the stage"
try:
    workflow.submit_review(db, B, mgr, "accept")
    raise AssertionError("reviewing a rejected candidate should fail")
except workflow.WorkflowError:
    pass
workflow.reopen(db, B, sysadmin, note="renegotiated")
db.commit()
assert B.status == workflow.RETURNED and B.current_stage == "manager", (B.status, B.current_stage)
print("reject+reopen: B back to manager/returned at the rejected stage")

# --- manager accepts B -> director ---
workflow.submit_review(db, B, mgr, "accept")
db.commit()
assert B.current_stage == "director" and B.status == "pending"

# --- director sends back ONE step -> manager ---
workflow.send_back(db, B, director, note="confirm parking")
db.commit()
assert B.current_stage == "manager" and B.status == workflow.RETURNED
print("send-back: director bounced B one step to manager")

# --- coordinator cannot send back (first layer) ---
workflow.submit_review(db, C, coord, "accept")  # C -> manager
db.commit()
try:
    # put C at coordinator artificially? Instead test on a coordinator-stage one: D
    workflow.send_back(db, D, coord)
    raise AssertionError("coordinator send_back should fail")
except workflow.WorkflowError:
    print("guard: coordinator cannot send back from first layer")

# --- full happy path to final approval ---
workflow.submit_review(db, B, mgr, "accept")   # manager -> director
db.commit()
workflow.submit_review(db, B, director, "accept")  # director -> done
db.commit()
assert B.current_stage == workflow.DONE and B.status == workflow.APPROVED_FINAL, (B.current_stage, B.status)
try:
    workflow.submit_review(db, B, director, "accept")
    raise AssertionError("acting on an approved_final candidate should fail")
except workflow.WorkflowError:
    pass
print("final: B approved_final / done")

# --- audit log captured the whole journey for B ---
from sqlalchemy import select as _select  # noqa: E402

b_reviews = db.scalars(
    _select(models.Review)
    .where(models.Review.candidate_id == B.id)
    .order_by(models.Review.id)
).all()
actions = [r.action for r in b_reviews]
assert actions == ["star", "reject", "reopen", "accept", "send_back", "accept", "accept"], actions
print("audit log for B:", actions)

# --- current_decision helper returns the latest gating decision at a stage ---
dec = workflow.current_decision(db, B.id, "manager")
assert dec is not None and dec.action == "accept"
print("current_decision(manager) =", dec.action)

print("\nALL WORKFLOW TESTS PASSED")
