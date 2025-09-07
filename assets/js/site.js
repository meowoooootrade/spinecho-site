// Toggle sidebar on small screens
document.addEventListener('DOMContentLoaded', () => {
  const btn = document.querySelector('[data-menu]');
  const bar = document.querySelector('.sidebar');
  if (!btn || !bar) return;
  btn.addEventListener('click', () => bar.classList.toggle('open'));
});
