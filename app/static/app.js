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
  tableSort: { key: "scoreTotal", dir: "desc" },
  queueSort: { key: "score", dir: "desc" },
  tableSearch: "",
  tableExpandedActions: new Set(),
  tableActionHistory: {},
  offlineSyncing: false,
  reviewedThisSession: new Set(),
  sidebarView: "main",
  funnelDateFilter: { from: "", to: "" },
  tableDateFilters: {
    pending: { from: "", to: "" },
    observation: { from: "", to: "" },
    rejected: { from: "", to: "" },
    proposed: { from: "", to: "" },
    approved: { from: "", to: "" },
    opening: { from: "", to: "" },
  },
};

const ROLE_LABEL = {
  jefatura: "Jefatura",
  jefecomercial: "Jefe Comercial",
  coordinador: "Coordinador",
  arriendo: "Arriendo y Patentes",
  comite: "Comité",
  gerente: "Gerente",
  gerentegeneral: "Gerente General",
  sysadmin: "Sysadmin",
};

const REQUESTER_CATEGORY_EMAILS = {
  Sucursal: new Set([
    "admricardo@porunpaismejor.com.mx", "venfelipe@porunpaismejor.com.mx",
    "ventnoe@porunpaismejor.com.mx", "ventluis@porunpaismejor.com.mx",
    "admalemaggi@porunpaismejor.com.mx", "ventmarco@porunpaismejor.com.mx",
    "ventkarba@porunpaismejor.com.mx", "ventgerman@porunpaismejor.com.mx",
    "ventcatalina@porunpaismejor.com.mx", "admroberto@porunpaismejor.com.mx",
    "ventjoaravena@porunpaismejor.com.mx", "admivan@porunpaismejor.com.mx",
    "vensebastian@porunpaismejor.com.mx", "admjennifer@porunpaismejor.com.mx",
    "ventlorena@porunpaismejor.com.mx",
  ]),
  Franquicia: new Set([
    "franfrancisco@porunpaismejor.com.mx", "franwalter@porunpaismejor.com.mx",
    "franarnaldo@porunpaismejor.com.mx", "franvgarrido@porunpaismejor.com.mx",
    "franclaudio@porunpaismejor.com.mx", "franbastian@porunpaismejor.com.mx",
    "franmauricio@porunpaismejor.com.mx", "frangabriel@porunpaismejor.com.mx",
    "franalejandro@porunpaismejor.com.mx", "franjosev@porunpaismejor.com.mx",
    "franmaxi@porunpaismejor.com.mx", "francesar@porunpaismejor.com.mx",
    "franximena@porunpaismejor.com.mx", "franchristian@porunpaismejor.com.mx",
    "franantonio@porunpaismejor.com.mx",
  ]),
  Arriendos: new Set(["aypcelia@porunpaismejor.com.mx"]),
};

const PROJECT_VARIABLE_FIELDS = [
  ["cve_unidad", "text"],
  ["unidad", "text"],
  ["comuna", "text"],
  ["provincia", "text"],
  ["region", "text"],
  ["mt2", "number"],
  ["valor_arriendo", "text"],
  ["gastos_comunes", "text"],
  ["clausula_salida", "text"],
  ["meses_gracia", "text"],
  ["plazo_arriendo", "text"],
  ["garantia", "text"],
  ["tipo_proyecto", "text"],
  ["fecha_apertura_aproximada", "date"],
  ["contacto_nombre", "text"],
  ["contacto_telefono", "text"],
  ["contacto_email", "text"],
  ["fecha_entrega_local", "date"],
];

const PROJECT_MAIL_RECIPIENTS = [
  "mbustos@farmaciasdoctorsimi.cl",
  "amarquez@farmaciasdoctorsimi.cl",
  "icruz@farmaciasdoctorsimi.cl",
  "dgonzalez@farmaciasdoctorsimi.cl",
  "mmadridf@farmaciasdoctorsimi.cl",
  "rmalave@farmaciasdoctorsimi.cl",
  "ptarsetti@farmaciasdoctorsimi.cl",
  "yarevalo@farmaciasdoctorsimi.cl",
  "efredes@farmaciasdoctorsimi.cl",
  "dbustos@farmaciasdoctorsimi.cl",
  "kcarrera@farmaciasdoctorsimi.cl",
  "kleiva@farmaciasdoctorsimi.cl",
  "lberrios@farmaciasdoctorsimi.cl",
  "bdonoso@farmaciasdoctorsimi.cl",
  "arriendos@farmaciasdoctorsimi.cl",
  "emeza@farmaciasdoctorsimi.cl",
];

const PROJECT_COMMUNES = `
ALGARROBO
ALHUÉ
ALTO BIOBÍO
ALTO DEL CARMEN
ALTO HOSPICIO
ANCUD
ANDACOLLO
ANGOL
ANTÁRTICA
ANTOFAGASTA
ANTUCO
ARAUCO
ARICA
AYSÉN
BUIN
BULNES
CABILDO
CABO DE HORNOS
CABRERO
CALAMA
CALBUCO
CALDERA
CALERA
CALERA DE TANGO
CALLE LARGA
CAMARONES
CAMIÑA
CANELA
CAÑETE
CARAHUE
CARTAGENA
CASABLANCA
CASTRO
CATEMU
CAUQUENES
CERRILLOS
CERRO NAVIA
CHAITÉN
CHANCO
CHAÑARAL
CHÉPICA
CHIGUAYANTE
CHILE CHICO
CHILLÁN
CHILLÁN VIEJO
CHIMBARONGO
CHOLCHOL
CHONCHI
CISNES
COBQUECURA
COCHAMÓ
COCHRANE
CODEGUA
COELEMU
COIHUECO
COINCO
COLBÚN
COLCHANE
COLINA
COLLIPULLI
COLTAUCO
COMBARBALÁ
CONCEPCIÓN
CONCHALÍ
CONCÓN
CONSTITUCIÓN
CONTULMO
COPIAPÓ
COQUIMBO
CORONEL
CORRAL
COYHAIQUE
CUNCO
CURACAUTÍN
CURACAVÍ
CURACO DE VÉLEZ
CURANILAHUE
CURARREHUE
CUREPTO
CURICÓ
DALCAHUE
DIEGO DE ALMAGRO
DOÑIHUE
EL BOSQUE
EL CARMEN
EL MONTE
EL QUISCO
EL TABO
EMPEDRADO
ERCILLA
ESTACIÓN CENTRAL
FLORIDA
FREIRE
FREIRINA
FRESIA
FRUTILLAR
FUTALEUFÚ
FUTRONO
GALVARINO
GENERAL LAGOS
GORBEA
GRANEROS
GUAITECAS
HIJUELAS
HUALAIHUÉ
HUALAÑÉ
HUALPÉN
HUALQUI
HUARA
HUASCO
HUECHURABA
ILLAPEL
INDEPENDENCIA
IQUIQUE
ISLA DE MAIPO
ISLA DE PASCUA
JUAN FERNÁNDEZ
LA CISTERNA
LA CRUZ
LA ESTRELLA
LA FLORIDA
LA GRANJA
LA HIGUERA
LA LIGUA
LA PINTANA
LA REINA
LA SERENA
LA UNIÓN
LAGO RANCO
LAGO VERDE
LAGUNA BLANCA
LAJA
LAMPA
LANCO
LAS CABRAS
LAS CONDES
LAUTARO
LEBU
LICANTÉN
LIMACHE
LINARES
LITUECHE
LLAILLAY
LLANQUIHUE
LO BARNECHEA
LO ESPEJO
LO PRADO
LOLOL
LONCOCHE
LONGAVÍ
LONQUIMAY
LOS ÁLAMOS
LOS ANDES
LOS ÁNGELES
LOS LAGOS
LOS MUERMOS
LOS SAUCES
LOS VILOS
LOTA
LUMACO
MACHALÍ
MACUL
MÁFIL
MAIPÚ
MALLOA
MARCHIHUE
MARÍA ELENA
MARÍA PINTO
MARIQUINA
MAULE
MAULLÍN
MEJILLONES
MELIPEUCO
MELIPILLA
MOLINA
MONTE PATRIA
MOSTAZAL
MULCHÉN
NACIMIENTO
NANCAGUA
NATALES
NAVIDAD
NEGRETE
NINHUE
NOGALES
NUEVA IMPERIAL
ÑIQUÉN
ÑUÑOA
O'HIGGINS
OLIVAR
OLLAGÜE
OLMUÉ
OSORNO
OVALLE
PADRE HURTADO
PADRE LAS CASAS
PAIGUANO
PAILLACO
PAINE
PALENA
PALMILLA
PANGUIPULLI
PANQUEHUE
PAPUDO
PAREDONES
PARRAL
PEDRO AGUIRRE CERDA
PELARCO
PELLUHUE
PEMUCO
PENCAHUE
PENCO
PEÑAFLOR
PEÑALOLÉN
PERALILLO
PERQUENCO
PETORCA
PEUMO
PICA
PICHIDEGUA
PICHILEMU
PINTO
PIRQUE
PITRUFQUÉN
PLACILLA
PORTEZUELO
PORVENIR
POZO ALMONTE
PRIMAVERA
PROVIDENCIA
PUCHUNCAVÍ
PUCÓN
PUDAHUEL
PUENTE ALTO
PUERTO MONTT
PUERTO OCTAY
PUERTO VARAS
PUMANQUE
PUNITAQUI
PUNTA ARENAS
PUQUELDÓN
PURÉN
PURRANQUE
PUTAENDO
PUTRE
PUYEHUE
QUEILÉN
QUELLÓN
QUEMCHI
QUILACO
QUILICURA
QUILLECO
QUILLÓN
QUILLOTA
QUILPUÉ
QUINCHAO
QUINTA DE TILCOCO
QUINTA NORMAL
QUINTERO
QUIRIHUE
RANCAGUA
RÁNQUIL
RAUCO
RECOLETA
RENAICO
RENCA
RENGO
REQUÍNOA
RETIRO
RINCONADA
RÍO BUENO
RÍO CLARO
RÍO HURTADO
RÍO IBÁÑEZ
RÍO NEGRO
RÍO VERDE
ROMERAL
SAAVEDRA
SAGRADA FAMILIA
SALAMANCA
SAN ANTONIO
SAN BERNARDO
SAN CARLOS
SAN CLEMENTE
SAN ESTEBAN
SAN FABIÁN
SAN FELIPE
SAN FERNANDO
SAN GREGORIO
SAN IGNACIO
SAN JAVIER
SAN JOAQUÍN
SAN JOSÉ DE MAIPO
SAN JUAN DE LA COSTA
SAN MIGUEL
SAN NICOLÁS
SAN PABLO
SAN PEDRO
SAN PEDRO DE ATACAMA
SAN PEDRO DE LA PAZ
SAN RAFAEL
SAN RAMÓN
SAN ROSENDO
SAN VICENTE
SANTA BÁRBARA
SANTA CRUZ
SANTA JUANA
SANTA MARÍA
SANTIAGO
SANTO DOMINGO
SIERRA GORDA
TALAGANTE
TALCA
TALCAHUANO
TALTAL
TEMUCO
TENO
TEODORO SCHMIDT
TIERRA AMARILLA
TILTIL
TIMAUKEL
TIRÚA
TOCOPILLA
TOLTÉN
TOMÉ
TORRES DEL PAINE
TORTEL
TRAIGUÉN
TREHUACO
TUCAPEL
VALDIVIA
VALLENAR
VALPARAÍSO
VICHUQUÉN
VICTORIA
VICUÑA
VILCÚN
VILLA ALEGRE
VILLA ALEMANA
VILLARRICA
VIÑA DEL MAR
VITACURA
YERBAS BUENAS
YUMBEL
YUNGAY
ZAPALLAR
`.trim().split("\n");

const PROJECT_REGIONS = `
AISÉN DEL GENERAL CARLOS IBÁÑEZ DEL CAMPO
ANTOFAGASTA
ARICA Y PARINACOTA
ATACAMA
BIOBÍO
COQUIMBO
LA ARAUCANÍA
LIBERTADOR GENERAL BERNARDO O'HIGGINS
LOS LAGOS
LOS RÍOS
MAGALLANES Y DE LA ANTÁRTICA CHILENA
MAULE
METROPOLITANA DE SANTIAGO
ÑUBLE
TARAPACÁ
VALPARAÍSO
`.trim().split("\n");

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

const CACHE_VERSION = "v1";

function storageKey(name) {
  const user = State.user?.id || State.user?.email || "anon";
  return `siteSwiper.${CACHE_VERSION}.${user}.${name}`;
}

function readJsonStorage(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (_) {
    return fallback;
  }
}

function writeJsonStorage(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) {}
}

function cachedCandidates() {
  return readJsonStorage(storageKey("candidates"), []);
}

function cachedUser() {
  return readJsonStorage(`siteSwiper.${CACHE_VERSION}.lastUser`, null);
}

function saveUserCache(user) {
  if (user?.id || user?.email) writeJsonStorage(`siteSwiper.${CACHE_VERSION}.lastUser`, user);
}

function saveCandidateCache(items = State.tableCandidates) {
  if (Array.isArray(items) && items.length) writeJsonStorage(storageKey("candidates"), items);
}

function offlineActions() {
  return readJsonStorage(storageKey("offlineActions"), []);
}

function saveOfflineActions(items) {
  writeJsonStorage(storageKey("offlineActions"), items);
}

function isOfflineError(err) {
  return err?.name === "TypeError" || err?.status >= 500;
}

function offlineActionLabel(entry) {
  const body = entry.body || {};
  const action = body.action || body.group || "";
  return ACTION_LABEL[action] || groupLabel(action) || action || "accion";
}

function enqueueOfflineAction(entry) {
  const items = offlineActions();
  items.push({ id: `${Date.now()}-${Math.random().toString(16).slice(2)}`, created_at: new Date().toISOString(), ...entry });
  saveOfflineActions(items);
  toast(`Sin conexion DB: accion guardada (${items.length})`);
}

async function flushOfflineActions() {
  if (!State.user || State.offlineSyncing) return;
  let items = offlineActions();
  if (!items.length) return;
  State.offlineSyncing = true;
  let synced = 0;
  try {
    while (items.length) {
      const entry = items[0];
      try {
        await api(entry.url, {
          method: entry.method || "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(entry.body || {}),
        });
        items.shift();
        synced += 1;
        saveOfflineActions(items);
      } catch (err) {
        if (isOfflineError(err)) break;
        items.shift();
        saveOfflineActions(items);
        toast(`No se pudo sincronizar ${offlineActionLabel(entry)}: ${err.message}`);
      }
    }
  } finally {
    State.offlineSyncing = false;
  }
  if (synced) {
    toast(items.length ? `Sincronizadas ${synced}; pendientes ${items.length}` : `Sincronizadas ${synced} acciones`);
    try { await refreshCandidateTable(); } catch (_) {}
    if (["jefatura", "jefecomercial", "coordinador", "arriendo", "comite", "gerente", "gerentegeneral"].includes(State.user?.role)) {
      try { await loadQueue(); } catch (_) {}
    }
  }
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

const businessIconCache = new Map();

function drawPinIcon(image = null) {
  const canvas = document.createElement("canvas");
  canvas.width = 96;
  canvas.height = 120;
  const ctx = canvas.getContext("2d");
  ctx.scale(2, 2);

  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,0.28)";
  ctx.shadowBlur = 4;
  ctx.shadowOffsetY = 2;
  ctx.beginPath();
  ctx.moveTo(24, 58);
  ctx.bezierCurveTo(19, 45, 5, 37, 5, 22);
  ctx.bezierCurveTo(5, 11.5, 13.5, 3, 24, 3);
  ctx.bezierCurveTo(34.5, 3, 43, 11.5, 43, 22);
  ctx.bezierCurveTo(43, 37, 29, 45, 24, 58);
  ctx.closePath();
  ctx.fillStyle = "#020617";
  ctx.fill();
  ctx.restore();

  ctx.beginPath();
  ctx.arc(24, 22, 18, 0, Math.PI * 2);
  ctx.fillStyle = "#020617";
  ctx.fill();

  ctx.beginPath();
  ctx.arc(24, 22, 14.5, 0, Math.PI * 2);
  ctx.fillStyle = "#ffffff";
  ctx.fill();

  if (image) {
    const box = 26;
    const scale = Math.min(box / image.naturalWidth, box / image.naturalHeight);
    const w = image.naturalWidth * scale;
    const h = image.naturalHeight * scale;
    ctx.save();
    ctx.beginPath();
    ctx.arc(24, 22, 13, 0, Math.PI * 2);
    ctx.clip();
    ctx.drawImage(image, 24 - w / 2, 22 - h / 2, w, h);
    ctx.restore();
  } else {
    ctx.beginPath();
    ctx.arc(24, 22, 9, 0, Math.PI * 2);
    ctx.fillStyle = "#10b981";
    ctx.fill();
  }

  return {
    url: canvas.toDataURL("image/png"),
    scaledSize: new google.maps.Size(48, 60),
    anchor: new google.maps.Point(24, 58),
  };
}

function loadPinImage(url) {
  const absoluteUrl = new URL(url, window.location.origin).href;
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = absoluteUrl;
  });
}

async function businessIcon(b) {
  const attrs = b.attributes || {};
  const meta = businessMeta(b);
  const url = attrs.image_url || meta?.image;
  if (!url) return drawPinIcon();
  if (!businessIconCache.has(url)) {
    businessIconCache.set(url, loadPinImage(url).then((image) => drawPinIcon(image)));
  }
  return businessIconCache.get(url);
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
  for (const b of items) {
    const icon = await businessIcon(b);
    const m = new google.maps.Marker({
      position: { lat: b.lat, lng: b.lng },
      map: State.businessVisible ? State.map : null,
      title: b.name || businessMeta(b)?.label || b.category || "Business",
      icon,
    });
    m.addListener("click", () => {
      info.setContent(businessInfoHtml(b));
      info.open(State.map, m);
    });
    State.businessMarkers.push(m);
  }
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

const SCORE_KEYS = ["ScoreTotal", "SCORETOTAL", "score_total"];
const PROJECTION_KEYS = ["PROYECCIÓN", "PROYECCION", "Proyeccion", "PROYECCIÃ“N"];
const PROJECTION_ID_KEYS = ["ID Proyección", "ID Proyeccion", "ID ProyecciÃ³n", "ID"];
function candidateScore(c) {
  const d = c.display_data || {};
  for (const k of SCORE_KEYS) {
    if (d[k] !== undefined && d[k] !== "") return { key: k, value: d[k] };
  }
  return null;
}

function candidateProjection(c) {
  const d = c.display_data || {};
  for (const k of PROJECTION_KEYS) {
    if (d[k] !== undefined && d[k] !== "") return d[k];
  }
  return "";
}

function candidateProjectionId(c) {
  return displayValue(c, PROJECTION_ID_KEYS) || c.id;
}

function projectionBandClass(raw) {
  const value = numericValue(raw);
  if (value == null) return "mid";
  if (value < 50) return "low";
  if (value < 70) return "mid";
  return "high";
}

function scoreBandClass(raw) {
  const value = numericValue(raw);
  if (value == null) return "mid";
  if (value <= 40) return "low";
  if (value <= 70) return "mid";
  return "high";
}

function numericValue(raw) {
  const cleaned = String(raw ?? "").replace(/[^\d,.-]/g, "").replace(",", ".");
  const value = parseFloat(cleaned);
  return Number.isFinite(value) ? value : null;
}

const PRIORITY_COLUMNS = [
  ["ID Proyección", "ID"],
  ["NombreSolicitante"],
  ["CorreoSolicitante"],
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
  ["ScoreTotal", "SCORETOTAL", "score_total"],
  ["NivelScore"],
  ["ScoreProyeccion"],
  ["ScoreRedPropia"],
  ["ScoreCUT"],
  ["ScoreCompetencia"],
  ["CUTUnico"],
  ["CantidadLocalesMismoCUT"],
  ["CveUnidadPropiaCercana"],
  ["DistanciaLocalPropioM"],
  ["EstatusLocalPropioCercano"],
  ["NivelRedPropia"],
  ["CantidadCompetencia200m"],
  ["DistanciaCompetenciaM"],
  ["NomRegion"],
  ["NomComuna"],
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
  "CorreoComplemento", "CveSimiCercano",
]);

function isDateKey(key) {
  return /fecha/i.test(String(key));
}

function displayRowValue(key, value) {
  return isDateKey(key) ? formatTableDate(value) : value;
}

const SIDEBAR_FIXED_FIELDS = [
  ["DIRECCIÓN", "Direccion", "DIRECCION"],
  ["NombreSolicitante"],
  ["CorreoSolicitante"],
  ["Solicitado por"],
  ["FRONTIS"],
  ["MT2"],
  ["ValorArriendo", "Valor Arriendo"],
  ["DIVISION", "Division"],
  ["TIPOLOGÍA", "Tipologia", "TIPOLOGIA"],
  ["FECHA"],
];

const AGE_BAND_KEYS = ["<30", "30-40", "40-50", "50-60", "60-75", "75<"];

function displayFirstAvailable(display_data, variants) {
  for (const key of variants) {
    if (display_data[key] !== undefined && display_data[key] !== "" && display_data[key] != null) {
      return [variants[0], displayRowValue(key, display_data[key])];
    }
  }
  return null;
}

function sidebarAgeRows(display_data) {
  const values = AGE_BAND_KEYS
    .map((key) => {
      const raw = display_data[key];
      const numeric = numericValue(raw);
      return raw !== undefined && raw !== "" && raw != null && numeric != null
        ? { key, raw, numeric }
        : null;
    })
    .filter(Boolean);
  if (!values.length) return [];
  const max = Math.max(...values.map((item) => item.numeric));
  return values
    .filter((item) => item.numeric === max)
    .map((item) => [item.key, item.raw]);
}

function buildSidebarDisplayRows(display_data, group) {
  const rows = [];
  for (const variants of SIDEBAR_FIXED_FIELDS) {
    const row = displayFirstAvailable(display_data, variants);
    if (row) rows.push(row);
    if (group === "observation" && variants[0] === "Solicitado por") {
      const tipoEstatus = displayFirstAvailable(display_data, ["TipoEstatus"]);
      const proyeccionCercana = displayFirstAvailable(
        display_data,
        ["ProyeccionCercana", "IDProyeccionCercana", "IDProyeccionCercano"]
      );
      if (tipoEstatus) rows.push(tipoEstatus);
      if (proyeccionCercana) rows.push(proyeccionCercana);
    }
  }
  rows.push(...sidebarAgeRows(display_data));
  const nearby = displayFirstAvailable(display_data, ["CveUnidadCercana"]);
  if (nearby) rows.push(nearby);
  return rows;
}

function buildDisplayRows(display_data) {
  const rows = [];
  const seen = new Set();
  for (const variants of PRIORITY_COLUMNS) {
    for (const key of variants) {
      if (display_data[key] !== undefined && display_data[key] !== "" && display_data[key] != null) {
        if (variants[0] === "ID Proyección") {
          variants.forEach((v) => seen.add(v));
          break;
        }
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

function candidateRequestedBy(candidate) {
  if (candidate?.requested_by) return candidate.requested_by;
  const email = String(displayValue(candidate || {}, [
    "CorreoSolicitante", "Correo Solicitante", "CORREOSOLICITANTE",
  ]) || "").trim().toLowerCase();
  for (const [category, emails] of Object.entries(REQUESTER_CATEGORY_EMAILS)) {
    if (emails.has(email)) return category;
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
  if (["pending", "observation", "proposed", "approved", "rejected", "opening"].includes(c.workflow_group)) return c.workflow_group;
  if (c.workflow_group === "suggested") return "pending";
  if (c.workflow_group === "project") return "approved";
  if (c.status === "por_abrir") return "opening";
  if (c.status === "locales_proyecto") return "approved";
  if (c.status === "proyecto") return "opening";
  if (c.status === "aprobado") return "proposed";
  if (c.status === "rechazado") return "rejected";
  if (["observacion", "observation"].includes(c.status)) return "observation";
  if (c.status === "sugerido") return "pending";
  if (c.status === "pendiente" || c.status === "devuelto") return "pending";
  if (c.status === "approved_final" || c.status === "approved") return "proposed";
  if (c.status === "rejected") return "rejected";
  if (c.status === "suggested") return "pending";
  if (c.last_decision === "project") return "approved";
  if (c.last_decision === "reject") return "rejected";
  if (["like", "dislike", "star"].includes(c.last_decision)) return "pending";
  if (c.last_decision === "accept") return "proposed";
  return "pending";
}

function upsertTableCandidate(candidate) {
  if (!candidate) return;
  const idx = State.tableCandidates.findIndex((c) => c.id === candidate.id);
  if (idx >= 0) State.tableCandidates[idx] = candidate;
  else State.tableCandidates.push(candidate);
  saveCandidateCache();
}

function removeTableCandidate(candidateId) {
  State.tableCandidates = State.tableCandidates.filter((c) => c.id !== candidateId);
}

function syncStatsPayload(stats) {
  if (!stats || !$("statsGrid")) return;
  if ($("dashboard")?.classList?.contains("hidden")) return;
  renderStatsPayload(stats);
}

function applyActionResult(result, candidateId = null) {
  const updated = result?.candidate || result;
  if (updated?.id) upsertTableCandidate(updated);
  if (result?.next_candidate?.id) upsertTableCandidate(result.next_candidate);
  syncStatsPayload(result?.stats);

  if (State.current?.id === (candidateId || updated?.id)) {
    State.current = result?.next_candidate || null;
    $("progress").textContent = result?.remaining > 0 ? `${result.remaining}  proyecciones pendientes` : "Queue empty";
    if (State.current) {
      renderCandidate(State.current);
      loadHistory(State.current.id);
    } else {
      $("candidatePanel").classList.add("hidden");
      $("reviewControls").classList.add("hidden");
      $("emptyState").classList.remove("hidden");
      $("emptyTitle").textContent = "Queue empty";
      $("emptyMsg").textContent = "Nothing to review in your layer right now.";
    }
  }
  if (!$("candidateTableView").classList.contains("hidden")) renderCandidateTable();
}

function optimisticCandidate(candidate, target) {
  const updated = typeof structuredClone === "function" ? structuredClone(candidate) : JSON.parse(JSON.stringify(candidate));
  const role = State.user?.role;
  const now = new Date().toISOString();
  updated.last_decision = target;
  updated.last_action_at = now;
  updated.last_actor_role = role;
  if (["jefatura", "jefecomercial", "coordinador"].includes(role)) {
    if (role === "coordinador" && target === "opening") {
      updated.status = "por_abrir";
      updated.workflow_group = "opening";
      updated.current_stage = "Proyecto";
    } else if (target === "accept") {
      updated.last_decision = "like";
      updated.status = "pendiente";
      updated.workflow_group = "pending";
    } else if (target === "reject") {
      updated.last_decision = "dislike";
      updated.status = "pendiente";
      updated.workflow_group = "pending";
    }
  } else if (["comite", "gerentegeneral"].includes(role) && ["project", "accept"].includes(target)) {
    updated.status = "locales_proyecto";
    updated.workflow_group = "approved";
    updated.current_stage = "Aprobado";
    updated.last_decision = "project";
  } else if (target === "approved" || target === "accept") {
    updated.status = "aprobado";
    updated.workflow_group = "proposed";
    updated.current_stage = "Propuesto";
    updated.last_decision = "accept";
  } else if (target === "rejected" || target === "reject") {
    updated.status = "rechazado";
    updated.workflow_group = "rejected";
    updated.last_decision = "reject";
  } else if (target === "project") {
    updated.status = "locales_proyecto";
    updated.workflow_group = "approved";
    updated.current_stage = "Aprobado";
    updated.last_decision = "project";
  } else if (target === "opening") {
    updated.status = "por_abrir";
    updated.workflow_group = "opening";
    updated.current_stage = "Proyecto";
    updated.last_decision = "opening";
  }
  return updated;
}

function candidateAllowedForCurrentRole(candidate) {
  const role = State.user?.role;
  const group = candidateGroup(candidate);
  if (["jefatura", "jefecomercial", "coordinador"].includes(role) && State.reviewedThisSession.has(candidate.id)) {
    return false;
  }
  if (["jefatura", "jefecomercial", "coordinador"].includes(role)) return group === "pending";
  if (["arriendo", "gerente"].includes(role)) return group === "pending";
  if (["comite", "gerentegeneral"].includes(role)) return group === "proposed";
  return false;
}

function nextCachedCandidate(excludeId = null) {
  const pool = sortTableRows((State.tableCandidates.length ? State.tableCandidates : cachedCandidates())
    .filter((c) => c.id !== excludeId && candidateAllowedForCurrentRole(c)));
  return pool[0] || null;
}

function applyOfflineOptimistic(candidateId, target) {
  const source = State.tableCandidates.find((c) => c.id === candidateId) || State.current;
  if (!source) return;
  if (["accept", "reject", "like", "dislike"].includes(target)) {
    State.reviewedThisSession.add(candidateId);
  }
  const updated = optimisticCandidate(source, target);
  upsertTableCandidate(updated);
  if (!$("candidateTableView").classList.contains("hidden")) renderCandidateTable();
  if (State.current?.id === candidateId) {
    State.current = nextCachedCandidate(candidateId);
    if (State.current) {
      renderCandidate(State.current);
      loadHistory(State.current.id);
      $("progress").textContent = `${Math.max(offlineActions().length, 1)} acciones pendientes de sincronizar`;
    } else {
      $("candidatePanel").classList.add("hidden");
      $("reviewControls").classList.add("hidden");
      $("emptyState").classList.remove("hidden");
      $("emptyTitle").textContent = "Sin conexion DB";
      $("emptyMsg").textContent = "Las acciones quedaron guardadas y se sincronizaran al reconectar.";
    }
  }
}

function groupLabel(group) {
  return { pending: "Pendiente", observation: "Observación", proposed: "Propuesto", approved: "Aprobado", rejected: "Rechazado", opening: "Proyecto" }[group] || group;
}

function groupExportLabel(group) {
  return {
    pending: "Pendientes",
    observation: "Observación",
    proposed: "Propuestos",
    approved: "Aprobados",
    rejected: "Rechazados",
    opening: "Proyectos",
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
  if (group === "observation") return dates.observation || dates.rejected;
  if (group === "proposed") return dates.proposed;
  if (group === "approved") return dates.approved;
  if (group === "rejected") return dates.rejected;
  if (group === "opening") return dates.opening || dates.approved;
  return "";
}

function candidateTableDate(c, group) {
  return formatTableDate(candidateTableDateRaw(c, group));
}

const FUNNEL_STAGES = [
  { key: "pending", label: "Pendientes + Observación", groups: ["pending", "observation"] },
  { key: "rejected", label: "Rechazados", groups: ["rejected"] },
  { key: "approved", label: "Aprobados", groups: ["approved"] },
  { key: "opening", label: "Proyectos", groups: ["opening"] },
];

function candidateMatchesFunnelDate(c) {
  const filter = State.funnelDateFilter;
  if (!filter.from && !filter.to) return true;
  const group = candidateGroup(c);
  const key = santiagoDateKey(candidateTableDateRaw(c, group));
  if (!key) return false;
  if (filter.from && key < filter.from) return false;
  if (filter.to && key > filter.to) return false;
  return true;
}

function funnelStageCounts() {
  const visible = State.tableCandidates.filter(candidateMatchesFunnelDate);
  return FUNNEL_STAGES.map((stage) => ({
    ...stage,
    count: visible.filter((candidate) => stage.groups.includes(candidateGroup(candidate))).length,
  }));
}

function renderFunnel() {
  const container = $("funnelStages");
  if (!container) return;
  const stages = funnelStageCounts();
  const total = stages.reduce((sum, stage) => sum + stage.count, 0);
  const maxCount = Math.max(1, ...stages.map((stage) => stage.count));
  $("funnelTotal").textContent = `${total} locales`;
  container.innerHTML = stages.map((stage) => {
    const percentage = total ? (stage.count / total) * 100 : 0;
    const width = stage.count ? 48 + (stage.count / maxCount) * 52 : 48;
    return `<button type="button" class="funnel-stage funnel-${esc(stage.key)}" data-funnel-group="${esc(stage.key)}">
      <span class="funnel-stage-label">${esc(stage.label)}</span>
      <span class="funnel-bar" style="width:${width.toFixed(1)}%">
        <strong>${stage.count}</strong><span>${percentage.toLocaleString("es-CL", { maximumFractionDigits: 1 })}%</span>
      </span>
    </button>`;
  }).join("");
  container.querySelectorAll("[data-funnel-group]").forEach((button) => {
    button.onclick = () => openTableFromFunnel(button.dataset.funnelGroup);
  });
}

async function openTableFromFunnel(group) {
  State.tableGroup = group;
  State.tableDateFilters[group] = { ...State.funnelDateFilter };
  await openCandidateTable();
}

async function toggleFunnelView() {
  const showFunnel = State.sidebarView !== "funnel";
  State.sidebarView = showFunnel ? "funnel" : "main";
  $("sidebarMainView").classList.toggle("hidden", showFunnel);
  $("funnelPanel").classList.toggle("hidden", !showFunnel);
  $("funnelBtn").classList.toggle("active", showFunnel);
  $("funnelBtn").title = showFunnel ? "Volver al local" : "Ver embudo";
  $("funnelBtn").setAttribute("aria-label", $("funnelBtn").title);
  if (showFunnel) {
    await refreshCandidateTable();
    renderFunnel();
  }
}

function numericSortValue(raw) {
  const cleaned = String(raw ?? "").replace(/[^\d,.-]/g, "").replace(",", ".");
  const value = parseFloat(cleaned);
  return Number.isFinite(value) ? value : null;
}

function tableSortValue(c, key) {
  const group = candidateGroup(c);
  const vars = c.project_variables || {};
  if (group === "opening") {
    if (key === "idProj") return vars.cve_unidad || "";
    if (key === "address") return vars.unidad || "";
    if (key === "applicant") return vars.region || "";
    if (key === "projection") return vars.comuna || "";
    if (key === "scoreTotal") return "";
  }
  if (key === "idProj") return numericSortValue(displayValue(c, ["ID Proyección", "ID Proyeccion", "ID ProyecciÃ³n", "ID"])) ?? displayValue(c, ["ID Proyección", "ID Proyeccion", "ID ProyecciÃ³n", "ID"]) ?? c.id;
  if (key === "address") return displayValue(c, ["DIRECCIÓN", "DIRECCION", "Direccion", "DIRECCIÃ“N"]) || candidateTitle(c);
  if (key === "applicant") return displayValue(c, ["NombreSolicitante"]) || "";
  if (key === "requestedBy") return candidateRequestedBy(c);
  if (key === "projection") return numericSortValue(displayValue(c, ["PROYECCIÓN", "PROYECCION", "PROYECCIÃ“N"])) ?? displayValue(c, ["PROYECCIÓN", "PROYECCION", "PROYECCIÃ“N"]) ?? "";
  if (key === "scoreTotal") return numericSortValue(displayValue(c, ["ScoreTotal", "SCORETOTAL", "score_total"])) ?? displayValue(c, ["ScoreTotal", "SCORETOTAL", "score_total"]) ?? "";
  if (key === "date") return parseUtcLikeDate(candidateTableDateRaw(c, group))?.getTime() ?? null;
  if (key === "stage") return c.current_stage || "";
  if (key === "group") return groupLabel(group);
  if (key === "rejectNote") return c.last_reject_note || "";
  return "";
}

function compareTableValues(a, b) {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), "es", { numeric: true, sensitivity: "base" });
}

function sortTableRows(rows) {
  const { key, dir } = State.tableSort;
  if (!key) return rows;
  const factor = dir === "desc" ? -1 : 1;
  return [...rows].sort((a, b) => {
    const result = compareTableValues(tableSortValue(a, key), tableSortValue(b, key));
    return result === 0 ? a.id - b.id : result * factor;
  });
}

function syncTableSortHeaders() {
  document.querySelectorAll(".candidate-table th.sortable").forEach((th) => {
    const active = th.dataset.sortKey === State.tableSort.key;
    th.classList.toggle("sorted", active);
    th.dataset.sortDir = active ? State.tableSort.dir : "";
  });
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

function searchText(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function isOwnCandidate(candidate) {
  if (!["jefecomercial", "coordinador"].includes(State.user?.role)) return false;
  const owner = displayValue(candidate, ["CorreoSolicitante", "Correo Solicitante", "CORREOSOLICITANTE"]);
  return Boolean(owner && searchText(owner).trim() === searchText(State.user?.email).trim());
}

function candidateMatchesTableSearch(c) {
  const query = searchText(State.tableSearch).trim();
  if (!query) return true;
  const vars = c.project_variables || {};
  const values = [
    c.id,
    displayValue(c, ["ID Proyección", "ID Proyeccion", "ID ProyecciÃ³n", "ID"]),
    displayValue(c, ["DIRECCIÓN", "DIRECCION", "Direccion", "DIRECCIÃ“N"]),
    displayValue(c, ["NombreSolicitante"]),
    candidateRequestedBy(c),
    displayValue(c, ["NomComuna", "Comuna", "COMUNA"]),
    displayValue(c, ["NomRegion", "Region", "REGION"]),
    vars.cve_unidad,
    vars.unidad,
    vars.comuna,
    vars.region,
  ];
  return values.some((value) => searchText(value).includes(query));
}

function syncTableDateFilterInputs() {
  const filter = State.tableDateFilters[State.tableGroup] || { from: "", to: "" };
  $("tableDateFrom").value = filter.from || "";
  $("tableDateTo").value = filter.to || "";
}

function tableCounts(items) {
  return items.reduce((acc, c) => {
    const group = candidateGroup(c);
    acc[group] = (acc[group] || 0) + 1;
    return acc;
  }, { pending: 0, observation: 0, proposed: 0, approved: 0, rejected: 0, opening: 0 });
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
  appendVisibilityParams(params);
  window.location.href = `/candidates/export.xlsx?${params.toString()}`;
}

function exportCommitteeSessionExcel() {
  window.location.href = "/candidates/export-session.xlsx";
}

function queueSortParams() {
  const params = new URLSearchParams();
  params.set("sort_by", State.queueSort.key);
  params.set("sort_dir", State.queueSort.dir);
  appendVisibilityParams(params);
  return params.toString();
}

function appendVisibilityParams(params) {
  return params;
}

function queueSortSuffix() {
  return `?${queueSortParams()}`;
}

function visibilitySuffix() {
  const params = appendVisibilityParams(new URLSearchParams());
  const value = params.toString();
  return value ? `?${value}` : "";
}

function directProjectionIdFromUrl() {
  const match = decodeURIComponent(window.location.pathname || "").match(/^\/ID=(\d+)\/?$/i);
  return match ? match[1] : null;
}

async function loadDirectProjectionCandidate() {
  const projectionId = directProjectionIdFromUrl();
  if (!projectionId) return false;
  try {
    const candidate = await api(`/candidates/by-projection/${encodeURIComponent(projectionId)}${visibilitySuffix()}`);
    if (candidateGroup(candidate) !== "pending") {
      toast(`ID ${projectionId} no esta pendiente`);
      return false;
    }
    State.current = candidate;
    $("dashboard").classList.add("hidden");
    $("emptyState").classList.add("hidden");
    $("candidatePanel").classList.remove("hidden");
    $("reviewControls").classList.remove("hidden");
    $("progress").textContent = `ID ${projectionId} cargado`;
    renderCandidate(candidate);
    loadHistory(candidate.id);
    return true;
  } catch (e) {
    const cached = cachedCandidates().find((candidate) =>
      String(candidateProjectionId(candidate) || "") === String(projectionId) && candidateGroup(candidate) === "pending"
    );
    if (cached) {
      State.current = cached;
      $("dashboard").classList.add("hidden");
      $("emptyState").classList.add("hidden");
      $("candidatePanel").classList.remove("hidden");
      $("reviewControls").classList.remove("hidden");
      $("progress").textContent = `ID ${projectionId} cargado desde cache`;
      renderCandidate(cached);
      loadHistory(cached.id);
      return true;
    }
    toast(`No se pudo cargar ID ${projectionId}: ${e.message}`);
    return false;
  }
}

function syncQueueSortControls() {
  const byId = $("sortByIdBtn");
  const byScore = $("sortByScoreBtn");
  const dir = $("sortDirBtn");
  if (!byId || !byScore || !dir) return;
  byId.classList.toggle("active", State.queueSort.key === "id");
  byScore.classList.toggle("active", State.queueSort.key === "score");
  dir.textContent = State.queueSort.dir === "desc" ? "Descendente" : "Ascendente";
  dir.classList.toggle("active", true);
}

async function setQueueSort(key = null, toggleDir = false) {
  if (key) {
    State.queueSort.key = key;
    State.tableSort = { key: key === "score" ? "scoreTotal" : "idProj", dir: State.queueSort.dir };
  }
  if (toggleDir) {
    State.queueSort.dir = State.queueSort.dir === "desc" ? "asc" : "desc";
  }
  State.tableSort = { key: State.queueSort.key === "score" ? "scoreTotal" : "idProj", dir: State.queueSort.dir };
  syncQueueSortControls();
  if (!$("candidateTableView").classList.contains("hidden")) renderCandidateTable();
  if (State.user && ["jefatura", "jefecomercial", "coordinador", "arriendo", "comite", "gerente", "gerentegeneral"].includes(State.user.role)) {
    await loadQueue();
  }
}

async function refreshCandidateTable() {
  let items = [];
  const params = appendVisibilityParams(new URLSearchParams());
  const suffix = params.toString() ? `?${params.toString()}` : "";
  try {
    items = await api(`/candidates${suffix}`);
    saveCandidateCache(items);
    flushOfflineActions();
  } catch (e) {
    items = cachedCandidates();
    if (!items.length) {
      toast("Error: " + e.message);
      return;
    }
    toast("Usando cache local");
  }
  State.tableCandidates = items;
  renderCandidateTable();
  if (State.sidebarView === "funnel") renderFunnel();
}

function renderCandidateTable() {
  const counts = tableCounts(State.tableCandidates);
  $("pendingCount").textContent = counts.pending;
  $("observationCount").textContent = counts.observation;
  $("proposedCount").textContent = counts.proposed;
  $("approvedCount").textContent = counts.approved;
  $("rejectedCount").textContent = counts.rejected;
  $("openingCount").textContent = counts.opening;
  $("exportCurrentTableBtn").textContent = `Exportar ${groupExportLabel(State.tableGroup)}`;
  syncTableDateFilterInputs();
  syncCandidateTableHeaders();

  document.querySelectorAll(".table-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.group === State.tableGroup);
  });
  syncTableSortHeaders();

  const rows = sortTableRows(State.tableCandidates.filter((c) =>
    candidateGroup(c) === State.tableGroup &&
    candidateMatchesDateFilter(c, State.tableGroup) &&
    candidateMatchesTableSearch(c)
  ));
  const totalGroupRows = counts[State.tableGroup] || 0;
  $("tableCount").textContent = `${rows.length} de ${totalGroupRows} locales`;
  $("candidateTableBody").innerHTML = rows.length
    ? rows.map((c) => tableRowHtml(c)).join("")
    : `<tr><td colspan="11" class="table-empty">Sin locales en ${esc(groupLabel(State.tableGroup).toLowerCase())}</td></tr>`;

  document.querySelectorAll("[data-table-status]").forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      updateCandidateGroup(Number(btn.dataset.id), btn.dataset.tableStatus);
    };
  });
  document.querySelectorAll("[data-project-variables]").forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      openProjectVariablesForm(Number(btn.dataset.id), { activateOnSave: btn.dataset.activate === "true" });
    };
  });
  document.querySelectorAll("[data-table-history]").forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      toggleTableActionHistory(Number(btn.dataset.id));
    };
  });
  document.querySelectorAll("[data-candidate-row]").forEach((row) => {
    row.onclick = () => selectCandidateFromTable(Number(row.dataset.candidateRow));
  });
  fitActionColumnWidth();
}

function syncCandidateTableHeaders() {
  const opening = State.tableGroup === "opening";
  const labels = opening
    ? {
        idProj: "CveUnidad",
        address: "Unidad",
        applicant: "Region",
        requestedBy: "Solicitado por",
        projection: "Comuna",
        scoreTotal: "ScoreTotal",
        date: "Fecha Proyecto",
        stage: "Etapa",
        group: "Estado",
      }
    : {
        idProj: "ID Proyeccion",
        address: "Direccion",
        applicant: "Solicitante",
        requestedBy: "Solicitado por",
        projection: "ProyeccionMM",
        scoreTotal: "ScoreTotal",
        date: "Fecha",
        stage: "Etapa",
        group: "Estado",
      };
  Object.entries(labels).forEach(([key, label]) => {
    const th = document.querySelector(`.candidate-table th[data-sort-key="${key}"]`);
    if (th) th.childNodes[0].nodeValue = label;
  });
}

function tableRowHtml(c) {
  const group = candidateGroup(c);
  const vars = c.project_variables || {};
  const isOpening = group === "opening";
  const idProj = isOpening ? (vars.cve_unidad || "") : (displayValue(c, ["ID Proyección", "ID Proyeccion", "ID ProyecciÃ³n", "ID"]) || c.id);
  const address = isOpening ? (vars.unidad || "") : (displayValue(c, ["DIRECCIÓN", "DIRECCION", "Direccion", "DIRECCIÃ“N"]) || candidateTitle(c));
  const applicant = isOpening ? (vars.region || "") : (displayValue(c, ["NombreSolicitante"]) || "");
  const requestedBy = candidateRequestedBy(c);
  const proyeccion = isOpening ? (vars.comuna || "") : (displayValue(c, ["PROYECCIÓN", "PROYECCION", "PROYECCIÃ“N"]) || "");
  const scoreTotal = isOpening ? "" : displayValue(c, ["ScoreTotal", "SCORETOTAL", "score_total"]);
  const date = candidateTableDate(c, group);
  const historyOpen = State.tableExpandedActions.has(c.id);
  const actions = candidateTableActions(group, c).map(([target, label]) => {
    if (target === "activate") {
      return `<button class="table-action status-opening" data-id="${c.id}" data-project-variables data-activate="true">${esc(label)}</button>`;
    }
    return `<button class="table-action status-${esc(target)}" data-id="${c.id}" data-table-status="${target}" ${target === group ? "disabled" : ""}>${esc(label)}</button>`;
  }).join("");
  const selectedClass = State.current?.id === c.id ? " selected" : "";
  const mainRow = `<tr class="${selectedClass.trim()}" data-candidate-row="${c.id}">
    <td class="col-history"><button class="table-history-btn" data-id="${c.id}" data-table-history>${historyOpen ? "Ocultar" : "Ver acciones"}</button></td>
    <td class="col-actions"><div class="table-actions">${actions}</div></td>
    <td class="resizable-col">${esc(idProj)}</td>
    <td class="resizable-col col-address" title="${esc(address)}">${esc(address)}</td>
    <td>${esc(applicant)}</td>
    <td>${esc(requestedBy)}</td>
    <td>${esc(proyeccion)}</td>
    <td>${esc(scoreTotal)}</td>
    <td>${esc(c.current_stage)}</td>
    <td><span class="table-status ${esc(group)}">${esc(groupLabel(group))}</span></td>
    <td>${esc(date)}</td>
  </tr>`;
  if (!historyOpen) return mainRow;
  return mainRow + `<tr class="table-action-history-row"><td colspan="11">${tableActionHistoryHtml(c.id)}</td></tr>`;
}

function tableActionHistoryHtml(candidateId) {
  const rawReviews = State.tableActionHistory[candidateId];
  const reviews = Array.isArray(rawReviews) ? rawReviews.filter((r) => r.action !== "skip") : rawReviews;
  if (!reviews) return `<div class="table-action-history">Cargando acciones...</div>`;
  if (!reviews.length) return `<div class="table-action-history">Sin acciones registradas.</div>`;
  return `<div class="table-action-history">${reviews.map((r) => {
    const who = r.reviewer_name || ROLE_LABEL[r.reviewer_role] || r.reviewer_role || "-";
    const when = formatTableDate(r.created_at);
    const note = r.note ? `<div class="table-action-history-note">${esc(r.note)}</div>` : "";
    return `<div class="table-action-history-item">
      <strong>${esc(ACTION_LABEL[r.action] || r.action)}</strong>
      <div>${esc(who)}${note}</div>
      <span>${esc(when)}</span>
    </div>`;
  }).join("")}</div>`;
}

async function toggleTableActionHistory(candidateId) {
  if (State.tableExpandedActions.has(candidateId)) {
    State.tableExpandedActions.delete(candidateId);
    renderCandidateTable();
    return;
  }
  State.tableExpandedActions.add(candidateId);
  renderCandidateTable();
  if (!State.tableActionHistory[candidateId]) {
    try {
      State.tableActionHistory[candidateId] = await api(`/candidates/${candidateId}/reviews${visibilitySuffix()}`);
    } catch (e) {
      State.tableActionHistory[candidateId] = [{ action: "error", reviewer_name: "Error", note: e.message, created_at: "" }];
    }
    renderCandidateTable();
  }
}

async function updateCandidateGroup(candidateId, group) {
  let note = "Cambio desde vista tabla";
  const candidate = State.tableCandidates.find((c) => c.id === candidateId);
  const currentGroup = candidate ? candidateGroup(candidate) : "";
  const isJefaturaMetric = ["like", "dislike"].includes(group);
  if (group === "rejected" || group === "dislike") {
    note = prompt("Ingrese comentario de rechazo:");
    if (!note || !note.trim()) return toast("Comentario requerido");
  }
  if (["comite", "gerentegeneral", "sysadmin"].includes(State.user?.role) && group === "approved") {
    note = await committeeApprovalNote(candidate, null);
    if (note === undefined) return;
  }
  const url = isJefaturaMetric
    ? `/candidates/${candidateId}/review${queueSortSuffix()}`
    : `/candidates/${candidateId}/status${queueSortSuffix()}`;
  const body = isJefaturaMetric
    ? { action: group, note }
    : { group, note };
  try {
    const result = await api(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    toast("Estado actualizado");
    if (["like", "dislike"].includes(group)) {
      State.reviewedThisSession.add(candidateId);
    }
    if (State.tableExpandedActions.has(candidateId)) {
      delete State.tableActionHistory[candidateId];
    }
    applyActionResult(result, candidateId);
  } catch (e) {
    if (!isOfflineError(e)) return toast("Error: " + e.message);
    enqueueOfflineAction({ url, method: "POST", body, candidateId });
    applyOfflineOptimistic(candidateId, group);
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
  if (!$("candidateTableView").classList.contains("hidden")) renderCandidateTable();
}

function candidateTableActions(group, candidate = null) {
  const role = State.user?.role;
  if (role === "sysadmin") {
    if (group === "pending") {
      return [["like", "Like"], ["dislike", "Dislike"], ["skip", "Omitir"], ["proposed", "Proponer"], ["rejected", "Rechazar"]];
    }
    if (["rejected", "observation"].includes(group)) return [["pending", "Pendiente"], ["proposed", "Proponer nuevamente"]];
    if (group === "proposed") return [["skip", "Omitir"], ["approved", "Aprobar"], ["rejected", "Rechazar"]];
    if (group === "approved") return [["activate", "Dar de alta"], ["rejected", "Dar de baja"]];
    if (group === "opening") return [["rejected", "Dar de baja"]];
    return [];
  }
  if (["jefatura", "jefecomercial", "coordinador"].includes(role) && group === "pending") {
    return candidate && isOwnCandidate(candidate)
      ? [["skip", "Omitir"]]
      : [["like", "\u{1F44D}"], ["dislike", "\u{1F44E}"]];
  }
  if (role === "coordinador" && group === "approved") {
    return [["activate", "Dar de alta"]];
  }
  if (["arriendo", "gerente"].includes(role) && group === "pending") {
    return [["skip", "Omitir"], ["proposed", "Proponer"], ["rejected", "Rechazar"]];
  }
  if (["arriendo", "gerente"].includes(role) && ["rejected", "observation"].includes(group)) {
    return [["proposed", "Proponer nuevamente"]];
  }
  if (["comite", "gerentegeneral"].includes(role)) {
    if (group === "proposed") {
      const actions = [["approved", "Aprobar"], ["rejected", "Rechazar"]];
      if (role === "gerentegeneral") actions.unshift(["skip", "Omitir"]);
      return actions;
    }
    if (["approved", "opening"].includes(group)) return [["rejected", "Dar de baja"]];
  }
  return [];
}

function renderProjectMailRecipients() {
  const list = $("projectMailRecipients");
  list.innerHTML = PROJECT_MAIL_RECIPIENTS.map((email) => `
    <label class="project-mail-recipient">
      <input type="checkbox" value="${esc(email)}" checked />
      <span>${esc(email)}</span>
    </label>
  `).join("");
}

function toggleProjectMailPanel(show = null) {
  const panel = $("projectMailPanel");
  const shouldShow = show ?? panel.classList.contains("hidden");
  panel.classList.toggle("hidden", !shouldShow);
  if (shouldShow && !$("projectMailRecipients").children.length) renderProjectMailRecipients();
}

function closeProjectVariablesForm() {
  $("projectVariablesModal").classList.add("hidden");
  $("projectMailPanel").classList.add("hidden");
  $("projectVariablesForm").reset();
  $("projectVariablesForm").dataset.candidateId = "";
  $("projectVariablesForm").dataset.activateOnSave = "false";
}

function showLoading(message = "Procesando...") {
  $("loadingText").textContent = message;
  $("loadingModal").classList.remove("hidden");
}

function hideLoading() {
  $("loadingModal").classList.add("hidden");
}

function requestCommitteeDivision(candidate = State.current) {
  return new Promise((resolve) => {
    const modal = $("divisionModal");
    const form = $("divisionForm");
    $("divisionSubtitle").textContent = candidate
      ? `${displayValue(candidate, ["ID Proyección", "ID Proyeccion", "ID"]) || candidate.id} - ${candidateTitle(candidate)}`
      : "";
    form.reset();
    const close = (value = null) => {
      modal.classList.add("hidden");
      form.onsubmit = null;
      $("divisionCancelBtn").onclick = null;
      $("divisionBackBtn").onclick = null;
      resolve(value);
    };
    form.onsubmit = (event) => {
      event.preventDefault();
      const data = new FormData(form);
      close({
        division: data.get("division"),
        conditions: (data.get("conditions") || "").trim(),
      });
    };
    $("divisionCancelBtn").onclick = () => close(null);
    $("divisionBackBtn").onclick = () => close(null);
    modal.classList.remove("hidden");
  });
}

async function committeeApprovalNote(candidate, existingNote = null) {
  if (!["comite", "gerentegeneral", "sysadmin"].includes(State.user?.role)) return existingNote;
  const result = await requestCommitteeDivision(candidate);
  if (!result || !result.division) return undefined;
  let text = `División: ${result.division}`;
  if (result.conditions) text += `\nCondiciones de aprobación: ${result.conditions}`;
  return existingNote ? `${existingNote}\n${text}` : text;
}

function fillProjectVariableForm(values) {
  const form = $("projectVariablesForm");
  PROJECT_VARIABLE_FIELDS.forEach(([key]) => {
    const field = form.elements[key];
    if (!field) return;
    field.value = values?.[key] ?? "";
  });
}

function projectVariableFormPayload() {
  const form = $("projectVariablesForm");
  const payload = {};
  PROJECT_VARIABLE_FIELDS.forEach(([key, type]) => {
    const field = form.elements[key];
    if (!field) return;
    const raw = String(field.value || "").trim();
    if (!raw) {
      payload[key] = null;
    } else if (type === "number") {
      payload[key] = Number(raw);
    } else {
      payload[key] = raw;
    }
  });
  return payload;
}

function missingActivationVariables(values) {
  return [
    ["cve_unidad", "CveUnidad"],
    ["unidad", "Unidad"],
    ["region", "Región"],
    ["comuna", "Comuna"],
  ].filter(([key]) => !values[key]).map(([, label]) => label);
}

async function activateCandidate(candidateId) {
  const result = await api(`/candidates/${candidateId}/status${queueSortSuffix()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ group: "opening", note: "Dar de alta" }),
  });
  applyActionResult(result, candidateId);
}

function uppercaseProjectVariableField(field) {
  if (!field || field.type === "date" || field.type === "number") return;
  const start = field.selectionStart;
  const end = field.selectionEnd;
  field.value = field.value.toUpperCase();
  try { field.setSelectionRange(start, end); } catch (_) {}
}

function projectMailSelectedRecipients() {
  return [...$("projectMailRecipients").querySelectorAll("input[type='checkbox']:checked")]
    .map((input) => input.value);
}

async function createProjectMail() {
  const recipients = projectMailSelectedRecipients();
  if (!recipients.length) return toast("Seleccione al menos un correo");
  const values = projectVariableFormPayload();
  const shouldActivate = $("projectVariablesForm").dataset.activateOnSave === "true";
  const missing = shouldActivate ? missingActivationVariables(values) : [];
  if (missing.length) {
    return toast(`Complete antes de dar de alta: ${missing.join(", ")}`);
  }
  if (!values.cve_unidad || !values.unidad) {
    return toast("CveUnidad y Unidad son obligatorios");
  }
  const candidateId = Number($("projectVariablesForm").dataset.candidateId);
  if (!candidateId) return;
  $("projectMailCreateBtn").disabled = true;
  showLoading("Enviando correo...");
  try {
    await api(`/candidates/${candidateId}/project-variables/email`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recipients, variables: values }),
    });
    if (shouldActivate) await activateCandidate(candidateId);
    toast(shouldActivate ? "Local dado de alta y correo enviado" : "Correo enviado");
    closeProjectVariablesForm();
  } catch (err) {
    toast("Error: " + err.message);
  } finally {
    hideLoading();
    $("projectMailCreateBtn").disabled = false;
  }
}

function toggleAllProjectMailRecipients() {
  if (!$("projectMailRecipients").children.length) renderProjectMailRecipients();
  const checks = [...$("projectMailRecipients").querySelectorAll("input[type='checkbox']")];
  const shouldCheck = checks.some((input) => !input.checked);
  checks.forEach((input) => { input.checked = shouldCheck; });
  $("projectMailSelectAllBtn").textContent = shouldCheck ? "Quitar todos" : "Seleccionar todos";
}

function wireProjectVariableUppercase() {
  PROJECT_VARIABLE_FIELDS.forEach(([name]) => {
    const field = $("projectVariablesForm")?.elements?.[name];
    if (!field) return;
    field.oninput = () => uppercaseProjectVariableField(field);
    field.onchange = () => uppercaseProjectVariableField(field);
  });
}

function fillProjectDatalist(id, values) {
  const list = $(id);
  if (!list || list.children.length) return;
  list.innerHTML = values.map((value) => `<option value="${esc(value)}"></option>`).join("");
}

function wireProjectVariableCatalogs() {
  fillProjectDatalist("comunaOptions", PROJECT_COMMUNES);
  fillProjectDatalist("regionOptions", PROJECT_REGIONS);
}

async function openProjectVariablesForm(candidateId, { activateOnSave = false } = {}) {
  const candidate = State.tableCandidates.find((c) => c.id === candidateId);
  $("projectVariablesForm").dataset.candidateId = String(candidateId);
  $("projectVariablesForm").dataset.activateOnSave = activateOnSave ? "true" : "false";
  $("projectVariablesSubmitBtn").textContent = activateOnSave ? "Dar de alta" : "Guardar";
  $("projectVariablesSubtitle").textContent = candidate
    ? `${displayValue(candidate, ["ID Proyección", "ID Proyeccion", "ID"]) || candidate.id} - ${candidateTitle(candidate)}`
    : `Local ${candidateId}`;
  const condBox = $("projectApprovalConditions");
  if (candidate?.approval_conditions) {
    condBox.textContent = `Condiciones de aprobación: ${candidate.approval_conditions}`;
    condBox.classList.remove("hidden");
  } else {
    condBox.textContent = "";
    condBox.classList.add("hidden");
  }
  try {
    const values = await api(`/candidates/${candidateId}/project-variables${visibilitySuffix()}`);
    fillProjectVariableForm(values);
    $("projectVariablesModal").classList.remove("hidden");
  } catch (e) {
    toast("Error: " + e.message);
  }
}

async function saveProjectVariablesForm(e) {
  e.preventDefault();
  const candidateId = Number($("projectVariablesForm").dataset.candidateId);
  if (!candidateId) return;
  const values = projectVariableFormPayload();
  const shouldActivate = $("projectVariablesForm").dataset.activateOnSave === "true";
  const missing = shouldActivate ? missingActivationVariables(values) : [];
  if (missing.length) return toast(`Complete antes de dar de alta: ${missing.join(", ")}`);
  const submitBtn = $("projectVariablesForm").querySelector("button[type='submit']");
  if (submitBtn) submitBtn.disabled = true;
  showLoading("Guardando variables...");
  try {
    await api(`/candidates/${candidateId}/project-variables`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
    if (shouldActivate) await activateCandidate(candidateId);
    toast(shouldActivate ? "Local dado de alta" : "Variables guardadas");
    closeProjectVariablesForm();
  } catch (err) {
    toast("Error: " + err.message);
  } finally {
    hideLoading();
    if (submitBtn) submitBtn.disabled = false;
  }
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
  accept: "Propuesto", reject: "Rechazado", star: "Destacado (historico)", like: "Like",
  dislike: "Dislike", skip: "Omitido", send_back: "Devuelto", reopen: "Reabierto",
  project: "Aprobado", opening: "Proyecto", variables_save: "Variables guardadas", variables_email: "Correo enviado",
};

function actionFeedbackMessage(action) {
  if (action === "like") return "Le diste like";
  if (action === "dislike") return "Le diste dislike";
  if (action === "accept") return "Aprobaste este local";
  if (action === "reject") return "Rechazaste este local";
  if (action === "skip") return "Omitiste este local";
  return ACTION_LABEL[action] || "";
}

function userActionForCandidate(reviews = []) {
  const userId = State.user?.id;
  const actions = new Set(["like", "dislike", "skip", "accept", "reject"]);
  return [...reviews]
    .reverse()
    .find((r) => actions.has(r.action) && (!userId || r.reviewer_id === userId));
}

function renderCandidateBanner(candidate, reviews = null) {
  const banner = $("returnedBanner");
  const ownAction = Array.isArray(reviews) ? userActionForCandidate(reviews) : null;
  if (ownAction) {
    banner.textContent = actionFeedbackMessage(ownAction.action);
    banner.classList.remove("hidden");
  } else if (candidate?.status === "returned" || candidate?.status === "devuelto") {
    banner.textContent = "Devuelto para nueva revision";
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
}

function jefaturaMetricCounts(reviews) {
  return reviews
    .filter((r) => ["jefatura", "jefecomercial", "coordinador", "arriendo"].includes(r.reviewer_role) || ["jefatura", "jefecomercial", "coordinador", "arriendo"].includes(r.stage))
    .reduce((acc, r) => {
      if (r.action === "like") acc.like += 1;
      else if (r.action === "dislike") acc.dislike += 1;
      return acc;
    }, { like: 0, dislike: 0 });
}

function renderJefaturaMetrics(reviews = []) {
  const panel = $("jefaturaMetrics");
  if (!panel) return;
  const counts = jefaturaMetricCounts(reviews);
  const total = counts.like + counts.dislike;
  if (!total) {
    panel.classList.add("hidden");
    panel.innerHTML = "";
    return;
  }
  panel.innerHTML = `
    <span class="metric-pill like">👍 ${counts.like}</span>
    <span class="metric-pill dislike">👎 ${counts.dislike}</span>
  `;
  panel.classList.remove("hidden");
}

function renderCandidate(c) {
  if (!c) return;
  const region = displayValue(c, ["NomRegion", "Region", "REGION"]);
  const comuna = displayValue(c, ["NomComuna", "Comuna", "COMUNA"]);
  $("cardTitle").textContent = [region, comuna].filter(Boolean).join(", ") || "Sin region/comuna";
  $("cardLocation").textContent = "";
  renderJefaturaMetrics([]);

  const idBadge = $("idBadge");
  const projectionId = candidateProjectionId(c);
  if (projectionId) {
    idBadge.textContent = `ID: ${projectionId}`;
    idBadge.classList.remove("hidden");
  } else {
    idBadge.classList.add("hidden");
  }

  renderCandidateBanner(c);

  // Score badge.
  const scoreInfo = candidateScore(c);
  const scoreBadge = $("scoreBadge");
  if (scoreInfo) {
    scoreBadge.textContent = `Score: ${scoreInfo.value}`;
    scoreBadge.className = `score-badge ${scoreBandClass(scoreInfo.value)}`;
    scoreBadge.classList.remove("hidden");
  } else {
    scoreBadge.classList.add("hidden");
  }

  const projection = candidateProjection(c);
  const projectionBadge = $("projectionBadge");
  if (projection) {
    projectionBadge.textContent = projection;
    projectionBadge.className = `projection-badge ${projectionBandClass(projection)}`;
    projectionBadge.classList.remove("hidden");
  } else {
    projectionBadge.classList.add("hidden");
  }

  $("cardCoords").textContent = "";

  const sidebarData = { ...(c.display_data || {}) };
  const requestedBy = candidateRequestedBy(c);
  if (requestedBy) sidebarData["Solicitado por"] = requestedBy;
  const rows = buildSidebarDisplayRows(sidebarData, candidateGroup(c));
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
  const isJefaturaLikeRole = ["jefatura", "jefecomercial", "coordinador"].includes(role);
  const ownCandidate = isOwnCandidate(c);
  const canRepropose = ["arriendo", "gerente"].includes(role) && ["rejected", "observation"].includes(group);
  const canAccept =
    (isJefaturaLikeRole && group === "pending" && !ownCandidate) ||
    (["arriendo", "gerente"].includes(role) && ["pending", "rejected", "observation"].includes(group)) ||
    (["comite", "gerentegeneral"].includes(role) && group === "proposed") ||
    role === "sysadmin";
  const canReject =
    (isJefaturaLikeRole && group === "pending" && !ownCandidate) ||
    (["arriendo", "gerente"].includes(role) && group === "pending") ||
    (["comite", "gerentegeneral"].includes(role) && ["proposed", "approved", "opening"].includes(group)) ||
    role === "sysadmin";
  const canSkip =
    (isJefaturaLikeRole && group === "pending") ||
    (["arriendo", "gerente"].includes(role) && group === "pending") ||
    (role === "gerentegeneral" && group === "proposed") ||
    role === "sysadmin";
  const sysadminActions = $("sysadminCandidateActions");
  if (role === "sysadmin") {
    sysadminActions.innerHTML = candidateTableActions(group, c).map(([target, label]) =>
      `<button type="button" class="table-action status-${esc(target === "activate" ? "opening" : target)}" data-sysadmin-action="${esc(target)}">${esc(label)}</button>`
    ).join("");
    sysadminActions.querySelectorAll("[data-sysadmin-action]").forEach((button) => {
      button.onclick = () => {
        const target = button.dataset.sysadminAction;
        if (target === "activate") openProjectVariablesForm(c.id, { activateOnSave: true });
        else updateCandidateGroup(c.id, target);
      };
    });
    sysadminActions.classList.remove("hidden");
  } else {
    sysadminActions.innerHTML = "";
    sysadminActions.classList.add("hidden");
  }
  $("acceptBtn").textContent = isJefaturaLikeRole ? "\u{1F44D}" : canRepropose ? "↻" : "✓";
  $("acceptBtn").title = isJefaturaLikeRole ? "Like" : canRepropose ? "Proponer nuevamente" : "Accept";
  $("acceptBtn").setAttribute("aria-label", $("acceptBtn").title);
  $("rejectBtn").textContent = isJefaturaLikeRole ? "\u{1F44E}" : "X";
  $("rejectBtn").title = isJefaturaLikeRole ? "Dislike" : "Reject";
  $("rejectBtn").setAttribute("aria-label", isJefaturaLikeRole ? "Dislike" : "Reject");
  $("acceptBtn").classList.toggle("hidden", role === "sysadmin" || !canAccept);
  $("rejectBtn").classList.toggle("hidden", role === "sysadmin" || !canReject);
  $("skipBtn").classList.toggle("hidden", role === "sysadmin" || !canSkip);
}

async function loadHistory(candidateId) {
  const section = $("historySection");
  const list = $("historyList");
  let reviews = [];
  try { reviews = await api(`/candidates/${candidateId}/reviews${visibilitySuffix()}`); } catch (_) {}
  renderJefaturaMetrics(reviews);
  if (State.current?.id === candidateId) renderCandidateBanner(State.current, reviews);
  reviews = reviews.filter((r) => r.action !== "skip");
  // Show only prior actions (anything already recorded for this candidate).
  if (!reviews.length) {
    section.classList.add("hidden");
    list.innerHTML = "";
    return;
  }
  list.innerHTML = reviews.map((r) => {
    const when = formatTableDate(r.created_at);
    const role = ROLE_LABEL[r.reviewer_role] || r.reviewer_role || "?";
    const who = r.reviewer_name ? `${r.reviewer_name} - ${role}` : role;
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
  let data = null;
  try {
    data = await api(`/queue${queueSortSuffix()}`);
    flushOfflineActions();
  } catch (e) {
    const candidate = nextCachedCandidate(State.current?.id || null);
    if (!candidate) throw e;
    data = {
      candidate,
      remaining: (State.tableCandidates.length ? State.tableCandidates : cachedCandidates())
        .filter(candidateAllowedForCurrentRole).length,
    };
    toast("DB sin conexion: usando cache local");
  }
  $("progress").textContent =
    data.remaining > 0 ? `${data.remaining} proyecciones pendientes` : "Queue empty";
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
  }
  if (["comite", "gerentegeneral", "sysadmin"].includes(State.user?.role) && action === "accept") {
    note = await committeeApprovalNote(candidate, note);
    if (note === undefined) {
      decide._busy = false;
      return;
    }
  }
  const url = `/candidates/${candidate.id}/review${queueSortSuffix()}`;
  const body = { action, note };
  try {
    const result = await api(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const isJefaturaLikeRole = ["jefatura", "jefecomercial", "coordinador"].includes(State.user?.role);
    const effectiveAction = isJefaturaLikeRole && action === "accept"
      ? "like"
      : isJefaturaLikeRole && action === "reject"
        ? "dislike"
        : action;
    if (["like", "dislike"].includes(effectiveAction)) {
      State.reviewedThisSession.add(candidate.id);
    }
    const label = isJefaturaLikeRole && action === "accept"
      ? "Like"
      : isJefaturaLikeRole && action === "reject"
        ? "Dislike"
        : ACTION_LABEL[action] || "Done";
    toast(label);
    flashPanel(action);
    applyActionResult(result, candidate.id);
  } catch (e) {
    if (!isOfflineError(e)) {
      toast("Error: " + e.message);
    } else {
      enqueueOfflineAction({ url, method: "POST", body, candidateId: candidate.id });
      flashPanel(action);
      applyOfflineOptimistic(candidate.id, action);
    }
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
  $("progress").textContent = "Administrador";
  await refreshStats();
  await refreshDashProjects();
}

async function refreshStats() {
  let s;
  try { s = await api("/stats"); } catch (_) { return; }
  renderStatsPayload(s);
}

function renderStatsPayload(s) {
  const cells = [
    ["Jefatura", s.queues.jefatura, "stage"],
    ["JefeComercial", s.queues.jefecomercial, "stage"],
    ["Coordinador", s.queues.coordinador, "stage"],
    ["Arriendo y Patentes", s.queues.arriendo, "stage"],
    ["Comité", s.queues.comite, "stage"],
    ["Gerente", s.queues.gerente, "stage"],
    ["Gerente General", s.queues.gerentegeneral, "stage"],
    ["Observación", s.statuses.observation, "stage"],
    ["Propuestos", s.statuses.proposed, "stage"],
    ["Aprobados", s.statuses.approved, "ok"],
    ["Rechazados", s.statuses.rejected, "bad"],
    ["Proyectos", s.statuses.por_abrir, "ok"],
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
async function refreshUsers() {
  let users = [];
  try { users = await api("/users"); } catch (_) { return; }
  $("userList").innerHTML = `
    <div class="user-table-wrap">
      <table class="user-table">
        <thead>
          <tr>
            <th>Nombre</th>
            <th>Correo</th>
            <th>Cargo</th>
            <th>Rol</th>
            <th>Grupo / División</th>
            <th>Supervisores</th>
            <th>Activo</th>
            <th>Nueva contraseña</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          ${users.map(userRowHtml).join("")}
        </tbody>
      </table>
    </div>`;
  wireUserTableActions();
  renderOrgChart(users);
}

function syncNewUserRoleFields() {
  const role = $("newUserRole").value;
  const needsDivision = ["jefatura", "jefecomercial", "coordinador"].includes(role);
  $("newUserCommercialDivisionRow").classList.toggle("hidden", !needsDivision);
  $("newUserCommercialDivision").innerHTML = divisionOptionsForRole(role, $("newUserCommercialDivision").value || "SUCURSAL");
  $("newUserSupervisorsRow").classList.toggle("hidden", role !== "jefecomercial");
}

function roleOptions(selected) {
  return Object.entries(ROLE_LABEL).map(([value, label]) =>
    `<option value="${esc(value)}" ${value === selected ? "selected" : ""}>${esc(label)}</option>`
  ).join("");
}

function divisionOptionsForRole(role, selected) {
  const values = role === "jefatura"
    ? [["SUCURSAL", "Sucursal"], ["FRANQUICIA", "Franquicia"], ["APERTURA", "Apertura"]]
    : ["jefecomercial", "coordinador"].includes(role)
      ? [["SUCURSAL", "Sucursal"], ["FRANQUICIA", "Franquicia"]]
      : [];
  const validSelected = values.some(([value]) => value === selected) ? selected : values[0]?.[0];
  return values.map(([value, label]) =>
    `<option value="${value}" ${value === validSelected ? "selected" : ""}>${label}</option>`
  ).join("");
}

function userRowHtml(u) {
  const scopedRole = ["jefatura", "jefecomercial", "coordinador"].includes(u.role);
  return `<tr data-user-id="${esc(u.id)}">
    <td><input class="user-edit-name" value="${esc(u.name)}" /></td>
    <td class="user-email-cell">${esc(u.email)}</td>
    <td><input class="user-edit-job" value="${esc(u.job_title || "")}" placeholder="Cargo" /></td>
    <td><select class="user-edit-role">${roleOptions(u.role)}</select></td>
    <td>
      <select class="user-edit-division ${scopedRole ? "" : "hidden"}">
        ${divisionOptionsForRole(u.role, u.commercial_division || (u.role === "jefatura" ? "APERTURA" : "SUCURSAL"))}
      </select>
      <span class="user-division-empty ${scopedRole ? "hidden" : ""}">-</span>
    </td>
    <td><textarea class="user-edit-supervisors" rows="2" placeholder="Correos">${esc(u.supervisor_emails || "")}</textarea></td>
    <td><input class="user-edit-active" type="checkbox" ${u.active ? "checked" : ""} /></td>
    <td>
      <div class="password-row compact">
        <input class="user-edit-password" type="password" placeholder="Sin cambio" />
        <button type="button" class="mini-btn" data-toggle-row-password>Mostrar</button>
      </div>
    </td>
    <td>
      <div class="user-actions">
        <button type="button" class="mini-btn save" data-save-user>Guardar</button>
        <button type="button" class="mini-btn danger" data-delete-user>Eliminar</button>
      </div>
    </td>
  </tr>`;
}

function syncUserRowDivision(row) {
  const role = row.querySelector(".user-edit-role").value;
  const isScoped = ["jefatura", "jefecomercial", "coordinador"].includes(role);
  const select = row.querySelector(".user-edit-division");
  select.innerHTML = divisionOptionsForRole(role, select.value || (role === "jefatura" ? "APERTURA" : "SUCURSAL"));
  select.classList.toggle("hidden", !isScoped);
  row.querySelector(".user-division-empty").classList.toggle("hidden", isScoped);
}

function togglePasswordInput(input, btn) {
  const showing = input.type === "text";
  input.type = showing ? "password" : "text";
  btn.textContent = showing ? "Mostrar" : "Ocultar";
}

function wireUserTableActions() {
  document.querySelectorAll("#userList tr[data-user-id]").forEach((row) => {
    row.querySelector(".user-edit-role").onchange = () => syncUserRowDivision(row);
    row.querySelector("[data-toggle-row-password]").onclick = () =>
      togglePasswordInput(row.querySelector(".user-edit-password"), row.querySelector("[data-toggle-row-password]"));
    row.querySelector("[data-save-user]").onclick = () => saveUserRow(row);
    row.querySelector("[data-delete-user]").onclick = () => deleteUserRow(row);
  });
}

async function saveUserRow(row) {
  const out = $("userResult");
  const role = row.querySelector(".user-edit-role").value;
  const body = {
    name: row.querySelector(".user-edit-name").value.trim(),
    role,
    job_title: row.querySelector(".user-edit-job").value.trim(),
    supervisor_emails: row.querySelector(".user-edit-supervisors").value.trim(),
    active: row.querySelector(".user-edit-active").checked,
  };
  const password = row.querySelector(".user-edit-password").value;
  if (password) body.password = password;
  if (["jefatura", "jefecomercial", "coordinador"].includes(role)) body.commercial_division = row.querySelector(".user-edit-division").value;
  try {
    await api(`/users/${encodeURIComponent(row.dataset.userId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    out.textContent = "Usuario actualizado.";
    out.className = "result-msg ok";
    await refreshUsers();
  } catch (e) {
    out.textContent = "Error: " + e.message;
    out.className = "result-msg err";
  }
}

async function deleteUserRow(row) {
  const email = row.querySelector(".user-email-cell").textContent;
  if (!confirm(`Eliminar usuario ${email}?`)) return;
  const out = $("userResult");
  try {
    await api(`/users/${encodeURIComponent(row.dataset.userId)}`, { method: "DELETE" });
    out.textContent = "Usuario eliminado.";
    out.className = "result-msg ok";
    await refreshUsers();
  } catch (e) {
    out.textContent = "Error: " + e.message;
    out.className = "result-msg err";
  }
}

function defaultOrgPosition(user, index) {
  const roleOrder = {
    arriendo: [760, 150],
    comite: [760, 280],
    gerentegeneral: [980, 280],
    coordinador: [360, 250],
    jefecomercial: [240, 420],
    jefatura: [80, 250],
    gerente: [560, 150],
    sysadmin: [20, 24],
  };
  const base = roleOrder[user.role] || [60, 80];
  return {
    x: user.org_x ?? (base[0] + (index % 3) * 230),
    y: user.org_y ?? (base[1] + Math.floor(index / 3) * 130),
  };
}

function userAccentClass(role) {
  if (role === "gerente") return "blue";
  if (role === "coordinador" || role === "jefecomercial") return "green";
  if (role === "arriendo") return "pink";
  if (role === "comite") return "purple";
  if (role === "gerentegeneral") return "purple";
  return "slate";
}

function renderOrgChart(users) {
  const chart = $("orgChart");
  if (!chart) return;
  const activeUsers = users.filter((u) => u.active);
  chart.innerHTML = activeUsers.map((u, index) => {
    const pos = defaultOrgPosition(u, index);
    const supervisors = (u.supervisor_emails || "").split(/\r?\n|,|;/).map((s) => s.trim()).filter(Boolean);
    const supervisorPreview = supervisors.slice(0, 4);
    return `<article class="org-node ${userAccentClass(u.role)}" data-org-user="${esc(u.id)}" style="left:${pos.x}px;top:${pos.y}px">
      <strong>${esc(u.job_title || ROLE_LABEL[u.role] || u.role)}</strong>
      <span>${esc(u.name)}</span>
      <small>${esc(ROLE_LABEL[u.role] || u.role)}${u.commercial_division ? ` · ${esc(u.commercial_division)}` : ""}</small>
      ${supervisors.length ? `<em>${supervisors.length} supervisor(es)</em><ul>${supervisorPreview.map((email) => `<li>${esc(email)}</li>`).join("")}${supervisors.length > supervisorPreview.length ? `<li>+${supervisors.length - supervisorPreview.length} más</li>` : ""}</ul>` : ""}
    </article>`;
  }).join("");
  wireOrgDrag();
}

function wireOrgDrag() {
  const chart = $("orgChart");
  chart.querySelectorAll(".org-node").forEach((node) => {
    node.onpointerdown = (event) => {
      event.preventDefault();
      node.setPointerCapture(event.pointerId);
      node.classList.add("dragging");
      const rect = chart.getBoundingClientRect();
      const nodeRect = node.getBoundingClientRect();
      const offsetX = event.clientX - nodeRect.left;
      const offsetY = event.clientY - nodeRect.top;
      const onMove = (moveEvent) => {
        const x = Math.max(8, moveEvent.clientX - rect.left - offsetX + chart.scrollLeft);
        const y = Math.max(8, moveEvent.clientY - rect.top - offsetY + chart.scrollTop);
        node.style.left = `${x}px`;
        node.style.top = `${y}px`;
      };
      const onEnd = async () => {
        node.classList.remove("dragging");
        node.removeEventListener("pointermove", onMove);
        node.removeEventListener("pointerup", onEnd);
        node.removeEventListener("pointercancel", onEnd);
        try {
          await api(`/users/${encodeURIComponent(node.dataset.orgUser)}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              org_x: Math.round(parseFloat(node.style.left) || 0),
              org_y: Math.round(parseFloat(node.style.top) || 0),
            }),
          });
        } catch (e) {
          toast("No se pudo guardar posición: " + e.message);
        }
      };
      node.addEventListener("pointermove", onMove);
      node.addEventListener("pointerup", onEnd);
      node.addEventListener("pointercancel", onEnd);
    };
  });
}

async function resetOrgLayout() {
  const users = await api("/users");
  await Promise.all(users.map((u) => api(`/users/${encodeURIComponent(u.id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ org_x: null, org_y: null }),
  })));
  await refreshUsers();
}

function wireDrawer() {
  const openDrawer = async () => {
    await refreshUsers();
    syncNewUserRoleFields();
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
      job_title: $("newUserJobTitle").value.trim(),
      supervisor_emails: $("newUserSupervisors").value.trim(),
    };
    if (["jefatura", "jefecomercial", "coordinador"].includes(body.role)) {
      body.commercial_division = $("newUserCommercialDivision").value;
    }
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
      $("newUserName").value = $("newUserEmail").value = $("newUserPassword").value = $("newUserJobTitle").value = $("newUserSupervisors").value = "";
      await refreshUsers();
    } catch (e) {
      out.textContent = "Error: " + e.message;
      out.className = "result-msg err";
    }
  };
}

function applyTableColumnWidth(index, width) {
  const table = document.querySelector(".candidate-table");
  if (!table) return;
  const th = table.querySelectorAll("thead th")[index - 1];
  if (th && (th.classList.contains("col-actions") || th.classList.contains("col-history"))) return;
  const next = Math.max(70, Math.min(520, Math.round(width)));
  table.querySelectorAll(`th:nth-child(${index}), td:nth-child(${index})`).forEach((cell) => {
    cell.style.width = `${next}px`;
    cell.style.minWidth = `${next}px`;
    cell.style.maxWidth = `${next}px`;
  });
  try { localStorage.setItem(`candidateTableCol${index}`, String(next)); } catch (_) {}
}

function tableColumnIndex(table, className) {
  const ths = [...table.querySelectorAll("thead th")];
  const idx = ths.findIndex((th) => th.classList.contains(className));
  return idx === -1 ? 0 : idx + 1;
}

function fitActionColumnWidth() {
  const table = document.querySelector(".candidate-table");
  if (!table) return;
  const ths = table.querySelectorAll("thead th");
  const historyIndex = tableColumnIndex(table, "col-history");
  const actionIndex = tableColumnIndex(table, "col-actions");

  if (historyIndex) {
    const historyHeader = ths[historyIndex - 1];
    const historyCells = [...table.querySelectorAll(`td:nth-child(${historyIndex})`)];
    const historyWidth = Math.ceil(Math.max(
      historyHeader ? historyHeader.scrollWidth : 0,
      ...historyCells.map((cell) => cell.scrollWidth)
    ) + 22);
    table.querySelectorAll(`th:nth-child(${historyIndex}), td:nth-child(${historyIndex})`).forEach((cell) => {
      const width = Math.max(132, Math.min(220, historyWidth));
      cell.style.width = `${width}px`;
      cell.style.minWidth = `${width}px`;
      cell.style.maxWidth = `${width}px`;
    });
  }

  if (actionIndex) {
    const actionCells = [...table.querySelectorAll(`td:nth-child(${actionIndex}) .table-actions`)];
    const header = ths[actionIndex - 1];
    const configuredActionsWidth = measureActionButtonsWidth(candidateTableActions(State.tableGroup));
    const contentWidth = Math.max(
      header ? header.scrollWidth : 0,
      configuredActionsWidth,
      ...actionCells.map((el) => el.scrollWidth)
    );
    const hasActions = candidateTableActions(State.tableGroup).length > 0;
    const width = Math.ceil(contentWidth + (hasActions ? 32 : 18));
    table.querySelectorAll(`th:nth-child(${actionIndex}), td:nth-child(${actionIndex})`).forEach((cell) => {
      const next = Math.max(96, Math.min(360, width));
      cell.style.width = `${next}px`;
      cell.style.minWidth = `${next}px`;
      cell.style.maxWidth = `${next}px`;
    });
  }
}

function wireTableColumnResize() {
  const table = document.querySelector(".candidate-table");
  if (!table) return;
  fitActionColumnWidth();
  table.querySelectorAll("thead th").forEach((th, i) => {
    const index = i + 1;
    if (th.classList.contains("col-actions") || th.classList.contains("col-history")) return;
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
  $("skipBtn").onclick = () => decide("skip");
  $("sendBackBtn").onclick = sendBack;
  $("enrichBtn").onclick = toggleBusiness;
  $("funnelBtn").onclick = toggleFunnelView;
  $("toggleViewBtn").onclick = () => setView(State.view === "map" ? "streetview" : "map");
  $("sidebarToggleBtn").onclick = () => {
    const collapsed = document.body.classList.toggle("sidebar-collapsed");
    const label = collapsed ? "Mostrar panel" : "Ocultar panel";
    $("sidebarToggleBtn").title = label;
    $("sidebarToggleBtn").setAttribute("aria-label", label);
    resizeMapSoon();
  };
  $("tableViewBtn").onclick = openCandidateTable;
  $("exportSessionBtn").onclick = exportCommitteeSessionExcel;
  $("sortByIdBtn").onclick = () => setQueueSort("id");
  $("sortByScoreBtn").onclick = () => setQueueSort("score");
  $("sortDirBtn").onclick = () => setQueueSort(null, true);
  $("exportCurrentTableBtn").onclick = () => exportCandidateExcel(false);
  $("exportAllTableBtn").onclick = () => exportCandidateExcel(true);
  $("closeTableBtn").onclick = closeCandidateTable;
  $("projectVariablesCloseBtn").onclick = closeProjectVariablesForm;
  $("projectVariablesCancelBtn").onclick = closeProjectVariablesForm;
  $("projectVariablesForm").onsubmit = saveProjectVariablesForm;
  $("projectMailToggleBtn").onclick = () => toggleProjectMailPanel();
  $("projectMailCancelBtn").onclick = () => toggleProjectMailPanel(false);
  $("projectMailCreateBtn").onclick = createProjectMail;
  $("projectMailSelectAllBtn").onclick = toggleAllProjectMailRecipients;
  $("newUserRole").onchange = syncNewUserRoleFields;
  $("toggleNewUserPasswordBtn").onclick = () =>
    togglePasswordInput($("newUserPassword"), $("toggleNewUserPasswordBtn"));
  $("resetOrgLayoutBtn").onclick = resetOrgLayout;
  wireProjectVariableCatalogs();
  wireProjectVariableUppercase();
  wireTableColumnResize();
  $("tableSearchInput").oninput = () => {
    State.tableSearch = $("tableSearchInput").value;
    renderCandidateTable();
  };
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
  $("funnelDateFrom").onchange = () => {
    State.funnelDateFilter.from = $("funnelDateFrom").value;
    renderFunnel();
  };
  $("funnelDateTo").onchange = () => {
    State.funnelDateFilter.to = $("funnelDateTo").value;
    renderFunnel();
  };
  $("clearFunnelDateBtn").onclick = () => {
    State.funnelDateFilter = { from: "", to: "" };
    $("funnelDateFrom").value = "";
    $("funnelDateTo").value = "";
    renderFunnel();
  };
  document.querySelectorAll(".candidate-table th.sortable").forEach((th) => {
    th.onclick = (e) => {
      if (e.target?.classList?.contains("table-col-resizer")) return;
      const key = th.dataset.sortKey;
      State.tableSort = {
        key,
        dir: State.tableSort.key === key && State.tableSort.dir === "asc" ? "desc" : "asc",
      };
      renderCandidateTable();
    };
  });
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
  $("tourBtn").onclick = () => {
    if (State.user && window.Onboarding) window.Onboarding.start(State.user, { force: true });
  };

  document.addEventListener("keydown", (e) => {
    const t = e.target;
    if (t instanceof Element && t.matches("input, textarea, select")) return;
    if (!$("projectVariablesModal").classList.contains("hidden")) {
      if (e.key === "Escape") closeProjectVariablesForm();
      return;
    }
    if (!$("divisionModal").classList.contains("hidden")) {
      if (e.key === "Escape") $("divisionCancelBtn").click();
      return;
    }
    if (!$("candidateTableView").classList.contains("hidden")) {
      if (e.key === "Escape") closeCandidateTable();
      return;
    }
    if (!State.current) return;
    const k = e.key.toLowerCase();
    if (e.key === "ArrowRight") { e.preventDefault(); decide("accept"); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); decide("reject"); }
    else if (e.key === "ArrowDown" || k === "k") { e.preventDefault(); decide("skip"); }
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
  $("queueSortControls").classList.add("hidden");
  $("exportSessionBtn").classList.add("hidden");
  $("candidateTableView").classList.add("hidden");
  State.sidebarView = "main";
  $("sidebarMainView").classList.remove("hidden");
  $("funnelPanel").classList.add("hidden");
  $("funnelBtn").classList.remove("active");
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
      const user = cachedUser();
      if (ex.status !== 401 && user) {
        await startApp(user, { offline: true });
        return;
      }
      err.textContent = ex.message || "Login failed";
    }
  };
}

async function startApp(user, opts = {}) {
  State.user = user;
  if (!opts.offline) saveUserCache(user);
  State.tableCandidates = cachedCandidates();
  $("loginScreen").classList.add("hidden");
  $("sidebar").classList.remove("hidden");

  const isSysadmin = user.role === "sysadmin";
  const isReviewer = ["jefatura", "jefecomercial", "coordinador", "arriendo", "comite", "gerente", "gerentegeneral"].includes(user.role);
  const canSendBack = false;

  const roleLabel = ROLE_LABEL[user.role] || user.role;
  $("projectName").textContent = `${user.name} - ${roleLabel}${opts.offline ? " (cache)" : ""}`;
  $("menuBtn").classList.toggle("hidden", !isSysadmin);
  $("sendBackBtn").classList.toggle("hidden", !canSendBack);
  $("skipBtn").classList.remove("hidden");
  $("rejectBtn").classList.remove("hidden");
  $("acceptBtn").classList.remove("hidden");
  $("toggleViewBtn").classList.remove("hidden");
  $("sidebarToggleBtn").classList.remove("hidden");
  $("sidebarToggleBtn").title = "Ocultar panel";
  $("sidebarToggleBtn").setAttribute("aria-label", "Ocultar panel");
  $("tableViewBtn").classList.remove("hidden");
  $("queueSortControls").classList.toggle("hidden", !isReviewer || ["comite", "gerentegeneral", "arriendo", "gerente"].includes(user.role));
  syncQueueSortControls();
  $("exportSessionBtn").classList.toggle("hidden", !["comite", "gerentegeneral"].includes(user.role));

  if (opts.offline) toast("DB sin conexion: sesion local recuperada");
  try { await loadGoogleMaps(); } catch (e) { console.warn(e); }
  try { await loadBusinessMarkers(); } catch (_) {}
  if (State.tableCandidates.length) renderCandidateTable();

  const directLoaded = await loadDirectProjectionCandidate();
  if (directLoaded) {
    refreshCandidateTable();
  } else if (isSysadmin) {
    await showDashboard();
  } else if (isReviewer) {
    try { await loadQueue(); } catch (e) { toast("DB sin conexion: esperando cache local"); }
    refreshCandidateTable();
  }
  flushOfflineActions();

  // First-run guided tour (role-branched; tracked in localStorage).
  if (window.Onboarding) window.Onboarding.maybeAutoStart(user);
}

async function boot() {
  initSidebarWidth();
  wireLogin();
  wireDrawer();
  wireInputs();
  wireSidebarResize();
  window.addEventListener("online", flushOfflineActions);
  setInterval(flushOfflineActions, 30000);
  let me = null;
  let meError = null;
  try { me = await api("/me"); } catch (err) { meError = err; }
  if (me) {
    await startApp(me);
  } else if (meError && meError.status !== 401 && cachedUser()) {
    await startApp(cachedUser(), { offline: true });
  } else {
    showLogin();
  }
}

boot();
