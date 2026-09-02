from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from tests.characterization.support import login, seed_candidate


def test_factibility_document_library_http_contract_uses_isolated_filesystem():
    candidate = seed_candidate(projection_id=990301, group="opening")
    group_key = "legal_nuevo"

    with TestClient(app) as client:
        login(
            client,
            "characterization-admin@example.test",
            "characterization-admin-password",
        )
        uploaded = client.post(
            f"/factibilidad/locations/{candidate.id}/groups/{group_key}/attachments",
            files={
                "files": (
                    "contrato caracterizacion.pdf",
                    b"%PDF-1.4\ncharacterization\n%%EOF",
                    "application/pdf",
                )
            },
        )

        assert uploaded.status_code == 200
        assert [row["name"] for row in uploaded.json()] == [
            "contrato caracterizacion.pdf"
        ]
        stored = uploaded.json()[0]
        assert stored["content_type"] == "application/pdf"

        listed = client.get(
            f"/factibilidad/locations/{candidate.id}/groups/{group_key}/attachments"
        )
        opened = client.get(stored["url"])
        library = client.get(
            f"/factibilidad/locations/{candidate.id}/attachments"
        )

        assert listed.status_code == 200
        assert listed.json() == uploaded.json()
        assert opened.status_code == 200
        assert opened.content.startswith(b"%PDF-1.4")
        assert opened.headers["content-disposition"].startswith("inline;")
        legal_group = next(
            row for row in library.json() if row["key"] == group_key
        )
        assert legal_group["area"] == "legal"
        assert legal_group["files"] == uploaded.json()

        deleted = client.delete(stored["url"])
        assert deleted.status_code == 200
        assert deleted.json() == []
        assert client.get(stored["url"]).status_code == 404


def test_factibility_sales_sheet_accepts_two_images_and_rejects_a_third():
    candidate = seed_candidate(projection_id=990302, group="opening")
    png = b"\x89PNG\r\n\x1a\ncharacterization"

    with TestClient(app) as client:
        login(
            client,
            "characterization-admin@example.test",
            "characterization-admin-password",
        )
        endpoint = f"/factibilidad/locations/{candidate.id}/sales-sheet/images"
        first_two = client.post(
            endpoint,
            files=[
                ("files", ("fachada.png", png, "image/png")),
                ("files", ("interior.png", png, "image/png")),
            ],
        )
        third = client.post(
            endpoint,
            files={"files": ("tercera.png", png, "image/png")},
        )

        assert first_two.status_code == 200
        assert [row["name"] for row in first_two.json()] == [
            "fachada.png",
            "interior.png",
        ]
        assert third.status_code == 400
        assert third.json()["detail"] == "La ficha admite un máximo de dos imágenes."

        for image in first_two.json():
            opened = client.get(image["url"])
            assert opened.status_code == 200
            assert opened.headers["content-type"] == "image/png"
            assert client.delete(image["url"]).status_code == 200
