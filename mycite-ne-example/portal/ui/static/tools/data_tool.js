(function () {
  function qs(selector, root) { return (root || document).querySelector(selector); }

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
        },
        null,
        2
      );
    }
    if (leftPaneEl) leftPaneEl.textContent = JSON.stringify(left, null, 2);
    if (rightPaneEl) rightPaneEl.textContent = JSON.stringify(right, null, 2);

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
    try { payload = await res.json(); } catch (_) { payload = {}; }
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
