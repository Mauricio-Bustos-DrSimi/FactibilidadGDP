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
jefe_comercial = mkuser(workflow.JEFE_COMERCIAL)
coordinador = mkuser(workflow.COORDINADOR)
arriendo = mkuser(workflow.ARRIENDO)
gerente = mkuser(workflow.GERENTE)
comite = mkuser(workflow.COMITE)
gerente_general = mkuser(workflow.GERENTE_GENERAL)
sysadmin = mkuser(workflow.SYSADMIN)

project = models.Project(name="WF Demo")
db.add(project)
db.flush()
candidates = []
for index in range(12):
    candidate = models.LocationCandidate(
        project_id=project.project_id,
        lat=-33.4 - index,
        lng=-70.6,
        display_data={"n": index},
    )
    db.add(candidate)
    candidates.append(candidate)
db.commit()

a, b, c, d, e, f, g, h, i, j, k, l = candidates
assert workflow.next_for_role(db, workflow.JEFATURA).id == a.id
for action in {"like", "dislike", "skip", "accept", "reject", "project", "opening"}:
    assert workflow.can_act(db, sysadmin, a, action)

# Initial reviewers keep like/dislike as metrics without moving the candidate.
workflow.submit_review(db, a, jefatura, "reject", note="sin estacionamiento")
assert workflow.candidate_group(db, a) == "pending"
assert a.last_action == "dislike"
workflow.submit_review(db, a, jefatura, "like")
db.commit()
assert workflow.candidate_group(db, a) == "pending"
try:
    workflow.submit_review(db, a, jefatura, "star")
    raise AssertionError("Highlighting must no longer be available")
except workflow.WorkflowError:
    pass

# Arriendo y Patentes / Gerente move candidates into Propuestos.
try:
    workflow.submit_review(db, a, comite, "accept")
    raise AssertionError("Comite must not approve pending candidates")
except workflow.WorkflowError:
    pass
workflow.submit_review(db, a, arriendo, "accept")
db.commit()
assert workflow.candidate_group(db, a) == "proposed"
assert a.current_stage == workflow.PROPOSED_STAGE
assert workflow.can_act(db, arriendo, a, "reject")
assert workflow.can_act(db, arriendo, a, "skip")

# Comite promotes Propuestos into Aprobados.
assert workflow.next_for_role(db, workflow.COMITE).id == a.id
workflow.submit_review(db, a, comite, "accept")
db.commit()
assert workflow.candidate_group(db, a) == "approved"
assert a.status == workflow.PROJECT
assert a.current_stage == workflow.APPROVED_STAGE

# Only the coordinator advances an Aprobado after variables are complete.
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
workflow.submit_review(db, b, jefatura, "like")
workflow.submit_review(db, b, gerente, "accept")
db.commit()
assert workflow.candidate_group(db, b) == "proposed"
assert workflow.next_for_role(db, workflow.GERENTE_GENERAL).id == b.id
workflow.submit_review(db, b, gerente_general, "accept")
db.commit()
assert workflow.candidate_group(db, b) == "approved"
workflow.submit_review(db, b, gerente_general, "reject", note="dar de baja")
db.commit()
assert workflow.candidate_group(db, b) == "rejected"

# Arriendo, Gerente, and both final approver roles may reject from Propuestos.
workflow.submit_review(db, c, arriendo, "accept")
assert workflow.can_act(db, gerente, c, "reject")
assert workflow.can_act(db, gerente, c, "skip")
assert workflow.can_act(db, arriendo, c, "reject")
assert workflow.can_act(db, arriendo, c, "skip")
workflow.submit_review(db, c, comite, "reject", note="rechazado en aprobados")
workflow.submit_review(db, d, gerente, "accept")
workflow.submit_review(db, d, gerente_general, "reject", note="rechazado en aprobados")
db.commit()
assert workflow.candidate_group(db, c) == "rejected"
assert workflow.candidate_group(db, d) == "rejected"

# Arriendo and Gerente may reject Pendientes and propose them again.
workflow.submit_review(db, g, arriendo, "reject", note="antecedentes incompletos")
db.commit()
assert workflow.candidate_group(db, g) == "rejected"
workflow.submit_review(db, g, gerente, "accept", note="antecedentes corregidos")
db.commit()
assert workflow.candidate_group(db, g) == "proposed"

# Source observations have the same recovery permissions as rejected candidates.
h.status = workflow.OBSERVATION
h.workflow_group = workflow.OBSERVATION
db.commit()
assert workflow.candidate_group(db, h) == "observation"
assert workflow.can_act(db, arriendo, h, "accept")
assert workflow.can_act(db, arriendo, h, "reject")
assert workflow.can_act(db, gerente, h, "accept")
assert workflow.can_act(db, gerente, h, "reject")
assert not workflow.can_act(db, jefatura, h, "accept")
workflow.submit_review(db, h, arriendo, "reject", note="observacion descartada")
db.commit()
assert workflow.candidate_group(db, h) == "rejected"
assert workflow.can_act(db, arriendo, h, "study")
assert workflow.can_act(db, gerente, h, "study")
workflow.submit_review(db, h, gerente, "study", note="rechazado en estudio")
assert workflow.candidate_group(db, h) == "study"
workflow.submit_review(db, h, arriendo, "reject", note="estudio descartado")
db.commit()
assert workflow.candidate_group(db, h) == "rejected"
workflow.submit_review(db, h, arriendo, "accept", note="observación resuelta")
db.commit()
assert workflow.candidate_group(db, h) == "proposed"

# Arriendo, Gerente, and Sysadmin manage the En Estudio flow.
assert workflow.can_act(db, arriendo, j, "study")
assert workflow.can_act(db, gerente, j, "study")
assert not workflow.can_act(db, coordinador, j, "study")
workflow.submit_review(db, j, arriendo, "study", note="local llamativo")
db.commit()
assert workflow.candidate_group(db, j) == "study"
assert workflow.can_act(db, gerente, j, "accept")
assert workflow.can_act(db, gerente, j, "reject")
workflow.submit_review(db, j, gerente, "accept", note="avanza a propuesto")
db.commit()
assert workflow.candidate_group(db, j) == "proposed"
assert workflow.can_act(db, gerente, j, "project")
workflow.submit_review(db, j, gerente, "project", note="División: SUCURSAL")
db.commit()
assert workflow.candidate_group(db, j) == "approved"

k.status = workflow.OBSERVATION
k.workflow_group = workflow.OBSERVATION
l.status = workflow.OBSERVATION
l.workflow_group = workflow.OBSERVATION
db.commit()
workflow.submit_review(db, k, gerente, "study", note="requiere análisis")
assert workflow.candidate_group(db, k) == "study"
workflow.submit_review(db, k, arriendo, "reject", note="estudio descartado")
workflow.submit_review(db, l, gerente, "reject", note="observación descartada")
db.commit()
assert workflow.candidate_group(db, k) == "rejected"
assert workflow.candidate_group(db, l) == "rejected"

# Arriendos y Patentes can complete the operational flow through Proyecto.
workflow.submit_review(db, i, arriendo, "accept")
assert workflow.candidate_group(db, i) == "proposed"
workflow.submit_review(db, i, arriendo, "project")
assert workflow.candidate_group(db, i) == "approved"
db.add(models.CandidateProjectVariables(
    candidate_id=i.id,
    cve_unidad="CL8888",
    unidad="LOCAL ARRIENDOS",
    region="METROPOLITANA DE SANTIAGO",
    comuna="SANTIAGO",
))
db.flush()
workflow.submit_review(db, i, arriendo, "opening")
assert workflow.candidate_group(db, i) == "opening"
workflow.submit_review(db, i, arriendo, "reject", note="baja por arriendos")
db.commit()
assert workflow.candidate_group(db, i) == "rejected"

# Jefe Comercial and Coordinador cannot vote for their own candidate.
e.display_data = {"CorreoSolicitante": jefe_comercial.email}
f.display_data = {"CorreoSolicitante": coordinador.email.upper()}
assert not workflow.can_act(db, jefe_comercial, e, "like")
assert not workflow.can_act(db, jefe_comercial, e, "dislike")
assert workflow.can_act(db, coordinador, e, "like")
assert not workflow.can_act(db, coordinador, f, "like")
assert workflow.can_act(db, jefe_comercial, f, "dislike")
try:
    workflow.submit_review(db, e, jefe_comercial, "like")
    raise AssertionError("Jefe Comercial must not vote for their own candidate")
except workflow.WorkflowError:
    pass

first_before_skip = workflow.next_for_role(db, workflow.JEFATURA)
workflow.submit_review(db, first_before_skip, jefatura, "skip")
db.commit()
first_after_skip = workflow.next_for_role(db, workflow.JEFATURA)
assert first_after_skip.id != first_before_skip.id

db.close()
print("ALL WORKFLOW TESTS PASSED")
