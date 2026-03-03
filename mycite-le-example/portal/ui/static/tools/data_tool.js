(function () {
  function qs(selector, root) { return (root || document).querySelector(selector); }
  function qsa(selector, root) { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); }

  var app = qs("#dataToolApp");
  if (!app) return;

  var sourceSel = qs("#dtSource", app);
  var subjectInput = qs("#dtSubject", app);
  var invMethodSel = qs("#dtInvMethod", app);
  var modeSel = qs("#dtMode", app);
  var lensSel = qs("#dtLens", app);

  var tableInput = qs("#dtTableId", app);
  var rowInput = qs("#dtRowId", app);
  var fieldInput = qs("#dtFieldId", app);
  var valueInput = qs("#dtValue", app);
  var scopeSel = qs("#dtScope", app);

  var navBtn = qs("#dtNavBtn", app);
  var invBtn = qs("#dtInvBtn", app);
  var modeBtn = qs("#dtModeBtn", app);
  var lensBtn = qs("#dtLensBtn", app);
  var stageBtn = qs("#dtStageBtn", app);
  var resetBtn = qs("#dtResetBtn", app);
  var commitBtn = qs("#dtCommitBtn", app);
  var refreshBtn = qs("#dtRefreshBtn", app);

  var messagesEl = qs("#dtMessages", app);
  var stateEl = qs("#dtStateSummary", app);
  var leftPaneEl = qs("#dtLeftPane", app);
  var rightPaneEl = qs("#dtRightPane", app);

  var iconModal = qs("#dtIconModal");
  var iconListEl = qs("#dtIconList");
  var iconSearchInput = qs("#dtIconSearch");
  var iconTargetEl = qs("#dtIconTarget");
  var iconCloseBtn = qs("#dtIconCloseBtn");
  var iconClearBtn = qs("#dtIconClearBtn");

  var iconCatalog = [];
  var iconCatalogLoaded = false;
  var iconTargetDatumId = "";

  function escapeText(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function setMessages(errors, warnings) {
    var err = Array.isArray(errors) ? errors.filter(Boolean) : [];
    var warn = Array.isArray(warnings) ? warnings.filter(Boolean) : [];
    if (!messagesEl) return;
    if (!err.length && !warn.length) {
      messagesEl.style.display = "none";
      messagesEl.innerHTML = "";
      return;
    }
    messagesEl.style.display = "block";
    messagesEl.innerHTML = "";

    err.forEach(function (msg) {
      var row = document.createElement("div");
      row.className = "data-message is-error";
      row.textContent = msg;
      messagesEl.appendChild(row);
    });

    warn.forEach(function (msg) {
      var row = document.createElement("div");
      row.className = "data-message is-warn";
      row.textContent = msg;
      messagesEl.appendChild(row);
    });
  }

  function extractDatumEntries(payload) {
    var out = [];

    function walk(value) {
      if (!value) return;
      if (Array.isArray(value)) {
        value.forEach(walk);
        return;
      }
      if (typeof value !== "object") return;

      var datumId = typeof value.datum_id === "string" ? value.datum_id.trim() : "";
      var labelText = typeof value.label_text === "string" ? value.label_text.trim() : "";
      var iconRelpath = typeof value.icon_relpath === "string" ? value.icon_relpath.trim() : "";
      var iconUrl = typeof value.icon_url === "string" ? value.icon_url.trim() : "";

      if (datumId) {
        out.push({
          datum_id: datumId,
          label_text: labelText || datumId,
          icon_relpath: iconRelpath,
          icon_url: iconUrl,
          icon_assigned: Boolean(value.icon_assigned || iconUrl || iconRelpath),
        });
      }

      Object.keys(value).forEach(function (key) {
        walk(value[key]);
      });
    }

    walk(payload);
    return out;
  }

  function renderDatumList(targetEl, entries) {
    targetEl.innerHTML = "";

    if (!entries.length) {
      var empty = document.createElement("p");
      empty.className = "data-tool__empty";
      empty.textContent = "No datum entries for this pane.";
      targetEl.appendChild(empty);
      return;
    }

    var list = document.createElement("div");
    list.className = "data-tool__datumList";

    entries.forEach(function (entry) {
      var row = document.createElement("div");
      row.className = "data-tool__datumRow";

      var iconBtn = document.createElement("button");
      iconBtn.type = "button";
      iconBtn.className = "data-tool__iconButton js-open-icon-picker";
      iconBtn.setAttribute("data-datum-id", entry.datum_id);
      iconBtn.setAttribute("title", "Set icon for " + entry.datum_id);

      if (entry.icon_url) {
        var image = document.createElement("img");
        image.src = entry.icon_url;
        image.alt = "";
        image.className = "datum-icon";
        iconBtn.appendChild(image);
      } else {
        var placeholder = document.createElement("span");
        placeholder.className = "datum-icon datum-icon--placeholder";
        placeholder.textContent = "+";
        iconBtn.appendChild(placeholder);
      }

      var textWrap = document.createElement("div");
      textWrap.className = "data-tool__datumText";

      var title = document.createElement("div");
      title.className = "data-tool__datumTitle";
      title.textContent = entry.label_text;

      var meta = document.createElement("div");
      meta.className = "data-tool__datumMeta";
      meta.innerHTML = "<code>" + escapeText(entry.datum_id) + "</code>";
      if (entry.icon_relpath) {
        meta.innerHTML += "<span>" + escapeText(entry.icon_relpath) + "</span>";
      } else {
        meta.innerHTML += "<span>no icon</span>";
      }

      textWrap.appendChild(title);
      textWrap.appendChild(meta);

      row.appendChild(iconBtn);
      row.appendChild(textWrap);
      list.appendChild(row);
    });

    targetEl.appendChild(list);
  }

  function renderPane(targetEl, paneVm) {
    if (!targetEl) return;

    var pane = paneVm && typeof paneVm === "object" ? paneVm : {};
    var payload = pane.payload && typeof pane.payload === "object" ? pane.payload : {};
    var entries = extractDatumEntries(payload);

    targetEl.innerHTML = "";

    var kindEl = document.createElement("div");
    kindEl.className = "data-tool__paneKind";
    kindEl.textContent = "kind: " + (pane.kind || "none");
    targetEl.appendChild(kindEl);

    var listWrap = document.createElement("div");
    listWrap.className = "data-tool__paneList";
    renderDatumList(listWrap, entries);
    targetEl.appendChild(listWrap);

    var details = document.createElement("details");
    details.className = "data-tool__raw";
    var summary = document.createElement("summary");
    summary.textContent = "Raw pane payload";
    var pre = document.createElement("pre");
    pre.textContent = JSON.stringify(payload, null, 2);
    details.appendChild(summary);
    details.appendChild(pre);
    targetEl.appendChild(details);
  }

  function render(snapshot) {
    var state = snapshot && snapshot.state ? snapshot.state : {};
    var left = snapshot && snapshot.left_pane_vm ? snapshot.left_pane_vm : {};
    var right = snapshot && snapshot.right_pane_vm ? snapshot.right_pane_vm : {};

    if (stateEl) {
      stateEl.textContent = JSON.stringify(
        {
          focus_source: state.focus_source,
          focus_subject: state.focus_subject,
          mode: state.mode,
          lens_context: state.lens_context,
          selection: state.selection,
          staged_edits: snapshot.staged_edits || [],
          staged_presentation_edits: snapshot.staged_presentation_edits || { datum_icons: {} },
        },
        null,
        2
      );
    }

    renderPane(leftPaneEl, left);
    renderPane(rightPaneEl, right);

    if (modeSel && state.mode) modeSel.value = state.mode;
    if (sourceSel && state.focus_source) sourceSel.value = state.focus_source;

    var selection = state.selection || {};
    if (tableInput && selection.table_id && !tableInput.value) tableInput.value = selection.table_id;
    if (rowInput && selection.row_id && !rowInput.value) rowInput.value = selection.row_id;
    if (fieldInput && selection.field_id && !fieldInput.value) fieldInput.value = selection.field_id;

    setMessages(snapshot.errors || [], snapshot.warnings || []);
  }

  async function api(path, options) {
    var res = await fetch(path, options || {});
    var payload = {};
    try {
      payload = await res.json();
    } catch (_) {
      payload = {};
    }
    if (!res.ok) {
      throw new Error(payload.description || payload.message || "Request failed");
    }
    return payload;
  }

  async function getState() {
    var payload = await api("/portal/api/data/state");
    render(payload);
    return payload;
  }

  async function postDirective(action, subject, method, args) {
    var payload = await api("/portal/api/data/directive", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: action, subject: subject, method: method, args: args || {} }),
    });
    render(payload);
    return payload;
  }

  async function stageEdit() {
    var payload = await api("/portal/api/data/stage_edit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        table_id: tableInput ? tableInput.value : "",
        row_id: rowInput ? rowInput.value : "",
        field_id: fieldInput ? fieldInput.value : "",
        display_value: valueInput ? valueInput.value : "",
      }),
    });
    render(payload);
    return payload;
  }

  async function resetStaging() {
    var payload = await api("/portal/api/data/reset_staging", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scope: scopeSel ? scopeSel.value : "all",
        table_id: tableInput ? tableInput.value : "",
        row_id: rowInput ? rowInput.value : "",
      }),
    });
    render(payload);
    return payload;
  }

  async function commit() {
    var payload = await api("/portal/api/data/commit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scope: scopeSel ? scopeSel.value : "all",
        table_id: tableInput ? tableInput.value : "",
        row_id: rowInput ? rowInput.value : "",
      }),
    });
    render(payload);
    return payload;
  }

  async function loadIconCatalog() {
    if (iconCatalogLoaded) return iconCatalog;
    var payload = await api("/portal/api/data/icons/list");
    iconCatalog = Array.isArray(payload.icon_relpaths) ? payload.icon_relpaths : [];
    iconCatalogLoaded = true;
    return iconCatalog;
  }

  function renderIconOptions() {
    if (!iconListEl) return;

    var filter = iconSearchInput ? iconSearchInput.value.trim().toLowerCase() : "";
    var filtered = iconCatalog.filter(function (rel) {
      if (!filter) return true;
      return rel.toLowerCase().indexOf(filter) !== -1;
    });

    iconListEl.innerHTML = "";
    if (!filtered.length) {
      var empty = document.createElement("p");
      empty.className = "data-tool__empty";
      empty.textContent = "No icons match current filter.";
      iconListEl.appendChild(empty);
      return;
    }

    filtered.forEach(function (rel) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "data-tool__iconOption";
      btn.setAttribute("data-icon-relpath", rel);

      var img = document.createElement("img");
      img.src = "/portal/static/icons/" + rel;
      img.alt = "";
      img.className = "datum-icon";

      var text = document.createElement("span");
      text.textContent = rel;

      btn.appendChild(img);
      btn.appendChild(text);
      iconListEl.appendChild(btn);
    });
  }

  function closeIconModal() {
    if (!iconModal) return;
    iconModal.hidden = true;
    iconTargetDatumId = "";
    if (iconTargetEl) iconTargetEl.textContent = "";
  }

  async function openIconModal(datumId) {
    iconTargetDatumId = String(datumId || "").trim();
    if (!iconTargetDatumId || !iconModal) return;

    if (iconTargetEl) {
      iconTargetEl.innerHTML = "Target datum: <code>" + escapeText(iconTargetDatumId) + "</code>";
    }

    iconModal.hidden = false;

    try {
      await loadIconCatalog();
      renderIconOptions();
      if (iconSearchInput) iconSearchInput.focus();
    } catch (err) {
      setMessages([err.message], []);
      closeIconModal();
    }
  }

  async function setDatumIcon(iconRelpath) {
    if (!iconTargetDatumId) return;
    try {
      await postDirective("man", "datum_icon", "set", {
        datum_id: iconTargetDatumId,
        icon_relpath: String(iconRelpath || ""),
      });
      closeIconModal();
    } catch (err) {
      setMessages([err.message], []);
    }
  }

  if (iconSearchInput) {
    iconSearchInput.addEventListener("input", renderIconOptions);
  }

  if (iconCloseBtn) {
    iconCloseBtn.addEventListener("click", closeIconModal);
  }

  qsa("[data-role='close-icon-modal']").forEach(function (node) {
    node.addEventListener("click", closeIconModal);
  });

  if (iconClearBtn) {
    iconClearBtn.addEventListener("click", function () {
      setDatumIcon("");
    });
  }

  if (iconListEl) {
    iconListEl.addEventListener("click", function (event) {
      var button = event.target && event.target.closest ? event.target.closest(".data-tool__iconOption") : null;
      if (!button) return;
      var rel = button.getAttribute("data-icon-relpath") || "";
      setDatumIcon(rel);
    });
  }

  if (leftPaneEl) {
    leftPaneEl.addEventListener("click", function (event) {
      var button = event.target && event.target.closest ? event.target.closest(".js-open-icon-picker") : null;
      if (!button) return;
      openIconModal(button.getAttribute("data-datum-id") || "");
    });
  }

  if (rightPaneEl) {
    rightPaneEl.addEventListener("click", function (event) {
      var button = event.target && event.target.closest ? event.target.closest(".js-open-icon-picker") : null;
      if (!button) return;
      openIconModal(button.getAttribute("data-datum-id") || "");
    });
  }

  if (navBtn) {
    navBtn.addEventListener("click", function () {
      postDirective("nav", sourceSel ? sourceSel.value : "auto", "top_level_view", {}).catch(function (err) {
        setMessages([err.message], []);
      });
    });
  }

  if (invBtn) {
    invBtn.addEventListener("click", function () {
      postDirective("inv", subjectInput ? subjectInput.value : "", invMethodSel ? invMethodSel.value : "summary", {}).catch(function (err) {
        setMessages([err.message], []);
      });
    });
  }

  if (modeBtn) {
    modeBtn.addEventListener("click", function () {
      var mode = modeSel ? modeSel.value : "general";
      postDirective("med", "state", "mode=" + mode, { mode: mode }).catch(function (err) {
        setMessages([err.message], []);
      });
    });
  }

  if (lensBtn) {
    lensBtn.addEventListener("click", function () {
      var lens = lensSel ? lensSel.value : "default";
      postDirective("med", "state", "lens=" + lens, { lens: lens }).catch(function (err) {
        setMessages([err.message], []);
      });
    });
  }

  if (stageBtn) {
    stageBtn.addEventListener("click", function () {
      stageEdit().catch(function (err) {
        setMessages([err.message], []);
      });
    });
  }

  if (resetBtn) {
    resetBtn.addEventListener("click", function () {
      resetStaging().catch(function (err) {
        setMessages([err.message], []);
      });
    });
  }

  if (commitBtn) {
    commitBtn.addEventListener("click", function () {
      commit().catch(function (err) {
        setMessages([err.message], []);
      });
    });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener("click", function () {
      getState().catch(function (err) {
        setMessages([err.message], []);
      });
    });
  }

  getState().catch(function (err) {
    setMessages([err.message], []);
  });
})();
