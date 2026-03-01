/* MyCite Portal JS
 * - Home tab switching (client-side)
 * - Sidebar alias filter (client-side)
 * No backend coupling; safe to keep while routes evolve.
 */

(function () {
  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

  // ---- Home tabs: buttons toggle panels by data-tab / data-panel ----
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
    // initialize from URL (?tab=inbox), else default to first tab
    const url = new URL(window.location.href);
    const tab = url.searchParams.get("tab") || (tabs[0] && tabs[0].getAttribute("data-tab"));
    if (tab) setActiveTab(tab);

    tabs.forEach(btn => {
      btn.addEventListener("click", () => {
        const t = btn.getAttribute("data-tab");
        if (!t) return;
        setActiveTab(t);

        // update URL without reload (keeps state shareable)
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
        const ok = text.toLowerCase().includes(q);
        li.style.display = ok ? "" : "none";
      });
    });
  }
})();
