"""Workflow smoke test for jefatura/comite roles."""
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


jefatura = mkuser("jefatura")
comite = mkuser("comite")
sysadmin = mkuser("sysadmin")

proj = models.Project(name="WF Demo")
db.add(proj)
db.flush()
cands = []
for i in range(5):
    c = models.LocationCandidate(project_id=proj.project_id, lat=-33.4 - i, lng=-70.6, display_data={"n": i})
    db.add(c)
    cands.append(c)
db.flush()
db.commit()

A, B, C, D, E = cands
assert workflow.candidate_group(db, A) == "pending"
assert workflow.next_for_role(db, "jefatura").id == A.id
print("created", len(cands), "pending candidates")

try:
    workflow.submit_review(db, A, jefatura, "reject")
    raise AssertionError("reject without note should fail")
except workflow.WorkflowError:
    print("guard: reject requires comment")

workflow.submit_review(db, A, jefatura, "reject", note="sin estacionamiento")
db.commit()
assert workflow.candidate_group(db, A) == "pending"
assert A.status == "pendiente"
assert A.workflow_group == "pendiente"
assert A.last_action == "dislike"
print("jefatura disliked A as a metric")

workflow.submit_review(db, A, jefatura, "star")
db.commit()
assert workflow.candidate_group(db, A) == "suggested"
assert A.priority is True
assert workflow.next_for_role(db, "comite").id == A.id
print("jefatura highlighted A into suggested")

workflow.submit_review(db, A, comite, "accept")
db.commit()
assert workflow.candidate_group(db, A) == "approved"
assert A.status == "aprobado"
assert A.workflow_group == "aprobado"
assert A.current_stage == workflow.APPROVED_STAGE
print("comite approved A")

workflow.submit_review(db, C, jefatura, "star")
workflow.submit_review(db, C, comite, "accept")
db.commit()
try:
    workflow.submit_review(db, C, jefatura, "opening")
    raise AssertionError("opening should require project variables")
except workflow.WorkflowError:
    print("guard: proyecto requires project variables")
db.add(models.CandidateProjectVariables(
    candidate_id=C.id,
    cve_unidad="CL9999",
    unidad="LOCAL TEST",
    region="METROPOLITANA DE SANTIAGO",
    comuna="SANTIAGO",
))
db.flush()
workflow.submit_review(db, C, jefatura, "opening")
db.commit()
assert workflow.candidate_group(db, C) == "opening"
assert C.status == workflow.OPENING
assert C.current_stage == workflow.PROJECT_STAGE
try:
    workflow.submit_review(db, C, sysadmin, "reject", note="no debe cambiar")
    raise AssertionError("opening should be final")
except workflow.WorkflowError:
    print("proyecto is final")

workflow.submit_review(db, A, comite, "reject", note="cierre solicitado")
db.commit()
assert workflow.candidate_group(db, A) == "rejected"
print("comite can dar de baja from approved")

try:
    workflow.submit_review(db, B, comite, "reject")
    raise AssertionError("comite reject without note should fail")
except workflow.WorkflowError:
    print("guard: comite reject requires comment")

workflow.submit_review(db, B, jefatura, "accept")
db.commit()
assert workflow.candidate_group(db, B) == "pending"
assert B.last_action == "like"
print("jefatura liked B as a metric")

workflow.submit_review(db, B, jefatura, "star")
db.commit()
assert workflow.candidate_group(db, B) == "suggested"
assert workflow.next_for_role(db, "comite").id == B.id
print("jefatura highlighted B into suggested")

workflow.submit_review(db, B, comite, "accept")
db.commit()
assert workflow.candidate_group(db, B) == "approved"
workflow.submit_review(db, B, comite, "reject", note="renta alta")
db.commit()
assert workflow.candidate_group(db, B) == "rejected"
print("comite can dar de baja approved candidates")

first_before_skip = workflow.next_for_role(db, "jefatura")
workflow.submit_review(db, first_before_skip, jefatura, "skip")
db.commit()
first_after_skip = workflow.next_for_role(db, "jefatura")
assert first_after_skip.id != first_before_skip.id
print("skip sends pending candidate to the back")

print("\nALL WORKFLOW TESTS PASSED")
