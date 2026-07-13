"""Tabular ingestion + map-reference coordinate parsing.

Supports:
- CSV with comma or semicolon delimiter (auto-detected)
- European decimal separator in coordinates (comma → dot)
- Separate Latitud/Longitud columns OR a single map-reference column
- Cleans "NULL" string values and formats age-band columns as percentages
"""
from __future__ import annotations

import io
import math
import re
import os
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlparse

import pandas as pd

# Column names tried (case-insensitive) when no map column is declared.
DEFAULT_MAP_COLUMN_CANDIDATES = (
    "maps", "map", "url", "coordinates", "coordenadas", "ubicacion", "ubicación",
)

# Recognised names for explicit latitude / longitude columns (case-insensitive).
_LAT_NAMES = ("lat", "latitude", "latitud")
_LNG_NAMES = ("lng", "lon", "longitude", "longitud")

# A plain "lat,lng" pair with dot decimals, e.g. "19.4326,-99.1332".
_LATLNG_RE = re.compile(
    r"^\s*\(?\s*(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*\)?\s*$"
)

# Coordinate patterns found inside Google Maps URLs, in priority order.
_URL_PATTERNS = (
    re.compile(r"!3d(-?\d{1,3}\.\d+)!4d(-?\d{1,3}\.\d+)"),
    re.compile(r"@(-?\d{1,3}\.\d+),(-?\d{1,3}\.\d+)"),
    re.compile(r"(?:[?&](?:q|query|ll|center|destination|daddr)=)(-?\d{1,3}\.\d+),(-?\d{1,3}\.\d+)"),
)

# Age-band column name pattern: <30, 30-40, 40-50, 60-75, 75<, etc.
_AGE_BAND_RE = re.compile(r"^(<\s*\d+|\d+\s*-\s*\d+|\d+\s*<)$")

# A single number that uses comma as decimal separator (e.g. "-33,40214", "4,6").
_EURO_DECIMAL_RE = re.compile(r"^-?\d+,\d+$")

# Default Postgres import settings used by the automatic ingestion flow.
DEFAULT_PG_SCHEMA = "dw_simi"
DEFAULT_CANDIDATE_TABLE = "SolicitudesProyecciones"
DEFAULT_BUSINESS_TABLES = (
    "PI_Ahumada",
    "PI_CruzVerde",
    "PI_Salcobrand",
    "PI_Maicao",
    "PI_EstacionesMetro",
    "LocalesSimi",
)

CANDIDATE_DISPLAY_COLUMNS = (
    "ID Proyección",
    "NombreSolicitante",
    "CorreoSolicitante",
    "DIRECCIÓN",
    "FRONTIS",
    "DIVISION",
    "TIPOLOGÍA",
    "FECHA",
    "ESTATUS",
    "<30",
    "30-40",
    "40-50",
    "50-60",
    "60-75",
    "75<",
    "PROYECCIÓN",
    "Latitud",
    "Longitud",
    "MT2",
    "ValorArriendo",
    "GastosComunes",
    "ValorGGCC",
    "VentaVariable",
    "ValorVentaVariable",
    "CveUnidadCercana",
    "TipoEstatus",
    "IDProyeccionCercano",
    "ScoreTotal",
    "NivelScore",
    "ScoreProyeccion",
    "ScoreRedPropia",
    "ScoreCUT",
    "ScoreCompetencia",
    "CUTUnico",
    "CantidadLocalesMismoCUT",
    "CveUnidadPropiaCercana",
    "DistanciaLocalPropioM",
    "EstatusLocalPropioCercano",
    "NivelRedPropia",
    "CantidadCompetencia200m",
    "DistanciaCompetenciaM",
    "NomRegion",
    "NomComuna",
)

CANDIDATE_SOURCE_COLUMNS = {
    "ID Proyección": "ID",
}

BUSINESS_TABLE_LABELS = {
    "PI_Ahumada": "Farmacia Ahumada",
    "PI_CruzVerde": "Farmacia Cruz Verde",
    "PI_Salcobrand": "Farmacia Salcobrand",
    "PI_Maicao": "Maicao",
    "PI_EstacionesMetro": "Estacion de Metro",
    "LocalesSimi": "Locales Simi",
}

BUSINESS_IMAGE_FILENAMES = {
    "PI_Ahumada": "Ahumada.png",
    "PI_CruzVerde": "CruzVerde.png",
    "PI_Salcobrand": "Salcobrand.png",
    "PI_Maicao": "Maicao.png",
    "PI_EstacionesMetro": "EstacionesMetro.png",
    "LocalesSimi": "DrSimi.png",
}

DEFAULT_IMAGE_URL_PREFIX = "/images"

_BUSINESS_RESERVED_COLUMNS = {
    "latitud",
    "longitud",
    "lat",
    "lng",
    "lon",
    "latitude",
    "longitude",
    "direccion",
    "comuna",
    "region",
    "cveunidad",
    "nombreestacion",
    "cvemetro",
    "unidad",
    "name",
    "nombre",
}

BUSINESS_ATTRIBUTE_COLUMNS = {
    "PI_Ahumada": (
        "CveUnidad",
        "Direccion",
        "Comuna",
        "Latitud",
        "Longitud",
        "Telefono",
        "Horas24",
        "Estacionamiento",
        "ServicioAtencionFarmaceuticaEspecializada",
        "HorarioLunesViernes",
        "HorarioSabado",
        "HorarioDomingo",
        "EsNueva",
        "Region",
        "CveSimiCercano",
        "Distancia",
    ),
    "PI_CruzVerde": (
        "CveUnidad",
        "Horario",
        "HorarioSabado",
        "HorarioDomingo",
        "Direccion",
        "Comuna",
        "Region",
        "Latitud",
        "Longitud",
        "Dermoconsejero",
        "AsistenciaDermo",
        "AsistenciaNutri",
        "24Horas",
        "AtencionAuto",
        "Estacionamiento",
        "RetiroTienda",
        "EsNueva",
        "CveSimiCercano",
        "Distancia",
    ),
    "PI_Salcobrand": (
        "CveUnidad",
        "Direccion",
        "Comuna",
        "TiempoEspera",
        "Latitud",
        "Longitud",
        "HorarioLunesViernes",
        "HorarioSabado",
        "HorarioDomingo",
        "HorarioEspecial",
        "Region",
        "EsNueva",
        "CveSimiCercano",
        "Distancia",
    ),
    "PI_Maicao": (
        "CveUnidad",
        "Nombre",
        "EsFarmacia",
        "EstaAbierta",
        "HorarioLunesViernes",
        "HorarioSabado",
        "HorarioDomingo",
        "HorarioFarmacia",
        "Region",
        "Comuna",
        "Direccion",
        "Latitud",
        "Longitud",
        "CveSimiCercano",
        "Distancia",
    ),
    "PI_EstacionesMetro": (
        "CveMetro",
        "NombreEstacion",
        "LineaCorta",
        "Linea",
        "Latitud",
        "Longitud",
        "Terminal",
        "Combinacion",
        "CombinacionLinea",
        "EnConstruccion",
        "CveSimiCercano",
        "Distancia",
    ),
    "LocalesSimi": (
        "CveUnidad",
        "Unidad",
        "Comuna",
        "Latitud",
        "Longitud",
        "Estatus",
    ),
}


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def _valid(lat: float, lng: float) -> bool:
    return (
        not (math.isnan(lat) or math.isnan(lng))
        and -90.0 <= lat <= 90.0
        and -180.0 <= lng <= 180.0
    )


def _parse_coord_float(val: Any) -> Optional[float]:
    """Parse a coordinate value that may use European comma as decimal separator."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("null", "nan", ""):
        return None
    s = s.replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def normalize_json_value(value: Any) -> Any:
    """Return a JSON-safe value for display_data/attributes."""
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _norm_key(value: str) -> str:
    ascii_key = unicodedata.normalize("NFKD", str(value))
    ascii_key = ascii_key.encode("ascii", "ignore").decode("ascii")
    return ascii_key.strip().lower()


def _row_lookup(row: Mapping[str, Any], *names: str) -> Any:
    lowered = {_norm_key(k): k for k in row}
    for name in names:
        key = lowered.get(_norm_key(name))
        if key is not None:
            return row.get(key)
    return None


def _row_display_name(row: Mapping[str, Any], default: Optional[str] = None) -> Optional[str]:
    value = (
        _row_lookup(row, "Direccion")
        or _row_lookup(row, "name")
        or _row_lookup(row, "Nombre")
        or _row_lookup(row, "Unidad")
        or _row_lookup(row, "CveUnidad")
        or _row_lookup(row, "NombreEstacion")
        or _row_lookup(row, "CveMetro")
        or default
    )
    return None if value is None else str(value)


def _format_number_text(value: str) -> str:
    try:
        number = float(value.replace(",", "."))
    except ValueError:
        return value
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def parse_map_ref(raw: Any) -> tuple[Optional[float], Optional[float]]:
    """Return (lat, lng) from a combined map-reference string, or (None, None)."""
    if raw is None:
        return None, None
    text = str(raw).strip()
    if not text or text.lower() == "nan":
        return None, None

    # 1. Plain "lat,lng" with dot decimals.
    m = _LATLNG_RE.match(text)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))
        if _valid(lat, lng):
            return lat, lng

    # 2. URL — try known coordinate patterns.
    if "http" in text.lower() or "google" in text.lower() or "/" in text:
        decoded = unquote(text)
        for pat in _URL_PATTERNS:
            m = pat.search(decoded)
            if m:
                lat, lng = float(m.group(1)), float(m.group(2))
                if _valid(lat, lng):
                    return lat, lng
        try:
            qs = parse_qs(urlparse(decoded).query)
            for key in ("q", "query", "ll", "center", "destination", "daddr"):
                if key in qs:
                    mm = _LATLNG_RE.match(qs[key][0])
                    if mm:
                        lat, lng = float(mm.group(1)), float(mm.group(2))
                        if _valid(lat, lng):
                            return lat, lng
        except Exception:
            pass

    return None, None


# ---------------------------------------------------------------------------
# File reading
# ---------------------------------------------------------------------------

def read_table(content: bytes, filename: str) -> pd.DataFrame:
    """Read CSV or XLSX bytes into a DataFrame (all values as strings).

    Auto-detects:
    - Delimiter: semicolon (Spanish-locale exports), comma, or tab.
    - Encoding: UTF-8-BOM, UTF-8, Windows-1252 (cp1252), Latin-1.
    """
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xls", ".xlsm")):
        return pd.read_excel(io.BytesIO(content), dtype=str, keep_default_na=False)

    # Encoding candidates: cp1252 is the most common for Spanish Windows CSV exports.
    # Use encoding_errors='strict' so bad decodings raise and we try the next candidate.
    encodings = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
    for enc in encodings:
        for sep in (";", ",", "\t"):
            try:
                df = pd.read_csv(
                    io.BytesIO(content),
                    dtype=str,
                    keep_default_na=False,
                    sep=sep,
                    encoding=enc,
                    encoding_errors="strict",
                )
                if len(df.columns) > 1:
                    return df
            except (UnicodeDecodeError, Exception):
                continue
    # Last resort: latin-1 never raises on any byte sequence.
    for sep in (";", ",", "\t"):
        try:
            df = pd.read_csv(
                io.BytesIO(content), dtype=str, keep_default_na=False,
                sep=sep, encoding="latin-1",
            )
            if len(df.columns) > 1:
                return df
        except Exception:
            continue
    return pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False, encoding="latin-1")


# ---------------------------------------------------------------------------
# Column detection
# ---------------------------------------------------------------------------

def detect_latlon_columns(df: pd.DataFrame) -> tuple[Optional[str], Optional[str]]:
    """Return (lat_col, lng_col) if the DataFrame has explicit coordinate columns."""
    lowered = {c.lower(): c for c in df.columns}
    lat_col = next((lowered[n] for n in _LAT_NAMES if n in lowered), None)
    lng_col = next((lowered[n] for n in _LNG_NAMES if n in lowered), None)
    return lat_col, lng_col


def resolve_map_column(df: pd.DataFrame, declared: Optional[str]) -> str:
    """Pick the map column: declared > known names > first column."""
    if declared:
        if declared in df.columns:
            return declared
        lowered = {c.lower(): c for c in df.columns}
        if declared.lower() in lowered:
            return lowered[declared.lower()]
        raise ValueError(f"Declared map_column '{declared}' not found in {list(df.columns)}")

    lowered = {c.lower(): c for c in df.columns}
    for cand in DEFAULT_MAP_COLUMN_CANDIDATES:
        if cand in lowered:
            return lowered[cand]

    if len(df.columns) == 0:
        raise ValueError("Source file has no columns")
    return df.columns[0]


# ---------------------------------------------------------------------------
# Display value formatting
# ---------------------------------------------------------------------------

def _format_display_value(col: str, raw: str) -> Optional[str]:
    """Clean a display_data value.

    Returns None to skip the field entirely (NULL / empty).
    Converts age-band proportions to percentages.
    Normalises European decimal comma to dot for numeric fields.
    """
    cleaned = raw.strip()
    if not cleaned or cleaned.upper() == "NULL":
        return None

    col_stripped = col.strip()

    if _norm_key(col_stripped) == "cveunidadcercana":
        return "\n".join(part.strip() for part in cleaned.split(";") if part.strip())

    if _norm_key(col_stripped) == "frontis":
        return f"{_format_number_text(cleaned)} mts"

    if _norm_key(col_stripped) == "proyeccion":
        return f"${_format_number_text(cleaned)} MM"

    # Age-band columns: proportion (0–1) → percentage string.
    if _AGE_BAND_RE.match(col_stripped):
        try:
            f = float(cleaned.replace(",", "."))
            return f"{f * 100:.0f}%"
        except (ValueError, TypeError):
            pass

    # Single number with European comma decimal → dot.
    if _EURO_DECIMAL_RE.match(cleaned):
        return cleaned.replace(",", ".")

    return cleaned


# ---------------------------------------------------------------------------
# Candidate building
# ---------------------------------------------------------------------------

def build_candidates(
    df: pd.DataFrame,
    map_column: Optional[str],
    lat_col: Optional[str] = None,
    lng_col: Optional[str] = None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Turn DataFrame rows into candidate dicts.

    When lat_col/lng_col are provided, coordinates come from those columns and
    map_column (if any) is kept only as a display field (map_ref).
    Returns (records, parsed_count, failed_count).
    """
    records: list[dict[str, Any]] = []
    parsed = 0
    failed = 0

    # Columns that hold coordinate data are excluded from the legend.
    coord_cols = {c for c in (lat_col, lng_col) if c}
    # The map column is also excluded from the legend only when it's the sole
    # coordinate source; when lat/lng cols exist, map_column (e.g. DIRECCIÓN)
    # stays in display_data.
    legend_exclude = coord_cols if (lat_col and lng_col) else (coord_cols | ({map_column} if map_column else set()))
    display_cols = [c for c in df.columns if c not in legend_exclude]

    for _, row in df.iterrows():
        # --- Coordinates ---
        if lat_col and lng_col:
            lat = _parse_coord_float(row.get(lat_col))
            lng = _parse_coord_float(row.get(lng_col))
            # Use the map/address column as the raw reference for display, if present.
            map_ref_raw = row.get(map_column) if map_column else None
        else:
            raw = row.get(map_column)
            lat, lng = parse_map_ref(raw)
            map_ref_raw = raw

        if lat is not None and lng is not None and _valid(lat, lng):
            parsed += 1
        else:
            lat = lng = None
            failed += 1

        # --- Display data ---
        display_data: dict[str, Any] = {}
        for col in display_cols:
            raw_val = row.get(col)
            if raw_val is None:
                continue
            formatted = _format_display_value(col, str(raw_val))
            if formatted is not None:
                display_data[col] = formatted

        records.append(
            {
                "map_ref": None if map_ref_raw is None else str(map_ref_raw),
                "lat": lat,
                "lng": lng,
                "display_data": display_data,
            }
        )

    return records, parsed, failed


# ---------------------------------------------------------------------------
# Postgres ingestion helpers
# ---------------------------------------------------------------------------

def postgres_connection_settings() -> dict[str, Any]:
    """Connection settings for the dw_simi Postgres source."""
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5433")),
        "dbname": os.getenv("POSTGRES_DB", "TinderLocales"),
        # Credentials must come from the environment — never hardcode them.
        "user": os.getenv("POSTGRES_USER", ""),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
    }


def postgres_import_settings() -> dict[str, Any]:
    """Table settings for the automatic DB ingestion flow."""
    business_tables = os.getenv("BUS_TABLES")
    return {
        "schema": os.getenv("PG_SCHEMA", DEFAULT_PG_SCHEMA),
        "candidate_table": os.getenv("CAND_TABLE", DEFAULT_CANDIDATE_TABLE),
        "business_tables": tuple(
            t.strip()
            for t in (business_tables or ",".join(DEFAULT_BUSINESS_TABLES)).split(",")
            if t.strip()
        ),
    }


def postgres_candidate_min_id() -> Optional[int]:
    """Minimum SolicitudesProyecciones.ID to import, when configured."""
    raw_value = os.getenv("CANDIDATE_MIN_ID", "").strip()
    if not raw_value:
        return None
    try:
        min_id = int(raw_value)
    except ValueError as exc:
        raise ValueError("CANDIDATE_MIN_ID must be an integer.") from exc
    if min_id < 0:
        raise ValueError("CANDIDATE_MIN_ID must be zero or greater.")
    return min_id


def fetch_postgres_rows(
    table: str,
    schema: Optional[str] = None,
    connection_settings: Optional[Mapping[str, Any]] = None,
    min_id_column: Optional[str] = None,
    min_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Fetch rows from a Postgres table as dictionaries.

    psycopg2 is imported lazily so CSV/XLSX ingestion keeps working without it.
    """
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError as exc:  # pragma: no cover - depends on local env
        raise RuntimeError(
            "psycopg2 is required for Postgres ingestion. Install psycopg2-binary "
            "or run the file-based ingestion path."
        ) from exc

    settings = dict(connection_settings or postgres_connection_settings())
    schema_name = schema or postgres_import_settings()["schema"]
    params: tuple[Any, ...] = ()
    if min_id_column is not None and min_id is not None:
        sql = f'SELECT * FROM "{schema_name}"."{table}" WHERE "{min_id_column}" >= %s;'
        params = (min_id,)
    else:
        sql = f'SELECT * FROM "{schema_name}"."{table}";'
    with psycopg2.connect(**settings) as conn:  # noqa: S608
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur]


def candidate_record_from_row(
    row: Mapping[str, Any],
    project_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build a location_candidate-compatible record from one DB row."""
    lat = _parse_coord_float(_row_lookup(row, "Latitud", "latitud", "lat", "latitude"))
    lng = _parse_coord_float(
        _row_lookup(row, "Longitud", "longitud", "lng", "lon", "longitude")
    )
    has_valid_coords = lat is not None and lng is not None and _valid(lat, lng)
    map_ref = f"{lat},{lng}" if has_valid_coords else None

    row_keys = {_norm_key(k): k for k in row}
    display_data: dict[str, Any] = {}
    for column in CANDIDATE_DISPLAY_COLUMNS:
        source_column = CANDIDATE_SOURCE_COLUMNS.get(column, column)
        key = row_keys.get(_norm_key(source_column))
        if key is None:
            continue
        value = row.get(key)
        if value is None:
            continue
        if (
            _AGE_BAND_RE.match(str(column).strip())
            or _norm_key(column) in {"cveunidadcercana", "frontis", "proyeccion"}
        ):
            formatted = _format_display_value(str(column), str(value))
            if formatted is not None:
                display_data[column] = formatted
            continue
        normalized = normalize_json_value(value)
        if normalized is not None:
            display_data[column] = normalized

    record = {
        "map_ref": map_ref,
        "lat": lat if has_valid_coords else None,
        "lng": lng if has_valid_coords else None,
        "display_data": display_data,
    }
    if project_id is not None:
        record["project_id"] = project_id
    return record


def build_candidate_records_from_rows(
    rows: Iterable[Mapping[str, Any]],
    project_id: Optional[str] = None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Turn Postgres candidate rows into location_candidate records."""
    records: list[dict[str, Any]] = []
    parsed = 0
    failed = 0
    for row in rows:
        record = candidate_record_from_row(row, project_id)
        if record["lat"] is not None and record["lng"] is not None:
            parsed += 1
        else:
            failed += 1
        records.append(record)
    return records, parsed, failed


def business_record_from_row(
    row: Mapping[str, Any],
    source_table: str,
    image_url_prefix: str = DEFAULT_IMAGE_URL_PREFIX,
) -> Optional[dict[str, Any]]:
    """Build a BusinessLocation-compatible record from one POI DB row."""
    lat = _parse_coord_float(_row_lookup(row, "Latitud", "latitud", "lat", "latitude"))
    lng = _parse_coord_float(
        _row_lookup(row, "Longitud", "longitud", "lng", "lon", "longitude")
    )
    if lat is None or lng is None or not _valid(lat, lng):
        return None

    label = BUSINESS_TABLE_LABELS.get(source_table, source_table)
    image_filename = BUSINESS_IMAGE_FILENAMES.get(source_table)
    image_url = f"{image_url_prefix}/{image_filename}" if image_filename else None
    category = _row_lookup(row, "Region", "Comuna")

    attributes: dict[str, Any] = {}
    source_columns = BUSINESS_ATTRIBUTE_COLUMNS.get(source_table)
    if source_columns:
        row_keys = {_norm_key(k): k for k in row}
        for column in source_columns:
            row_key = row_keys.get(_norm_key(column))
            if row_key is None:
                continue
            normalized = normalize_json_value(row.get(row_key))
            if normalized is not None:
                attributes[column] = normalized
    else:
        for key, value in row.items():
            if _norm_key(key) in _BUSINESS_RESERVED_COLUMNS:
                continue
            normalized = normalize_json_value(value)
            if normalized is not None:
                attributes[key] = normalized

    attributes["_source_table"] = source_table
    attributes["Punto de Interes"] = label
    if image_url:
        attributes["image_url"] = image_url

    return {
        "name": _row_display_name(row, label),
        "lat": lat,
        "lng": lng,
        "category": None if category is None else str(category),
        "attributes": attributes,
    }


def build_business_records_from_rows(
    rows: Iterable[Mapping[str, Any]],
    source_table: str,
    image_url_prefix: str = DEFAULT_IMAGE_URL_PREFIX,
) -> tuple[list[dict[str, Any]], int]:
    """Turn Postgres POI rows into BusinessLocation records."""
    records: list[dict[str, Any]] = []
    failed = 0
    for row in rows:
        record = business_record_from_row(row, source_table, image_url_prefix)
        if record is None:
            failed += 1
            continue
        records.append(record)
    return records, failed


def fetch_candidate_records_from_postgres(
    project_id: Optional[str] = None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Fetch and build candidate records from the configured Postgres table."""
    settings = postgres_import_settings()
    rows = fetch_postgres_rows(
        settings["candidate_table"],
        settings["schema"],
        min_id_column="ID",
        min_id=postgres_candidate_min_id(),
    )
    return build_candidate_records_from_rows(rows, project_id)


def fetch_business_records_from_postgres() -> tuple[list[dict[str, Any]], int]:
    """Fetch and build all configured point-of-interest records from Postgres."""
    settings = postgres_import_settings()
    records: list[dict[str, Any]] = []
    failed = 0
    for table in settings["business_tables"]:
        table_rows = fetch_postgres_rows(table, settings["schema"])
        table_records, table_failed = build_business_records_from_rows(table_rows, table)
        records.extend(table_records)
        failed += table_failed
    return records, failed
