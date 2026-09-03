from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app import models
from app.database import SessionLocal, init_db
from app.documents import (
    ATTACHMENT_TYPES,
    DocumentAdapters,
    DocumentContext,
    DocumentError,
    DocumentPolicy,
    DocumentService,
    FactibilityDocumentGroup,
    FactibilityDocumentRepository,
    FileSystemDocumentStorage,
)


def _service(storage: FileSystemDocumentStorage) -> DocumentService:
    return DocumentService(
        storage,
        DocumentPolicy(max_bytes=1024, max_files=4),
        DocumentAdapters(
            projection_id=lambda candidate: "847",
            factibility_groups=(
                FactibilityDocumentGroup("legal", "legal_nuevo", "Nuevo", ()),
            ),
        ),
        FactibilityDocumentRepository(),
        shadow_mode=True,
    )


def test_document_storage_preserves_original_name_and_calculates_metadata(tmp_path: Path):
    storage = FileSystemDocumentStorage(tmp_path)
    policy = DocumentPolicy(max_bytes=1024, max_files=2)

    prepared = policy.prepare("Contrato Ñandú.pdf", b"%PDF-1.4\nbody")
    stored = storage.store_many(Path("Factibilidad/Proyeccion847/legal/legal_nuevo"), [prepared])

    assert len(stored) == 1
    assert stored[0].name == "Contrato _and.pdf"
    assert stored[0].size == 13
    assert stored[0].sha256 == "5b2de8fc92940656e7ae06d0864be972a778c80f7fc0a89a9ef9414956b0b789"
    assert stored[0].path.read_bytes() == b"%PDF-1.4\nbody"


def test_document_storage_rejects_paths_outside_its_root(tmp_path: Path):
    storage = FileSystemDocumentStorage(tmp_path)

    with pytest.raises(DocumentError) as error:
        storage.resolve_existing(Path("../outside"), "secret.pdf")

    assert error.value.status_code == 404
    assert error.value.detail == "Attachment not found"


@pytest.mark.parametrize(
    "filename",
    ["../outside.pdf", "folder/file.pdf", r"folder\file.pdf", ".."],
)
def test_document_policy_rejects_path_components_in_uploaded_names(filename: str):
    policy = DocumentPolicy(max_bytes=1024, max_files=2)

    with pytest.raises(DocumentError) as error:
        policy.prepare(filename, b"%PDF-1.4\nbody")

    assert error.value.status_code == 400
    assert error.value.detail == "Invalid attachment name."


def test_document_policy_rejects_empty_oversized_and_invalid_content():
    policy = DocumentPolicy(max_bytes=12, max_files=2)

    with pytest.raises(DocumentError, match="is empty"):
        policy.prepare("empty.pdf", b"")
    with pytest.raises(DocumentError) as oversized:
        policy.prepare("large.txt", b"x" * 13)
    with pytest.raises(DocumentError, match="is not a valid PDF"):
        policy.prepare("fake.pdf", b"not-a-pdf")

    assert oversized.value.status_code == 413


def test_document_storage_enforces_an_atomic_collection_limit(tmp_path: Path):
    storage = FileSystemDocumentStorage(tmp_path)
    policy = DocumentPolicy(max_bytes=1024, max_files=2)
    relative = Path("Factibilidad/Proyeccion847/ficha_imagenes")
    first = policy.prepare("fachada.png", b"\x89PNG\r\n\x1a\nfirst")
    second = policy.prepare("interior.png", b"\x89PNG\r\n\x1a\nsecond")
    third = policy.prepare("plano.png", b"\x89PNG\r\n\x1a\nthird")

    storage.store_many(relative, [first, second], maximum_total=2)
    with pytest.raises(DocumentError) as error:
        storage.store_many(relative, [third], maximum_total=2)

    assert error.value.status_code == 400
    assert error.value.detail == "La ficha admite un máximo de dos imágenes."
    assert [item.name for item in storage.list(relative)] == ["interior.png", "fachada.png"]


def test_two_concurrent_image_uploads_cannot_exceed_collection_limit(tmp_path: Path):
    storage = FileSystemDocumentStorage(tmp_path)
    policy = DocumentPolicy(max_bytes=1024, max_files=2)
    relative = Path("Factibilidad/Proyeccion847/ficha_imagenes")
    images = [
        policy.prepare(f"imagen_{index}.png", b"\x89PNG\r\n\x1a\n" + bytes([index]))
        for index in range(3)
    ]

    def upload(document):
        try:
            storage.store_many(relative, [document], maximum_total=2)
            return True
        except DocumentError:
            return False

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(upload, images))

    assert results.count(True) == 2
    assert len(storage.list(relative)) == 2


def test_document_policy_accepts_safe_svg_and_rejects_active_svg():
    policy = DocumentPolicy(max_bytes=2048, max_files=2)

    safe = policy.prepare(
        "plano.svg",
        b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" /></svg>',
    )

    assert safe.content_type == "image/svg+xml"
    with pytest.raises(DocumentError, match=r"not a valid image/svg\+xml"):
        policy.prepare("activo.svg", b"<svg><script>alert(1)</script></svg>")
    with pytest.raises(DocumentError, match=r"not a valid image/svg\+xml"):
        policy.prepare("evento.svg", b'<svg onload="alert(1)"></svg>')


def test_document_storage_never_overwrites_a_repeated_name(tmp_path: Path):
    storage = FileSystemDocumentStorage(tmp_path)
    policy = DocumentPolicy(max_bytes=1024, max_files=2)
    relative = Path("Proyeccion847")
    document = policy.prepare("contrato.pdf", b"%PDF-1.4\nbody")

    first = storage.store_many(relative, [document])
    second = storage.store_many(relative, [document])

    assert first[0].name == "contrato.pdf"
    assert second[0].name == "contrato_2.pdf"


def test_document_storage_cleans_new_files_when_metadata_description_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    storage = FileSystemDocumentStorage(tmp_path)
    policy = DocumentPolicy(max_bytes=1024, max_files=2)
    document = policy.prepare("contrato.pdf", b"%PDF-1.4\nbody")

    def fail_description(_: Path):
        raise OSError("stat failed")

    monkeypatch.setattr(storage, "describe", fail_description)
    with pytest.raises(DocumentError, match="Could not store file"):
        storage.store_many(Path("Factibilidad/Proyeccion847/legal"), [document])

    assert not (tmp_path / "Factibilidad/Proyeccion847/legal/contrato.pdf").exists()


def test_document_storage_pruning_never_removes_configured_root(tmp_path: Path):
    storage = FileSystemDocumentStorage(tmp_path)
    policy = DocumentPolicy(max_bytes=1024, max_files=2)
    document = policy.prepare("contrato.pdf", b"%PDF-1.4\nbody")
    relative = Path("Factibilidad/Proyeccion847/legal")
    storage.store_many(relative, [document])

    storage.delete(relative, "contrato.pdf", prune=100)

    assert tmp_path.exists()


def test_document_policy_exposes_all_required_business_file_families():
    assert {
        ".png",
        ".jpeg",
        ".svg",
        ".pdf",
        ".docx",
        ".xlsx",
        ".pptx",
        ".dwg",
        ".dxf",
        ".dgn",
        ".ifc",
        ".rvt",
        ".skp",
        ".pln",
    } <= set(ATTACHMENT_TYPES)


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("contrato.docx", b"PK\x03\x04document"),
        ("presupuesto.xlsx", b"PK\x03\x04spreadsheet"),
        ("presentacion.pptx", b"PK\x03\x04slides"),
        ("contrato.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1document"),
        ("plano.dwg", b"AC1027drawing"),
        ("plano.dxf", b"0\nSECTION\n2\nENTITIES"),
        ("modelo.ifc", b"ISO-10303-21;\nHEADER;"),
    ],
)
def test_document_policy_validates_known_file_family_signatures(
    filename: str, content: bytes
):
    policy = DocumentPolicy(max_bytes=1024, max_files=2)

    assert policy.prepare(filename, content).name == filename
    with pytest.raises(DocumentError, match="does not match"):
        policy.prepare(filename, b"arbitrary renamed content")


def test_factibility_metadata_keeps_projection_id_and_domain_context(tmp_path: Path):
    init_db()
    policy = DocumentPolicy(max_bytes=1024, max_files=2)
    storage = FileSystemDocumentStorage(tmp_path)
    prepared = policy.prepare("contrato.pdf", b"%PDF-1.4\nbody")
    stored = storage.store_many(Path("Factibilidad/Proyeccion847/legal/legal_nuevo"), [prepared])[0]
    context = DocumentContext(
        domain="factibilidad",
        candidate_id=41,
        projection_id="847",
        local="CL0847, LOCAL DE PRUEBA",
        area="legal",
        macro_task="legal_nuevo",
        category="macro_task",
    )
    repository = FactibilityDocumentRepository()

    with SessionLocal() as db:
        repository.record(db, context, prepared, stored, user_id="user-1")
        db.commit()
    with SessionLocal() as db:
        records = repository.list_active(db, context)

    assert len(records) == 1
    assert records[0].projection_id == "847"
    assert records[0].candidate_id == 41
    assert records[0].area == "legal"
    assert records[0].group_key == "legal_nuevo"
    assert records[0].uploaded_by_id == "user-1"


def test_existing_factibility_file_is_inventoried_idempotently(tmp_path: Path):
    init_db()
    storage = FileSystemDocumentStorage(tmp_path)
    service = _service(storage)
    candidate = models.LocationCandidate(
        id=42,
        project_id="test-project",
        display_data={"ID": 847, "CveUnidad": "CL0847", "Unidad": "PRUEBA"},
    )
    prepared = service.policy.prepare("heredado.pdf", b"%PDF-1.4\nlegacy")
    storage.store_many(
        Path("Factibilidad/Proyeccion847/legal/legal_nuevo"), [prepared]
    )

    with SessionLocal() as db:
        first = service.list_factibility_documents(db, candidate, "legal_nuevo")
        second = service.list_factibility_documents(db, candidate, "legal_nuevo")
    context = DocumentContext(
        domain="factibilidad",
        candidate_id=42,
        projection_id="847",
        local="CL0847, PRUEBA",
        area="legal",
        macro_task="legal_nuevo",
        category="macro_task",
    )
    with SessionLocal() as db:
        records = service.metadata.list_active(db, context)

    assert [item.name for item in first] == ["heredado.pdf"]
    assert second == first
    assert len(records) == 1
    assert records[0].projection_id == "847"
    assert records[0].uploaded_by_id is None


def test_factibility_documents_persist_and_remain_isolated_after_storage_restart(
    tmp_path: Path,
):
    policy = DocumentPolicy(max_bytes=1024, max_files=2)
    first_storage = FileSystemDocumentStorage(tmp_path)
    document = policy.prepare("contrato.pdf", b"%PDF-1.4\nbody")
    first_storage.store_many(
        Path("Factibilidad/Proyeccion847/legal/legal_nuevo"), [document]
    )

    restarted_storage = FileSystemDocumentStorage(tmp_path)

    assert [
        item.name
        for item in restarted_storage.list(
            Path("Factibilidad/Proyeccion847/legal/legal_nuevo")
        )
    ] == ["contrato.pdf"]
    assert restarted_storage.list(
        Path("Factibilidad/Proyeccion848/legal/legal_nuevo")
    ) == []


def test_failed_metadata_commit_removes_only_newly_uploaded_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    init_db()
    storage = FileSystemDocumentStorage(tmp_path)
    service = _service(storage)
    candidate = models.LocationCandidate(
        id=44,
        project_id="test-project",
        display_data={"ID": 847},
    )
    user = models.User(id="uploader", email="uploader@example.test", role="sysadmin")

    class Upload:
        filename = "nuevo.pdf"

        async def read(self, size: int = -1) -> bytes:
            return b"%PDF-1.4\nnew"

        async def close(self) -> None:
            return None

    with SessionLocal() as db:
        def fail_commit() -> None:
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(db, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="database unavailable"):
            asyncio.run(
                service.upload_factibility_documents(
                    db, user, candidate, "legal_nuevo", [Upload()]
                )
            )

    assert storage.list(
        Path("Factibilidad/Proyeccion847/legal/legal_nuevo")
    ) == []


def test_failed_factibility_delete_restores_exact_legacy_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    init_db()
    storage = FileSystemDocumentStorage(tmp_path)
    service = _service(storage)
    candidate = models.LocationCandidate(
        id=43,
        project_id="test-project",
        display_data={"ID": 847},
    )
    relative = Path("Factibilidad/Proyeccion847/legal/legal_nuevo")
    legacy_bytes = b"legacy PDF bytes that predate strict validation"
    storage.directory(relative, create=True).joinpath("heredado.pdf").write_bytes(
        legacy_bytes
    )

    with SessionLocal() as db:
        service.list_factibility_documents(db, candidate, "legal_nuevo")

        def fail_commit() -> None:
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(db, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="database unavailable"):
            service.delete_factibility_document(
                db, candidate, "legal_nuevo", "heredado.pdf"
            )

    restored = storage.resolve_existing(relative, "heredado.pdf")
    assert restored.name == "heredado.pdf"
    assert restored.read_bytes() == legacy_bytes


def test_shadow_mode_never_deletes_a_base_gdp_document(tmp_path: Path):
    policy = DocumentPolicy(max_bytes=1024, max_files=2)
    storage = FileSystemDocumentStorage(tmp_path)
    repository = FactibilityDocumentRepository()
    service = _service(storage)
    document = policy.prepare("contrato.pdf", b"%PDF-1.4\nbase")
    storage.store_many(Path("Proyeccion847"), [document])
    candidate = models.LocationCandidate(
        id=41,
        project_id="test-project",
        display_data={"ID": 847},
    )

    with pytest.raises(DocumentError) as error:
        service.delete_candidate_document(
            None, None, candidate, "contrato.pdf"  # type: ignore[arg-type]
        )

    assert error.value.status_code == 409
    assert storage.resolve_existing(
        Path("Proyeccion847"), "contrato.pdf"
    ).is_file()
