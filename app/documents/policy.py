"""Validation and naming policy for user-supplied documents."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from fastapi import HTTPException

from app.documents.types import PreparedDocument


ATTACHMENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".docm": "application/vnd.ms-word.document.macroEnabled.12",
    ".rtf": "application/rtf",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".pptm": "application/vnd.ms-powerpoint.presentation.macroEnabled.12",
    ".odp": "application/vnd.oasis.opendocument.presentation",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".dwg": "application/vnd.dwg",
    ".dxf": "image/vnd.dxf",
    ".dgn": "application/octet-stream",
    ".dwf": "model/vnd.dwf",
    ".rvt": "application/octet-stream",
    ".rfa": "application/octet-stream",
    ".ifc": "model/ifc",
    ".pln": "application/octet-stream",
    ".skp": "application/vnd.sketchup.skp",
}
IMAGE_TYPES = {
    extension: media_type
    for extension, media_type in ATTACHMENT_TYPES.items()
    if media_type.startswith("image/")
}
SHEET_IMAGE_TYPES = {
    extension: media_type
    for extension, media_type in IMAGE_TYPES.items()
    if extension in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
}


def detected_image_type(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith(b"BM"):
        return "image/bmp"
    return None


class DocumentPolicy:
    def __init__(self, *, max_bytes: int, max_files: int) -> None:
        self.max_bytes = max_bytes
        self.max_files = max_files

    def safe_name(self, filename: str) -> str:
        source = Path(filename or "").name
        suffix = Path(source).suffix.lower()
        stem = Path(source).stem
        if suffix not in ATTACHMENT_TYPES:
            raise HTTPException(400, f"Unsupported attachment extension: {suffix or '(none)'}")
        safe_stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", stem).strip(" ._")[:100] or "archivo"
        return f"{safe_stem}{suffix}"

    def prepare(self, filename: str, content: bytes) -> PreparedDocument:
        safe_name = self.safe_name(filename)
        if not content:
            raise HTTPException(400, f"{safe_name} is empty.")
        if len(content) > self.max_bytes:
            max_mb = self.max_bytes // (1024 * 1024)
            raise HTTPException(413, f"{safe_name} exceeds the {max_mb} MB limit.")
        suffix = Path(safe_name).suffix.lower()
        if suffix in IMAGE_TYPES and suffix != ".svg":
            detected = detected_image_type(content)
            expected = IMAGE_TYPES[suffix]
            if detected != expected:
                raise HTTPException(400, f"{safe_name} is not a valid {expected} image.")
        elif suffix == ".svg":
            sample = content[:4096].lstrip().lower()
            if b"<svg" not in sample or b"<script" in sample:
                raise HTTPException(400, f"{safe_name} is not a valid image/svg+xml image.")
        elif suffix == ".pdf" and not content.startswith(b"%PDF-"):
            raise HTTPException(400, f"{safe_name} is not a valid PDF document.")
        return PreparedDocument(
            name=safe_name,
            content=content,
            content_type=ATTACHMENT_TYPES[suffix],
            sha256=hashlib.sha256(content).hexdigest(),
        )

    def validate_count(self, count: int) -> None:
        if count <= 0:
            raise HTTPException(400, "Select at least one file.")
        if count > self.max_files:
            raise HTTPException(
                400,
                f"A maximum of {self.max_files} files can be uploaded at once.",
            )


__all__ = [
    "ATTACHMENT_TYPES",
    "DocumentPolicy",
    "IMAGE_TYPES",
    "SHEET_IMAGE_TYPES",
]
