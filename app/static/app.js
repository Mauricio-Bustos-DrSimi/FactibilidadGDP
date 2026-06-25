/* Site Swiper — sidebar layout with embedded Street View. */
"use strict";

const State = {
  projectId: localStorage.getItem("ss_project_id") || null,
  project: null,
  current: null,
  map: null,
  candidateMarker: null,
  businessMarkers: [],
  businessVisible: true,
  mapsReady: false,
  svService: null,
  panorama: null,
  view: "map",   // "map" | "streetview"
};

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------
const $ = (id) => document.getElementById(id);
const api = async (url, opts) => {
  const res = await fetch(url, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.headers.get("content-type")?.includes("application/json")
    ? res.json()
    : res;
};

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add("hidden"), 1600);
}

// ---------------------------------------------------------------------------
// Google Maps bootstrap
// ---------------------------------------------------------------------------
async function loadGoogleMaps() {
  const cfg = await api("/config");
  if (!cfg.google_maps_api_key) {
    $("map").innerHTML =
      '<div style="padding:24px;color:#94a3b8;text-align:center;margin-top:20vh">' +
      "Google Maps API key not set.<br/>Set <code>GOOGLE_MAPS_API_KEY</code> and restart.</div>";
    State.mapsReady = false;
    return;
  }
  await new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = `https://maps.googleapis.com/maps/api/js?key=${cfg.google_maps_api_key}`;
    s.async = true;
    s.onload = resolve;
    s.onerror = () => reject(new Error("Maps failed to load"));
    document.head.appendChild(s);
  });
  initMap();
  State.mapsReady = true;
}

function initMap() {
  const el = $("map");
  console.log("[Maps] container size:", el.offsetWidth + "×" + el.offsetHeight);
  State.map = new google.maps.Map(el, {
    center: { lat: -33.45, lng: -70.67 },
    zoom: 15,
    disableDefaultUI: true,
    zoomControl: true,
    gestureHandling: "greedy",
    clickableIcons: false,
  });
  State.svService = new google.maps.StreetViewService();
}

// ---------------------------------------------------------------------------
// View toggle (map ↔ street view, full right panel)
// ---------------------------------------------------------------------------
function setView(view) {
  State.view = view;
  const toMap = view === "map";

  // Show exactly one panel via display; the other is fully removed from
  // rendering. This avoids any z-index / stacking-context ambiguity with
  // Google's internally-injected map/panorama elements.
  $("map").style.display        = toMap ? "block" : "none";
  $("streetview").style.display = toMap ? "none"  : "block";

  $("toggleViewBtn").textContent = toMap ? "📷 Street View" : "🗺️ Map";
  $("toggleViewBtn").title = toMap ? "Switch to Street View" : "Switch to Map";

  if (toMap) {
    // Re-showing the map: it must recompute its size after being display:none.
    if (State.mapsReady) {
      google.maps.event.trigger(State.map, "resize");
      if (State.current?.lat != null)
        State.map.setCenter({ lat: State.current.lat, lng: State.current.lng });
    }
  } else if (State.current?.lat != null) {
    // Re-showing street view: load/refresh the panorama, then nudge it to
    // recompute size now that its container is visible again.
    updateStreetView(State.current.lat, State.current.lng);
    if (State.panorama) google.maps.event.trigger(State.panorama, "resize");
  }
}

// ---------------------------------------------------------------------------
// Street View
// ---------------------------------------------------------------------------
function computeHeading(from, to) {
  const toRad = (d) => (d * Math.PI) / 180;
  const dLng = toRad(to.lng - from.lng);
  const lat1 = toRad(from.lat);
  const lat2 = toRad(to.lat);
  const y = Math.sin(dLng) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

function updateStreetView(lat, lng) {
  if (!State.svService) return;
  const target = { lat, lng };
  State.svService.getPanorama(
    { location: target, radius: 100, preference: google.maps.StreetViewPreference.NEAREST },
    (data, status) => {
      if (status === google.maps.StreetViewStatus.OK) {
        if (!State.panorama) {
          State.panorama = new google.maps.StreetViewPanorama($("streetview"), {
            addressControl: false,
            fullscreenControl: false,
            motionTracking: false,
            motionTrackingControl: false,
            linksControl: true,
            enableCloseButton: false,
            zoomControl: false,
          });
        }
        const svPos = data.location.latLng;
        State.panorama.setPosition(svPos);
        const heading = computeHeading(
          { lat: svPos.lat(), lng: svPos.lng() },
          target
        );
        State.panorama.setPov({ heading, pitch: 0 });
        $("svUnavailable").classList.add("hidden");
      } else {
        $("svUnavailable").classList.remove("hidden");
      }
    }
  );
}

// ---------------------------------------------------------------------------
// Markers
// ---------------------------------------------------------------------------
function setCandidateMarker(candidate) {
  if (!State.mapsReady) return;
  if (State.candidateMarker) State.candidateMarker.setMap(null);
  if (!candidate || candidate.lat == null) return;

  const pos = { lat: candidate.lat, lng: candidate.lng };
  State.candidateMarker = new google.maps.Marker({
    position: pos,
    map: State.map,
    title: candidateTitle(candidate),
    zIndex: 999,
    icon: {
      path: google.maps.SymbolPath.BACKWARD_CLOSED_ARROW,
      scale: 7,
      fillColor: "#3b82f6",
      fillOpacity: 1,
      strokeColor: "#fff",
      strokeWeight: 2,
    },
    animation: google.maps.Animation.DROP,
  });
  State.map.panTo(pos);
}

async function loadBusinessMarkers() {
  if (!State.mapsReady) return;
  State.businessMarkers.forEach((m) => m.setMap(null));
  State.businessMarkers = [];
  let items = [];
  try { items = await api("/business"); } catch (_) { return; }

  const info = new google.maps.InfoWindow();
  items.forEach((b) => {
    const m = new google.maps.Marker({
      position: { lat: b.lat, lng: b.lng },
      map: State.businessVisible ? State.map : null,
      title: b.name || b.category || "Business",
      icon: {
        path: google.maps.SymbolPath.CIRCLE,
        scale: 6,
        fillColor: "#10b981",
        fillOpacity: 0.85,
        strokeColor: "#064e3b",
        strokeWeight: 1,
      },
    });
    m.addListener("click", () => {
      const attrs = Object.entries(b.attributes || {})
        .map(([k, v]) => `<div><b>${esc(k)}:</b> ${esc(v)}</div>`)
        .join("");
      info.setContent(
        `<div style="min-width:140px"><b>${esc(b.name || "Business")}</b>` +
        (b.category ? `<div>${esc(b.category)}</div>` : "") +
        attrs + "</div>"
      );
      info.open(State.map, m);
    });
    State.businessMarkers.push(m);
  });
}

function toggleBusiness() {
  State.businessVisible = !State.businessVisible;
  $("enrichBtn").classList.toggle("active", State.businessVisible);
  State.businessMarkers.forEach((m) =>
    m.setMap(State.businessVisible ? State.map : null)
  );
}

// ---------------------------------------------------------------------------
// Candidate rendering
// ---------------------------------------------------------------------------
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function candidateTitle(c) {
  const d = c.display_data || {};
  return (
    d.DIRECCIÓN || d.Direccion || d.DIRECCION ||
    d.name || d.Name || d.title || d.address || d.Address ||
    `Candidate #${c.id}`
  );
}

const SCORE_KEYS = ["PROYECCIÓN", "PROYECCION", "score", "Score", "SCORE", "proyeccion", "proyección"];

function candidateScore(c) {
  const d = c.display_data || {};
  for (const k of SCORE_KEYS) {
    if (d[k] !== undefined && d[k] !== "") return { key: k, value: d[k] };
  }
  return null;
}

// Columns shown first, in this order (multiple variants for resilience).
const PRIORITY_COLUMNS = [
  ["NombreSolicitante"],
  ["DIVISION", "Division"],
  ["DIRECCIÓN", "Direccion", "DIRECCION"],
  ["PROYECCIÓN", "PROYECCION", "Proyeccion"],
  ["TIPOLOGÍA", "Tipologia", "TIPOLOGIA"],
  ["ValorArriendo", "Valor Arriendo"],
  ["CveUnidadCercana"],
  ["DistanciaUnidadCercana", "Distancia Unidad Cercana"],
];

// Internal IDs/emails never worth showing.
const ALWAYS_SKIP = new Set([
  "CUT", "BRICK", "IDComplemento", "FechaComplemento",
  "CorreoComplemento", "CveSimiCercano", "ID", "CorreoSolicitante",
]);

function buildDisplayRows(display_data) {
  const rows = [];
  const seen = new Set();

  // 1. Priority columns in user-defined order.
  for (const variants of PRIORITY_COLUMNS) {
    for (const key of variants) {
      if (display_data[key] !== undefined && display_data[key] !== "" && display_data[key] != null) {
        rows.push([key, display_data[key]]);
        variants.forEach((v) => seen.add(v));
        break;
      }
    }
  }

  // 2. Remaining columns not already shown and not always-skipped.
  for (const [k, v] of Object.entries(display_data)) {
    if (!seen.has(k) && !ALWAYS_SKIP.has(k) && v !== "" && v != null) {
      rows.push([k, v]);
    }
  }

  return rows;
}

function renderCandidate(c) {
  if (!c) return;
  const title = candidateTitle(c);
  $("cardTitle").textContent = title;

  // Score badge.
  const scoreInfo = candidateScore(c);
  const scoreBadge = $("scoreBadge");
  if (scoreInfo) {
    const num = parseFloat(scoreInfo.value);
    scoreBadge.textContent = `Score ${scoreInfo.value}`;
    scoreBadge.className =
      "score-badge" + (num >= 65 ? " high" : num < 50 ? " low" : "");
    scoreBadge.classList.remove("hidden");
  } else {
    scoreBadge.classList.add("hidden");
  }

  const coords =
    c.lat != null
      ? `${c.lat.toFixed(5)}, ${c.lng.toFixed(5)}`
      : "No coordinates";
  $("cardCoords").textContent = coords;

  const rows = buildDisplayRows(c.display_data || {});
  $("cardData").innerHTML =
    rows
      .map(
        ([k, v]) =>
          `<div class="legend-row"><span class="legend-key">${esc(k)}</span><span class="legend-val">${esc(v)}</span></div>`
      )
      .join("") || '<div style="color:var(--muted);font-size:13px">No extra data</div>';

  const link = $("cardMapLink");
  if (c.lat != null) {
    link.href = `https://www.google.com/maps/search/?api=1&query=${c.lat},${c.lng}`;
    link.style.display = "inline-block";
  } else if (c.map_ref && /^https?:/i.test(c.map_ref)) {
    link.href = c.map_ref;
    link.style.display = "inline-block";
  } else {
    link.style.display = "none";
  }

  $("candidatePanel").classList.remove("hidden");
  $("actions").classList.remove("hidden");
  $("emptyState").classList.add("hidden");

  setCandidateMarker(c);
  if (c.lat != null) updateStreetView(c.lat, c.lng);
}

function updateProgress(data) {
  $("progress").textContent =
    `${data.decided} of ${data.total} decided · ${data.remaining} left`;
}

// ---------------------------------------------------------------------------
// Flow
// ---------------------------------------------------------------------------
async function loadNext() {
  if (!State.projectId) {
    $("projectName").textContent = "No project — open ☰ to start";
    $("candidatePanel").classList.add("hidden");
    $("actions").classList.add("hidden");
    $("emptyState").classList.add("hidden");
    return;
  }
  const data = await api(`/projects/${State.projectId}/next`);
  updateProgress(data);
  if (data.candidate) {
    State.current = data.candidate;
    renderCandidate(data.candidate);
  } else {
    State.current = null;
    $("candidatePanel").classList.add("hidden");
    $("actions").classList.add("hidden");
    if (data.total === 0) {
      $("emptyTitle").textContent = "No candidates yet";
      $("emptyMsg").textContent =
        "Open ☰ to ingest a CSV/XLSX of candidate locations.";
    } else {
      $("emptyTitle").textContent = "All done!";
      $("emptyMsg").textContent =
        "Every candidate in this project has a decision.";
    }
    $("emptyState").classList.remove("hidden");
    if (State.candidateMarker) State.candidateMarker.setMap(null);
  }
}

async function decide(verdict) {
  if (!State.current || decide._busy) return;
  decide._busy = true;
  const candidate = State.current;
  try {
    await api(`/projects/${State.projectId}/decisions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ candidate_id: candidate.id, verdict }),
    });
    const label = { accept: "Accepted ✓", reject: "Rejected ✕", star: "Starred ★" }[verdict];
    toast(label);
    // Brief colour flash on the panel.
    const panel = $("candidatePanel");
    const flash = { accept: "#22c55e", reject: "#ef4444", star: "#f59e0b" }[verdict];
    panel.style.transition = "background-color 0.12s";
    panel.style.backgroundColor = flash + "22";
    setTimeout(() => {
      panel.style.backgroundColor = "";
      setTimeout(() => { panel.style.transition = ""; }, 150);
    }, 200);
    await new Promise((r) => setTimeout(r, 220));
    await loadNext();
  } catch (e) {
    toast("Error: " + e.message);
  } finally {
    decide._busy = false;
  }
}

// ---------------------------------------------------------------------------
// Setup drawer
// ---------------------------------------------------------------------------
async function refreshProjects() {
  const projects = await api("/projects");
  const sel = $("projectSelect");
  sel.innerHTML = "";
  const none = document.createElement("option");
  none.value = "";
  none.textContent = projects.length ? "— select a project —" : "— no projects yet —";
  sel.appendChild(none);
  projects.forEach((p) => {
    const o = document.createElement("option");
    o.value = p.project_id;
    o.textContent = p.name;
    if (p.project_id === State.projectId) o.selected = true;
    sel.appendChild(o);
  });
}

async function selectProject(id) {
  State.projectId = id || null;
  if (id) {
    localStorage.setItem("ss_project_id", id);
    State.project = await api(`/projects/${id}`);
    $("projectName").textContent = State.project.name;
  } else {
    localStorage.removeItem("ss_project_id");
    State.project = null;
  }
  await loadNext();
}

function wireDrawer() {
  $("menuBtn").onclick = async () => {
    await refreshProjects();
    $("drawer").classList.remove("hidden");
  };
  const close = () => $("drawer").classList.add("hidden");
  $("drawerClose").onclick = close;
  $("drawerBackdrop").onclick = close;

  $("projectSelect").onchange = (e) => selectProject(e.target.value);

  $("createProjectBtn").onclick = async () => {
    const name = $("newProjectName").value.trim();
    if (!name) return toast("Enter a project name");
    try {
      const p = await api("/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          project_url: $("newProjectUrl").value.trim() || null,
        }),
      });
      $("newProjectName").value = "";
      $("newProjectUrl").value = "";
      await refreshProjects();
      await selectProject(p.project_id);
      $("projectSelect").value = p.project_id;
      toast("Project created");
    } catch (e) {
      toast("Error: " + e.message);
    }
  };

  $("ingestBtn").onclick = async () => {
    if (!State.projectId) return toast("Select/create a project first");
    const f = $("candidateFile").files[0];
    if (!f) return toast("Choose a file");
    const fd = new FormData();
    fd.append("file", f);
    const mc = $("mapColumn").value.trim();
    if (mc) fd.append("config", JSON.stringify({ map_column: mc }));
    const out = $("ingestResult");
    out.textContent = "Uploading…";
    out.className = "result-msg";
    try {
      const r = await api(`/projects/${State.projectId}/ingest`, {
        method: "POST",
        body: fd,
      });
      out.textContent =
        `Created ${r.candidates_created} candidates from ${r.rows_read} rows.\n` +
        `Map column: "${r.map_column}". Parsed: ${r.parsed_coordinates}, failed: ${r.failed_coordinates}.`;
      out.className = "result-msg ok";
      await loadNext();
    } catch (e) {
      out.textContent = "Error: " + e.message;
      out.className = "result-msg err";
    }
  };

  $("businessIngestBtn").onclick = async () => {
    const f = $("businessFile").files[0];
    if (!f) return toast("Choose a file");
    const fd = new FormData();
    fd.append("file", f);
    fd.append("replace", "true");
    const out = $("businessResult");
    out.textContent = "Uploading…";
    out.className = "result-msg";
    try {
      const r = await api("/business/ingest", { method: "POST", body: fd });
      out.textContent = `Loaded ${r.locations_created} locations (failed: ${r.failed_coordinates}).`;
      out.className = "result-msg ok";
      await loadBusinessMarkers();
    } catch (e) {
      out.textContent = "Error: " + e.message;
      out.className = "result-msg err";
    }
  };

  const doExport = () => {
    if (!State.projectId) return toast("Select a project first");
    window.location.href = `/projects/${State.projectId}/results`;
  };
  $("drawerExportBtn").onclick = doExport;
  $("exportBtn").onclick = doExport;
}

// ---------------------------------------------------------------------------
// Inputs: buttons + keyboard
// ---------------------------------------------------------------------------
function wireInputs() {
  $("acceptBtn").onclick = () => decide("accept");
  $("rejectBtn").onclick = () => decide("reject");
  $("starBtn").onclick   = () => decide("star");
  $("enrichBtn").onclick = toggleBusiness;
  $("toggleViewBtn").onclick = () => setView(State.view === "map" ? "streetview" : "map");

  document.addEventListener("keydown", (e) => {
    const t = e.target;
    if (t instanceof Element && t.matches("input, textarea, select")) return;
    if (!State.current) return;
    if (e.key === "ArrowRight") { e.preventDefault(); decide("accept"); }
    else if (e.key === "ArrowLeft")  { e.preventDefault(); decide("reject"); }
    else if (e.key === "ArrowUp" || e.key.toLowerCase() === "s") {
      e.preventDefault(); decide("star");
    }
  });
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
async function boot() {
  wireDrawer();
  wireInputs();
  try { await loadGoogleMaps(); } catch (e) { console.warn(e); }
  try { await loadBusinessMarkers(); } catch (_) {}
  if (State.projectId) {
    try { await selectProject(State.projectId); }
    catch (_) { await selectProject(null); }
  } else {
    await loadNext();
  }
}

boot();
