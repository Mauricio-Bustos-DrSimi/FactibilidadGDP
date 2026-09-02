/* Shared browser shell: identity screen, module selection and navigation. */
"use strict";

(function exposeApplicationShell(global) {
  const FACTIBILITY_USER_EMAIL = "admjennifer@porunpaismejor.com.mx";
  const FACTIBILITY_ACCESS_DENIED =
    "Acceso denegado, su usuario no tiene permiso para realizar esta acción.";

  function create({
    state,
    byId,
    api,
    roleLabel,
    cachedUser,
    saveUserCache,
    stopGestorSync,
    stopFactibilitySync,
    toast,
  }) {
    function canAccessFactibility(user = state.user) {
      return Boolean(user) && (
        user.role === "sysadmin" ||
        String(user.email || "").trim().toLowerCase() === FACTIBILITY_USER_EMAIL
      );
    }

    function showFactibilityAccessDenied() {
      toast(FACTIBILITY_ACCESS_DENIED, { duration: 5000, centered: true });
    }

    function showLogin() {
      stopGestorSync();
      stopFactibilitySync();
      state.module = null;
      state.user = null;
      document.title = "Plataforma de Proyectos";
      document.body.classList.remove("module-factibility", "sidebar-collapsed");
      byId("loginScreen").classList.remove("hidden");
      byId("moduleMenu").classList.add("hidden");
      byId("sidebar").classList.add("hidden");
      byId("toggleViewBtn").classList.add("hidden");
      byId("sidebarToggleBtn").classList.add("hidden");
      byId("tableViewBtn").classList.add("hidden");
      byId("queueSortControls").classList.add("hidden");
      byId("exportSessionBtn").classList.add("hidden");
      byId("candidateTableView").classList.add("hidden");
      byId("factibilityView").classList.add("hidden");
      state.sidebarView = "main";
      byId("sidebarHeader").classList.remove("hidden");
      byId("sidebarMainView").classList.remove("hidden");
      byId("funnelPanel").classList.add("hidden");
      byId("funnelBtn").classList.remove("active");
      byId("factibilitySidebar").classList.add("hidden");
    }

    function showModuleMenu(user, opts = {}) {
      if (!user) return showLogin();
      stopGestorSync();
      stopFactibilitySync();
      state.user = user;
      state.module = null;
      if (!opts.offline) saveUserCache(user);
      document.title = "Plataforma de Proyectos";
      document.body.classList.remove("module-factibility", "sidebar-collapsed");
      byId("loginScreen").classList.add("hidden");
      byId("moduleMenu").classList.remove("hidden");
      byId("moduleUserName").textContent = `${user.name} · ${roleLabel(user)}`;
      byId("sidebar").classList.add("hidden");
      byId("candidateTableView").classList.add("hidden");
      byId("factibilityView").classList.add("hidden");
      byId("toggleViewBtn").classList.add("hidden");
      byId("sidebarToggleBtn").classList.add("hidden");
      byId("tableViewBtn").classList.add("hidden");
    }

    function wireLogin() {
      byId("loginForm").onsubmit = async (event) => {
        event.preventDefault();
        const error = byId("loginError");
        error.textContent = "";
        try {
          const user = await api("/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              email: byId("loginEmail").value.trim(),
              password: byId("loginPassword").value,
            }),
          });
          showModuleMenu(user);
        } catch (exception) {
          const user = cachedUser();
          if (exception.status !== 401 && user) {
            showModuleMenu(user, { offline: true });
            return;
          }
          error.textContent = exception.message || "Login failed";
        }
      };
    }

    function wireNavigation({ startGestor, startFactibility }) {
      byId("moduleBackBtn").onclick = () => showModuleMenu(state.user);
      byId("gestorModuleBtn").onclick = () => startGestor(state.user);
      byId("factibilityModuleBtn").onclick = () => startFactibility(state.user);
      const logout = async () => {
        try { await api("/auth/logout", { method: "POST" }); } catch (_) {}
        global.location.reload();
      };
      byId("logoutBtn").onclick = logout;
      byId("moduleLogoutBtn").onclick = logout;
    }

    function restoreSession(user, error) {
      if (user) {
        showModuleMenu(user);
      } else if (error && error.status !== 401 && cachedUser()) {
        showModuleMenu(cachedUser(), { offline: true });
      } else {
        showLogin();
      }
    }

    return Object.freeze({
      canAccessFactibility,
      restoreSession,
      showFactibilityAccessDenied,
      showLogin,
      showModuleMenu,
      wireLogin,
      wireNavigation,
    });
  }

  window.ApplicationShell = Object.freeze({ create });
})(window);
