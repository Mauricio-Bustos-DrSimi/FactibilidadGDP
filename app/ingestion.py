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

    # Age-band columns: proportion (0–1) → percentage string.
    if _AGE_BAND_RE.match(col_stripped):
        try:
            f = float(cleaned.replace(",", "."))
            return f"{f * 100:.1f}%"
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
