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
  tableGroup: "pending",
  tableCandidates: [],
  tableDateFilters: {
    pending: { from: "", to: "" },
    rejected: { from: "", to: "" },
    suggested: { from: "", to: "" },
    approved: { from: "", to: "" },
    project: { from: "", to: "" },
  },
};

const ROLE_LABEL = {
  jefatura: "Jefatura",
  comite: "Comité",
  gerente: "Gerente",
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
  $("toggleViewBtn").textContent = toMap ? "Street View" : "Mapa";
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
  LocalesSimi: { label: "Locales Simi", image: "/images/DrSimi.png" },
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
  LocalesSimi: [
    "CveUnidad",
    "Unidad",
    "Comuna",
    "Latitud",
    "Longitud",
    "Estatus",
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
  if (text.includes("simi")) return BUSINESS_SOURCE_META.LocalesSimi;
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

function isDateKey(key) {
  return /fecha/i.test(String(key));
}

function displayRowValue(key, value) {
  return isDateKey(key) ? formatTableDate(value) : value;
}

function buildDisplayRows(display_data) {
  const rows = [];
  const seen = new Set();
  for (const variants of PRIORITY_COLUMNS) {
    for (const key of variants) {
      if (display_data[key] !== undefined && display_data[key] !== "" && display_data[key] != null) {
        rows.push([key, displayRowValue(key, display_data[key])]);
        variants.forEach((v) => seen.add(v));
        break;
      }
    }
  }
  for (const [k, v] of Object.entries(display_data)) {
    if (!seen.has(k) && !ALWAYS_SKIP.has(k) && v !== "" && v != null) {
      rows.push([k, displayRowValue(k, v)]);
    }
  }
  return rows;
}

function displayValue(c, keys) {
  const d = c.display_data || {};
  for (const key of keys) {
    if (d[key] !== undefined && d[key] !== null && d[key] !== "") return d[key];
  }
  return "";
}

function resizeMapSoon() {
  setTimeout(() => {
    if (State.map && window.google?.maps) google.maps.event.trigger(State.map, "resize");
  }, 80);
}

function sidebarMaxWidth() {
  return Math.min(560, Math.max(320, window.innerWidth - 420));
}

function setSidebarWidth(width) {
  const next = Math.max(260, Math.min(sidebarMaxWidth(), Math.round(width)));
  document.documentElement.style.setProperty("--sidebar-active-w", `${next}px`);
  try { localStorage.setItem("sidebarWidth", String(next)); } catch (_) {}
  resizeMapSoon();
}

function initSidebarWidth() {
  let saved = 340;
  try { saved = Number(localStorage.getItem("sidebarWidth")) || 340; } catch (_) {}
  setSidebarWidth(saved);
}

function wireSidebarResize() {
  const handle = $("sidebarResizeHandle");
  handle.onpointerdown = (e) => {
    if (document.body.classList.contains("sidebar-collapsed")) return;
    e.preventDefault();
    handle.setPointerCapture(e.pointerId);
    document.body.classList.add("sidebar-resizing");

    const onMove = (moveEvent) => setSidebarWidth(moveEvent.clientX);
    const onEnd = () => {
      document.body.classList.remove("sidebar-resizing");
      handle.removeEventListener("pointermove", onMove);
      handle.removeEventListener("pointerup", onEnd);
      handle.removeEventListener("pointercancel", onEnd);
    };

    handle.addEventListener("pointermove", onMove);
    handle.addEventListener("pointerup", onEnd);
    handle.addEventListener("pointercancel", onEnd);
  };

  window.addEventListener("resize", () => {
    const current = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--sidebar-active-w"), 10) || 340;
    setSidebarWidth(current);
  });
}

function candidateGroup(c) {
  if (c.status === "locales_proyecto") return "project";
  if (c.status === "approved_final") return "approved";
  if (c.status === "rejected") return "rejected";
  if (c.status === "suggested") return "suggested";
  if (c.last_decision === "project") return "project";
  if (c.last_decision === "reject") return "rejected";
  if (c.last_decision === "like") return "suggested";
  if (c.last_decision === "accept" || c.last_decision === "star") return "approved";
  return "pending";
}

function groupLabel(group) {
  return { pending: "Pendiente", suggested: "Sugerido", approved: "Aprobado", rejected: "Rechazado", project: "Local Proyecto" }[group] || group;
}

function groupExportLabel(group) {
  return {
    pending: "Pendientes",
    suggested: "Sugeridos",
    approved: "Aprobados",
    rejected: "Rechazados",
    project: "Locales Proyecto",
  }[group] || groupLabel(group);
}

function formatTableDate(value) {
  if (!value) return "";
  let raw = String(value).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    raw = `${raw}T00:00:00Z`;
  } else if (/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(raw)) {
    raw = raw.replace(" ", "T") + "Z";
  }
  const date = new Date(raw);
  if (!Number.isNaN(date.getTime())) {
    return date.toLocaleString("es-CL", {
      timeZone: "America/Santiago",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }
  return String(value);
}

function parseUtcLikeDate(value) {
  if (!value) return null;
  let raw = String(value).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    raw = `${raw}T00:00:00Z`;
  } else if (/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(raw)) {
    raw = raw.replace(" ", "T") + "Z";
  }
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? null : date;
}

function santiagoDateKey(value) {
  const date = parseUtcLikeDate(value);
  if (!date) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Santiago",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${byType.year}-${byType.month}-${byType.day}`;
}

function candidateTableDateRaw(c, group) {
  const dates = c.workflow_dates || {};
  if (group === "pending") return displayValue(c, ["FECHA", "Fecha", "fecha"]);
  if (group === "suggested") return dates.jefatura_like;
  if (group === "approved") return dates.comite_approved;
  if (group === "rejected") return dates.rejected;
  if (group === "project") return dates.project;
  return "";
}

function candidateTableDate(c, group) {
  return formatTableDate(candidateTableDateRaw(c, group));
}

function candidateMatchesDateFilter(c, group) {
  const filter = State.tableDateFilters[group] || { from: "", to: "" };
  if (!filter.from && !filter.to) return true;
  const key = santiagoDateKey(candidateTableDateRaw(c, group));
  if (!key) return false;
  if (filter.from && key < filter.from) return false;
  if (filter.to && key > filter.to) return false;
  return true;
}

function syncTableDateFilterInputs() {
  const filter = State.tableDateFilters[State.tableGroup] || { from: "", to: "" };
  $("tableDateFrom").value = filter.from || "";
  $("tableDateTo").value = filter.to || "";
}

function tableCounts(items) {
  return items.reduce((acc, c) => {
    acc[candidateGroup(c)] += 1;
    return acc;
  }, { pending: 0, suggested: 0, approved: 0, rejected: 0, project: 0 });
}

async function openCandidateTable() {
  $("candidateTableView").classList.remove("hidden");
  await refreshCandidateTable();
}

function closeCandidateTable() {
  $("candidateTableView").classList.add("hidden");
}

function exportCandidateExcel(allGroups = false) {
  const params = new URLSearchParams();
  if (allGroups) params.set("all_groups", "true");
  else params.set("group", State.tableGroup);
  window.location.href = `/candidates/export.xlsx?${params.toString()}`;
}

async function refreshCandidateTable() {
  let items = [];
  try { items = await api("/candidates"); } catch (e) { toast("Error: " + e.message); return; }
  State.tableCandidates = items;
  renderCandidateTable();
}

function renderCandidateTable() {
  const counts = tableCounts(State.tableCandidates);
  $("pendingCount").textContent = counts.pending;
  $("suggestedCount").textContent = counts.suggested;
  $("approvedCount").textContent = counts.approved;
  $("rejectedCount").textContent = counts.rejected;
  $("projectCount").textContent = counts.project;
  $("exportCurrentTableBtn").textContent = `Exportar ${groupExportLabel(State.tableGroup)}`;
  syncTableDateFilterInputs();

  document.querySelectorAll(".table-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.group === State.tableGroup);
  });

  const rows = State.tableCandidates.filter((c) =>
    candidateGroup(c) === State.tableGroup && candidateMatchesDateFilter(c, State.tableGroup)
  );
  const totalGroupRows = counts[State.tableGroup] || 0;
  $("tableCount").textContent = `${rows.length} de ${totalGroupRows} locales`;
  $("candidateTableBody").innerHTML = rows.length
    ? rows.map((c) => tableRowHtml(c)).join("")
    : `<tr><td colspan="9" class="table-empty">Sin locales en ${esc(groupLabel(State.tableGroup).toLowerCase())}</td></tr>`;

  document.querySelectorAll("[data-table-status]").forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      updateCandidateGroup(Number(btn.dataset.id), btn.dataset.tableStatus);
    };
  });
  document.querySelectorAll("[data-candidate-row]").forEach((row) => {
    row.onclick = () => selectCandidateFromTable(Number(row.dataset.candidateRow));
  });
  fitActionColumnWidth();
}

function tableRowHtml(c) {
  const idProj = displayValue(c, ["ID Proyección", "ID Proyeccion", "ID ProyecciÃ³n", "ID"]) || c.id;
  const address = displayValue(c, ["DIRECCIÓN", "DIRECCION", "Direccion", "DIRECCIÃ“N"]) || candidateTitle(c);
  const applicant = displayValue(c, ["NombreSolicitante"]) || "";
  const proyeccion = displayValue(c, ["PROYECCIÓN", "PROYECCION", "PROYECCIÃ“N"]) || "";
  const group = candidateGroup(c);
  const date = candidateTableDate(c, group);
  const rejectNote = c.last_reject_note || "";
  const actions = candidateTableActions(group).map(([target, label]) =>
    `<button class="table-action status-${esc(target)}" data-id="${c.id}" data-table-status="${target}" ${target === group ? "disabled" : ""}>${esc(label)}</button>`
  ).join("");
  return `<tr data-candidate-row="${c.id}">
    <td class="resizable-col">${esc(idProj)}</td>
    <td class="resizable-col col-address" title="${esc(address)}">${esc(address)}</td>
    <td>${esc(applicant)}</td>
    <td>${esc(proyeccion)}</td>
    <td>${esc(date)}</td>
    <td>${esc(c.current_stage)}</td>
    <td><span class="table-status ${esc(group)}">${esc(groupLabel(group))}</span></td>
    <td>${esc(rejectNote)}</td>
    <td><div class="table-actions">${actions}</div></td>
  </tr>`;
}

async function updateCandidateGroup(candidateId, group) {
  let note = "Cambio desde vista tabla";
  const candidate = State.tableCandidates.find((c) => c.id === candidateId);
  const currentGroup = candidate ? candidateGroup(candidate) : "";
  if (group === "rejected") {
    note = prompt("Ingrese comentario de rechazo:");
    if (!note || !note.trim()) return toast("Comentario requerido");
  } else if (State.user?.role === "jefatura" && currentGroup === "rejected" && group === "suggested") {
    note = prompt("Ingrese comentario para volver a sugerir:");
    if (!note || !note.trim()) return toast("Comentario requerido");
  }
  try {
    await api(`/candidates/${candidateId}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ group, note }),
    });
    toast("Estado actualizado");
    await refreshCandidateTable();
    await refreshStats();
    if (State.current?.id === candidateId) {
      const updated = State.tableCandidates.find((c) => c.id === candidateId);
      if (updated) {
        State.current = updated;
        renderCandidate(updated);
        loadHistory(updated.id);
      }
    }
  } catch (e) {
    toast("Error: " + e.message);
  }
}

function selectCandidateFromTable(candidateId) {
  const candidate = State.tableCandidates.find((c) => c.id === candidateId);
  if (!candidate) return;
  State.current = candidate;
  $("dashboard").classList.add("hidden");
  $("emptyState").classList.add("hidden");
  renderCandidate(candidate);
  loadHistory(candidate.id);
}

function candidateTableActions(group) {
  const role = State.user?.role;
  if (role === "sysadmin") {
    return [["skip", "Skip"], ["pending", "Pendiente"], ["suggested", "Sugerido"], ["approved", "Aprobar"], ["rejected", "Rechazar"], ["project", "Proyecto"]];
  }
  if (role === "jefatura" && group === "pending") {
    return [["suggested", "\u{1F44D}"], ["rejected", "\u{1F44E}"]];
  }
  if (role === "jefatura" && group === "suggested") {
    return [["rejected", "\u{1F44E}"]];
  }
  if (role === "jefatura" && group === "rejected") {
    return [["suggested", "\u{1F44D}"]];
  }
  if (role === "comite" && ["suggested", "approved", "rejected"].includes(group)) {
    return [["skip", "Skip"], ["approved", "Aprobar"], ["rejected", "Rechazar"]];
  }
  if (role === "gerente" && group === "approved") {
    return [["rejected", "Rechazar"], ["project", "Local Proyecto"]];
  }
  if (role === "gerente" && group === "project") {
    return [["rejected", "Dar de baja"]];
  }
  return [];
}

function measureActionButtonsWidth(actions) {
  if (!actions.length) return 72;
  const probe = document.createElement("div");
  probe.className = "table-actions action-width-probe";
  probe.style.position = "absolute";
  probe.style.visibility = "hidden";
  probe.style.left = "-9999px";
  probe.style.top = "0";
  probe.innerHTML = actions.map(([target, label]) =>
    `<button class="table-action status-${esc(target)}">${esc(label)}</button>`
  ).join("");
  document.body.appendChild(probe);
  const width = probe.scrollWidth;
  probe.remove();
  return width;
}

const ACTION_LABEL = {
  accept: "Approved", reject: "Rejected", star: "Starred", like: "Like",
  skip: "Skipped", send_back: "Sent back", reopen: "Reopened",
};

function renderCandidate(c) {
  if (!c) return;
  $("cardTitle").textContent = candidateTitle(c);

  // Returned banner.
  const banner = $("returnedBanner");
  if (c.status === "returned") {
    banner.textContent = "Returned to your layer for re-review";
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
  updateReviewButtons(c);

  setCandidateMarker(c);
  if (c.lat != null) updateStreetView(c.lat, c.lng);
}

function updateReviewButtons(c) {
  const role = State.user?.role;
  const group = candidateGroup(c);
  const canAccept =
    (role === "jefatura" && ["pending", "rejected"].includes(group)) ||
    (role === "comite" && ["suggested", "approved", "rejected"].includes(group)) ||
    (role === "gerente" && group === "approved") ||
    role === "sysadmin";
  const canReject =
    (role === "jefatura" && ["pending", "suggested"].includes(group)) ||
    (role === "comite" && ["suggested", "approved", "rejected"].includes(group)) ||
    (role === "gerente" && ["approved", "project"].includes(group)) ||
    role === "sysadmin";
  const canSkip =
    (role === "jefatura" && group === "pending") ||
    (role === "comite" && ["suggested", "approved", "rejected"].includes(group)) ||
    (role === "gerente" && ["approved", "project"].includes(group)) ||
    role === "sysadmin";
  $("acceptBtn").textContent = role === "jefatura" ? "\u{1F44D}" : "✓";
  $("acceptBtn").title = role === "jefatura" ? "Like" : "Accept";
  $("acceptBtn").setAttribute("aria-label", role === "jefatura" ? "Like" : "Accept");
  $("rejectBtn").textContent = role === "jefatura" ? "\u{1F44E}" : "X";
  $("rejectBtn").title = role === "jefatura" ? "Dislike" : "Reject";
  $("rejectBtn").setAttribute("aria-label", role === "jefatura" ? "Dislike" : "Reject");
  $("acceptBtn").classList.toggle("hidden", !canAccept);
  $("rejectBtn").classList.toggle("hidden", !canReject);
  $("skipBtn").classList.toggle("hidden", !canSkip);
  $("starBtn").classList.add("hidden");
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
    const when = formatTableDate(r.created_at);
    const who = `${ROLE_LABEL[r.reviewer_role] || r.reviewer_role || "?"}`;
    const note = r.note ? `<div class="hist-note">“${esc(r.note)}”</div>` : "";
    return `<div class="hist-row">
      <div class="hist-head"><span class="hist-action act-${esc(r.action)}">${esc(ACTION_LABEL[r.action] || r.action)}</span>
      <span class="hist-meta">${esc(who)} - ${esc(when)}</span></div>${note}</div>`;
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
  let note = $("noteInput").value.trim() || null;
  if (action === "reject" && !note) {
    note = prompt("Ingrese comentario de rechazo:");
    if (!note || !note.trim()) {
      decide._busy = false;
      return toast("Comentario requerido");
    }
  } else if (State.user?.role === "jefatura" && candidateGroup(candidate) === "rejected" && action === "accept" && !note) {
    note = prompt("Ingrese comentario para volver a sugerir:");
    if (!note || !note.trim()) {
      decide._busy = false;
      return toast("Comentario requerido");
    }
  }
  try {
    await api(`/candidates/${candidate.id}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, note }),
    });
    const label = State.user?.role === "jefatura" && action === "accept"
      ? "Like"
      : State.user?.role === "jefatura" && action === "reject"
        ? "Dislike"
        : ACTION_LABEL[action] || "Done";
    toast(label);
    await flashPanel(action);
    await loadQueue();
    if (!$("candidateTableView").classList.contains("hidden")) await refreshCandidateTable();
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
    toast("Sent back");
    await loadQueue();
    if (!$("candidateTableView").classList.contains("hidden")) await refreshCandidateTable();
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
    ["Jefatura", s.queues.jefatura, "stage"],
    ["Comité", s.queues.comite, "stage"],
    ["Gerente", s.queues.gerente, "stage"],
    ["Sugeridos", s.statuses.suggested, "stage"],
    ["Approved", s.statuses.approved_final, "ok"],
    ["Rejected", s.statuses.rejected, "bad"],
    ["Proyecto", s.statuses.locales_proyecto, "ok"],
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
         <a href="/projects/${p.project_id}/results" class="proj-export">Export</a></div>`
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

function applyTableColumnWidth(index, width) {
  const table = document.querySelector(".candidate-table");
  if (!table) return;
  if (index === table.querySelectorAll("thead th").length) return;
  const next = Math.max(70, Math.min(520, Math.round(width)));
  table.querySelectorAll(`th:nth-child(${index}), td:nth-child(${index})`).forEach((cell) => {
    cell.style.width = `${next}px`;
    cell.style.minWidth = `${next}px`;
    cell.style.maxWidth = `${next}px`;
  });
  try { localStorage.setItem(`candidateTableCol${index}`, String(next)); } catch (_) {}
}

function fitActionColumnWidth() {
  const table = document.querySelector(".candidate-table");
  if (!table) return;
  const index = table.querySelectorAll("thead th").length;
  const actionCells = [...table.querySelectorAll("td:last-child .table-actions")];
  const header = table.querySelector("th:last-child");
  const configuredActionsWidth = measureActionButtonsWidth(candidateTableActions(State.tableGroup));
  const contentWidth = Math.max(
    header ? header.scrollWidth : 0,
    configuredActionsWidth,
    ...actionCells.map((el) => el.scrollWidth)
  );
  const hasActions = candidateTableActions(State.tableGroup).length > 0;
  const width = Math.ceil(contentWidth + (hasActions ? 32 : 18));
  table.querySelectorAll(`th:nth-child(${index}), td:nth-child(${index})`).forEach((cell) => {
    cell.style.width = `${width}px`;
    cell.style.minWidth = `${width}px`;
    cell.style.maxWidth = `${width}px`;
  });
}

function wireTableColumnResize() {
  const table = document.querySelector(".candidate-table");
  if (!table) return;
  table.querySelectorAll("thead th").forEach((th, i) => {
    const index = i + 1;
    if (index === table.querySelectorAll("thead th").length) {
      fitActionColumnWidth();
      return;
    }
    const saved = Number(localStorage.getItem(`candidateTableCol${index}`));
    if (saved) applyTableColumnWidth(index, saved);
    if (th.querySelector(".table-col-resizer")) return;

    const handle = document.createElement("span");
    handle.className = "table-col-resizer";
    handle.title = "Ajustar columna";
    th.appendChild(handle);

    handle.onpointerdown = (e) => {
      e.preventDefault();
      e.stopPropagation();
      handle.setPointerCapture(e.pointerId);
      document.body.classList.add("table-col-resizing");
      const startX = e.clientX;
      const startWidth = th.getBoundingClientRect().width;

      const onMove = (moveEvent) => {
        applyTableColumnWidth(index, startWidth + moveEvent.clientX - startX);
      };
      const onEnd = () => {
        document.body.classList.remove("table-col-resizing");
        handle.removeEventListener("pointermove", onMove);
        handle.removeEventListener("pointerup", onEnd);
        handle.removeEventListener("pointercancel", onEnd);
      };

      handle.addEventListener("pointermove", onMove);
      handle.addEventListener("pointerup", onEnd);
      handle.addEventListener("pointercancel", onEnd);
    };
  });
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
  $("sidebarToggleBtn").onclick = () => {
    const collapsed = document.body.classList.toggle("sidebar-collapsed");
    const label = collapsed ? "Mostrar panel" : "Ocultar panel";
    $("sidebarToggleBtn").title = label;
    $("sidebarToggleBtn").setAttribute("aria-label", label);
    resizeMapSoon();
  };
  $("tableViewBtn").onclick = openCandidateTable;
  $("exportCurrentTableBtn").onclick = () => exportCandidateExcel(false);
  $("exportAllTableBtn").onclick = () => exportCandidateExcel(true);
  $("closeTableBtn").onclick = closeCandidateTable;
  wireTableColumnResize();
  $("tableDateFrom").onchange = () => {
    State.tableDateFilters[State.tableGroup].from = $("tableDateFrom").value;
    renderCandidateTable();
  };
  $("tableDateTo").onchange = () => {
    State.tableDateFilters[State.tableGroup].to = $("tableDateTo").value;
    renderCandidateTable();
  };
  $("clearTableDateFilterBtn").onclick = () => {
    State.tableDateFilters[State.tableGroup] = { from: "", to: "" };
    renderCandidateTable();
  };
  document.querySelectorAll(".table-tab").forEach((btn) => {
    btn.onclick = () => {
      State.tableGroup = btn.dataset.group;
      renderCandidateTable();
    };
  });
  $("logoutBtn").onclick = async () => {
    try { await api("/auth/logout", { method: "POST" }); } catch (_) {}
    location.reload();
  };

  document.addEventListener("keydown", (e) => {
    const t = e.target;
    if (t instanceof Element && t.matches("input, textarea, select")) return;
    if (!$("candidateTableView").classList.contains("hidden")) {
      if (e.key === "Escape") closeCandidateTable();
      return;
    }
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
  $("sidebarToggleBtn").classList.add("hidden");
  $("tableViewBtn").classList.add("hidden");
  $("candidateTableView").classList.add("hidden");
  document.body.classList.remove("sidebar-collapsed");
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
  const isReviewer = ["jefatura", "comite", "gerente"].includes(user.role);
  const canSendBack = false;

  const roleLabel = ROLE_LABEL[user.role] || user.role;
  $("projectName").textContent = `${user.name} - ${roleLabel}`;
  $("menuBtn").classList.toggle("hidden", !isSysadmin);
  $("sendBackBtn").classList.toggle("hidden", !canSendBack);
  $("skipBtn").classList.remove("hidden");
  $("starBtn").classList.add("hidden");
  $("rejectBtn").classList.remove("hidden");
  $("acceptBtn").classList.remove("hidden");
  $("toggleViewBtn").classList.remove("hidden");
  $("sidebarToggleBtn").classList.remove("hidden");
  $("sidebarToggleBtn").title = "Ocultar panel";
  $("sidebarToggleBtn").setAttribute("aria-label", "Ocultar panel");
  $("tableViewBtn").classList.remove("hidden");

  try { await loadGoogleMaps(); } catch (e) { console.warn(e); }
  try { await loadBusinessMarkers(); } catch (_) {}

  if (isSysadmin) {
    await showDashboard();
  } else if (isReviewer) {
    await loadQueue();
  }
}

async function boot() {
  initSidebarWidth();
  wireLogin();
  wireDrawer();
  wireInputs();
  wireSidebarResize();
  let me = null;
  try { me = await api("/me"); } catch (_) { /* 401 */ }
  if (me) await startApp(me);
  else showLogin();
}

boot();

