/* Site Swiper — first-run onboarding tour (spotlight coachmarks).
 *
 * Role-branched walkthrough that highlights the *real* UI elements one at a
 * time. Auto-runs the first time each user signs in (tracked in localStorage,
 * keyed by user id + tour version) and can be replayed anytime from the header
 * "?" button. No dependencies, no backend state — pure DOM + CSS.
 */
"use strict";

(function () {
  const TOUR_VERSION = 1; // bump to re-trigger the tour for everyone
  const storageKey = (userId) => `siteswiper.onboarding.v${TOUR_VERSION}.${userId}`;

  const $ = (sel) => document.querySelector(sel);

  // ------------------------------------------------------------------ //
  // Small helpers
  // ------------------------------------------------------------------ //
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  // getClientRects() is empty when the element (or an ancestor) is display:none,
  // but non-empty for visible position:fixed elements — unlike offsetParent,
  // which is always null for fixed elements even when they're on screen.
  const isVisible = (el) => !!(el && el.getClientRects().length > 0);

  function waitVisible(selector, timeout = 1500) {
    return new Promise((resolve) => {
      const t0 = Date.now();
      const tick = () => {
        const el = $(selector);
        if (isVisible(el)) return resolve(el);
        if (Date.now() - t0 > timeout) return resolve(el || null);
        setTimeout(tick, 50);
      };
      tick();
    });
  }

  // ------------------------------------------------------------------ //
  // Drawer helpers (sysadmin steps point at the Setup drawer)
  // ------------------------------------------------------------------ //
  async function openDrawer() {
    const drawer = $("#drawer");
    if (drawer && drawer.classList.contains("hidden")) {
      const menu = $("#menuBtn");
      if (menu) menu.click(); // triggers app.js openDrawer (refreshes + shows)
    }
    await waitVisible("#createUserBtn", 1800);
    // The panel slides in with a 0.2s translateX animation; wait for it to
    // finish so the tour measures the element's settled position, not a
    // mid-slide one. Fallback timeout in case the animation already fired.
    const panel = document.querySelector(".drawer-panel");
    if (panel) {
      await new Promise((res) => {
        let done = false;
        const finish = () => { if (!done) { done = true; res(); } };
        panel.addEventListener("animationend", finish, { once: true });
        setTimeout(finish, 450);
      });
    }
  }
  function closeDrawer() {
    const close = $("#drawerClose");
    const drawer = $("#drawer");
    if (close && drawer && !drawer.classList.contains("hidden")) close.click();
  }

  // ------------------------------------------------------------------ //
  // Step definitions per role
  // ------------------------------------------------------------------ //
  function stepsFor(user) {
    const role = user.role;
    const name = (user.name || "").split(" ")[0] || "";
    const welcome = name ? `Te damos la bienvenida, ${name}` : "Te damos la bienvenida";

    if (role === "sysadmin") {
      return [
        {
          title: welcome,
          text: "Eres el Administrador del sistema. Configuras los datos que todos revisan y supervisas todo el flujo. Aquí tienes un recorrido de 60 segundos.",
        },
        {
          target: "#statsGrid",
          title: "Resumen del flujo",
          text: "Un conteo en vivo de los candidatos que esperan en cada capa de revisión (Coordinador, Gerente, Director), además de los totales aprobados y rechazados.",
        },
        {
          target: "#dashProjects",
          title: "Proyectos",
          text: "Todos los proyectos que has creado. Exporta a CSV los resultados decididos de un proyecto directamente desde aquí.",
        },
        {
          target: "#createUserBtn",
          title: "Crea revisores",
          text: "Abre Configuración para agregar a quienes revisan: un Coordinador, un Gerente y un Director para cada capa de revisión.",
          before: openDrawer,
        },
        {
          target: "#createProjectBtn",
          title: "Crea un proyecto",
          text: "Un proyecto es la unidad de trabajo: cada candidato y cada decisión pertenece a uno.",
          before: openDrawer,
        },
        {
          target: "#ingestBtn",
          title: "Carga candidatos",
          text: "Sube un CSV/XLSX de ubicaciones candidatas al proyecto seleccionado. Cada fila se convierte en una tarjeta para revisar.",
          before: openDrawer,
        },
        {
          target: "#businessIngestBtn",
          title: "Capa de negocios",
          text: "Sube las ubicaciones de negocios compartidas (farmacias, estaciones de metro…) que se dibujan en el mapa de todos como contexto.",
          before: openDrawer,
        },
        {
          target: "#drawerExportBtn",
          title: "Exporta resultados",
          text: "Descarga los candidatos decididos en CSV cuando lo necesites.",
          before: openDrawer,
        },
        {
          target: "#tourBtn",
          title: "¡Todo listo!",
          text: "Ese es todo el flujo. Repite este recorrido cuando quieras con el botón ?.",
          before: async () => closeDrawer(),
        },
      ];
    }

    // Reviewer roles: coordinator | manager | director
    const roleIntro = {
      coordinator:
        "Eres el Coordinador: la primera capa de revisión. Los candidatos llegan primero a tu cola; lo que apruebas pasa al Gerente.",
      manager:
        "Eres el Gerente: la segunda capa de revisión. Revisas lo que aprobaron los Coordinadores y puedes devolver un paso los candidatos débiles.",
      director:
        "Eres el Director: la capa de revisión final. Tu aprobación es la decisión definitiva; también puedes devolver un candidato para revisarlo de nuevo.",
    }[role] || "Aquí tienes un recorrido rápido por tu espacio de revisión.";

    const steps = [
      { title: welcome, text: roleIntro },
      {
        target: "#candidatePanel",
        title: "El candidato",
        text: "La ubicación en revisión: su dirección, la insignia de puntuación y todos los datos que necesitas para decidir.",
      },
      {
        target: "#toggleViewBtn",
        title: "Mapa y Street View",
        text: "Alterna entre el mapa y Street View para evaluar el punto exacto sobre el terreno.",
      },
      {
        target: "#enrichBtn",
        title: "Negocios cercanos",
        text: "Muestra u oculta los locales existentes en el mapa (farmacias, estaciones de metro y más) para dar contexto al candidato.",
      },
      {
        target: "#actions",
        title: "Toma la decisión",
        text:
          "Rechazar ✕ (←), Omitir ⤼ (↓), Destacar ★ (↑ / S) para una opción fuerte, Aceptar ✓ (→). " +
          "Con botones o con teclado, ambos funcionan.",
      },
    ];

    if (role === "manager" || role === "director") {
      steps.push({
        target: "#sendBackBtn",
        title: "Devolver un paso",
        text: "¿Aún no puedes decidir? Devuelve el candidato a la capa anterior para otra revisión.",
      });
    }

    steps.push(
      {
        target: "#noteInput",
        title: "Deja una nota",
        text: "Agrega una nota opcional a cualquier decisión: se guarda en el historial del candidato para el siguiente revisor.",
      },
      {
        target: "#tourBtn",
        title: "¡Listo!",
        text: "Esa es tu cola. Repite este recorrido cuando quieras con el botón ?.",
      }
    );

    return steps;
  }

  // ------------------------------------------------------------------ //
  // Engine
  // ------------------------------------------------------------------ //
  const Tour = {
    steps: [],
    i: 0,
    userId: null,
    els: null,
    active: false,

    async start(user, { force = false } = {}) {
      if (this.active) return;
      this.userId = user.id;
      this.steps = stepsFor(user);
      if (!this.steps.length) return;
      this.i = 0;
      this.active = true;
      this._build();
      this._enterDemo(user);
      document.addEventListener("keydown", this._onKey, true);
      window.addEventListener("resize", this._reposition, true);
      await this._render();
    },

    end(markSeen = true) {
      if (!this.active) return;
      this.active = false;
      document.removeEventListener("keydown", this._onKey, true);
      window.removeEventListener("resize", this._reposition, true);
      if (this.els) {
        this.els.root.remove();
        this.els = null;
      }
      this._exitDemo();
      closeDrawer();
      if (markSeen && this.userId) {
        try {
          localStorage.setItem(storageKey(this.userId), "done");
        } catch (_) {}
      }
    },

    async next() {
      if (this.i >= this.steps.length - 1) return this.end(true);
      this.i += 1;
      await this._render();
    },

    async back() {
      if (this.i === 0) return;
      this.i -= 1;
      await this._render();
    },

    // ---- empty-queue demo ---- //
    // Reviewer steps point at the candidate card and action buttons, which the
    // app hides when the queue is empty. So the tour can still highlight them,
    // temporarily reveal those (real) controls with a preview candidate and
    // restore the original state when the tour ends.
    _demo: null,
    _enterDemo(user) {
      if (!["coordinator", "manager", "director"].includes(user.role)) return;
      const panel = $("#candidatePanel");
      const controls = $("#reviewControls");
      const empty = $("#emptyState");
      if (!panel || !controls) return;
      if (!panel.classList.contains("hidden")) return; // queue has a real card already

      this._demo = {
        cardTitle: $("#cardTitle")?.innerHTML,
        cardCoords: $("#cardCoords")?.innerHTML,
        cardData: $("#cardData")?.innerHTML,
        badgeHidden: $("#scoreBadge")?.classList.contains("hidden"),
        emptyShown: empty && !empty.classList.contains("hidden"),
      };

      if ($("#cardTitle")) $("#cardTitle").textContent = "Av. Ejemplo 123 (vista previa)";
      if ($("#cardCoords")) $("#cardCoords").textContent = "Ejemplo · aún no hay cola activa";
      if ($("#cardData")) {
        $("#cardData").innerHTML =
          '<div class="legend-row"><span class="legend-key">Dirección</span><span class="legend-val">Av. Ejemplo 123</span></div>' +
          '<div class="legend-row"><span class="legend-key">Superficie</span><span class="legend-val">85 m²</span></div>' +
          '<div class="legend-row"><span class="legend-key">Puntuación</span><span class="legend-val">72</span></div>';
      }
      const badge = $("#scoreBadge");
      if (badge) { badge.textContent = "Puntuación 72"; badge.className = "score-badge high"; }

      if (empty) empty.classList.add("hidden");
      panel.classList.remove("hidden");
      controls.classList.remove("hidden");
    },
    _exitDemo() {
      if (!this._demo) return;
      const panel = $("#candidatePanel");
      const controls = $("#reviewControls");
      const empty = $("#emptyState");
      if ($("#cardTitle")) $("#cardTitle").innerHTML = this._demo.cardTitle ?? "";
      if ($("#cardCoords")) $("#cardCoords").innerHTML = this._demo.cardCoords ?? "";
      if ($("#cardData")) $("#cardData").innerHTML = this._demo.cardData ?? "";
      const badge = $("#scoreBadge");
      if (badge && this._demo.badgeHidden) badge.classList.add("hidden");
      panel?.classList.add("hidden");
      controls?.classList.add("hidden");
      if (empty && this._demo.emptyShown) empty.classList.remove("hidden");
      this._demo = null;
    },

    // ---- rendering ---- //
    _build() {
      const root = document.createElement("div");
      root.className = "ob-root";
      root.innerHTML = `
        <div class="ob-overlay"></div>
        <div class="ob-spotlight"></div>
        <div class="ob-tooltip" role="dialog" aria-modal="true">
          <button class="ob-skip" type="button" aria-label="Omitir recorrido">Omitir ✕</button>
          <div class="ob-title"></div>
          <div class="ob-text"></div>
          <div class="ob-foot">
            <span class="ob-count"></span>
            <div class="ob-nav">
              <button class="ob-back" type="button">Atrás</button>
              <button class="ob-next" type="button">Siguiente</button>
            </div>
          </div>
        </div>`;
      document.body.appendChild(root);

      const q = (c) => root.querySelector(c);
      this.els = {
        root,
        overlay: q(".ob-overlay"),
        spot: q(".ob-spotlight"),
        tip: q(".ob-tooltip"),
        title: q(".ob-title"),
        text: q(".ob-text"),
        count: q(".ob-count"),
        back: q(".ob-back"),
        next: q(".ob-next"),
        skip: q(".ob-skip"),
      };

      this.els.next.onclick = () => this.next();
      this.els.back.onclick = () => this.back();
      this.els.skip.onclick = () => this.end(true);
      // Clicking the dimmed backdrop does nothing (avoids accidental skips).
      this.els.overlay.onclick = (e) => e.stopPropagation();
    },

    async _render() {
      const step = this.steps[this.i];
      const { els } = this;
      if (step.before) {
        try { await step.before(); } catch (_) {}
        if (!this.active) return; // ended mid-await
      }

      els.title.textContent = step.title || "";
      els.text.textContent = step.text || "";
      els.count.textContent = `${this.i + 1} / ${this.steps.length}`;
      els.back.style.visibility = this.i === 0 ? "hidden" : "visible";
      els.next.textContent = this.i === this.steps.length - 1 ? "Finalizar" : "Siguiente";

      let target = step.target ? $(step.target) : null;
      if (target && !isVisible(target)) target = null;
      this._target = target;

      if (target) {
        try {
          target.scrollIntoView({ block: "center", inline: "nearest" });
        } catch (_) {}
        // Let scroll settle, then position against the final rect.
        await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
        if (!this.active) return;
      }
      this._position(target);
      // Keep the spotlight glued to the target for a short window so it
      // follows any settling layout — e.g. the Setup drawer's 0.2s slide-in
      // transform — instead of freezing at a mid-animation position.
      if (target) this._track(target);
    },

    // Re-measure the target every frame for ~600ms after a step renders.
    _track(target) {
      cancelAnimationFrame(this._trackRaf);
      const start = performance.now();
      const step = (now) => {
        if (!this.active || this._target !== target || !isVisible(target)) return;
        this._position(target);
        if (now - start < 600) this._trackRaf = requestAnimationFrame(step);
      };
      this._trackRaf = requestAnimationFrame(step);
    },

    _position(target) {
      const { els } = this;
      const pad = 8;
      if (!target) {
        els.overlay.classList.add("ob-overlay--full");
        els.spot.style.display = "none";
        this._placeTip(null);
        return;
      }
      els.overlay.classList.remove("ob-overlay--full");
      els.spot.style.display = "block";
      const r = target.getBoundingClientRect();
      Object.assign(els.spot.style, {
        top: `${r.top - pad}px`,
        left: `${r.left - pad}px`,
        width: `${r.width + pad * 2}px`,
        height: `${r.height + pad * 2}px`,
      });
      this._placeTip(r);
    },

    _placeTip(r) {
      const { tip } = this.els;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const m = 12;
      const gap = 14;
      const tw = tip.offsetWidth;
      const th = tip.offsetHeight;

      // No target, or narrow screen: center / bottom-pin.
      if (!r || vw < 640) {
        tip.style.left = `${clamp((vw - tw) / 2, m, vw - tw - m)}px`;
        tip.style.top = r
          ? `${clamp(vh - th - m, m, vh - th - m)}px`
          : `${clamp((vh - th) / 2, m, vh - th - m)}px`;
        return;
      }

      let top, left;
      if (vw - r.right >= tw + gap + m) {
        left = r.right + gap;
        top = r.top + r.height / 2 - th / 2;
      } else if (vh - r.bottom >= th + gap + m) {
        top = r.bottom + gap;
        left = r.left + r.width / 2 - tw / 2;
      } else if (r.top >= th + gap + m) {
        top = r.top - gap - th;
        left = r.left + r.width / 2 - tw / 2;
      } else if (r.left >= tw + gap + m) {
        left = r.left - gap - tw;
        top = r.top + r.height / 2 - th / 2;
      } else {
        left = (vw - tw) / 2;
        top = (vh - th) / 2;
      }
      tip.style.left = `${clamp(left, m, vw - tw - m)}px`;
      tip.style.top = `${clamp(top, m, vh - th - m)}px`;
    },

    // ---- bound handlers ---- //
    _reposition: null,
    _onKey: null,
  };

  // Bind handlers once (stable references for add/removeEventListener).
  Tour._reposition = () => {
    if (Tour.active) Tour._position(Tour._target && isVisible(Tour._target) ? Tour._target : null);
  };
  Tour._onKey = (e) => {
    if (!Tour.active) return;
    const swallow = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", " ", "s", "S", "k", "K", "Enter"];
    if (e.key === "Escape") {
      e.preventDefault(); e.stopImmediatePropagation();
      Tour.end(true);
    } else if (e.key === "ArrowRight" || e.key === "Enter") {
      e.preventDefault(); e.stopImmediatePropagation();
      Tour.next();
    } else if (e.key === "ArrowLeft") {
      e.preventDefault(); e.stopImmediatePropagation();
      Tour.back();
    } else if (swallow.includes(e.key)) {
      // Keep app decision shortcuts from firing behind the tour.
      e.preventDefault(); e.stopImmediatePropagation();
    }
  };

  // ------------------------------------------------------------------ //
  // Public API
  // ------------------------------------------------------------------ //
  window.Onboarding = {
    start(user, opts) {
      if (user) Tour.start(user, opts || {});
    },
    maybeAutoStart(user) {
      if (!user) return;
      let seen = null;
      try { seen = localStorage.getItem(storageKey(user.id)); } catch (_) {}
      if (!seen) Tour.start(user, {});
    },
    reset(userId) {
      try { localStorage.removeItem(storageKey(userId)); } catch (_) {}
    },
  };
})();
