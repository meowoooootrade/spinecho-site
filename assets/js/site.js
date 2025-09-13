// assets/js/site.js
document.addEventListener("DOMContentLoaded", () => {
  const root    = document.documentElement;
  const menuBtn = document.querySelector("[data-menu]");
  const sidebar = document.getElementById("sidebar") || document.querySelector(".sidebar");
  const themeBtn = document.getElementById("theme-toggle");

  // --- overlay (create once) ---
  let overlay = document.querySelector(".overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.className = "overlay";
    document.body.appendChild(overlay);
  }

  // --- aria helpers ---
  const setAria = (open) => {
    if (menuBtn) menuBtn.setAttribute("aria-expanded", String(open));
    if (sidebar) {
      sidebar.setAttribute("aria-hidden", String(!open));
      if (sidebar.id && menuBtn) menuBtn.setAttribute("aria-controls", sidebar.id);
    }
  };

  const lockScroll = (on) => {
    if (on) {
      root.classList.add("nav-open");
      document.body.style.overflow = "hidden";
    } else {
      root.classList.remove("nav-open");
      document.body.style.overflow = "";
    }
  };

  // --- nav open/close ---
  const openNav = () => {
    if (!sidebar) return;
    sidebar.classList.add("open");
    overlay.classList.add("is-show");
    setAria(true);
    lockScroll(true);
  };

  const closeNav = () => {
    if (!sidebar) return;
    sidebar.classList.remove("open");
    overlay.classList.remove("is-show");
    setAria(false);
    lockScroll(false);
  };

  const toggleNav = () => (sidebar?.classList.contains("open") ? closeNav() : openNav());

  // --- events ---
  if (menuBtn) {
    menuBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleNav();
    });
  }
  overlay.addEventListener("click", closeNav);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeNav(); });

  // --- theme toggle (persist + theme-color sync) ---
  (function initTheme(){
    const apply = (mode) => {
      root.dataset.theme = mode;
      if (themeBtn) themeBtn.textContent = (mode === "dark") ? "☀️" : "🌙";
      let meta = document.querySelector('meta[name="theme-color"]');
      if (!meta) {
        meta = document.createElement("meta");
        meta.name = "theme-color";
        document.head.appendChild(meta);
      }
      meta.content = (mode === "dark") ? "#1a2233" : "#f5fbfb";
    };

    // initial (head script may set it already; this resyncs the button label)
    const stored = localStorage.getItem("theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const initial = root.dataset.theme || stored || (prefersDark ? "dark" : "light");
    apply(initial);

    if (themeBtn) {
      themeBtn.addEventListener("click", () => {
        const next = root.dataset.theme === "dark" ? "light" : "dark";
        apply(next);
        localStorage.setItem("theme", next);
      });
    }
  })();

  // --- reduce motion support ---
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    document.body.classList.add("reduced-motion");
  }
});
