# Site Swiper — Location Selection Tool

"Tinder for site selection." Evaluate candidate geographic locations one at a time on a
Google Map with a metadata legend, then **accept / reject / star** each one. Every decision
is persisted to a local SQLite database. A global layer of existing business locations is
drawn on the map for context.

Works on both **mobile (touch)** and **desktop (mouse + keyboard)**.

---

## Quick start

```bash
# 1. Create a virtual environment and install dependencies
python -m venv .venv
.venv\Scripts\activate            # Windows PowerShell/CMD
# source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt

# 2. Set your Google Maps JavaScript API key (required for the map to render)
set GOOGLE_MAPS_API_KEY=your_key_here          # Windows CMD
# $env:GOOGLE_MAPS_API_KEY="your_key_here"     # Windows PowerShell
# export GOOGLE_MAPS_API_KEY=your_key_here     # macOS / Linux

# 3. Run
python run.py
#   …or:  uvicorn app.main:app --reload
```

Then open **http://127.0.0.1:8000**.

The SQLite database is created automatically on first run at `./data/site_swiper.db`.

> **No API key?** The app still fully works — ingestion, swiping (buttons + keyboard),
> persistence, and CSV export all run. Only the map tiles won't render; the candidate card,
> legend, and decision flow remain usable.

---

## Using the tool

1. Open the **☰ setup drawer** (top-left).
2. **Create a project** (the unit of work; everything is scoped to it).
3. **Ingest candidates**: upload a CSV/XLSX. One column holds the map reference
   (a Google Maps URL **or** a raw `lat,lng` string); all other columns become the legend.
   - The map column is auto-detected by name (`maps`, `map`, `url`, `coordinates`, …) or
     you can name it explicitly in the "Map column name" field.
4. (Optional) **Upload business locations** — a global enrichment layer shared across all
   projects (columns: `name, lat, lng, category`, plus any extras → `attributes`).
5. Swipe through candidates. **Export results** to CSV at any time.

### Sample data (run end-to-end with no external data)

- `data/sample_candidates.csv` — 12 candidate locations (mix of `lat,lng` and Maps URLs)
- `data/sample_business_locations.csv` — 12 existing business locations

### Decision controls (all three produce identical results)

| Action | Touch (mobile)      | Mouse (desktop)        | Keyboard      |
|--------|---------------------|------------------------|---------------|
| Accept | swipe **right**     | drag card right / **✓**| **→**         |
| Reject | swipe **left**      | drag card left / **✕** | **←**         |
| Star   | swipe **up**        | drag card up / **★**   | **↑** or **S**|

`star` = shortlisted / priority (a strong accept). Starred candidates get a distinct star
marker on the map and a star badge.

Decisions are **idempotent** per `(project, candidate)` — deciding the same candidate again
updates the verdict instead of creating a duplicate. On reload, only **undecided** candidates
are served, so sessions are resumable.

---

## Mobile notes

- Responsive from phone to desktop, no horizontal scroll; `viewport-fit=cover` + safe-area
  insets for notched devices.
- Tap targets ≥ 44px; the action buttons are bottom-anchored for one-handed use.
- Swipe gestures are gated to the **candidate card** (`touch-action: none`) so they never
  fight the native map pan/zoom. The legend overlay collapses on small screens.

---

## API endpoints

| Method | Path                              | Purpose                                            |
|--------|-----------------------------------|----------------------------------------------------|
| GET    | `/config`                         | Returns the Maps API key for the frontend          |
| POST   | `/projects`                       | Create a project                                   |
| GET    | `/projects`                       | List projects                                      |
| GET    | `/projects/{id}`                  | Get one project                                    |
| POST   | `/projects/{id}/ingest`           | Upload tabular file → populate candidates          |
| GET    | `/projects/{id}/next`             | Next undecided candidate + progress counts         |
| POST   | `/projects/{id}/decisions`        | Record accept/reject/star (upsert)                 |
| GET    | `/projects/{id}/results`          | Export decided candidates as CSV (incl. `verdict`) |
| GET    | `/business`                       | List global enrichment markers                     |
| POST   | `/business/ingest`                | Load/replace global business locations             |

Interactive API docs at **http://127.0.0.1:8000/docs**.

### Ingest config

`POST /projects/{id}/ingest` accepts a multipart `file` plus an optional `config` form field
(JSON or YAML) declaring the map column:

```json
{ "map_column": "maps" }
```

If omitted, the tool tries common column names, then falls back to the first column.

---

## Data model (SQLAlchemy → SQLite)

- **project** — `project_id` (UUID PK), `project_url` (separate from per-location map URLs),
  `name`, `source_file`, `notes`, `created_at`.
- **location_candidate** — `id`, `project_id` (FK), `map_ref` (raw value), `lat`, `lng`
  (parsed), `display_data` (JSON of the remaining columns → legend).
- **decision** — `id`, `project_id`, `candidate_id`, `verdict` (`accept|reject|star`),
  `note`, `decided_at`. Unique on `(project_id, candidate_id)` for idempotency.
- **business_location** — `id`, `name`, `lat`, `lng`, `category`, `attributes` (JSON).
  Global; no project FK.

---

## Map reference parsing

The map column is parsed (`app/ingestion.py`) from any of:

- Plain `lat,lng` (optionally parenthesised): `19.4326,-99.1332`, `(19.43, -99.13)`
- Google Maps URLs: `@lat,lng,zoom`, `!3dlat!4dlng`, and `?q=`/`ll=`/`center=`/`destination=`
  query forms.

Rows whose coordinates can't be parsed are still stored (and reported in the ingest summary);
candidates with coordinates are served first so the map always has a pin.

---

## Design decisions (the "open decisions" from the brief)

- **Project id ↔ URL**: PK is `project_id` (UUID); `project_url` is a separate column. *(Confirmed.)*
- **Source format**: CSV/XLSX, one map column + N display columns. *(Assumed.)*
- **Enrichment scope**: global, shared across projects, no project FK. *(Confirmed.)*
- **Star semantics**: a **third verdict** (strong-accept / shortlist), not an orthogonal flag.
  *(Confirmed default.)* To make it an orthogonal flag layered on `accept`, you'd add a boolean
  to `decision` and adjust the verdict enum — not done here per the brief's default.
- **Auth**: single-user, local, no authentication. *(Assumed.)*

---

## Project layout

```
app/
  main.py        FastAPI app + all endpoints + static serving
  database.py    Engine/session; auto-creates ./data/site_swiper.db
  models.py      SQLAlchemy ORM models
  schemas.py     Pydantic request/response schemas
  ingestion.py   pandas table reading + map-ref coordinate parsing
  static/        index.html, style.css, app.js (responsive frontend)
data/            SQLite db (auto) + sample CSVs
run.py           Convenience launcher
smoke_test.py    End-to-end API test (python smoke_test.py)
requirements.txt
```

## Tests

```bash
python smoke_test.py
```

Exercises the full flow on a temp DB: create project → ingest → next → decide (incl. upsert
idempotency) → resume → business ingest/list → CSV export.
