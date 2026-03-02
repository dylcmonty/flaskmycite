/* MyCite Portal JS
 * - Home/alias tab switching
 * - Sidebar alias filter
 * - Cross-portal theme standard for alias sessions and embed widgets
 */

(function () {
  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

  const THEME_STANDARD = {
    defaultTheme: "paper",
    themes: [
      { id: "paper", label: "Paper" },
      { id: "ocean", label: "Ocean" },
      { id: "forest", label: "Forest" },
      { id: "midnight", label: "Midnight" }
    ],
    sanitize(themeId) {
      const token = String(themeId || "").trim().toLowerCase();
      return this.themes.some(t => t.id === token) ? token : this.defaultTheme;
    }
  };
  window.MyCiteThemeStandard = THEME_STANDARD;

  const PORTAL_THEME_STORAGE_KEY = "mycite.theme.portal.default";

  function applyTheme(themeId) {
    const safe = THEME_STANDARD.sanitize(themeId);
    THEME_STANDARD.themes.forEach(t => document.body.classList.remove(`theme-${t.id}`));
    document.body.classList.add(`theme-${safe}`);
    document.body.setAttribute("data-theme", safe);
    qsa("[data-current-theme]").forEach(node => { node.textContent = safe; });
    return safe;
  }

  function withThemeParam(rawUrl, themeId) {
    if (!rawUrl) return rawUrl;
    try {
      const u = new URL(rawUrl, window.location.origin);
      u.searchParams.set("theme", themeId);
      return u.toString();
    } catch (_) {
      return rawUrl;
    }
  }

  function persistTheme(storageKey, themeId) {
    try { window.localStorage.setItem(storageKey, themeId); } catch (_) { }
  }

  function getStoredTheme(storageKey) {
    try { return window.localStorage.getItem(storageKey) || ""; } catch (_) { return ""; }
  }

  function setThemeInUrl(themeId) {
    try {
      const next = new URL(window.location.href);
      next.searchParams.set("theme", themeId);
      window.history.replaceState({}, "", next);
    } catch (_) { }
  }

  function detectPreferredTheme(storageKey) {
    try {
      const urlTheme = new URL(window.location.href).searchParams.get("theme") || "";
      if (urlTheme) return THEME_STANDARD.sanitize(urlTheme);
    } catch (_) { }
    const stored = getStoredTheme(storageKey);
    return THEME_STANDARD.sanitize(stored || THEME_STANDARD.defaultTheme);
  }

  function syncThemedIframes(themeId) {
    qsa("[data-themed-iframe]").forEach(frame => {
      const src = frame.getAttribute("src") || "";
      if (!src) return;
      const themedSrc = withThemeParam(src, themeId);
      if (themedSrc && themedSrc !== src) {
        frame.setAttribute("src", themedSrc);
      }
    });
  }

  function initThemeSelector() {
    const picker = qs("[data-theme-selector]");
    if (!picker) {
      const fallback = detectPreferredTheme(PORTAL_THEME_STORAGE_KEY);
      applyTheme(fallback);
      return;
    }

    if (!picker.options.length) {
      THEME_STANDARD.themes.forEach(t => {
        const opt = document.createElement("option");
        opt.value = t.id;
        opt.textContent = t.label;
        picker.appendChild(opt);
      });
    }

    const scope = picker.getAttribute("data-theme-scope") || "portal";
    const orgId = picker.getAttribute("data-org-msn-id") || "default";
    const storageKey = scope === "portal" ? PORTAL_THEME_STORAGE_KEY : `mycite.theme.${scope}.${orgId}`;
    const initial = detectPreferredTheme(storageKey);

    picker.value = initial;
    const applied = applyTheme(initial);
    syncThemedIframes(applied);
    setThemeInUrl(applied);

    picker.addEventListener("change", () => {
      const next = applyTheme(picker.value);
      picker.value = next;
      persistTheme(storageKey, next);
      persistTheme(PORTAL_THEME_STORAGE_KEY, next);
      syncThemedIframes(next);
      setThemeInUrl(next);
    });
  }

  // ---- Home and alias tabs ----
  const tabs = qsa(".hometabs__tab");
  const panels = qsa(".panel");

  function setActiveTab(tabName) {
    tabs.forEach(btn => {
      const isActive = btn.getAttribute("data-tab") === tabName;
      btn.classList.toggle("is-active", isActive);
    });
    panels.forEach(p => {
      const isActive = p.getAttribute("data-panel") === tabName;
      p.classList.toggle("is-active", isActive);
    });
  }

  if (tabs.length && panels.length) {
    const url = new URL(window.location.href);
    const tab = url.searchParams.get("tab") || (tabs[0] && tabs[0].getAttribute("data-tab"));
    if (tab) setActiveTab(tab);

    tabs.forEach(btn => {
      btn.addEventListener("click", () => {
        const t = btn.getAttribute("data-tab");
        if (!t) return;
        setActiveTab(t);
        const next = new URL(window.location.href);
        next.searchParams.set("tab", t);
        window.history.replaceState({}, "", next);
      });
    });
  }

  // ---- Alias sidebar filter ----
  const search = qs("#aliasSearch");
  const list = qs("#aliasList");
  if (search && list) {
    const items = qsa(".navcol__item", list);
    search.addEventListener("input", () => {
      const q = (search.value || "").trim().toLowerCase();
      items.forEach(li => {
        const a = qs(".navcol__linkTitle", li);
        const b = qs(".navcol__linkSub", li);
        const text = ((a && a.textContent) || "") + " " + ((b && b.textContent) || "");
        li.style.display = text.toLowerCase().includes(q) ? "" : "none";
      });
    });
  }

  initThemeSelector();
})();
