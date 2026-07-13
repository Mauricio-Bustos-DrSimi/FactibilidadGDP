"""Unit tests for the Postgres row -> record mappers (no live DB required).

Exercises ingestion.candidate_record_from_row and business_record_from_row
with fake dict rows, so the automated-ingestion path has coverage without
needing a Postgres connection.
"""
from decimal import Decimal
import os

from app import ingestion

# --- Candidate mapping -------------------------------------------------------
cand_row = {
    "ID": "P-123",
    "NombreSolicitante": "Juan Perez",
    "DIRECCIÓN": "Av Siempre Viva 742",
    "FRONTIS": "8",
    "PROYECCIÓN": "63",
    "ScoreTotal": Decimal("87.6"),
    "NomRegion": "METROPOLITANA DE SANTIAGO",
    "NomComuna": "SANTIAGO",
    "CveUnidadCercana": "A12; B34",
    "ValorArriendo": Decimal("1500000"),
    "ESTATUS": " PROCESADO ",
    "Latitud": "-33.41427",
    "Longitud": "-70.55922",
}
rec = ingestion.candidate_record_from_row(cand_row, project_id="proj1")

assert rec["project_id"] == "proj1"
assert abs(rec["lat"] - (-33.41427)) < 1e-6, rec["lat"]
assert abs(rec["lng"] - (-70.55922)) < 1e-6, rec["lng"]
assert rec["map_ref"] == "-33.41427,-70.55922", rec["map_ref"]

dd = rec["display_data"]
assert dd["ID Proyección"] == "P-123", dd            # mapped from source column "ID"
assert dd["NombreSolicitante"] == "Juan Perez"
assert dd["DIRECCIÓN"] == "Av Siempre Viva 742"
assert dd["FRONTIS"] == "8 mts", dd["FRONTIS"]       # frontis formatting
assert dd["PROYECCIÓN"] == "$63 MM", dd["PROYECCIÓN"]  # proyeccion formatting
assert dd["ScoreTotal"] == 87.6, dd["ScoreTotal"]
assert dd["NomRegion"] == "METROPOLITANA DE SANTIAGO"
assert dd["NomComuna"] == "SANTIAGO"
assert dd["CveUnidadCercana"] == "A12\nB34", dd["CveUnidadCercana"]  # ";" -> newlines
assert dd["ValorArriendo"] == 1500000.0, dd["ValorArriendo"]  # Decimal -> float
assert ingestion.candidate_source_group(dd) == "pending"
print("candidate mapping OK:", {k: dd[k] for k in ("FRONTIS", "PROYECCIÓN", "CveUnidadCercana")})

rejected_rec = ingestion.candidate_record_from_row({"ESTATUS": "rechazado"})
assert ingestion.candidate_source_group(rejected_rec["display_data"]) == "rejected"

# Candidate with no/invalid coordinates -> lat/lng/map_ref all None, still a record.
rec_bad = ingestion.candidate_record_from_row({"NombreSolicitante": "X"}, project_id="p")
assert rec_bad["lat"] is None and rec_bad["lng"] is None and rec_bad["map_ref"] is None
print("candidate without coords handled")

old_min_id = os.environ.get("CANDIDATE_MIN_ID")
old_fetch = ingestion.fetch_postgres_rows
captured_fetch_args = {}


def fake_fetch_postgres_rows(table, schema=None, connection_settings=None, min_id_column=None, min_id=None):
    captured_fetch_args.update(
        {
            "table": table,
            "schema": schema,
            "min_id_column": min_id_column,
            "min_id": min_id,
        }
    )
    return [
        {
            "ID": "600",
            "NombreSolicitante": "Filtro",
            "Latitud": "-33.41427",
            "Longitud": "-70.55922",
        }
    ]


try:
    os.environ["CANDIDATE_MIN_ID"] = "600"
    ingestion.fetch_postgres_rows = fake_fetch_postgres_rows
    filtered_records, filtered_parsed, filtered_failed = ingestion.fetch_candidate_records_from_postgres("proj1")
finally:
    ingestion.fetch_postgres_rows = old_fetch
    if old_min_id is None:
        os.environ.pop("CANDIDATE_MIN_ID", None)
    else:
        os.environ["CANDIDATE_MIN_ID"] = old_min_id

assert captured_fetch_args["min_id_column"] == "ID", captured_fetch_args
assert captured_fetch_args["min_id"] == 600, captured_fetch_args
assert len(filtered_records) == 1 and filtered_parsed == 1 and filtered_failed == 0
print("candidate min id filter OK:", captured_fetch_args["min_id"])

# --- Business (POI) mapping --------------------------------------------------
biz_row = {
    "CveUnidad": "0123",
    "Direccion": "Calle Falsa 123",
    "Comuna": "Santiago",
    "Region": "RM",
    "Telefono": "555-1234",
    "Distancia": Decimal("12.5"),
    "Latitud": "-33.45",
    "Longitud": "-70.66",
}
brec = ingestion.business_record_from_row(biz_row, "PI_Ahumada")
assert brec is not None
assert abs(brec["lat"] - (-33.45)) < 1e-6 and abs(brec["lng"] - (-70.66)) < 1e-6
assert brec["name"] == "Calle Falsa 123", brec["name"]   # prefers Direccion
assert brec["category"] == "RM", brec["category"]        # Region before Comuna

attrs = brec["attributes"]
assert attrs["_source_table"] == "PI_Ahumada"
assert attrs["Punto de Interes"] == "Farmacia Ahumada"
assert attrs["image_url"] == "/images/Ahumada.png", attrs["image_url"]
assert attrs["CveUnidad"] == "0123"
assert attrs["Distancia"] == 12.5, attrs["Distancia"]    # Decimal -> float
print("business mapping OK:", {k: attrs[k] for k in ("Punto de Interes", "image_url", "Distancia")})

simi_row = {
    "CveUnidad": "CL0002",
    "Unidad": "SAN PABLO",
    "Comuna": "SANTIAGO",
    "Latitud": "-33,434306",
    "Longitud": "-70,651444",
    "Estatus": "ABIERTA",
}
simi_rec = ingestion.business_record_from_row(simi_row, "LocalesSimi")
assert simi_rec is not None
assert abs(simi_rec["lat"] - (-33.434306)) < 1e-6 and abs(simi_rec["lng"] - (-70.651444)) < 1e-6
assert simi_rec["name"] == "SAN PABLO", simi_rec["name"]
assert simi_rec["category"] == "SANTIAGO", simi_rec["category"]

simi_attrs = simi_rec["attributes"]
assert simi_attrs["_source_table"] == "LocalesSimi"
assert simi_attrs["Punto de Interes"] == "Locales Simi"
assert simi_attrs["image_url"] == "/images/DrSimi.png", simi_attrs["image_url"]
assert simi_attrs["Estatus"] == "ABIERTA"
print("locales simi mapping OK:", {k: simi_attrs[k] for k in ("Punto de Interes", "image_url", "Estatus")})

# Business row with invalid coordinates -> dropped (None).
assert ingestion.business_record_from_row({"Latitud": "abc", "Longitud": ""}, "PI_Maicao") is None
print("business without coords dropped")

print("\nALL POSTGRES MAPPER TESTS PASSED")
