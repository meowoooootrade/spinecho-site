document.addEventListener("DOMContentLoaded", () => {
  const menuBtn = document.querySelector("[data-menu]");
  const sidebar = document.querySelector(".sidebar");
  if (!menuBtn || !sidebar) return;

  // 背景オーバーレイ
  const overlay = document.createElement("div");
  overlay.className = "overlay";
  document.body.appendChild(overlay);

  const open = () => {
    sidebar.classList.add("open");
    overlay.classList.add("is-show");
    menuBtn.setAttribute("aria-expanded", "true");
    document.documentElement.classList.add("nav-open");
  };
  const close = () => {
    sidebar.classList.remove("open");
    overlay.classList.remove("is-show");
    menuBtn.setAttribute("aria-expanded", "false");
    document.documentElement.classList.remove("nav-open");
  };
  const toggle = () => (sidebar.classList.contains("open") ? close() : open());

  menuBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggle();
  });
  overlay.addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") close();
  });

  // === Theme toggle ===
  (function(){
    const root = document.documentElement;
    const btn  = document.querySelector("#theme-toggle");

    // 保存されたテーマ or OS設定を初期値にする
    const stored = localStorage.getItem("theme"); // 'light' | 'dark' | null
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const initial = stored || (prefersDark ? "dark" : "light");

    applyTheme(initial);

    // クリックで切替
    if (btn) {
      btn.addEventListener("click", () => {
        const next = root.dataset.theme === "dark" ? "light" : "dark";
        applyTheme(next);
        localStorage.setItem("theme", next);
      });
    }

    function applyTheme(mode){
      if (mode === "dark") {
        root.dataset.theme = "dark";
        if (btn) btn.textContent = "☀️";
        setThemeColor("#0b1220");
      } else {
        root.dataset.theme = "light";
        if (btn) btn.textContent = "🌙";
        setThemeColor("#f5fbfb");
      }
    }

    // アドレスバー色(モバイル)も合わせる
    function setThemeColor(color){
      let meta = document.querySelector('meta[name="theme-color"]');
      if (!meta) {
        meta = document.createElement("meta");
        meta.setAttribute("name", "theme-color");
        document.head.appendChild(meta);
      }
      meta.setAttribute("content", color);
    }
  })();

});
