from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.documents import DocumentPolicy, FileSystemDocumentStorage


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

    with pytest.raises(HTTPException) as error:
        storage.resolve_existing(Path("../outside"), "secret.pdf")

    assert error.value.status_code == 404
    assert error.value.detail == "Attachment not found"


def test_document_policy_rejects_empty_oversized_and_invalid_content():
    policy = DocumentPolicy(max_bytes=12, max_files=2)

    with pytest.raises(HTTPException, match="is empty"):
        policy.prepare("empty.pdf", b"")
    with pytest.raises(HTTPException) as oversized:
        policy.prepare("large.txt", b"x" * 13)
    with pytest.raises(HTTPException, match="is not a valid PDF"):
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
    with pytest.raises(HTTPException) as error:
        storage.store_many(relative, [third], maximum_total=2)

    assert error.value.status_code == 400
    assert error.value.detail == "La ficha admite un máximo de dos imágenes."
    assert [item.name for item in storage.list(relative)] == ["interior.png", "fachada.png"]


def test_document_policy_accepts_safe_svg_and_rejects_active_svg():
    policy = DocumentPolicy(max_bytes=2048, max_files=2)

    safe = policy.prepare(
        "plano.svg",
        b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" /></svg>',
    )

    assert safe.content_type == "image/svg+xml"
    with pytest.raises(HTTPException, match=r"not a valid image/svg\+xml"):
        policy.prepare("activo.svg", b"<svg><script>alert(1)</script></svg>")


def test_document_storage_never_overwrites_a_repeated_name(tmp_path: Path):
    storage = FileSystemDocumentStorage(tmp_path)
    policy = DocumentPolicy(max_bytes=1024, max_files=2)
    relative = Path("Proyeccion847")
    document = policy.prepare("contrato.pdf", b"%PDF-1.4\nbody")

    first = storage.store_many(relative, [document])
    second = storage.store_many(relative, [document])

    assert first[0].name == "contrato.pdf"
    assert second[0].name == "contrato_2.pdf"
