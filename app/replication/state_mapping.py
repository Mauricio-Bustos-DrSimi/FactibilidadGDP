"""Auditable translation from legacy workflow values to the new catalog."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StateMapping:
    codigo: str
    certeza: str


STATE_MAPPING: dict[str, StateMapping] = {
    "pendiente": StateMapping("PENDIENTE", "EXACTA"),
    "pending": StateMapping("PENDIENTE", "EXACTA"),
    "devuelto": StateMapping("PENDIENTE", "INFERIDA"),
    "returned": StateMapping("PENDIENTE", "INFERIDA"),
    "sugerido": StateMapping("PENDIENTE", "INFERIDA"),
    "suggested": StateMapping("PENDIENTE", "INFERIDA"),
    "observacion": StateMapping("OBSERVACION", "EXACTA"),
    "observation": StateMapping("OBSERVACION", "EXACTA"),
    "rechazado": StateMapping("RECHAZADO", "EXACTA"),
    "rejected": StateMapping("RECHAZADO", "EXACTA"),
    "en_estudio": StateMapping("EN_ESTUDIO", "EXACTA"),
    "study": StateMapping("EN_ESTUDIO", "EXACTA"),
    # workflow.py stores `aprobado` while the UI group is Propuestos.
    "aprobado": StateMapping("PROPUESTO", "INFERIDA"),
    "approved": StateMapping("PROPUESTO", "INFERIDA"),
    "approved_final": StateMapping("PROPUESTO", "INFERIDA"),
    # `locales_proyecto` is the UI group Aprobados, before the final opening.
    "locales_proyecto": StateMapping("APROBADO", "INFERIDA"),
    "approved_location": StateMapping("APROBADO", "INFERIDA"),
    # Factibilidad currently consumes the final `opening`/`por_abrir` group.
    "por_abrir": StateMapping("PROYECTO", "INFERIDA"),
    "opening": StateMapping("PROYECTO", "INFERIDA"),
    "project": StateMapping("PROYECTO", "INFERIDA"),
}


def translate_state(value: object) -> StateMapping:
    normalized = str(value or "").strip().lower()
    return STATE_MAPPING.get(normalized, StateMapping("PENDIENTE", "DESCONOCIDA"))
