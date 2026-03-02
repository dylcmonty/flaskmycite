(function () {
  function qs(selector, root) { return (root || document).querySelector(selector); }
  function ce(tag, className) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    return el;
  }

  const root = qs("#dataApp");
  if (!root) return;

  const modeSelect = qs("#dataModeSelect", root);
  const tableSelect = qs("#dataTableSelect", root);
  const instanceSelect = qs("#dataInstanceSelect", root);
  const resetBtn = qs("#dataResetBtn", root);
  const commitBtn = qs("#dataCommitBtn", root);
  const revertBtn = qs("#dataRevertBtn", root);
  const grid = qs("#dataGrid", root);
  const statusEl = qs("#dataStatus", root);
  const messagesEl = qs("#dataMessages", root);

  const state = {
    tables: [],
    tableId: "",
    instanceId: "",
    mode: root.getAttribute("data-default-mode") || "general",
    view: null,
    focusedCell: null,
  };

  function setStatus(text) {
    if (!statusEl) return;
    statusEl.textContent = text || "";
  }

  function setMessages(errors, warnings) {
    if (!messagesEl) return;
    messagesEl.innerHTML = "";

    const errList = Array.isArray(errors) ? errors.filter(Boolean) : [];
    const warnList = Array.isArray(warnings) ? warnings.filter(Boolean) : [];

    if (!errList.length && !warnList.length) {
      messagesEl.style.display = "none";
      return;
    }

    messagesEl.style.display = "block";

    errList.forEach(function (msg) {
      const row = ce("div", "data-message is-error");
      row.textContent = msg;
      messagesEl.appendChild(row);
    });

    warnList.forEach(function (msg) {
      const row = ce("div", "data-message is-warn");
      row.textContent = msg;
      messagesEl.appendChild(row);
    });
  }

  async function api(path, options) {
    const res = await fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, options || {}));
    let payload = {};
    try {
      payload = await res.json();
    } catch (_) {
      payload = {};
    }
    if (!res.ok) {
      const message = payload && payload.description ? payload.description : "Request failed";
      throw new Error(message);
    }
    return payload;
  }

  function replaceOptions(select, rows, valueKey, labelKey) {
    if (!select) return;
    select.innerHTML = "";
    rows.forEach(function (row) {
      const opt = document.createElement("option");
      opt.value = String(row[valueKey] || "");
      opt.textContent = String(row[labelKey] || row[valueKey] || "");
      select.appendChild(opt);
    });
  }

  function gatherViewMessages(view, extraErrors, extraWarnings) {
    const errors = [];
    const warnings = [];

    (extraErrors || []).forEach(function (msg) { if (msg) errors.push(msg); });
    (extraWarnings || []).forEach(function (msg) { if (msg) warnings.push(msg); });

    if (view && Array.isArray(view.errors)) {
      view.errors.forEach(function (msg) { if (msg) errors.push(msg); });
    }
    if (view && Array.isArray(view.warnings)) {
      view.warnings.forEach(function (msg) { if (msg) warnings.push(msg); });
    }
    if (view && Array.isArray(view.rows)) {
      view.rows.forEach(function (row) {
        (row.errors || []).forEach(function (msg) { if (msg) errors.push(msg); });
        (row.warnings || []).forEach(function (msg) { if (msg) warnings.push(msg); });
      });
    }

    return { errors: errors, warnings: warnings };
  }

  async function loadTables() {
    const payload = await api("/portal/api/data/tables");
    state.tables = Array.isArray(payload.tables) ? payload.tables : [];

    if (!state.tables.length) {
      replaceOptions(tableSelect, [], "table_id", "title");
      replaceOptions(instanceSelect, [], "instance_id", "instance_id");
      state.tableId = "";
      state.instanceId = "";
      state.view = null;
      renderGrid();
      setStatus("No data tables are available in this portal.");
      setMessages([], []);
      return;
    }

    replaceOptions(tableSelect, state.tables, "table_id", "title");
    state.tableId = tableSelect.value;
    await loadInstancesAndView();
  }

  async function loadInstancesAndView() {
    if (!state.tableId) {
      state.view = null;
      renderGrid();
      return;
    }

    const payload = await api("/portal/api/data/table/" + encodeURIComponent(state.tableId) + "/instances");
    const instances = Array.isArray(payload.instances) ? payload.instances : [];

    const rows = [{ instance_id: "", signature: [], row_count: 0, label: "(all rows)" }].concat(
      instances.map(function (item) {
        return {
          instance_id: String(item.instance_id || ""),
          label: String(item.instance_id || "") + " (" + String(item.row_count || 0) + " rows)",
        };
      })
    );

    replaceOptions(instanceSelect, rows, "instance_id", "label");
    state.instanceId = "";
    await loadView();
  }

  async function loadView(extraErrors, extraWarnings) {
    if (!state.tableId) {
      state.view = null;
      renderGrid();
      return;
    }

    const query = new URLSearchParams();
    query.set("mode", state.mode || "general");
    if (state.instanceId) {
      query.set("instance", state.instanceId);
    }

    const payload = await api("/portal/api/data/table/" + encodeURIComponent(state.tableId) + "/view?" + query.toString());
    state.view = payload.view || null;
    renderGrid();

    const msgs = gatherViewMessages(state.view, extraErrors || [], extraWarnings || []);
    setMessages(msgs.errors, msgs.warnings);
    setStatus("Loaded table view.");
  }

  async function stageEdit(rowId, fieldId, displayValue) {
    const payload = await api("/portal/api/data/stage_edit", {
      method: "POST",
      body: JSON.stringify({
        table_id: state.tableId,
        row_id: rowId,
        field_id: fieldId,
        display_value: displayValue,
        instance_id: state.instanceId,
        mode: state.mode,
      }),
    });

    state.view = payload.view || state.view;
    renderGrid();

    const result = payload.result || {};
    const msgs = gatherViewMessages(state.view, result.errors || [], result.warnings || []);
    setMessages(msgs.errors, msgs.warnings);
    setStatus(payload.ok ? "Staged edit saved." : "Stage edit failed.");
  }

  async function revertFocusedCell() {
    if (!state.focusedCell) {
      return;
    }

    const payload = await api("/portal/api/data/revert_edit", {
      method: "POST",
      body: JSON.stringify({
        table_id: state.tableId,
        row_id: state.focusedCell.rowId,
        field_id: state.focusedCell.fieldId,
        instance_id: state.instanceId,
        mode: state.mode,
      }),
    });

    state.view = payload.view || state.view;
    renderGrid();

    const result = payload.result || {};
    const msgs = gatherViewMessages(state.view, result.errors || [], result.warnings || []);
    setMessages(msgs.errors, msgs.warnings);
    setStatus(payload.ok ? "Cell reverted." : "Revert failed.");
  }

  async function resetStaging() {
    const payload = await api("/portal/api/data/reset", {
      method: "POST",
      body: JSON.stringify({ table_id: state.tableId, instance_id: state.instanceId, mode: state.mode }),
    });
    state.view = payload.view || state.view;
    renderGrid();

    const result = payload.result || {};
    const msgs = gatherViewMessages(state.view, result.errors || [], result.warnings || []);
    setMessages(msgs.errors, msgs.warnings);
    setStatus(payload.ok ? "Staging reset." : "Reset failed.");
  }

  async function commitStaging() {
    const payload = await api("/portal/api/data/commit", {
      method: "POST",
      body: JSON.stringify({ table_id: state.tableId, instance_id: state.instanceId, mode: state.mode }),
    });
    state.view = payload.view || state.view;
    renderGrid();

    const result = payload.result || {};
    const msgs = gatherViewMessages(state.view, result.errors || [], result.warnings || []);
    setMessages(msgs.errors, msgs.warnings);
    setStatus(payload.ok ? "Commit completed." : "Commit failed.");
  }

  function renderGrid() {
    if (!grid) return;
    grid.innerHTML = "";
    state.focusedCell = null;
    if (revertBtn) revertBtn.disabled = true;

    if (!state.view || !Array.isArray(state.view.columns) || !state.view.columns.length) {
      const empty = ce("div", "data-grid__empty");
      empty.textContent = state.tableId ? "No rows available for this table/instance." : "Select a table to start.";
      grid.appendChild(empty);
      return;
    }

    const table = ce("table", "data-grid__table");
    const thead = ce("thead");
    const headRow = ce("tr");

    const rowHead = ce("th");
    rowHead.textContent = "row_id";
    headRow.appendChild(rowHead);

    state.view.columns.forEach(function (col) {
      const th = ce("th");
      th.textContent = col;
      headRow.appendChild(th);
    });

    if (state.mode === "inspect") {
      const thInspect = ce("th");
      thInspect.textContent = "inspect";
      headRow.appendChild(thInspect);
    }

    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = ce("tbody");
    (state.view.rows || []).forEach(function (row) {
      const tr = ce("tr");

      const idCell = ce("td", "data-grid__rowid");
      idCell.textContent = String(row.row_id || "");
      tr.appendChild(idCell);

      (state.view.columns || []).forEach(function (fieldId) {
        const td = ce("td");
        const input = ce("input", "data-grid__input");
        input.type = "text";
        input.value = String((row.fields || {})[fieldId] || "");
        input.setAttribute("data-row-id", String(row.row_id || ""));
        input.setAttribute("data-field-id", fieldId);
        input.setAttribute("data-original", String((row.fields || {})[fieldId] || ""));

        if ((row.staged_fields || []).indexOf(fieldId) >= 0) {
          input.classList.add("is-staged");
        }

        input.addEventListener("focus", function () {
          state.focusedCell = { rowId: String(row.row_id || ""), fieldId: fieldId };
          if (revertBtn) revertBtn.disabled = false;
        });

        input.addEventListener("blur", function () {
          const original = input.getAttribute("data-original") || "";
          if (input.value !== original) {
            stageEdit(String(row.row_id || ""), fieldId, input.value).catch(function (err) {
              setMessages([err.message], []);
              setStatus("Stage edit failed.");
            });
          }
        });

        td.appendChild(input);
        tr.appendChild(td);
      });

      if (state.mode === "inspect") {
        const inspectCell = ce("td", "data-grid__inspect");
        const inspect = row.inspect || {};
        inspectCell.textContent = JSON.stringify(inspect);
        tr.appendChild(inspectCell);
      }

      tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    grid.appendChild(table);
  }

  if (modeSelect) {
    modeSelect.value = state.mode;
    modeSelect.addEventListener("change", function () {
      state.mode = modeSelect.value || "general";
      loadView().catch(function (err) {
        setMessages([err.message], []);
      });
    });
  }

  if (tableSelect) {
    tableSelect.addEventListener("change", function () {
      state.tableId = tableSelect.value || "";
      loadInstancesAndView().catch(function (err) {
        setMessages([err.message], []);
      });
    });
  }

  if (instanceSelect) {
    instanceSelect.addEventListener("change", function () {
      state.instanceId = instanceSelect.value || "";
      loadView().catch(function (err) {
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
      commitStaging().catch(function (err) {
        setMessages([err.message], []);
      });
    });
  }

  if (revertBtn) {
    revertBtn.addEventListener("click", function () {
      revertFocusedCell().catch(function (err) {
        setMessages([err.message], []);
      });
    });
  }

  loadTables().catch(function (err) {
    setMessages([err.message], []);
    setStatus("Failed to load data tables.");
  });
})();
