/* Factibilidad browser module: list, checklist, approvals and local library. */
"use strict";

(function exposeFactibilityModule(global) {
  function create(deps) {
    const {
      getApplicationShell,
      shellState,
      byId: $,
      api,
      escape: esc,
      searchText,
      parseUtcLikeDate,
      santiagoDateKey,
      elapsedCalendarDays,
      formatTableDate,
      toast,
      openSalesSheet,
      saveUserCache,
      stopOtherModuleSync,
      roleLabels,
    } = deps;
    const state = {
      locations: [],
      expandedLocations: new Set(),
      selectedId: null,
      area: "legal",
      search: "",
      sort: "id_desc",
      attachmentContext: null,
      syncVersion: "",
      syncTimer: null,
      syncRunning: false,
    };

const FACTIBILITY_STATUS_LABELS = {
  realizado: "Realizado",
  en_proceso: "En Proceso",
  no_realizado: "No Realizado",
  no_aplica: "No Aplica",
};

const FACTIBILITY_DECISION_LABELS = {
  pendiente: "Pendiente",
  en_proceso: "En Proceso",
  rechazado: "Rechazado",
  completado: "Completado",
};

function factibilityGroupId(candidateId, groupKey) {
  return `${candidateId}:${groupKey}`;
}

function factibilityLocationHeading(item) {
  const candidate = item.candidate;
  const projectionId = candidateProjectionId(candidate) || candidate.id;
  const variables = item.sales_sheet || candidate.project_variables || {};
  const cveUnidad = variables.cve_unidad || displayValue(candidate, ["CveUnidad", "CVEUNIDAD"]);
  const unidad = variables.unidad || displayValue(candidate, ["Unidad", "UNIDAD"]);
  return {
    title: `ID ${projectionId}`,
    subtitle: [cveUnidad, unidad].filter(Boolean).join(", ") || "Sin CveUnidad y Unidad",
  };
}

function factibilityOverallProgress(item) {
  const total = item.task_groups.reduce((sum, group) => sum + group.total, 0);
  const completed = item.task_groups.reduce((sum, group) => sum + group.completed, 0);
  return {
    total,
    completed,
    progress: total ? Math.round((completed / total) * 100) : 0,
  };
}

function factibilityAreaProgress(item, area) {
  const groups = item.task_groups.filter((group) => group.area === area);
  const total = groups.reduce((sum, group) => sum + group.total, 0);
  const completed = groups.reduce((sum, group) => sum + group.completed, 0);
  return { total, completed, progress: total ? Math.round((completed / total) * 100) : 0 };
}

function factibilityProgressHue(progress) {
  return Math.max(0, Math.min(120, Number(progress) * 1.2));
}

function factibilityDisplayDecision(item) {
  const saved = item.decision?.decision;
  if (saved) return saved;
  const started = item.task_groups.some((group) =>
    group.subtasks.some((task) => task.status !== "no_realizado")
  );
  return started ? "en_proceso" : "pendiente";
}

function factibilityStatusOptions(selected) {
  return Object.entries(FACTIBILITY_STATUS_LABELS).map(([value, label]) =>
    `<option value="${value}"${value === selected ? " selected" : ""}>${label}</option>`
  ).join("");
}

function factibilityProjectionSortValue(item) {
  const value = candidateProjectionId(item.candidate) || item.candidate.id;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : String(value);
}

function factibilityProjectDate(item) {
  return candidateTableDateRaw(item.candidate, "opening");
}

function factibilityApprovalLabel(area) {
  return area === "legal" ? "Legal" : "Arquitectura";
}

function formatFactibilityApprovalDate(value) {
  const date = parseUtcLikeDate(value);
  if (!date) return "";
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "America/Santiago",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${byType.day}/${byType.month}/${byType.year} ${byType.hour}:${byType.minute}:${byType.second}`;
}

function factibilityApprovalDays(item, approval) {
  const start = santiagoDateKey(factibilityProjectDate(item));
  const end = santiagoDateKey(approval?.approved_at);
  return elapsedCalendarDays(start, end);
}

function factibilityApprovalText(item, area) {
  const approval = item.approvals?.[area];
  if (!approval) return `VB ${factibilityApprovalLabel(area)} - Pendiente`;
  const days = factibilityApprovalDays(item, approval);
  const delta = days == null ? "sin fecha de notificación" : `${days} día${days === 1 ? "" : "s"} desde notificación de proyecto`;
  return `VB ${factibilityApprovalLabel(area)} - ${formatFactibilityApprovalDate(approval.approved_at)} | ${delta}`;
}

function factibilityCompletionDays(item, completedAt) {
  if (!completedAt) return null;
  const start = santiagoDateKey(factibilityProjectDate(item));
  const end = santiagoDateKey(completedAt);
  return elapsedCalendarDays(start, end);
}

function factibilityElapsedText(item, completedAt) {
  const days = factibilityCompletionDays(item, completedAt);
  return `Días transcurridos: ${days == null ? "Pendiente" : days}`;
}

function visibleFactibilityLocations() {
  const query = searchText(state.search).trim();
  const filtered = state.locations.filter((item) => {
    if (!query) return true;
    const heading = factibilityLocationHeading(item);
    const variables = item.sales_sheet || item.candidate.project_variables || {};
    return [
      factibilityProjectionSortValue(item),
      heading.title,
      variables.cve_unidad,
      variables.unidad,
    ].some((value) => searchText(value).includes(query));
  });
  const [key, direction] = state.sort.split("_");
  const factor = direction === "asc" ? 1 : -1;
  return [...filtered].sort((a, b) => {
    if (key === "date") {
      const left = parseUtcLikeDate(factibilityProjectDate(a))?.getTime() || 0;
      const right = parseUtcLikeDate(factibilityProjectDate(b))?.getTime() || 0;
      return (left - right) * factor;
    }
    const left = factibilityProjectionSortValue(a);
    const right = factibilityProjectionSortValue(b);
    if (typeof left === "number" && typeof right === "number") return (left - right) * factor;
    return String(left).localeCompare(String(right), "es", { numeric: true }) * factor;
  });
}

function renderFactibilityLocations() {
  const container = $("factibilityLocations");
  const items = visibleFactibilityLocations();
  document.querySelectorAll("[data-factibility-area]").forEach((button) => {
    const active = button.dataset.factibilityArea === state.area;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  $("factibilitySearchInput").oninput = () => {
    state.search = $("factibilitySearchInput").value;
    renderFactibilityLocations();
  };
  $("factibilitySortSelect").onchange = () => {
    state.sort = $("factibilitySortSelect").value;
    renderFactibilityLocations();
  };
  $("factibilityCount").textContent = state.search
    ? `${items.length} de ${state.locations.length} locales en Proyectos`
    : `${items.length} local${items.length === 1 ? "" : "es"} en Proyectos`;
  if (!items.length) {
    container.innerHTML = `<div class="factibility-empty">${state.search ? "No hay locales que coincidan con la búsqueda." : "No hay locales actualmente en Proyectos."}</div>`;
    return;
  }
  container.innerHTML = items.map((item) => {
    const candidateId = item.candidate.id;
    const heading = factibilityLocationHeading(item);
    const decision = factibilityDisplayDecision(item);
    const overall = factibilityOverallProgress(item);
    const expanded = state.expandedLocations.has(candidateId);
    const selected = state.selectedId === candidateId;
    const approvals = expanded ? `
      <section class="factibility-vb-panel" aria-label="Vistos buenos del local">
        ${["legal", "arquitectura"].map((area) => {
          const approval = item.approvals?.[area];
          return `<button type="button" class="factibility-vb-check${approval ? " approved" : ""}"
            data-factibility-approval="${area}" data-candidate-id="${candidateId}"
            role="checkbox" aria-checked="${Boolean(approval)}" ${approval ? "disabled" : ""}>
            <span class="factibility-vb-box">${approval ? "✓" : ""}</span>
            <span>${esc(factibilityApprovalText(item, area))}</span>
          </button>`;
        }).join("")}
      </section>` : "";
    const groups = expanded ? item.task_groups
      .filter((group) => group.area === state.area)
      .map((group) => {
      const groupId = factibilityGroupId(candidateId, group.key);
      const rows = group.subtasks.map((task) => {
        const salesSheetButton = task.key === "legal_asociar_ficha_ventas"
          ? `<button type="button" class="factibility-sales-sheet-btn" data-factibility-sales-sheet="${candidateId}">Editar ficha</button>`
          : "";
        return `
        <div class="factibility-subtask" data-candidate-id="${candidateId}" data-task-key="${esc(task.key)}">
          <div class="factibility-subtask-heading">
            <span class="factibility-subtask-name">${esc(task.title)}</span>
            ${salesSheetButton}
          </div>
          <select class="factibility-status" aria-label="Estado de ${esc(task.title)}">
            ${factibilityStatusOptions(task.status)}
          </select>
          <textarea class="factibility-comment" rows="1" placeholder="Comentarios sobre esta tarea">${esc(task.comment || "")}</textarea>
        </div>`;
      }).join("");
      return `
        <section class="factibility-task-group" data-group-id="${esc(groupId)}">
          <div class="factibility-task-summary">
            <div class="factibility-task-title-row">
              <span>${esc(group.title)}</span>
              <div class="factibility-task-tools">
                <span class="factibility-task-progress-label" style="color:hsl(${factibilityProgressHue(group.progress)} 88% 52%)">${group.completed}/${group.total} · ${group.progress}%</span>
                <span class="factibility-task-elapsed${group.completed_at ? " completed" : ""}">${esc(factibilityElapsedText(item, group.completed_at))}</span>
                <button type="button" class="factibility-attachment-btn" data-factibility-files="${esc(group.key)}" data-group-title="${esc(group.title)}" data-candidate-id="${candidateId}">Adjuntar / ver archivos</button>
              </div>
            </div>
            <div class="factibility-progress-track" aria-label="Avance ${group.progress}%">
              <div class="factibility-progress-bar" style="width:${group.progress}%"></div>
            </div>
          </div>
          <div class="factibility-subtasks">${rows}</div>
        </section>`;
      }).join("") : "";
    return `
      <article class="factibility-location${selected ? " selected" : ""}" data-candidate-id="${candidateId}">
        <div class="factibility-location-summary" role="button" tabindex="0" aria-expanded="${expanded}">
          <div>
            <div class="factibility-location-title">${esc(heading.title)}</div>
            <div class="factibility-location-subtitle">${esc(heading.subtitle)}</div>
          </div>
          <div class="factibility-location-progress">
            <div class="factibility-location-progress-label">
              <span style="color:hsl(${factibilityProgressHue(overall.progress)} 88% 52%)">${overall.progress}%</span>
            </div>
            <div class="factibility-progress-track" aria-label="Avance total ${overall.progress}%">
              <div class="factibility-progress-bar" style="width:${overall.progress}%"></div>
            </div>
            <span class="factibility-decision-badge ${esc(decision)}">${esc(FACTIBILITY_DECISION_LABELS[decision] || decision)}</span>
            <button type="button" class="factibility-local-library-btn" data-factibility-local-library="${candidateId}">Biblioteca del local</button>
          </div>
        </div>
        <div class="factibility-location-body${expanded ? "" : " hidden"}">
          ${approvals}
          ${groups}
          <div class="factibility-actions">
            <button type="button" class="factibility-action reject" data-factibility-decision="rechazado" data-candidate-id="${candidateId}">Rechazar</button>
            <button type="button" class="factibility-action complete" data-factibility-decision="completado" data-candidate-id="${candidateId}">Completado</button>
          </div>
        </div>
      </article>`;
  }).join("");

  container.querySelectorAll(".factibility-location-summary").forEach((summary) => {
    const selectAndToggle = () => {
      const candidateId = Number(summary.closest(".factibility-location").dataset.candidateId);
      state.selectedId = candidateId;
      if (state.expandedLocations.has(candidateId)) state.expandedLocations.delete(candidateId);
      else state.expandedLocations.add(candidateId);
      renderFactibilityLocations();
    };
    summary.onclick = selectAndToggle;
    summary.onkeydown = (event) => {
      if (!["Enter", " "].includes(event.key)) return;
      event.preventDefault();
      selectAndToggle();
    };
  });
  container.querySelectorAll(".factibility-status").forEach((select) => {
    select.onchange = () => saveFactibilityTask(select.closest(".factibility-subtask"));
  });
  container.querySelectorAll(".factibility-comment").forEach((textarea) => {
    textarea.onblur = () => saveFactibilityTask(textarea.closest(".factibility-subtask"));
    textarea.onkeydown = (event) => {
      if (event.key !== "Enter" || event.shiftKey) return;
      event.preventDefault();
      saveFactibilityTask(textarea.closest(".factibility-subtask"));
    };
  });
  container.querySelectorAll("[data-factibility-sales-sheet]").forEach((button) => {
    button.onclick = () => openSalesSheet(Number(button.dataset.factibilitySalesSheet));
  });
  container.querySelectorAll("[data-factibility-approval]").forEach((button) => {
    button.onclick = () => saveFactibilityApproval(
      Number(button.dataset.candidateId),
      button.dataset.factibilityApproval,
      button,
    );
  });
  container.querySelectorAll("[data-factibility-decision]").forEach((button) => {
    button.onclick = () => saveFactibilityDecision(
      Number(button.dataset.candidateId),
      button.dataset.factibilityDecision,
      button,
    );
  });
  container.querySelectorAll("[data-factibility-files]").forEach((button) => {
    button.onclick = () => openFactibilityAttachments(
      Number(button.dataset.candidateId),
      button.dataset.factibilityFiles,
      button.dataset.groupTitle,
    );
  });
  container.querySelectorAll("[data-factibility-local-library]").forEach((button) => {
    button.onclick = (event) => {
      event.stopPropagation();
      openFactibilityLocalLibrary(Number(button.dataset.factibilityLocalLibrary));
    };
    button.onkeydown = (event) => event.stopPropagation();
  });
  renderFactibilitySidebar(
    state.locations.find((item) => item.candidate.id === state.selectedId) || null,
  );
}

function renderFactibilitySidebar(item) {
  const empty = $("factibilitySidebarEmpty");
  const content = $("factibilitySidebarContent");
  if (!item) {
    empty.classList.remove("hidden");
    content.classList.add("hidden");
    return;
  }
  const heading = factibilityLocationHeading(item);
  const overall = factibilityOverallProgress(item);
  const decision = factibilityDisplayDecision(item);
  const candidate = item.candidate;
  const variables = item.sales_sheet || candidate.project_variables || {};
  const division = String(candidate.approved_division || "").toUpperCase();
  const franchiseFlow = String(variables.flujo_franquicia || "").toUpperCase();
  empty.classList.add("hidden");
  content.classList.remove("hidden");
  $("factibilitySidebarId").textContent = heading.title;
  $("factibilitySidebarUnit").textContent = heading.subtitle;
  $("factibilitySidebarDecision").textContent = FACTIBILITY_DECISION_LABELS[decision] || decision;
  $("factibilitySidebarDecision").className = `factibility-decision-badge ${decision}`;
  $("factibilitySidebarProjectDate").textContent = formatTableDate(factibilityProjectDate(item)) || "Sin información";
  $("factibilitySidebarApprovals").innerHTML = ["legal", "arquitectura"].map((area) => `
    <div class="factibility-sidebar-approval${item.approvals?.[area] ? " approved" : ""}">
      ${esc(factibilityApprovalText(item, area))}
    </div>
  `).join("");
  $("factibilitySidebarDivision").textContent = division === "SUCURSAL"
    ? "Sucursales"
    : division === "FRANQUICIA" ? "Franquicias" : "Sin información";
  $("factibilitySidebarFlowRow").classList.toggle("hidden", division !== "FRANQUICIA");
  $("factibilitySidebarFlow").textContent = franchiseFlow === "SUBARRIENDO"
    ? "Subarriendo"
    : franchiseFlow === "FRANQUICIADO DIRECTO" ? "Contrato directo" : "Sin definir";
  $("factibilitySidebarContact").innerHTML = factibilityContactRows([
    ["Nombre", variables.contacto_nombre],
    ["Teléfono", variables.contacto_telefono],
    ["Email", variables.contacto_email],
  ]);
  const showFranchisee = division === "FRANQUICIA" && franchiseFlow === "SUBARRIENDO";
  $("factibilitySidebarFranchiseeSection").classList.toggle("hidden", !showFranchisee);
  $("factibilitySidebarFranchisee").innerHTML = showFranchisee ? factibilityContactRows([
    ["Nombre", variables.franquiciado_nombre],
    ["Teléfono", variables.franquiciado_telefono],
    ["Email", variables.franquiciado_email],
  ]) : "";
  $("factibilitySidebarPercent").textContent = `${overall.progress}%`;
  $("factibilitySidebarPercent").style.color = `hsl(${factibilityProgressHue(overall.progress)} 88% 52%)`;
  $("factibilitySidebarProgressBar").style.width = `${overall.progress}%`;
  const overallCompletedAt = item.completion?.completed_at;
  $("factibilitySidebarElapsed").textContent = factibilityElapsedText(item, overallCompletedAt);
  $("factibilitySidebarElapsed").classList.toggle("completed", Boolean(overallCompletedAt));
  $("factibilitySidebarGroups").innerHTML = ["legal", "arquitectura"].map((area) => {
    const progress = factibilityAreaProgress(item, area);
    const completedAt = item.completion?.areas?.[area];
    const title = area === "legal" ? "Legal" : "Arquitectura";
    return `
    <div class="factibility-sidebar-group">
      <div class="factibility-sidebar-group-row">
        <span>${title}</span>
        <strong style="color:hsl(${factibilityProgressHue(progress.progress)} 88% 52%)">${progress.progress}%</strong>
      </div>
      <div class="factibility-progress-track">
        <div class="factibility-progress-bar" style="width:${progress.progress}%"></div>
      </div>
      <div class="factibility-sidebar-elapsed${completedAt ? " completed" : ""}">${esc(factibilityElapsedText(item, completedAt))}</div>
    </div>`;
  }).join("");
}

function factibilityContactRows(rows) {
  const available = rows.filter(([, value]) => String(value || "").trim());
  if (!available.length) return '<span class="factibility-sidebar-missing">Sin información registrada</span>';
  return available.map(([label, value]) => `
    <div class="factibility-contact-row">
      <span>${esc(label)}</span>
      <strong>${esc(value)}</strong>
    </div>`).join("");
}

async function loadFactibilityLocations({ silent = false } = {}) {
  if (!silent) $("factibilityLocations").innerHTML = '<div class="factibility-empty">Cargando locales...</div>';
  try {
    state.locations = await api("/factibilidad/locations");
    renderFactibilityLocations();
  } catch (error) {
    if (!silent) $("factibilityLocations").innerHTML = `<div class="factibility-empty">${esc(error.message || "No fue posible cargar Factibilidad.")}</div>`;
  }
}

function stopFactibilitySync() {
  clearInterval(state.syncTimer);
  state.syncTimer = null;
  state.syncRunning = false;
  state.syncVersion = "";
}

async function pollFactibilityChanges() {
  if (shellState.module !== "factibilidad" || state.syncRunning || document.hidden) return;
  const active = document.activeElement;
  if (active?.matches?.(".factibility-comment, .factibility-status") ||
      (!$('projectVariablesModal').classList.contains("hidden") &&
       $("projectVariablesForm").dataset.mode === "factibility")) return;
  state.syncRunning = true;
  try {
    const result = await api("/factibilidad/sync-version");
    if (!state.syncVersion) {
      state.syncVersion = result.version;
    } else if (result.version !== state.syncVersion) {
      state.syncVersion = result.version;
      await loadFactibilityLocations({ silent: true });
    }
  } catch (_) {
    // A transient connectivity issue must not interrupt the user's editing.
  } finally {
    state.syncRunning = false;
  }
}

function startFactibilitySync() {
  stopFactibilitySync();
  pollFactibilityChanges();
  state.syncTimer = setInterval(pollFactibilityChanges, 2000);
}

function factibilityAttachmentEndpoint(context = state.attachmentContext) {
  if (!context) return "";
  return `/factibilidad/locations/${context.candidateId}/groups/${encodeURIComponent(context.groupKey)}/attachments`;
}

function renderFactibilityAttachmentsGallery(items) {
  const gallery = $("factibilityAttachmentsGallery");
  if (!items.length) {
    gallery.innerHTML = '<div class="attachments-empty">Esta macrotarea todavía no tiene archivos.</div>';
    return;
  }
  gallery.innerHTML = items.map((item) => {
    const extension = item.name.includes(".") ? item.name.split(".").pop().toUpperCase() : "ARCHIVO";
    const preview = String(item.content_type || "").startsWith("image/")
      ? `<a class="attachment-preview-link" href="${esc(item.url)}" target="_blank" rel="noopener"><img src="${esc(item.url)}" alt="${esc(item.name)}" /></a>`
      : `<a class="attachment-preview-link attachment-document-preview" href="${esc(item.url)}" target="_blank" rel="noopener"><span class="attachment-document-type">${esc(extension)}</span></a>`;
    return `<article class="attachment-item">
      ${preview}
      <div class="attachment-meta">
        <div class="attachment-meta-head">
          <a href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.name)}</a>
          <button type="button" class="attachment-delete-btn" data-factibility-file-delete="${esc(item.name)}" title="Eliminar archivo" aria-label="Eliminar ${esc(item.name)}">X</button>
        </div>
        <span>${esc(attachmentFileSize(item.size))} · ${esc(formatHistoryDate(item.modified_at))}</span>
      </div>
    </article>`;
  }).join("");
  gallery.querySelectorAll("[data-factibility-file-delete]").forEach((button) => {
    button.onclick = () => deleteFactibilityAttachment(button.dataset.factibilityFileDelete);
  });
}

async function openFactibilityAttachments(candidateId, groupKey, groupTitle) {
  const item = state.locations.find((entry) => entry.candidate.id === candidateId);
  if (!item) return toast("El local ya no está disponible");
  const heading = factibilityLocationHeading(item);
  state.attachmentContext = { candidateId, groupKey, groupTitle };
  $("factibilityAttachmentsSubtitle").textContent = `${heading.title} · ${groupTitle}`;
  $("factibilityAttachmentFilesInput").value = "";
  $("factibilityAttachmentSelection").textContent = "Ningún archivo seleccionado";
  $("factibilityAttachmentsGallery").innerHTML = '<div class="attachments-empty">Cargando archivos...</div>';
  $("factibilityAttachmentsModal").classList.remove("hidden");
  try {
    renderFactibilityAttachmentsGallery(await api(factibilityAttachmentEndpoint()));
  } catch (error) {
    $("factibilityAttachmentsGallery").innerHTML = `<div class="attachments-empty">${esc(error.message)}</div>`;
  }
}

function closeFactibilityAttachments() {
  $("factibilityAttachmentsModal").classList.add("hidden");
  $("factibilityAttachmentFilesInput").value = "";
  $("factibilityAttachmentSelection").textContent = "Ningún archivo seleccionado";
  state.attachmentContext = null;
}

async function uploadFactibilityAttachments() {
  if (!state.attachmentContext) return;
  const files = [...$("factibilityAttachmentFilesInput").files];
  if (!files.length) return toast("Seleccione al menos un archivo");
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  const button = $("factibilityAttachmentUploadBtn");
  button.disabled = true;
  button.textContent = "Subiendo...";
  try {
    const items = await api(factibilityAttachmentEndpoint(), { method: "POST", body: form });
    renderFactibilityAttachmentsGallery(items);
    $("factibilityAttachmentFilesInput").value = "";
    $("factibilityAttachmentSelection").textContent = "Ningún archivo seleccionado";
    toast("Archivos guardados en la biblioteca de Factibilidad");
  } catch (error) {
    toast("Error: " + error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Subir archivos";
  }
}

async function deleteFactibilityAttachment(filename) {
  if (!state.attachmentContext) return;
  if (!confirm(`¿Eliminar "${filename}" de esta macrotarea?`)) return;
  try {
    const url = `${factibilityAttachmentEndpoint()}/${encodeURIComponent(filename)}`;
    renderFactibilityAttachmentsGallery(await api(url, { method: "DELETE" }));
    toast("Archivo eliminado");
  } catch (error) {
    toast("Error: " + error.message);
  }
}

function renderFactibilityLocalLibrary(candidateId, groups) {
  const container = $("factibilityLocalLibraryContent");
  const withFiles = groups.filter((group) => group.files.length);
  if (!withFiles.length) {
    container.innerHTML = '<div class="attachments-empty">Este local todavía no tiene archivos. Expande una macrotarea y usa “Adjuntar / ver archivos”.</div>';
    return;
  }
  container.innerHTML = ["legal", "arquitectura"].map((area) => {
    const areaGroups = withFiles.filter((group) => group.area === area);
    if (!areaGroups.length) return "";
    const areaTitle = area === "legal" ? "Legal" : "Arquitectura";
    return `<section class="factibility-library-area">
      <h3>${areaTitle}</h3>
      <div class="factibility-library-groups">
        ${areaGroups.map((group) => `<article class="factibility-library-group">
          <div class="factibility-library-group-head">
            <div><strong>${esc(group.title)}</strong><span>${group.files.length} archivo${group.files.length === 1 ? "" : "s"}</span></div>
            <button type="button" class="factibility-attachment-btn" data-library-upload-group="${esc(group.key)}" data-group-title="${esc(group.title)}" data-candidate-id="${candidateId}">Adjuntar más</button>
          </div>
          <div class="factibility-library-files">
            ${group.files.map((file) => {
              const extension = file.name.includes(".") ? file.name.split(".").pop().toUpperCase() : "ARCHIVO";
              return `<a class="factibility-library-file" href="${esc(file.url)}" target="_blank" rel="noopener">
                <span class="attachment-document-type">${esc(extension)}</span>
                <span><strong>${esc(file.name)}</strong><small>${esc(attachmentFileSize(file.size))} · ${esc(formatHistoryDate(file.modified_at))}</small></span>
              </a>`;
            }).join("")}
          </div>
        </article>`).join("")}
      </div>
    </section>`;
  }).join("");
  container.querySelectorAll("[data-library-upload-group]").forEach((button) => {
    button.onclick = () => {
      closeFactibilityLocalLibrary();
      openFactibilityAttachments(
        Number(button.dataset.candidateId),
        button.dataset.libraryUploadGroup,
        button.dataset.groupTitle,
      );
    };
  });
}

async function openFactibilityLocalLibrary(candidateId) {
  const item = state.locations.find((entry) => entry.candidate.id === candidateId);
  if (!item) return toast("El local ya no está disponible");
  const heading = factibilityLocationHeading(item);
  $("factibilityLocalLibrarySubtitle").textContent = `${heading.title} · ${heading.subtitle}`;
  $("factibilityLocalLibraryContent").innerHTML = '<div class="attachments-empty">Cargando biblioteca...</div>';
  $("factibilityLocalLibraryModal").classList.remove("hidden");
  try {
    const groups = await api(`/factibilidad/locations/${candidateId}/attachments`);
    renderFactibilityLocalLibrary(candidateId, groups);
  } catch (error) {
    $("factibilityLocalLibraryContent").innerHTML = `<div class="attachments-empty">${esc(error.message)}</div>`;
  }
}

function closeFactibilityLocalLibrary() {
  $("factibilityLocalLibraryModal").classList.add("hidden");
  $("factibilityLocalLibraryContent").innerHTML = "";
}

async function openFactibilityView() {
  await startFactibilityApp(shellState.user);
}

function closeFactibilityView() {
  applicationShell.showModuleMenu(shellState.user);
}

async function saveFactibilityTask(row) {
  if (!row) return;
  const candidateId = Number(row.dataset.candidateId);
  const taskKey = row.dataset.taskKey;
  const status = row.querySelector(".factibility-status").value;
  const comment = row.querySelector(".factibility-comment").value.trim();
  const item = state.locations.find((entry) => entry.candidate.id === candidateId);
  const task = item?.task_groups.flatMap((group) => group.subtasks).find((entry) => entry.key === taskKey);
  if (task && task.status === status && (task.comment || "") === comment) return;
  try {
    await api(`/factibilidad/locations/${candidateId}/tasks/${encodeURIComponent(taskKey)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, comment }),
    });
    if (task) {
      task.status = status;
      task.comment = comment || null;
    }
    item.task_groups.forEach((group) => {
      group.completed = group.subtasks.filter((entry) => ["realizado", "no_aplica"].includes(entry.status)).length;
      group.progress = Math.round((group.completed / group.total) * 100);
    });
    renderFactibilityLocations();
    toast("Tarea de Factibilidad guardada");
  } catch (error) {
    toast("Error: " + error.message);
  }
}

async function saveFactibilityDecision(candidateId, decision, button) {
  const label = decision === "rechazado" ? "rechazar" : "marcar como completado";
  if (!confirm(`¿Desea ${label} este local solo en Factibilidad?`)) return;
  button.disabled = true;
  try {
    const result = await api(`/factibilidad/locations/${candidateId}/decision`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    });
    const item = state.locations.find((entry) => entry.candidate.id === candidateId);
    if (item) item.decision = result;
    renderFactibilityLocations();
    toast("Decisión de Factibilidad guardada sin cambiar el estado productivo");
  } catch (error) {
    button.disabled = false;
    toast("Error: " + error.message);
  }
}

function requestFactibilityApprovalConfirmation(label) {
  return new Promise((resolve) => {
    const modal = $("factibilityApprovalConfirmModal");
    const form = $("factibilityApprovalConfirmForm");
    const cancel = $("factibilityApprovalConfirmCancel");
    const accept = $("factibilityApprovalConfirmAccept");
    $("factibilityApprovalConfirmMessage").textContent =
      `¿Estás seguro de asignar el visto bueno para ${label}?`;
    let settled = false;
    const close = (confirmed) => {
      if (settled) return;
      settled = true;
      modal.classList.add("hidden");
      form.onsubmit = null;
      cancel.onclick = null;
      modal.onclick = null;
      window.removeEventListener("keydown", onKeydown, true);
      resolve(confirmed);
    };
    const onKeydown = (event) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      close(false);
    };
    form.onsubmit = (event) => {
      event.preventDefault();
      close(true);
    };
    cancel.onclick = () => close(false);
    modal.onclick = (event) => {
      if (event.target === modal) close(false);
    };
    window.addEventListener("keydown", onKeydown, true);
    modal.classList.remove("hidden");
    accept.focus();
  });
}

async function saveFactibilityApproval(candidateId, area, button) {
  const label = factibilityApprovalLabel(area);
  if (!await requestFactibilityApprovalConfirmation(label)) return;
  button.disabled = true;
  try {
    const result = await api(`/factibilidad/locations/${candidateId}/approvals/${area}`, {
      method: "PUT",
    });
    const item = state.locations.find((entry) => entry.candidate.id === candidateId);
    if (item) {
      item.approvals ||= {};
      item.approvals[area] = result;
    }
    renderFactibilityLocations();
    toast(`Visto bueno de ${label} registrado`);
  } catch (error) {
    button.disabled = false;
    toast("Error: " + error.message);
  }
}


    async function start(user) {
      const applicationShell = getApplicationShell();
      if (!user) return applicationShell.showLogin();
      if (!applicationShell.canAccessFactibility(user)) {
        applicationShell.showFactibilityAccessDenied();
        return;
      }
      stopOtherModuleSync();
      shellState.user = user;
      shellState.module = "factibilidad";
      state.selectedId = null;
      state.expandedLocations.clear();
      state.area = "legal";
      $("factibilitySearchInput").value = state.search;
      $("factibilitySortSelect").value = state.sort;
      saveUserCache(user);
      document.title = "Factibilidad";
      document.body.classList.remove("sidebar-collapsed");
      document.body.classList.add("module-factibility");
      $("loginScreen").classList.add("hidden");
      $("moduleMenu").classList.add("hidden");
      $("candidateTableView").classList.add("hidden");
      $("sidebar").classList.remove("hidden");
      $("sidebarHeader").classList.add("hidden");
      $("sidebarMainView").classList.add("hidden");
      $("funnelPanel").classList.add("hidden");
      $("factibilitySidebar").classList.remove("hidden");
      $("factibilitySidebarUser").textContent =
        `${user.name} · ${roleLabels[user.role] || user.role}`;
      $("factibilitySidebarEmpty").classList.remove("hidden");
      $("factibilitySidebarContent").classList.add("hidden");
      $("toggleViewBtn").classList.add("hidden");
      $("sidebarToggleBtn").classList.add("hidden");
      $("tableViewBtn").classList.add("hidden");
      $("factibilityView").classList.remove("hidden");
      await loadFactibilityLocations();
      startFactibilitySync();
    }

    function findLocation(candidateId) {
      return state.locations.find((entry) => entry.candidate.id === candidateId) || null;
    }

    function updateSalesSheet(candidateId, salesSheet) {
      const item = findLocation(candidateId);
      if (item) item.sales_sheet = salesSheet;
    }

    function selectArea(area) {
      state.area = area;
      renderFactibilityLocations();
    }

    function wire() {
      $("closeFactibilityBtn").onclick = closeFactibilityView;
      document.querySelectorAll("[data-factibility-area]").forEach((button) => {
        button.onclick = () => selectArea(button.dataset.factibilityArea);
      });
      $("factibilityAttachmentsCloseBtn").onclick = closeFactibilityAttachments;
      $("factibilityAttachmentUploadBtn").onclick = uploadFactibilityAttachments;
      $("factibilityAttachmentFilesInput").onchange = () => {
        const count = $("factibilityAttachmentFilesInput").files.length;
        $("factibilityAttachmentSelection").textContent = count
          ? `${count} archivo${count === 1 ? "" : "s"} seleccionado${count === 1 ? "" : "s"}`
          : "Ningún archivo seleccionado";
      };
      $("factibilityAttachmentsModal").onclick = (event) => {
        if (event.target === $("factibilityAttachmentsModal")) closeFactibilityAttachments();
      };
      $("factibilityLocalLibraryCloseBtn").onclick = closeFactibilityLocalLibrary;
      $("factibilityLocalLibraryModal").onclick = (event) => {
        if (event.target === $("factibilityLocalLibraryModal")) closeFactibilityLocalLibrary();
      };
    }

    function handleEscape(key) {
      if (key !== "Escape") return false;
      if (!$("factibilityAttachmentsModal").classList.contains("hidden")) {
        closeFactibilityAttachments();
        return true;
      }
      if (!$("factibilityLocalLibraryModal").classList.contains("hidden")) {
        closeFactibilityLocalLibrary();
        return true;
      }
      if (!$("factibilityView").classList.contains("hidden")) {
        closeFactibilityView();
        return true;
      }
      return false;
    }

    return Object.freeze({
      findLocation,
      handleEscape,
      start,
      stop: stopFactibilitySync,
      closeAttachments: closeFactibilityAttachments,
      closeLocalLibrary: closeFactibilityLocalLibrary,
      closeView: closeFactibilityView,
      locationHeading: factibilityLocationHeading,
      render: renderFactibilityLocations,
      updateSalesSheet,
      uploadAttachments: uploadFactibilityAttachments,
      wire,
    });
  }

  global.FactibilityModule = Object.freeze({ create });
})(window);
