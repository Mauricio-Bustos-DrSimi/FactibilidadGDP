/* Gestor de Proyecciones browser module lifecycle. */
"use strict";

(function exposeGDPModule(global) {
  const FUNNEL_STAGES = [
    { key: "pending", label: "Pendientes + Observación", groups: ["pending", "observation"] },
    { key: "study", label: "En Estudio", groups: ["study"] },
    { key: "proposed", label: "Propuestos", groups: ["proposed"] },
    { key: "approved", label: "Aprobados", groups: ["approved"] },
    { key: "opening", label: "Proyectos", groups: ["opening"] },
  ];

  function createFunnel(deps) {
    function candidateMatchesDate(candidate) {
      const filter = deps.state.funnelDateFilter;
      if (!filter.from && !filter.to) return true;
      const group = deps.candidateGroup(candidate);
      const key = deps.santiagoDateKey(deps.candidateTableDateRaw(candidate, group));
      if (!key) return false;
      if (filter.from && key < filter.from) return false;
      if (filter.to && key > filter.to) return false;
      return true;
    }

    function stageCounts() {
      const visible = deps.state.tableCandidates.filter(candidateMatchesDate);
      return FUNNEL_STAGES.filter((stage) => deps.viewerCanSeeGroup(stage.key)).map((stage) => ({
        ...stage,
        count: visible.filter((candidate) =>
          stage.groups.includes(deps.candidateGroup(candidate))
        ).length,
      }));
    }

    function cachedBaseline() {
      return Math.max(
        0,
        ...deps.state.tableCandidates
          .map(deps.candidateProjectionIdNumber)
          .filter((value) => value != null),
      );
    }

    async function refreshFunnelBaseline() {
      try {
        const payload = await deps.api("/funnel/baseline");
        const value = Number(payload.max_projection_id);
        deps.state.funnelBaseline = Number.isInteger(value) && value >= 0
          ? value
          : cachedBaseline();
      } catch (_) {
        deps.state.funnelBaseline = cachedBaseline();
      }
    }

    function renderFunnel() {
      const container = deps.byId("funnelStages");
      if (!container) return;
      const stages = stageCounts();
      const baseline = deps.state.funnelBaseline || cachedBaseline();
      const pendingStage = stages.find((stage) => stage.key === "pending");
      const widthBaseline = pendingStage?.count ||
        Math.max(1, ...stages.map((stage) => stage.count));
      deps.byId("funnelTotal").textContent =
        `Proyecciones realizadas: ${baseline} (100%)`;
      container.innerHTML = stages.map((stage) => {
        const percentage = baseline ? (stage.count / baseline) * 100 : 0;
        const relativeWidth = (stage.count / widthBaseline) * 100;
        const width = Math.min(100, Math.max(24, relativeWidth));
        return `<button type="button" class="funnel-stage funnel-${deps.escape(stage.key)}" data-funnel-group="${deps.escape(stage.key)}">
          <span class="funnel-stage-label">${deps.escape(stage.label)}</span>
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
      if (!deps.viewerCanSeeGroup(group)) return;
      deps.state.tableGroup = group;
      deps.state.tableDateFilters[group] = { ...deps.state.funnelDateFilter };
      await deps.openCandidateTable();
    }

    async function setFunnelView(showFunnel, refresh = true) {
      deps.state.sidebarView = showFunnel ? "funnel" : "main";
      deps.byId("sidebarMainView").classList.toggle("hidden", showFunnel);
      deps.byId("funnelPanel").classList.toggle("hidden", !showFunnel);
      deps.byId("funnelBtn").classList.toggle("active", showFunnel);
      deps.byId("funnelBtn").title = showFunnel ? "Volver al local" : "Ver Embudo";
      deps.byId("funnelBtn").setAttribute("aria-label", deps.byId("funnelBtn").title);
      if (showFunnel && refresh) {
        await deps.refreshCandidateTable();
        renderFunnel();
      }
    }

    async function toggleFunnelView() {
      await setFunnelView(deps.state.sidebarView !== "funnel");
    }

    return Object.freeze({
      openTableFromFunnel,
      refreshFunnelBaseline,
      renderFunnel,
      setFunnelView,
      toggleFunnelView,
    });
  }

  function createMapView({ state, byId, api }) {
    let mapsLoading = null;

    function initMap() {
      state.map = new global.google.maps.Map(byId("map"), {
        center: { lat: -33.45, lng: -70.67 },
        zoom: 15,
        disableDefaultUI: true,
        zoomControl: true,
        gestureHandling: "greedy",
        clickableIcons: false,
      });
      state.svService = new global.google.maps.StreetViewService();
    }

    async function loadGoogleMaps() {
      if (state.mapsReady) return;
      if (mapsLoading) return mapsLoading;
      const cfg = await api("/config");
      if (!cfg.google_maps_api_key) {
        byId("map").innerHTML =
          '<div style="padding:24px;color:#94a3b8;text-align:center;margin-top:20vh">' +
          "Google Maps API key not set.<br/>Set <code>GOOGLE_MAPS_API_KEY</code> and restart.</div>";
        state.mapsReady = false;
        return;
      }
      mapsLoading = new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = `https://maps.googleapis.com/maps/api/js?key=${cfg.google_maps_api_key}`;
        script.async = true;
        script.onload = resolve;
        script.onerror = () => reject(new Error("Maps failed to load"));
        document.head.appendChild(script);
      });
      await mapsLoading;
      initMap();
      state.mapsReady = true;
    }

    function computeHeading(from, to) {
      const toRad = (degrees) => (degrees * Math.PI) / 180;
      const deltaLongitude = toRad(to.lng - from.lng);
      const latitude1 = toRad(from.lat);
      const latitude2 = toRad(to.lat);
      const y = Math.sin(deltaLongitude) * Math.cos(latitude2);
      const x = Math.cos(latitude1) * Math.sin(latitude2) -
        Math.sin(latitude1) * Math.cos(latitude2) * Math.cos(deltaLongitude);
      return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
    }

    function updateStreetView(lat, lng) {
      if (!state.svService) return;
      const target = { lat, lng };
      state.svService.getPanorama(
        {
          location: target,
          radius: 100,
          preference: global.google.maps.StreetViewPreference.NEAREST,
        },
        (data, status) => {
          if (status === global.google.maps.StreetViewStatus.OK) {
            if (!state.panorama) {
              state.panorama = new global.google.maps.StreetViewPanorama(byId("streetview"), {
                addressControl: false,
                fullscreenControl: false,
                motionTracking: false,
                motionTrackingControl: false,
                linksControl: true,
                enableCloseButton: false,
                zoomControl: false,
              });
            }
            const streetPosition = data.location.latLng;
            state.panorama.setPosition(streetPosition);
            const heading = computeHeading(
              { lat: streetPosition.lat(), lng: streetPosition.lng() },
              target,
            );
            state.panorama.setPov({ heading, pitch: 0 });
            byId("svUnavailable").classList.add("hidden");
          } else {
            byId("svUnavailable").textContent =
              "No hay Street View disponible en esta ubicación";
            byId("svUnavailable").classList.remove("hidden");
          }
        },
      );
    }

    async function setView(view) {
      if (!state.mapsReady) {
        try { await loadGoogleMaps(); } catch (error) { console.warn(error); }
      }
      state.view = view;
      const toMap = view === "map";
      byId("map").style.display = toMap ? "block" : "none";
      byId("streetview").style.display = toMap ? "none" : "block";
      byId("toggleViewBtn").textContent = toMap ? "Street View" : "Mapa";
      byId("toggleViewBtn").title = toMap ? "Switch to Street View" : "Switch to Map";
      if (toMap) {
        if (state.mapsReady) {
          global.google.maps.event.trigger(state.map, "resize");
          if (state.current?.lat != null) {
            state.map.setCenter({ lat: state.current.lat, lng: state.current.lng });
          }
        }
        return;
      }
      const center = state.current?.lat != null
        ? { lat: state.current.lat, lng: state.current.lng }
        : state.map?.getCenter?.()?.toJSON?.();
      if (!center) {
        byId("svUnavailable").textContent = "Seleccione un local para abrir Street View";
        byId("svUnavailable").classList.remove("hidden");
        return;
      }
      byId("svUnavailable").classList.add("hidden");
      updateStreetView(center.lat, center.lng);
      requestAnimationFrame(() => {
        if (state.panorama) global.google.maps.event.trigger(state.panorama, "resize");
      });
    }

    return Object.freeze({ loadGoogleMaps, setView, updateStreetView });
  }

  function create(deps) {
    async function start(user, opts = {}) {
      if (!user) return deps.applicationShell.showLogin();
      deps.stopOtherModuleSync();
      deps.state.user = user;
      deps.state.module = "gestor";
      if (!opts.offline) deps.saveUserCache(user);
      deps.state.tableCandidates = deps.cachedCandidates().filter((candidate) =>
        deps.viewerCanSeeGroup(deps.candidateGroup(candidate))
      );
      if (deps.isViewerGerente()) deps.state.tableGroup = "study";
      document.title = "Gestor de Proyecciones";
      deps.prepareBody();
      deps.byId("loginScreen").classList.add("hidden");
      deps.byId("moduleMenu").classList.add("hidden");
      deps.byId("sidebar").classList.remove("hidden");
      deps.state.sidebarView = "main";
      deps.byId("sidebarHeader").classList.remove("hidden");
      deps.byId("sidebarMainView").classList.remove("hidden");
      deps.byId("funnelPanel").classList.add("hidden");
      deps.prepareLayout();
      await deps.setFunnelView(true, false);

      const isSysadmin = user.role === "sysadmin";
      const isReviewer = [
        "jefatura", "jefecomercial", "coordinador", "arriendo", "comite",
        "gerente", "gerentegeneral",
      ].includes(user.role);
      const roleLabel = deps.roleLabels[user.role] || user.role;
      deps.byId("projectName").textContent =
        `${user.name} - ${roleLabel}${opts.offline ? " (cache)" : ""}`;
      deps.byId("menuBtn").classList.toggle("hidden", !isSysadmin);
      deps.byId("sendBackBtn").classList.add("hidden");
      deps.byId("skipBtn").classList.remove("hidden");
      deps.byId("rejectBtn").classList.remove("hidden");
      deps.byId("acceptBtn").classList.remove("hidden");
      deps.byId("toggleViewBtn").classList.remove("hidden");
      deps.byId("sidebarToggleBtn").classList.remove("hidden");
      deps.byId("sidebarToggleBtn").title = "Ocultar panel";
      deps.byId("sidebarToggleBtn").setAttribute("aria-label", "Ocultar panel");
      deps.byId("tableViewBtn").classList.remove("hidden");
      deps.byId("queueSortControls").classList.toggle(
        "hidden",
        !isReviewer || ["comite", "gerentegeneral", "arriendo", "gerente"].includes(user.role),
      );
      deps.syncQueueSortControls();
      deps.byId("exportSessionBtn").classList.toggle(
        "hidden", !["comite", "gerentegeneral"].includes(user.role),
      );
      deps.byId("exportAllTableBtn").classList.toggle("hidden", deps.isViewerGerente());

      if (opts.offline) deps.toast("DB sin conexion: sesion local recuperada");
      await deps.setView("map");
      try { await deps.loadBusinessMarkers(); } catch (_) {}
      if (deps.state.tableCandidates.length) deps.renderCandidateTable();

      const directLoaded = await deps.loadDirectProjectionCandidate();
      if (!directLoaded && isSysadmin) {
        await deps.showDashboard();
      } else if (!directLoaded && isReviewer) {
        try { await deps.loadQueue(); } catch (_) {
          deps.toast("DB sin conexion: esperando cache local");
        }
      }
      await deps.refreshCandidateTable();
      deps.flushOfflineActions();
      deps.startLiveCandidateSync();
      if (global.Onboarding) global.Onboarding.maybeAutoStart(user);
    }

    function stop() {
      deps.stopLiveCandidateSync();
    }

    return Object.freeze({ start, stop });
  }

  global.GDPModule = Object.freeze({ create, createFunnel, createMapView });
})(window);
