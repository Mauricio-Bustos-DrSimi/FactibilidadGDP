/* Site Swiper — authenticated, multi-layer review UI. */
"use strict";

const State = {
  user: null,
  current: null,
  map: null,
  candidateMarker: null,
  businessMarkers: [],
  businessVisible: true,
  mapsReady: false,
  svService: null,
  panorama: null,
  view: "map", // "map" | "streetview"
};

const ROLE_LABEL = {
  coordinator: "Coordinator",
  manager: "Manager",
  director: "Director",
  sysadmin: "Sysadmin",
};

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------
const $ = (id) => document.getElementById(id);
const api = async (url, opts = {}) => {
  const res = await fetch(url, { credentials: "same-origin", ...opts });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    const err = new Error(detail);
    err.status = res.status;
    throw err;
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

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

// ---------------------------------------------------------------------------
// Google Maps bootstrap  (unchanged — legacy loader, no &loading=async)
// ---------------------------------------------------------------------------
let _mapsLoading = null;
async function loadGoogleMaps() {
  if (State.mapsReady) return;
  if (_mapsLoading) return _mapsLoading;
  const cfg = await api("/config");
  if (!cfg.google_maps_api_key) {
    $("map").innerHTML =
      '<div style="padding:24px;color:#94a3b8;text-align:center;margin-top:20vh">' +
      "Google Maps API key not set.<br/>Set <code>GOOGLE_MAPS_API_KEY</code> and restart.</div>";
    State.mapsReady = false;
    return;
  }
  _mapsLoading = new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = `https://maps.googleapis.com/maps/api/js?key=${cfg.google_maps_api_key}`;
    s.async = true;
    s.onload = resolve;
    s.onerror = () => reject(new Error("Maps failed to load"));
    document.head.appendChild(s);
  });
  await _mapsLoading;
  initMap();
  State.mapsReady = true;
}

function initMap() {
  State.map = new google.maps.Map($("map"), {
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
// View toggle (map <-> street view) — display-based, full right panel
// ---------------------------------------------------------------------------
function setView(view) {
  State.view = view;
  const toMap = view === "map";
  $("map").style.display = toMap ? "block" : "none";
  $("streetview").style.display = toMap ? "none" : "block";
  $("toggleViewBtn").textContent = toMap ? "📷 Street View" : "🗺️ Map";
  $("toggleViewBtn").title = toMap ? "Switch to Street View" : "Switch to Map";

  if (toMap) {
    if (State.mapsReady) {
      google.maps.event.trigger(State.map, "resize");
      if (State.current?.lat != null)
        State.map.setCenter({ lat: State.current.lat, lng: State.current.lng });
    }
  } else if (State.current?.lat != null) {
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
        const heading = computeHeading({ lat: svPos.lat(), lng: svPos.lng() }, target);
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
const BUSINESS_SOURCE_META = {
  PI_Ahumada: { label: "Farmacia Ahumada", image: "/images/Ahumada.png" },
  PI_CruzVerde: { label: "Farmacia Cruz Verde", image: "/images/CruzVerde.png" },
  PI_Salcobrand: { label: "Farmacia Salcobrand", image: "/images/Salcobrand.png" },
  PI_Maicao: { label: "Maicao", image: "/images/Maicao.png" },
  PI_EstacionesMetro: { label: "Estacion de Metro", image: "/images/EstacionesMetro.png" },
};

const BUSINESS_POPUP_ORDER = {
  PI_Ahumada: [
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
    "Punto de Interes",
  ],
  PI_CruzVerde: [
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
    "Punto de Interes",
  ],
  PI_Salcobrand: [
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
    "Punto de Interes",
  ],
  PI_Maicao: [
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
    "Punto de Interes",
  ],
  PI_EstacionesMetro: [
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
    "Punto de Interes",
  ],
};

function businessMeta(b) {
  const attrs = b.attributes || {};
  const source = attrs._source_table;
  if (source && BUSINESS_SOURCE_META[source]) return BUSINESS_SOURCE_META[source];

  const text = `${attrs["Punto de Interes"] || ""} ${b.name || ""} ${b.category || ""}`.toLowerCase();
  if (text.includes("cruz verde")) return BUSINESS_SOURCE_META.PI_CruzVerde;
  if (text.includes("salcobrand")) return BUSINESS_SOURCE_META.PI_Salcobrand;
  if (text.includes("maicao")) return BUSINESS_SOURCE_META.PI_Maicao;
  if (text.includes("metro")) return BUSINESS_SOURCE_META.PI_EstacionesMetro;
  if (text.includes("ahumada")) return BUSINESS_SOURCE_META.PI_Ahumada;
  return null;
}

function businessIcon(b) {
  const attrs = b.attributes || {};
  const meta = businessMeta(b);
  const url = attrs.image_url || meta?.image;
  if (!url) {
    return {
      path: google.maps.SymbolPath.CIRCLE,
      scale: 6,
      fillColor: "#10b981",
      fillOpacity: 0.85,
      strokeColor: "#064e3b",
      strokeWeight: 1,
    };
  }
  return {
    url,
    scaledSize: new google.maps.Size(34, 34),
    anchor: new google.maps.Point(17, 17),
  };
}

function businessInfoHtml(b) {
  const attrs = b.attributes || {};
  const meta = businessMeta(b);
  const title = b.name || meta?.label || b.category || "Punto de interes";
  const internalKeys = new Set(["_source_table", "image_url"]);
  const orderedKeys = BUSINESS_POPUP_ORDER[attrs._source_table] || [];
  const seen = new Set();
  const orderedEntries = orderedKeys
    .filter((k) => attrs[k] !== undefined && attrs[k] !== null && attrs[k] !== "")
    .map((k) => {
      seen.add(k);
      return [k, attrs[k]];
    });
  const remainingEntries = Object.entries(attrs)
    .filter(([k, v]) => !internalKeys.has(k) && !seen.has(k) && v !== undefined && v !== null && v !== "");
  const rows = orderedEntries.concat(remainingEntries)
    .map(([k, v]) => `<div><b>${esc(k)}:</b> ${esc(v)}</div>`)
    .join("");
  const logo = attrs.image_url || meta?.image;
  const logoHtml = logo
    ? `<img src="${esc(logo)}" alt="" style="width:34px;height:34px;object-fit:contain;margin-right:8px" />`
    : "";
  return `<div style="min-width:160px">
    <div style="display:flex;align-items:center;margin-bottom:6px">${logoHtml}<b>${esc(title)}</b></div>` +
    (b.category ? `<div>${esc(b.category)}</div>` : "") +
    rows + "</div>";
}

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
      title: b.name || businessMeta(b)?.label || b.category || "Business",
      icon: businessIcon(b),
    });
    m.addListener("click", () => {
      info.setContent(businessInfoHtml(b));
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

function numericValue(raw) {
  const cleaned = String(raw ?? "").replace(/[^\d,.-]/g, "").replace(",", ".");
  const value = parseFloat(cleaned);
  return Number.isFinite(value) ? value : null;
}

const PRIORITY_COLUMNS = [
  ["ID Proyección", "ID"],
  ["NombreSolicitante"],
  ["DIRECCIÓN", "Direccion", "DIRECCION"],
  ["FRONTIS"],
  ["DIVISION", "Division"],
  ["TIPOLOGÍA", "Tipologia", "TIPOLOGIA"],
  ["FECHA"],
  ["ESTATUS"],
  ["<30"],
  ["30-40"],
  ["40-50"],
  ["50-60"],
  ["60-75"],
  ["75<"],
  ["PROYECCIÓN", "PROYECCION", "Proyeccion"],
  ["Latitud"],
  ["Longitud"],
  ["MT2"],
  ["ValorArriendo", "Valor Arriendo"],
  ["GastosComunes"],
  ["ValorGGCC"],
  ["VentaVariable"],
  ["ValorVentaVariable"],
  ["CveUnidadCercana"],
  ["TipoEstatus"],
  ["IDProyeccionCercano"],
];
const ALWAYS_SKIP = new Set([
  "CUT", "BRICK", "IDComplemento", "FechaComplemento",
  "CorreoComplemento", "CveSimiCercano", "CorreoSolicitante",
]);

function buildDisplayRows(display_data) {
  const rows = [];
  const seen = new Set();
  for (const variants of PRIORITY_COLUMNS) {
    for (const key of variants) {
      if (display_data[key] !== undefined && display_data[key] !== "" && display_data[key] != null) {
        rows.push([key, display_data[key]]);
        variants.forEach((v) => seen.add(v));
        break;
      }
    }
  }
  for (const [k, v] of Object.entries(display_data)) {
    if (!seen.has(k) && !ALWAYS_SKIP.has(k) && v !== "" && v != null) {
      rows.push([k, v]);
    }
  }
  return rows;
}

const ACTION_LABEL = {
  accept: "Approved ✓", reject: "Rejected ✕", star: "Starred ★",
  skip: "Skipped ⤼", send_back: "Sent back ↩", reopen: "Reopened ⟳",
};

function renderCandidate(c) {
  if (!c) return;
  $("cardTitle").textContent = candidateTitle(c);

  // Returned banner.
  const banner = $("returnedBanner");
  if (c.status === "returned") {
    banner.textContent = "↩ Returned to your layer for re-review";
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }

  // Score badge.
  const scoreInfo = candidateScore(c);
  const scoreBadge = $("scoreBadge");
  if (scoreInfo) {
    const num = numericValue(scoreInfo.value);
    scoreBadge.textContent = `Score ${scoreInfo.value}`;
    scoreBadge.className = "score-badge" + (num != null && num >= 65 ? " high" : num != null && num < 50 ? " low" : "");
    scoreBadge.classList.remove("hidden");
  } else {
    scoreBadge.classList.add("hidden");
  }

  $("cardCoords").textContent =
    c.lat != null ? `${c.lat.toFixed(5)}, ${c.lng.toFixed(5)}` : "No coordinates";

  const rows = buildDisplayRows(c.display_data || {});
  $("cardData").innerHTML =
    rows.map(([k, v]) =>
      `<div class="legend-row"><span class="legend-key">${esc(k)}</span><span class="legend-val">${esc(v)}</span></div>`
    ).join("") || '<div style="color:var(--muted);font-size:13px">No extra data</div>';

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

  $("noteInput").value = "";
  $("candidatePanel").classList.remove("hidden");
  $("reviewControls").classList.remove("hidden");
  $("emptyState").classList.add("hidden");

  setCandidateMarker(c);
  if (c.lat != null) updateStreetView(c.lat, c.lng);
}

async function loadHistory(candidateId) {
  const section = $("historySection");
  const list = $("historyList");
  let reviews = [];
  try { reviews = await api(`/candidates/${candidateId}/reviews`); } catch (_) {}
  // Show only prior actions (anything already recorded for this candidate).
  if (!reviews.length) {
    section.classList.add("hidden");
    list.innerHTML = "";
    return;
  }
  list.innerHTML = reviews.map((r) => {
    const when = new Date(r.created_at).toLocaleDateString();
    const who = `${ROLE_LABEL[r.reviewer_role] || r.reviewer_role || "?"}`;
    const note = r.note ? `<div class="hist-note">“${esc(r.note)}”</div>` : "";
    return `<div class="hist-row">
      <div class="hist-head"><span class="hist-action act-${esc(r.action)}">${esc(ACTION_LABEL[r.action] || r.action)}</span>
      <span class="hist-meta">${esc(who)} · ${esc(when)}</span></div>${note}</div>`;
  }).join("");
  section.classList.remove("hidden");
}

// ---------------------------------------------------------------------------
// Reviewer flow
// ---------------------------------------------------------------------------
async function loadQueue() {
  const data = await api("/queue");
  $("progress").textContent =
    data.remaining > 0 ? `${data.remaining} in your queue` : "Queue empty";
  if (data.candidate) {
    State.current = data.candidate;
    renderCandidate(data.candidate);
    loadHistory(data.candidate.id);
  } else {
    State.current = null;
    $("candidatePanel").classList.add("hidden");
    $("reviewControls").classList.add("hidden");
    $("emptyState").classList.remove("hidden");
    $("emptyTitle").textContent = "Queue empty";
    $("emptyMsg").textContent = "Nothing to review in your layer right now.";
  }
}

async function decide(action) {
  if (!State.current || decide._busy) return;
  decide._busy = true;
  const candidate = State.current;
  const note = $("noteInput").value.trim() || null;
  try {
    await api(`/candidates/${candidate.id}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, note }),
    });
    toast(ACTION_LABEL[action] || "Done");
    await flashPanel(action);
    await loadQueue();
  } catch (e) {
    toast("Error: " + e.message);
  } finally {
    decide._busy = false;
  }
}

async function sendBack() {
  if (!State.current || decide._busy) return;
  decide._busy = true;
  const candidate = State.current;
  const note = $("noteInput").value.trim() || null;
  try {
    await api(`/candidates/${candidate.id}/send-back`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    });
    toast("Sent back ↩");
    await loadQueue();
  } catch (e) {
    toast("Error: " + e.message);
  } finally {
    decide._busy = false;
  }
}

function flashPanel(action) {
  const panel = $("candidatePanel");
  const flash = {
    accept: "#22c55e", reject: "#ef4444", star: "#f59e0b", skip: "#64748b",
  }[action] || "#64748b";
  panel.style.transition = "background-color 0.12s";
  panel.style.backgroundColor = flash + "22";
  return new Promise((r) =>
    setTimeout(() => {
      panel.style.backgroundColor = "";
      setTimeout(() => { panel.style.transition = ""; }, 150);
      r();
    }, 180)
  );
}

// ---------------------------------------------------------------------------
// Sysadmin dashboard
// ---------------------------------------------------------------------------
async function showDashboard() {
  $("dashboard").classList.remove("hidden");
  $("candidatePanel").classList.add("hidden");
  $("reviewControls").classList.add("hidden");
  $("emptyState").classList.add("hidden");
  $("progress").textContent = "Oversight";
  await refreshStats();
  await refreshDashProjects();
}

async function refreshStats() {
  let s;
  try { s = await api("/stats"); } catch (_) { return; }
  const cells = [
    ["Coordinator", s.queues.coordinator, "stage"],
    ["Manager", s.queues.manager, "stage"],
    ["Director", s.queues.director, "stage"],
    ["Approved", s.statuses.approved_final, "ok"],
    ["Rejected", s.statuses.rejected, "bad"],
    ["Total", s.total, "muted"],
  ];
  $("statsGrid").innerHTML = cells.map(([label, n, kind]) =>
    `<div class="stat-card stat-${kind}"><div class="stat-num">${n}</div><div class="stat-label">${label}</div></div>`
  ).join("");
}

async function refreshDashProjects() {
  let projects = [];
  try { projects = await api("/projects"); } catch (_) {}
  $("dashProjects").innerHTML = projects.length
    ? projects.map((p) =>
        `<div class="dash-proj-row"><span>${esc(p.name)}</span>
         <a href="/projects/${p.project_id}/results" class="proj-export">Export ↓</a></div>`
      ).join("")
    : '<div class="hint-text">No projects yet — open Setup to create one.</div>';
}

// ---------------------------------------------------------------------------
// Setup drawer (sysadmin)
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
    sel.appendChild(o);
  });
}

async function refreshUsers() {
  let users = [];
  try { users = await api("/users"); } catch (_) { return; }
  $("userList").innerHTML = users.map((u) =>
    `<div class="user-row"><span>${esc(u.name)}</span><span class="user-role">${esc(ROLE_LABEL[u.role] || u.role)}</span></div>`
  ).join("");
}

function selectedProjectId() {
  return $("projectSelect").value || null;
}

function wireDrawer() {
  const openDrawer = async () => {
    await Promise.all([refreshProjects(), refreshUsers()]);
    $("drawer").classList.remove("hidden");
  };
  $("menuBtn").onclick = openDrawer;
  $("dashManageBtn").onclick = openDrawer;
  const close = () => $("drawer").classList.add("hidden");
  $("drawerClose").onclick = close;
  $("drawerBackdrop").onclick = close;

  $("createUserBtn").onclick = async () => {
    const out = $("userResult");
    const body = {
      name: $("newUserName").value.trim(),
      email: $("newUserEmail").value.trim(),
      password: $("newUserPassword").value,
      role: $("newUserRole").value,
    };
    if (!body.name || !body.email || !body.password) {
      out.textContent = "Name, email and password are required.";
      out.className = "result-msg err";
      return;
    }
    try {
      await api("/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      out.textContent = `Created ${body.name} (${body.role}).`;
      out.className = "result-msg ok";
      $("newUserName").value = $("newUserEmail").value = $("newUserPassword").value = "";
      await refreshUsers();
    } catch (e) {
      out.textContent = "Error: " + e.message;
      out.className = "result-msg err";
    }
  };

  $("createProjectBtn").onclick = async () => {
    const name = $("newProjectName").value.trim();
    if (!name) return toast("Enter a project name");
    try {
      await api("/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, project_url: $("newProjectUrl").value.trim() || null }),
      });
      $("newProjectName").value = "";
      $("newProjectUrl").value = "";
      await refreshProjects();
      await refreshDashProjects();
      toast("Project created");
    } catch (e) {
      toast("Error: " + e.message);
    }
  };

  $("ingestBtn").onclick = async () => {
    const pid = selectedProjectId();
    if (!pid) return toast("Select/create a project first");
    const f = $("candidateFile").files[0];
    if (!f) return toast("Choose a file");
    const out = $("ingestResult");
    const fd = new FormData();
    fd.append("file", f);
    const mc = $("mapColumn").value.trim();
    if (mc) fd.append("config", JSON.stringify({ map_column: mc }));
    out.textContent = "Uploading…";
    out.className = "result-msg";
    try {
      const r = await api(`/projects/${pid}/ingest`, { method: "POST", body: fd });
      out.textContent = `Created ${r.candidates_created} candidates (${r.parsed_coordinates} with coords).`;
      out.className = "result-msg ok";
      await refreshStats();
    } catch (e) {
      out.textContent = "Error: " + e.message;
      out.className = "result-msg err";
    }
  };

  $("businessIngestBtn").onclick = async () => {
    const f = $("businessFile").files[0];
    if (!f) return toast("Choose a file");
    const out = $("businessResult");
    const fd = new FormData();
    fd.append("file", f);
    fd.append("replace", "true");
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

  $("drawerExportBtn").onclick = () => {
    const pid = selectedProjectId();
    if (!pid) return toast("Select a project first");
    window.location.href = `/projects/${pid}/results`;
  };
}

// ---------------------------------------------------------------------------
// Inputs: buttons + keyboard
// ---------------------------------------------------------------------------
function wireInputs() {
  $("acceptBtn").onclick = () => decide("accept");
  $("rejectBtn").onclick = () => decide("reject");
  $("starBtn").onclick = () => decide("star");
  $("skipBtn").onclick = () => decide("skip");
  $("sendBackBtn").onclick = sendBack;
  $("enrichBtn").onclick = toggleBusiness;
  $("toggleViewBtn").onclick = () => setView(State.view === "map" ? "streetview" : "map");
  $("logoutBtn").onclick = async () => {
    try { await api("/auth/logout", { method: "POST" }); } catch (_) {}
    location.reload();
  };

  document.addEventListener("keydown", (e) => {
    const t = e.target;
    if (t instanceof Element && t.matches("input, textarea, select")) return;
    if (!State.current) return;
    const k = e.key.toLowerCase();
    if (e.key === "ArrowRight") { e.preventDefault(); decide("accept"); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); decide("reject"); }
    else if (e.key === "ArrowDown" || k === "k") { e.preventDefault(); decide("skip"); }
    else if (e.key === "ArrowUp" || k === "s") { e.preventDefault(); decide("star"); }
  });
}

// ---------------------------------------------------------------------------
// Auth + boot
// ---------------------------------------------------------------------------
function showLogin() {
  $("loginScreen").classList.remove("hidden");
  $("sidebar").classList.add("hidden");
  $("toggleViewBtn").classList.add("hidden");
}

function wireLogin() {
  $("loginForm").onsubmit = async (e) => {
    e.preventDefault();
    const err = $("loginError");
    err.textContent = "";
    try {
      await api("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: $("loginEmail").value.trim(),
          password: $("loginPassword").value,
        }),
      });
      location.reload();
    } catch (ex) {
      err.textContent = ex.message || "Login failed";
    }
  };
}

async function startApp(user) {
  State.user = user;
  $("loginScreen").classList.add("hidden");
  $("sidebar").classList.remove("hidden");

  const isSysadmin = user.role === "sysadmin";
  const isReviewer = ["coordinator", "manager", "director"].includes(user.role);
  const canSendBack = ["manager", "director"].includes(user.role);

  $("projectName").textContent = `${user.name} · ${ROLE_LABEL[user.role] || user.role}`;
  $("menuBtn").classList.toggle("hidden", !isSysadmin);
  $("sendBackBtn").classList.toggle("hidden", !canSendBack);
  $("toggleViewBtn").classList.remove("hidden");

  try { await loadGoogleMaps(); } catch (e) { console.warn(e); }
  try { await loadBusinessMarkers(); } catch (_) {}

  if (isSysadmin) {
    await showDashboard();
  } else if (isReviewer) {
    await loadQueue();
  }
}

async function boot() {
  wireLogin();
  wireDrawer();
  wireInputs();
  let me = null;
  try { me = await api("/me"); } catch (_) { /* 401 */ }
  if (me) await startApp(me);
  else showLogin();
}

boot();
