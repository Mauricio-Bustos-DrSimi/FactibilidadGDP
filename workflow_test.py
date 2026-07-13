"""Workflow smoke test for the staged approval roles."""
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
    user = models.User(email=f"{role}@x.com", name=role.title(), password_hash="x", role=role)
    db.add(user)
    db.flush()
    return user


jefatura = mkuser(workflow.JEFATURA)
coordinador = mkuser(workflow.COORDINADOR)
arriendo = mkuser(workflow.ARRIENDO)
gerente = mkuser(workflow.GERENTE)
comite = mkuser(workflow.COMITE)
gerente_general = mkuser(workflow.GERENTE_GENERAL)

project = models.Project(name="WF Demo")
db.add(project)
db.flush()
candidates = []
for index in range(6):
    candidate = models.LocationCandidate(
        project_id=project.project_id,
        lat=-33.4 - index,
        lng=-70.6,
        display_data={"n": index},
    )
    db.add(candidate)
    candidates.append(candidate)
db.commit()

a, b, c, d, e, f = candidates
assert workflow.next_for_role(db, workflow.JEFATURA).id == a.id

# Initial reviewers keep their metric/highlight behavior.
workflow.submit_review(db, a, jefatura, "reject", note="sin estacionamiento")
assert workflow.candidate_group(db, a) == "pending"
assert a.last_action == "dislike"
workflow.submit_review(db, a, jefatura, "star")
db.commit()
assert workflow.candidate_group(db, a) == "suggested"

# Arriendo y Patentes / Gerente approve only into Aprobados.
try:
    workflow.submit_review(db, a, comite, "accept")
    raise AssertionError("Comite must not approve suggested candidates")
except workflow.WorkflowError:
    pass
workflow.submit_review(db, a, arriendo, "accept")
db.commit()
assert workflow.candidate_group(db, a) == "approved"
assert a.current_stage == workflow.APPROVED_STAGE
try:
    workflow.submit_review(db, a, arriendo, "reject", note="not allowed")
    raise AssertionError("Arriendo must only approve")
except workflow.WorkflowError:
    pass

# Comite promotes Aprobados into the new Locales Proyecto group.
assert workflow.next_for_role(db, workflow.COMITE).id == a.id
workflow.submit_review(db, a, comite, "accept")
db.commit()
assert workflow.candidate_group(db, a) == "project"
assert a.status == workflow.PROJECT
assert a.current_stage == workflow.LOCAL_PROJECT_STAGE

# Only the coordinator advances a Local Proyecto after variables are complete.
try:
    workflow.submit_review(db, a, coordinador, "opening")
    raise AssertionError("Proyecto must require variables")
except workflow.WorkflowError:
    pass
db.add(models.CandidateProjectVariables(
    candidate_id=a.id,
    cve_unidad="CL9999",
    unidad="LOCAL TEST",
    region="METROPOLITANA DE SANTIAGO",
    comuna="SANTIAGO",
))
db.flush()
workflow.submit_review(db, a, coordinador, "opening")
db.commit()
assert workflow.candidate_group(db, a) == "opening"
assert a.current_stage == workflow.PROJECT_STAGE

# Comite can dar de baja from the final Proyectos tab.
workflow.submit_review(db, a, comite, "reject", note="dar de baja")
db.commit()
assert workflow.candidate_group(db, a) == "rejected"

# Gerente and Gerente General provide the equivalent alternate path.
workflow.submit_review(db, b, jefatura, "star")
workflow.submit_review(db, b, gerente, "accept")
db.commit()
assert workflow.candidate_group(db, b) == "approved"
assert workflow.next_for_role(db, workflow.GERENTE_GENERAL).id == b.id
workflow.submit_review(db, b, gerente_general, "accept")
db.commit()
assert workflow.candidate_group(db, b) == "project"
workflow.submit_review(db, b, gerente_general, "reject", note="dar de baja")
db.commit()
assert workflow.candidate_group(db, b) == "rejected"

# Both final approver roles may reject directly from Aprobados.
workflow.submit_review(db, c, arriendo, "accept")
workflow.submit_review(db, c, comite, "reject", note="rechazado en aprobados")
workflow.submit_review(db, d, gerente, "accept")
workflow.submit_review(db, d, gerente_general, "reject", note="rechazado en aprobados")
db.commit()
assert workflow.candidate_group(db, c) == "rejected"
assert workflow.candidate_group(db, d) == "rejected"

first_before_skip = workflow.next_for_role(db, workflow.JEFATURA)
workflow.submit_review(db, first_before_skip, jefatura, "skip")
db.commit()
first_after_skip = workflow.next_for_role(db, workflow.JEFATURA)
assert first_after_skip.id != first_before_skip.id

db.close()
print("ALL WORKFLOW TESTS PASSED")
