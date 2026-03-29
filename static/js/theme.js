// static/js/theme.js
// Manages dark/light mode toggle and sidebar collapse state.
// The IIFE applies theme + sidebar state synchronously on script execution
// (loaded in <head>) to prevent flash of wrong theme/layout before first paint.

(function () {
  const THEME_KEY   = 'vz-theme';
  const SIDEBAR_KEY = 'vz-sidebar';

  // ── Theme ──────────────────────────────────────────────────────────────

  // Replace or create the Lucide <i> icon inside a button.
  // After createIcons() runs, the <i> is swapped to <svg> — this handles both cases.
  function _setLucideIcon(btn, iconName) {
    const existing = btn.querySelector('i, svg');
    const i = document.createElement('i');
    i.setAttribute('data-lucide', iconName);
    i.setAttribute('aria-hidden', 'true');
    if (existing) existing.replaceWith(i); else btn.appendChild(i);
    if (window.lucide) lucide.createIcons({ nodes: [btn] });
  }

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(THEME_KEY, theme);
    // Update button icon after DOM is available
    const btn = document.getElementById('theme-toggle');
    if (btn) {
      btn.title = theme === 'dark' ? '切換淺色模式' : '切換暗色模式';
      _setLucideIcon(btn, theme === 'dark' ? 'sun' : 'moon');
    }
  }

  window.toggleTheme = function () {
    const current = document.documentElement.dataset.theme || 'light';
    applyTheme(current === 'dark' ? 'light' : 'dark');
  };

  // ── Sidebar ────────────────────────────────────────────────────────────

  function applySidebar(collapsed) {
    document.documentElement.dataset.sidebarCollapsed = collapsed ? 'true' : 'false';
    localStorage.setItem(SIDEBAR_KEY, collapsed ? '1' : '0');
    const btn = document.getElementById('sidebar-toggle');
    if (btn) {
      btn.title = collapsed ? '展開側欄' : '收合側欄';
      btn.setAttribute('aria-label', btn.title);
      _setLucideIcon(btn, collapsed ? 'panel-left-open' : 'panel-left-close');
    }
  }

  window.toggleSidebar = function () {
    const current = document.documentElement.dataset.sidebarCollapsed === 'true';
    applySidebar(!current);
  };

  window.openMobileSidebar = function () {
    const sidebar = document.getElementById('sidebar');
    const btn     = document.getElementById('ham-btn');
    if (!sidebar) return;
    const isOpen = sidebar.classList.toggle('open');
    if (btn) btn.setAttribute('aria-expanded', String(isOpen));
    if (isOpen) {
      const close = (e) => {
        if (!sidebar.contains(e.target) && e.target !== btn) {
          sidebar.classList.remove('open');
          if (btn) btn.setAttribute('aria-expanded', 'false');
          document.removeEventListener('click', close, true);
        }
      };
      document.addEventListener('click', close, true);
    }
  };

  // ── Synchronous early apply (runs immediately, before first paint) ──────
  const savedTheme   = localStorage.getItem(THEME_KEY);
  const prefersDark  = window.matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.dataset.theme = savedTheme || (prefersDark ? 'dark' : 'light');

  const savedSidebar = localStorage.getItem(SIDEBAR_KEY);
  document.documentElement.dataset.sidebarCollapsed = savedSidebar === '1' ? 'true' : 'false';

  // ── Post-DOM wiring (button icons only) ────────────────────────────────
  document.addEventListener('DOMContentLoaded', function () {
    applyTheme(document.documentElement.dataset.theme);
    applySidebar(document.documentElement.dataset.sidebarCollapsed === 'true');
  });
})();
