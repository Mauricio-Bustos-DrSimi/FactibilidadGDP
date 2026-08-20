"""Stable business identifiers shared by replication and reconciliation."""
from __future__ import annotations

import re
import unicodedata
from typing import Any


def projection_id_from_display_data(display_data: dict[str, Any] | None) -> str | None:
    """Return the business projection ID without confusing it with the row PK."""
    for key, value in (display_data or {}).items():
        ascii_key = unicodedata.normalize("NFKD", str(key)).encode("ascii", "ignore").decode("ascii")
        normalized = re.sub(r"[^a-z]", "", ascii_key.lower())
        if normalized in {"id", "idproyeccion"} and value not in (None, ""):
            return str(value).strip().removesuffix(".0")
    return None
