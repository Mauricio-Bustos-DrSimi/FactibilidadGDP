"""Workflow smoke test for jefatura/comite/gerente roles."""
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
gerente = mkuser("gerente")
sysadmin = mkuser("sysadmin")

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
assert workflow.candidate_group(db, A) == "rejected"
assert A.status == "rechazado"
assert A.workflow_group == "rechazado"
assert workflow.next_for_role(db, "comite").id == A.id
print("jefatura disliked A")

workflow.submit_review(db, A, comite, "accept")
db.commit()
assert workflow.candidate_group(db, A) == "approved"
assert A.status == "aprobado"
assert A.workflow_group == "aprobado"
print("comite moved rejected A to approved")

workflow.submit_review(db, A, gerente, "accept")
db.commit()
assert workflow.candidate_group(db, A) == "project"
assert A.status == workflow.PROJECT
print("gerente promoted A to locales proyecto")

workflow.submit_review(db, A, gerente, "reject", note="cierre solicitado")
db.commit()
assert workflow.candidate_group(db, A) == "rejected"
print("gerente can dar de baja from locales proyecto")

try:
    workflow.submit_review(db, B, gerente, "accept")
    raise AssertionError("gerente should not approve pending candidates")
except workflow.WorkflowError:
    print("guard: gerente only promotes approved candidates")

workflow.submit_review(db, B, jefatura, "accept")
db.commit()
assert workflow.candidate_group(db, B) == "suggested"
assert workflow.next_for_role(db, "comite").id == B.id
print("jefatura liked B into suggested")

workflow.submit_review(db, B, jefatura, "reject", note="no cumple foco")
db.commit()
assert workflow.candidate_group(db, B) == "rejected"
try:
    workflow.submit_review(db, B, jefatura, "accept")
    raise AssertionError("jefatura should need a comment to re-suggest rejected candidates")
except workflow.WorkflowError:
    print("guard: jefatura re-suggest requires comment")
workflow.submit_review(db, B, jefatura, "accept", note="reevaluado por jefatura")
db.commit()
assert workflow.candidate_group(db, B) == "suggested"
print("jefatura can re-suggest rejected candidates")

workflow.submit_review(db, B, comite, "accept")
db.commit()
assert workflow.candidate_group(db, B) == "approved"
workflow.submit_review(db, B, gerente, "reject", note="no priorizado")
db.commit()
assert workflow.candidate_group(db, B) == "rejected"
print("gerente can reject approved candidates")
workflow.submit_review(db, B, comite, "accept")
db.commit()
assert workflow.candidate_group(db, B) == "approved"
workflow.submit_review(db, B, comite, "reject", note="renta alta")
db.commit()
assert workflow.candidate_group(db, B) == "rejected"
print("comite can approve and reject across tabs")

first_before_skip = workflow.next_for_role(db, "jefatura")
workflow.submit_review(db, first_before_skip, jefatura, "skip")
db.commit()
first_after_skip = workflow.next_for_role(db, "jefatura")
assert first_after_skip.id != first_before_skip.id
print("skip sends pending candidate to the back")

print("\nALL WORKFLOW TESTS PASSED")
