"""Exercise one live 8003 Gestor write and remove the generated test record."""
from __future__ import annotations

import http.cookiejar
import json
import os
import uuid
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
database_url = os.environ["DATABASE_URL"]
email = os.environ["SYSADMIN_EMAIL"]
password = os.environ["SYSADMIN_PASSWORD"]
note = f"smoke-overlay-{uuid.uuid4()}"
engine = create_engine(database_url)

with engine.connect() as connection:
    candidate_id = connection.scalar(text(
        "SELECT id FROM pruebas_gestor.candidato_ubicacion ORDER BY id LIMIT 1"
    ))
if candidate_id is None:
    raise RuntimeError("No replicated candidate is available for the smoke test")

cookies = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))


def post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"http://127.0.0.1:8003{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with client.open(request, timeout=15) as response:
        return json.load(response)


try:
    post("/auth/login", {"email": email, "password": password})
    result = post(f"/candidates/{candidate_id}/comment", {"note": note})
    if result.get("comment") != note and result.get("note") != note:
        raise RuntimeError("The live action did not return the test comment")
    with engine.connect() as connection:
        stored = connection.scalar(text("""
            SELECT count(*) FROM pruebas_gestor.revision_local
            WHERE id_candidato=:candidate_id AND comentario=:note
        """), {"candidate_id": candidate_id, "note": note})
    if stored != 1:
        raise RuntimeError("The live action was not stored in pruebas_gestor")
    print("SMOKE_OK action_saved_only_in=pruebas_gestor.revision_local")
finally:
    with engine.begin() as connection:
        connection.execute(text("""
            DELETE FROM pruebas_gestor.revision_local
            WHERE id_candidato=:candidate_id AND comentario=:note
        """), {"candidate_id": candidate_id, "note": note})
    engine.dispose()
