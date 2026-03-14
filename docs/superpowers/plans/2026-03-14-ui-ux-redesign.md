# UI/UX Redesign Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the visual design system — colour tokens, Inter typography, SVG icons, collapsible sidebar, dark mode, skeleton loaders, and polished component styles — without changing any backend behaviour.

**Architecture:** All changes are confined to `static/css/style.css`, `static/js/common.js`, `static/js/index.js`, `static/js/detail.js`, `templates/index.html`, and `templates/detail.html`. A new `static/css/theme.css` splits design tokens out from component rules. A new `static/js/theme.js` handles dark-mode toggle and sidebar collapse. No new Python files, no API changes.

**Tech Stack:** HTML5 Jinja2 templates · Vanilla CSS (CSS variables) · Vanilla JS (ES2020) · Inter (Google Fonts CDN) · Lucide Icons (CDN UMD build)

**Spec:** `docs/superpowers/specs/2026-03-14-ui-ux-redesign-design.md`

**Tests:** Run `pytest --tb=short -q` after every commit — all 325 must stay green (UI changes don't touch Python).

---

## Chunk 1: Design Token Foundation

**Files:**
- Create: `static/css/theme.css` — CSS variables (colours, type scale, spacing, shadows, transitions)
- Modify: `static/css/style.css` — remove inline hex/size literals, use token vars
- Modify: `templates/index.html` — add Inter Google Fonts link + Lucide CDN + `theme.css` link
- Modify: `templates/detail.html` — same head additions

---

### Task 1: Create `static/css/theme.css` with light + dark tokens

**Files:**
- Create: `static/css/theme.css`

- [ ] **Step 1: Create theme.css**

```css
/* static/css/theme.css
   Single source of truth for all design tokens.
   Components in style.css must only use var(--*) references defined here. */

/* ── Light mode (default) ─────────────────────────────────────────────── */
:root {
  /* Brand */
  --color-brand-50:   #eff6ff;
  --color-brand-100:  #dbeafe;
  --color-brand-500:  #3b82f6;
  --color-brand-600:  #2563eb;
  --color-brand-700:  #1d4ed8;

  /* Semantic */
  --color-success-bg: #f0fdf4;
  --color-success:    #16a34a;
  --color-warning-bg: #fffbeb;
  --color-warning:    #d97706;
  --color-danger-bg:  #fef2f2;
  --color-danger:     #dc2626;
  --color-info-bg:    #eff6ff;
  --color-info:       #2563eb;

  /* Neutral scale */
  --color-gray-0:   #ffffff;
  --color-gray-25:  #fafafa;
  --color-gray-50:  #f5f5f5;
  --color-gray-100: #e5e5e5;
  --color-gray-200: #d4d4d4;
  --color-gray-300: #a3a3a3;
  --color-gray-500: #737373;
  --color-gray-700: #404040;
  --color-gray-900: #171717;

  /* Mapped design tokens */
  --bg:            var(--color-gray-25);
  --surface:       var(--color-gray-0);
  --surface-2:     var(--color-gray-50);
  --border:        var(--color-gray-200);
  --border-subtle: var(--color-gray-100);
  --text:          var(--color-gray-900);
  --text-2:        var(--color-gray-700);
  --muted:         var(--color-gray-500);
  --placeholder:   var(--color-gray-300);
  --primary:       var(--color-brand-600);
  --primary-hover: var(--color-brand-700);
  --focus-ring:    0 0 0 3px rgba(37,99,235,.25);

  /* Typography */
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  --text-xs:   11px;
  --text-sm:   12px;
  --text-base: 14px;
  --text-md:   15px;
  --text-lg:   17px;
  --text-xl:   20px;
  --leading-tight:  1.3;
  --leading-snug:   1.4;
  --leading-normal: 1.6;
  --leading-relaxed:1.75;

  /* Layout */
  --radius-sm: 4px;
  --radius:    8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --sidebar-w:           240px;
  --sidebar-w-collapsed:  60px;

  /* Elevation */
  --shadow-xs: 0 1px 2px rgba(0,0,0,.05);
  --shadow-sm: 0 1px 3px rgba(0,0,0,.08), 0 1px 2px rgba(0,0,0,.04);
  --shadow-md: 0 4px 6px rgba(0,0,0,.07), 0 2px 4px rgba(0,0,0,.05);
  --shadow-lg: 0 10px 15px rgba(0,0,0,.10), 0 4px 6px rgba(0,0,0,.05);

  /* Motion */
  --t-fast: .10s ease;
  --t-base: .18s ease;
  --t-slow: .30s ease;
}

/* ── Dark mode ─────────────────────────────────────────────────────────── */
[data-theme="dark"] {
  --bg:            #0a0a0a;
  --surface:       #141414;
  --surface-2:     #1e1e1e;
  --border:        #2a2a2a;
  --border-subtle: #1f1f1f;
  --text:          #fafafa;
  --text-2:        #a3a3a3;
  --muted:         #737373;
  --placeholder:   #525252;
  --primary:       #3b82f6;
  --primary-hover: #2563eb;
  --focus-ring:    0 0 0 3px rgba(59,130,246,.35);

  /* Semantic dark */
  --color-success-bg: #052e16;
  --color-success:    #4ade80;
  --color-warning-bg: #451a03;
  --color-warning:    #fbbf24;
  --color-danger-bg:  #450a0a;
  --color-danger:     #f87171;
  --color-info-bg:    #0c1a2e;
  --color-info:       #60a5fa;

  --shadow-xs: 0 1px 2px rgba(0,0,0,.30);
  --shadow-sm: 0 1px 3px rgba(0,0,0,.40);
  --shadow-md: 0 4px 6px rgba(0,0,0,.50);
  --shadow-lg: 0 10px 15px rgba(0,0,0,.60);
}
```

- [ ] **Step 2: Verify file saved, spot-check dark vars exist**

```bash
grep -c "data-theme" static/css/theme.css
# expected: 1
grep "color-danger-bg" static/css/theme.css | wc -l
# expected: 2 (light + dark)
```

---

### Task 2: Add Inter font + Lucide CDN to both templates

**Files:**
- Modify: `templates/index.html` — `<head>` section
- Modify: `templates/detail.html` — `<head>` section

- [ ] **Step 1: In `templates/index.html`, replace the existing `<head>` font/CSS section**

Find the line that loads `style.css` and insert before it:

```html
  <!-- Design tokens -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/css/theme.css">
```

Also add Lucide before `</body>`:
```html
  <script src="https://unpkg.com/lucide@0.378.0/dist/umd/lucide.min.js"></script>
  <script>document.addEventListener('DOMContentLoaded', () => lucide.createIcons());</script>
```

- [ ] **Step 2: Repeat for `templates/detail.html`** (same `<head>` additions and same Lucide script before `</body>`)

- [ ] **Step 3: In `static/css/style.css`, change the `body` font-family rule**

```css
/* Before */
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; ... }

/* After */
body { font-family: var(--font-sans); ... }
```

- [ ] **Step 4: Replace all raw hex colour literals in style.css with token vars**

Map of substitutions (do in order to avoid partial matches):

| Old literal | New var |
|-------------|---------|
| `#4f46e5` | `var(--primary)` |
| `#4338ca` | `var(--primary-hover)` |
| `#16a34a` | `var(--color-success)` |
| `#d97706` | `var(--color-warning)` |
| `#dc2626` | `var(--color-danger)` |
| `#0284c7` | `var(--color-info)` |
| `#f8fafc` | `var(--bg)` |
| `#ffffff` | `var(--surface)` |
| `#e2e8f0` | `var(--border)` |
| `#1e293b` | `var(--text)` |
| `#64748b` | `var(--muted)` |
| `#dcfce7` | `var(--color-success-bg)` |
| `#fef3c7` | `var(--color-warning-bg)` |
| `#fee2e2` | `var(--color-danger-bg)` |
| `#eff6ff` | `var(--color-info-bg)` |

Run the sed commands:
```bash
cd static/css
sed -i '' 's/#4f46e5/var(--primary)/g' style.css
sed -i '' 's/#4338ca/var(--primary-hover)/g' style.css
sed -i '' 's/#16a34a/var(--color-success)/g' style.css
sed -i '' 's/#d97706/var(--color-warning)/g' style.css
sed -i '' 's/#dc2626/var(--color-danger)/g' style.css
sed -i '' 's/#0284c7/var(--color-info)/g' style.css
sed -i '' 's/#f8fafc/var(--bg)/g' style.css
sed -i '' 's/#ffffff/var(--surface)/g' style.css
sed -i '' 's/#e2e8f0/var(--border)/g' style.css
sed -i '' 's/#1e293b/var(--text)/g' style.css
sed -i '' 's/#64748b/var(--muted)/g' style.css
# The four background tokens (must come after their foreground tokens above)
sed -i '' 's/#dcfce7/var(--color-success-bg)/g' style.css
sed -i '' 's/#fef3c7/var(--color-warning-bg)/g' style.css
sed -i '' 's/#fee2e2/var(--color-danger-bg)/g' style.css
sed -i '' 's/#eff6ff/var(--color-info-bg)/g' style.css
```

- [ ] **Step 4b: Audit remaining raw hex values and replace any critical ones**

```bash
# See what hex values remain
grep -oE '#[0-9a-fA-F]{3,6}' static/css/style.css | sort -u
```

Replace any remaining values that are semantically equivalent to a token with their token. Key-point rainbow colours (`#fef2f2`, `#ef4444`, etc.) are intentional and may remain as-is — they are display-only decorations, not design tokens.

- [ ] **Step 5: Remove the old `:root { --primary: ... }` block from style.css** (now duplicated by theme.css)

In `style.css`, find the block that starts with `:root {` and contains `--primary` / `--success` / `--warning` etc. Delete the entire block from its opening `{` to its matching `}`. Confirm by checking `grep ":root" static/css/style.css` returns no remaining `:root` block.

- [ ] **Step 6: Run tests**

```bash
pytest --tb=short -q
# Expected: 325 passed
```

- [ ] **Step 7: Commit**

```bash
git add static/css/theme.css static/css/style.css templates/index.html templates/detail.html
git commit -m "feat(ui): design token foundation — theme.css, Inter font, Lucide CDN

- Extracted colour/type/shadow/motion tokens into static/css/theme.css
- Light + dark mode CSS variable overrides via [data-theme=dark]
- Replaced 15 primary hex values + remaining critical literals with var() refs
- Added Inter font (Google Fonts) to both templates
- Added Lucide Icons 0.378 UMD CDN to both templates

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Chunk 2: Sidebar Collapsible + Lucide Icons

**Files:**
- Create: `static/js/theme.js` — theme toggle + sidebar collapse state
- Modify: `templates/index.html` — sidebar HTML structure, Lucide icon markup
- Modify: `templates/detail.html` — same sidebar (shared markup)
- Modify: `static/css/style.css` — sidebar collapse CSS + icon styles

---

### Task 3: Create `static/js/theme.js`

**Files:**
- Create: `static/js/theme.js`

- [ ] **Step 1: Create theme.js**

```javascript
// static/js/theme.js
// Manages dark/light mode toggle and sidebar collapse state.
// The IIFE applies theme + sidebar state synchronously on script execution
// (loaded in <head>) to prevent flash of wrong theme/layout before first paint.

(function () {
  const THEME_KEY   = 'vz-theme';
  const SIDEBAR_KEY = 'vz-sidebar';

  // ── Theme ──────────────────────────────────────────────────────────────

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(THEME_KEY, theme);
    // Update button icon after DOM is available
    const btn = document.getElementById('theme-toggle');
    if (btn) {
      const icon = theme === 'dark' ? 'sun' : 'moon';
      btn.setAttribute('data-lucide', icon);
      btn.title = theme === 'dark' ? '切換淺色模式' : '切換暗色模式';
      if (window.lucide) lucide.createIcons({ nodes: [btn] });
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
      btn.setAttribute('data-lucide', collapsed ? 'panel-left-open' : 'panel-left-close');
      if (window.lucide) lucide.createIcons({ nodes: [btn] });
    }
  }

  window.toggleSidebar = function () {
    const current = document.documentElement.dataset.sidebarCollapsed === 'true';
    applySidebar(!current);
  };

  // ── Synchronous early apply (runs immediately, before first paint) ──────
  // Apply to <html> element directly — no DOM query needed.
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
```

- [ ] **Step 2: Add `theme.js` to both templates** (load in `<head>` before any other script to prevent flash):

In `templates/index.html` and `templates/detail.html`, add inside `<head>`:
```html
  <script src="/static/js/theme.js"></script>
```

---

### Task 4: Update sidebar HTML in both templates

**Files:**
- Modify: `templates/index.html`
- Modify: `templates/detail.html`

- [ ] **Step 1: Replace sidebar structure in `templates/index.html`**

Replace the `<aside class="sidebar">` block with:

```html
<aside class="sidebar" id="sidebar">
  <div class="sidebar-header">
    <div class="sidebar-logo">
      <i data-lucide="clapperboard" class="sidebar-logo-icon"></i>
      <span class="sidebar-logo-text">Video Analyzer</span>
    </div>
    <button id="sidebar-toggle" class="icon-btn" onclick="toggleSidebar()"
            title="收合側欄" aria-label="收合側欄">
      <i data-lucide="panel-left-close"></i>
    </button>
  </div>

  <nav class="sidebar-nav">
    <button class="nav-item active" onclick="showSection('analysis')" data-section="analysis">
      <i data-lucide="microscope" class="nav-icon"></i>
      <span class="nav-label">分析中心</span>
    </button>
    <button class="nav-item" onclick="showSection('review')" data-section="review">
      <i data-lucide="book-open" class="nav-icon"></i>
      <span class="nav-label">複習中心</span>
    </button>
    <button class="nav-item" onclick="showSection('search')" data-section="search">
      <i data-lucide="search" class="nav-icon"></i>
      <span class="nav-label">全文搜尋</span>
    </button>
    <button class="nav-item" onclick="showSection('stats')" data-section="stats">
      <i data-lucide="bar-chart-2" class="nav-icon"></i>
      <span class="nav-label">學習統計</span>
    </button>
    <button class="nav-item" onclick="showSection('labels')" data-section="labels">
      <i data-lucide="tag" class="nav-icon"></i>
      <span class="nav-label">標籤管理</span>
    </button>
  </nav>

  <div class="sidebar-status" id="sidebar-status">
    <!-- populated by loadStats() -->
  </div>

  <div class="sidebar-footer">
    <button id="theme-toggle" class="icon-btn" onclick="toggleTheme()"
            title="切換暗色模式" aria-label="切換暗色模式">
      <i data-lucide="moon"></i>
    </button>
  </div>
</aside>
```

- [ ] **Step 2: Update `templates/detail.html` sidebar** with the same structure. Note: on the detail page, no nav item gets a hard-coded `active` class — the sidebar is purely for navigation back to the index sections. The active state is not set on detail pages (it's a single-video view, not a section).

---

### Task 5: Add sidebar collapse CSS

**Files:**
- Modify: `static/css/style.css`

- [ ] **Step 1: Replace existing `.sidebar` block and add collapse styles (including collapsed tooltip)**

```css
/* ── Sidebar ─────────────────────────────────────────────────────────── */
.sidebar {
  width: var(--sidebar-w);
  min-height: 100vh;
  background: var(--surface-2);
  border-right: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width var(--t-slow);
  overflow: hidden;
}

/* Collapsed state */
[data-sidebar-collapsed="true"] .sidebar {
  width: var(--sidebar-w-collapsed);
}
[data-sidebar-collapsed="true"] .nav-label,
[data-sidebar-collapsed="true"] .sidebar-logo-text,
[data-sidebar-collapsed="true"] .sidebar-status {
  display: none;
}
[data-sidebar-collapsed="true"] .sidebar-header {
  justify-content: center;
}
[data-sidebar-collapsed="true"] .nav-item {
  justify-content: center;
  padding: 10px 0;
}
[data-sidebar-collapsed="true"] .sidebar-footer {
  justify-content: center;
}

/* Tooltip on collapsed nav items (title attribute rendered as tooltip via CSS) */
[data-sidebar-collapsed="true"] .nav-item {
  position: relative;
}
[data-sidebar-collapsed="true"] .nav-item::after {
  content: attr(title);
  position: absolute;
  left: calc(var(--sidebar-w-collapsed) + 8px);
  top: 50%;
  transform: translateY(-50%);
  background: var(--color-gray-900);
  color: var(--color-gray-0);
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transition: opacity var(--t-fast);
  z-index: 600;
}
[data-sidebar-collapsed="true"] .nav-item:hover::after { opacity: 1; }
[data-theme="dark"] [data-sidebar-collapsed="true"] .nav-item::after {
  background: var(--color-gray-50);
  color: var(--color-gray-900);
}
```

- [ ] **Step 2: Add `title` attributes to each nav-item in both templates** so the collapsed tooltip shows the section name:

In `templates/index.html` and `templates/detail.html`, update each nav button to include `title`:
```html
<button class="nav-item active" onclick="showSection('analysis')" data-section="analysis" title="分析中心">
<button class="nav-item" onclick="showSection('review')"   data-section="review"   title="複習中心">
<button class="nav-item" onclick="showSection('search')"   data-section="search"   title="全文搜尋">
<button class="nav-item" onclick="showSection('stats')"    data-section="stats"    title="學習統計">
<button class="nav-item" onclick="showSection('labels')"   data-section="labels"   title="標籤管理">
```
/* Sidebar sections */
.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 14px;
  border-bottom: 1px solid var(--border-subtle);
  gap: 8px;
}
.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--text-md);
  font-weight: 700;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
}
.sidebar-logo-icon { color: var(--primary); flex-shrink: 0; }
.sidebar-logo-text { overflow: hidden; text-overflow: ellipsis; }

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 8px;
  flex: 1;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border: none;
  background: none;
  border-radius: var(--radius);
  cursor: pointer;
  font-size: var(--text-base);
  font-weight: 500;
  color: var(--text-2);
  transition: background var(--t-fast), color var(--t-fast);
  white-space: nowrap;
  width: 100%;
  text-align: left;
}
.nav-item:hover { background: var(--border-subtle); color: var(--text); }
.nav-item.active { background: var(--color-brand-50); color: var(--primary); }
[data-theme="dark"] .nav-item.active { background: rgba(59,130,246,.12); }
.nav-icon { flex-shrink: 0; }

.sidebar-status {
  padding: 10px 14px 6px;
  border-top: 1px solid var(--border-subtle);
  font-size: var(--text-sm);
  color: var(--muted);
}
.sidebar-footer {
  padding: 10px 8px;
  border-top: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
}

/* Icon-only button */
.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  background: none;
  border-radius: var(--radius);
  cursor: pointer;
  color: var(--muted);
  transition: background var(--t-fast), color var(--t-fast);
  flex-shrink: 0;
}
.icon-btn:hover { background: var(--border-subtle); color: var(--text); }
```

- [ ] **Step 2: Run tests**

```bash
pytest --tb=short -q
# Expected: 325 passed
```

- [ ] **Step 3: Commit**

```bash
git add static/js/theme.js static/css/style.css templates/index.html templates/detail.html
git commit -m "feat(ui): collapsible sidebar + Lucide icons + theme toggle

- Collapsible sidebar (240px ↔ 60px) with localStorage persistence
- Sidebar nav items use Lucide SVG icons replacing emoji
- Dark/light mode toggle button in sidebar footer
- theme.js runs in <head> to prevent flash of wrong theme/sidebar state
- CSS collapse driven by [data-sidebar-collapsed] attribute on <html>

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Chunk 3: Toast + Badge + Tab Underline Redesign

**Files:**
- Modify: `static/js/common.js` — structured toast function
- Modify: `static/css/style.css` — toast styles, badge styles, tab underline styles

---

### Task 6: Redesign Toast notifications

**Files:**
- Modify: `static/js/common.js`
- Modify: `static/css/style.css`

- [ ] **Step 1: Rewrite `toast()` in `static/js/common.js`**

```javascript
// Replace existing toast() function

const _TOAST_ICONS = {
  success: 'circle-check',
  error:   'circle-x',
  warning: 'triangle-alert',
  info:    'info',
};

function toast(msg, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }

  // Cap at 5 toasts — remove oldest if over limit
  const existing = container.querySelectorAll('.toast');
  if (existing.length >= 5) existing[0].remove();

  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.innerHTML = `
    <i data-lucide="${_TOAST_ICONS[type] || 'info'}" class="toast-icon" aria-hidden="true"></i>
    <span class="toast-msg">${msg}</span>
    <button class="toast-close icon-btn" aria-label="關閉" onclick="this.closest('.toast').remove()">
      <i data-lucide="x" aria-hidden="true"></i>
    </button>`;
  container.appendChild(t);

  if (window.lucide) lucide.createIcons({ nodes: [t] });

  // Auto-remove after 4s with fade-out
  setTimeout(() => {
    t.classList.add('toast-hide');
    t.addEventListener('animationend', () => t.remove(), { once: true });
  }, 4000);
}
```

- [ ] **Step 2: Replace toast CSS in `static/css/style.css`**

```css
/* ── Toast ───────────────────────────────────────────────────────────── */
#toast-container {
  position: fixed;
  top: 20px;
  right: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 2000;
  pointer-events: none;
}
.toast {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 4px solid var(--color-info);
  border-radius: var(--radius);
  padding: 12px 14px;
  box-shadow: var(--shadow-md);
  font-size: var(--text-base);
  color: var(--text);
  max-width: 360px;
  pointer-events: auto;
  animation: toast-in .2s ease forwards;
}
.toast-success { border-left-color: var(--color-success); }
.toast-error   { border-left-color: var(--color-danger); }
.toast-warning { border-left-color: var(--color-warning); }
.toast-info    { border-left-color: var(--color-info); }

.toast-icon {
  flex-shrink: 0;
  color: var(--color-info);
}
.toast-success .toast-icon { color: var(--color-success); }
.toast-error   .toast-icon { color: var(--color-danger); }
.toast-warning .toast-icon { color: var(--color-warning); }

.toast-msg  { flex: 1; line-height: var(--leading-normal); }
.toast-close { margin-left: 4px; }
.toast-hide { animation: toast-out .2s ease forwards; }

@keyframes toast-in {
  from { opacity: 0; transform: translateX(20px); }
  to   { opacity: 1; transform: translateX(0); }
}
@keyframes toast-out {
  from { opacity: 1; transform: translateX(0); }
  to   { opacity: 0; transform: translateX(20px); }
}
```

---

### Task 7: Redesign Status Badges

**Files:**
- Modify: `static/css/style.css`
- Modify: `static/js/common.js`

- [ ] **Step 1: Update `badge()` in `static/js/common.js`**

```javascript
// Replace existing badge() function
function badge(status) {
  const map = {
    pending:    ['pending',    '等待中'],
    queued:     ['queued',     '排隊中'],
    processing: ['processing', '分析中'],
    completed:  ['completed',  '已完成'],
    failed:     ['failed',     '失敗'],
  };
  const [cls, label] = map[status] || ['pending', status];
  return `<span class="badge badge-${cls}">
    <span class="badge-dot"></span>${label}</span>`;
}
```

- [ ] **Step 2: Update badge CSS**

```css
/* ── Status Badges ────────────────────────────────────────────────────── */
.badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: .2px;
}
.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.badge-pending    { background: var(--color-gray-100); color: var(--muted); }
.badge-pending    .badge-dot { background: var(--muted); }
.badge-queued     { background: var(--color-info-bg); color: var(--color-info); }
.badge-queued     .badge-dot { background: var(--color-info); }
.badge-processing { background: var(--color-warning-bg); color: var(--color-warning);
                    animation: badge-pulse 2s ease-in-out infinite; }
.badge-processing .badge-dot { background: var(--color-warning); }
.badge-completed  { background: var(--color-success-bg); color: var(--color-success); }
.badge-completed  .badge-dot { background: var(--color-success); }
.badge-failed     { background: var(--color-danger-bg); color: var(--color-danger); }
.badge-failed     .badge-dot { background: var(--color-danger); }

@keyframes badge-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: .65; }
}
```

---

### Task 8: Tab underline style

**Files:**
- Modify: `static/css/style.css`

- [ ] **Step 1: Replace tab CSS**

```css
/* ── Tabs ─────────────────────────────────────────────────────────────── */
.tab-bar {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 0;
  overflow-x: auto;
  scrollbar-width: none;
}
.tab-bar::-webkit-scrollbar { display: none; }
.tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  border: none;
  border-bottom: 2px solid transparent;
  background: none;
  cursor: pointer;
  font-size: var(--text-base);
  font-weight: 500;
  color: var(--muted);
  white-space: nowrap;
  transition: color var(--t-fast), border-color var(--t-fast);
  margin-bottom: -1px;
}
.tab-btn:hover { color: var(--text); }
.tab-btn.active {
  color: var(--primary);
  border-bottom-color: var(--primary);
}
```

- [ ] **Step 2: Run tests**

```bash
pytest --tb=short -q
# Expected: 325 passed
```

- [ ] **Step 3: Commit**

```bash
git add static/js/common.js static/css/style.css
git commit -m "feat(ui): toast redesign, badge dot style, tab underline

- Toast: type-coloured left border + Lucide icon + slide-in/out animation + max-5 cap
- Badge: colour dot replaces ALL-CAPS text, softer backgrounds
- Tabs: underline style (no filled background), active = 2px blue border-bottom

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Chunk 4: Card Hover + Progress Step Redesign

**Files:**
- Modify: `static/css/style.css` — card hover, progress steps
- Modify: `static/js/detail.js` — renderProgress() rewrite

---

### Task 9: Card hover animation

**Files:**
- Modify: `static/css/style.css`

- [ ] **Step 1: Update `.card` styles**

```css
/* ── Card ─────────────────────────────────────────────────────────────── */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 20px 24px;
  transition: box-shadow var(--t-base), transform var(--t-base);
}
.card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}
.card-title {
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--text);
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.card-title i { color: var(--muted); }
```

---

### Task 10: Progress step redesign

**Files:**
- Modify: `static/css/style.css`
- Modify: `static/js/detail.js`

- [ ] **Step 1: Replace progress step CSS**

```css
/* ── Progress Steps ──────────────────────────────────────────────────── */
.progress-steps {
  display: flex;
  align-items: flex-start;
  gap: 0;
  margin: 16px 0;
}
.progress-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  position: relative;
}
/* Connector line between steps */
.progress-step:not(:last-child)::after {
  content: '';
  position: absolute;
  top: 14px;
  left: 50%;
  width: 100%;
  height: 2px;
  background: var(--border);
  transition: background var(--t-slow);
}
.progress-step.done:not(:last-child)::after { background: var(--color-success); }
.progress-step.active:not(:last-child)::after { background: var(--border); }

.step-circle {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-sm);
  font-weight: 700;
  background: var(--surface-2);
  border: 2px solid var(--border);
  color: var(--muted);
  position: relative;
  z-index: 1;
  transition: background var(--t-base), border-color var(--t-base), color var(--t-base);
}
.progress-step.done  .step-circle {
  background: var(--color-success);
  border-color: var(--color-success);
  color: #fff;
}
.progress-step.active .step-circle {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
  animation: step-pulse 1.8s ease-in-out infinite;
}
.step-label {
  margin-top: 6px;
  font-size: var(--text-xs);
  color: var(--muted);
  text-align: center;
  line-height: var(--leading-snug);
}
.progress-step.done  .step-label { color: var(--color-success); }
.progress-step.active .step-label { color: var(--primary); font-weight: 600; }

@keyframes step-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(37,99,235,.4); }
  50%       { box-shadow: 0 0 0 6px rgba(37,99,235,0); }
}
```

- [ ] **Step 2: Rewrite `renderProgress()` in `static/js/detail.js`**

Find the existing `function renderProgress(p)` and replace the inner step-rendering logic:

```javascript
function renderProgress(p) {
  const steps = [
    { key: 'audio_extract',    label: '音訊提取' },
    { key: 'transcription',    label: '語音轉文字' },
    { key: 'gpt_analysis',     label: 'GPT 分析' },
    { key: 'generate_summary', label: '生成摘要' },
  ];

  const currentStep = (p.step != null ? p.step : 1) - 1;  // 0-indexed; p.step=0 means no step active

  const stepsHtml = steps.map((s, i) => {
    let cls = 'inactive';
    let inner = i + 1;
    if (i < currentStep) {
      cls = 'done';
      inner = '<i data-lucide="check" style="width:14px;height:14px;stroke-width:3"></i>';
    } else if (i === currentStep) {
      cls = 'active';
    }
    return `
      <div class="progress-step ${cls}">
        <div class="step-circle">${inner}</div>
        <div class="step-label">${s.label}</div>
      </div>`;
  }).join('');

  const stepsEl = document.getElementById('progress-steps');
  if (stepsEl) {
    stepsEl.innerHTML = stepsHtml;
    if (window.lucide) lucide.createIcons({ nodes: [stepsEl] });
  }

  // Overall progress bar
  const pct = p.overall_pct ?? 0;
  const bar = document.getElementById('progress-bar');
  if (bar) bar.style.width = pct + '%';
  const pctEl = document.getElementById('progress-pct');
  if (pctEl) pctEl.textContent = Math.round(pct) + '%';
}
```

- [ ] **Step 3: Run tests**

```bash
pytest --tb=short -q
# Expected: 325 passed
```

- [ ] **Step 4: Commit**

```bash
git add static/css/style.css static/js/detail.js
git commit -m "feat(ui): card hover animation + numbered progress step redesign

- Cards: translateY(-1px) + shadow-md on hover
- Progress steps: numbered circles (1-4), check SVG when done, blue pulse on active
- Connector lines turn green as steps complete
- Replaced emoji step icons with semantic CSS states

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Chunk 5: Dark Mode + Skeleton Loaders

**Files:**
- Modify: `static/css/style.css` — skeleton keyframe + classes
- Modify: `static/js/index.js` — add skeleton to video list load
- Modify: `static/js/detail.js` — add skeleton to tab content load

---

### Task 11: Skeleton loaders

**Files:**
- Modify: `static/css/style.css`

- [ ] **Step 1: Add skeleton CSS**

```css
/* ── Skeleton Loader ──────────────────────────────────────────────────── */
.skeleton {
  background: linear-gradient(
    90deg,
    var(--surface-2) 25%,
    var(--border-subtle) 50%,
    var(--surface-2) 75%
  );
  background-size: 400% 100%;
  animation: skeleton-shimmer 1.4s ease infinite;
  border-radius: var(--radius-sm);
}
@keyframes skeleton-shimmer {
  0%   { background-position: 100% 50%; }
  100% { background-position: 0%   50%; }
}

/* Pre-built skeleton shapes */
.skel-text   { height: 14px; margin-bottom: 8px; }
.skel-text-sm { height: 11px; margin-bottom: 6px; width: 60%; }
.skel-row    { height: 44px; margin-bottom: 4px; border-radius: var(--radius); }
.skel-card   { height: 80px; border-radius: var(--radius-lg); margin-bottom: 12px; }
.skel-para > .skel-text:last-child { width: 70%; }
```

- [ ] **Step 2: Add table skeleton in `static/js/index.js`**

In `loadVideos()`, add skeleton before the fetch call:

```javascript
// Show skeleton rows while loading
function _tableSkeletonHtml(rows = 6) {
  return Array.from({ length: rows }, () =>
    `<tr>${Array.from({ length: 6 }, () =>
      `<td><div class="skeleton skel-text"></div></td>`
    ).join('')}</tr>`
  ).join('');
}

// Inside loadVideos(), before await api(...)
const tbody = document.querySelector('#video-table tbody');
if (tbody) tbody.innerHTML = _tableSkeletonHtml();
```

- [ ] **Step 3: Add tab-content skeleton in `static/js/detail.js`**

In the lazy-load logic for each tab (inside `switchTab()`), show skeleton while fetching:

```javascript
// Fixed alternating widths — deterministic, no Math.random()
const _SKEL_WIDTHS = ['90%', '75%', '85%', '65%'];
function _contentSkeletonHtml() {
  return `<div style="padding:20px">
    ${ _SKEL_WIDTHS.map(w =>
       `<div class="skeleton skel-text" style="width:${w}"></div>`
    ).join('') }
    <div class="skeleton skel-text skel-text-sm"></div>
  </div>`;
}
```

Call `panelEl.innerHTML = _contentSkeletonHtml()` before any async fetch in each tab loader.

---

### Task 12: Verify dark mode works end-to-end

**Files:**
- (theme.css already has dark vars from Task 1)

- [ ] **Step 1: Manual check list**

Start the server: `python3 main.py`

Open `http://localhost:8000` and verify:
1. Click moon icon in sidebar footer → page switches to dark
2. Reload page → dark mode persists (localStorage)
3. All cards, sidebar, badges, toasts readable in dark mode
4. Click sun icon → back to light mode

- [ ] **Step 2: Add missing dark-mode overrides to style.css** for any components not yet covered by the token system (e.g. modals, scrollbars, input focus rings):

```css
/* Dark mode overrides for components using hardcoded values */
[data-theme="dark"] .modal-box { box-shadow: 0 20px 60px rgba(0,0,0,.6); }
[data-theme="dark"] input,
[data-theme="dark"] select,
[data-theme="dark"] textarea {
  background: var(--surface-2);
  color: var(--text);
}
[data-theme="dark"] ::-webkit-scrollbar-track { background: var(--surface-2); }
[data-theme="dark"] ::-webkit-scrollbar-thumb { background: var(--border); }
```

- [ ] **Step 3: Run tests**

```bash
pytest --tb=short -q
# Expected: 325 passed
```

- [ ] **Step 4: Commit**

```bash
git add static/css/style.css static/js/index.js static/js/detail.js
git commit -m "feat(ui): skeleton loaders + dark mode polish

- Skeleton shimmer animation for table rows and tab content panels
- Dark mode overrides for modals, inputs, scrollbars
- Theme toggle (moon/sun) wired up via theme.js toggleTheme()

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Chunk 6: Transcript Layout + Responsive Breakpoints

**Files:**
- Modify: `static/css/style.css` — transcript speaker layout, responsive
- Modify: `templates/detail.html` — transcript segment markup tweak

---

### Task 13: Transcript speaker-layout

**Files:**
- Modify: `static/css/style.css`
- Modify: `templates/detail.html` (or `static/js/detail.js` renderTranscript section)

- [ ] **Step 1: Update transcript CSS**

```css
/* ── Transcript ──────────────────────────────────────────────────────── */
.transcript-body {
  padding: 8px 0;
  max-height: 420px;
  overflow-y: auto;
  scroll-behavior: smooth;
}
.transcript-seg {
  display: flex;
  gap: 14px;
  padding: 10px 16px;
  border-left: 3px solid transparent;
  border-radius: 0 var(--radius) var(--radius) 0;
  transition: background var(--t-fast), border-color var(--t-fast);
  line-height: var(--leading-relaxed);
  cursor: pointer;
}
.transcript-seg:hover { background: var(--surface-2); }
.transcript-seg.active {
  background: var(--color-brand-50);
  border-left-color: var(--primary);
}
[data-theme="dark"] .transcript-seg.active {
  background: rgba(59,130,246,.08);
}
.ts-time {
  flex-shrink: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--primary);
  font-variant-numeric: tabular-nums;
  min-width: 44px;
  padding-top: 2px;
}
.ts-text {
  font-size: var(--text-base);
  color: var(--text);
  line-height: var(--leading-relaxed);
}
```

- [ ] **Step 2: Update `renderTranscript()` in `static/js/detail.js`** to use the new `.ts-time` / `.ts-text` structure instead of the old `.ts-link` inside text approach:

```javascript
// In renderTranscript(), replace segment HTML generation:
function _segHtml(seg) {
  const sec  = seg.start ?? 0;
  const mins = String(Math.floor(sec / 60)).padStart(2, '0');
  const secs = String(Math.floor(sec % 60)).padStart(2, '0');
  return `<div class="transcript-seg" data-sec="${sec}" onclick="seekTo(${sec})">
    <span class="ts-time">${mins}:${secs}</span>
    <span class="ts-text">${seg.text ?? ''}</span>
  </div>`;
}
```

---

### Task 14: Three-tier responsive breakpoints

**Files:**
- Modify: `static/css/style.css`
- Modify: `templates/index.html`
- Modify: `templates/detail.html`

- [ ] **Step 0: Add hamburger button to both templates**

The hamburger is only visible on ≤768px screens (hidden via CSS on desktop). Insert it as the **first child of `<main>`** (or just before the main content wrapper) in both `templates/index.html` and `templates/detail.html`:

```html
<button class="ham-btn" id="ham-btn" aria-label="開啟選單" aria-expanded="false"
        onclick="window.openMobileSidebar()">
  <i data-lucide="menu" aria-hidden="true"></i>
</button>
```

Add `openMobileSidebar()` to `static/js/theme.js` inside the IIFE body (after the existing `toggleSidebar` definition):

```javascript
window.openMobileSidebar = function () {
  const sidebar = document.getElementById('sidebar');
  const btn     = document.getElementById('ham-btn');
  if (!sidebar) return;
  const isOpen = sidebar.classList.toggle('open');
  if (btn) btn.setAttribute('aria-expanded', String(isOpen));
  // Clicking outside closes sidebar
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
```

- [ ] **Step 1: Replace single `@media (max-width: 700px)` with three-tier system**

```css
/* ── Responsive ──────────────────────────────────────────────────────── */

/* Tablet landscape (≤1100px): sidebar auto-collapses */
@media (max-width: 1100px) {
  :root { --sidebar-w: var(--sidebar-w-collapsed); }
  .nav-label, .sidebar-logo-text, .sidebar-status { display: none; }
  .nav-item { justify-content: center; padding: 10px 0; }
  .sidebar-header { justify-content: center; }
}

/* Tablet portrait (≤768px): sidebar hidden, hamburger */
@media (max-width: 768px) {
  .sidebar {
    position: fixed;
    left: -100%;
    z-index: 500;
    transition: left var(--t-slow);
    box-shadow: var(--shadow-lg);
  }
  .sidebar.open { left: 0; }
  .main-content { margin-left: 0; }
  .detail-grid { grid-template-columns: 1fr; }
  .detail-col-right { position: static; }
  .ham-btn { display: flex; }
}

/* Ham button: hidden on desktop, flex on mobile */
.ham-btn {
  display: none;
  align-items: center;
  justify-content: center;
  width: 40px; height: 40px;
  background: none;
  border: none;
  cursor: pointer;
  border-radius: var(--radius-sm);
  color: var(--text-2);
  margin-bottom: 8px;
}
.ham-btn:hover { background: var(--surface-2); }

/* Mobile (≤480px): full-width, stacked */
@media (max-width: 480px) {
  .card { padding: 14px 16px; }
  .tab-btn { padding: 8px 10px; font-size: var(--text-sm); }
  .modal-box { margin: 16px; border-radius: var(--radius); }
}
```

- [ ] **Step 2: Run tests**

```bash
pytest --tb=short -q
# Expected: 325 passed
```

- [ ] **Step 3: Commit**

```bash
git add static/css/style.css static/js/theme.js templates/index.html templates/detail.html
git commit -m "feat(ui): transcript speaker layout + three-tier responsive breakpoints

- Transcript: fixed-width timestamp column + full-segment active highlight
- Responsive: 1100px (sidebar collapse) / 768px (sidebar hide) / 480px (mobile stack)
- Mobile: hamburger button toggles sidebar.open with outside-click handler
- Transcript renderTranscript() updated to ts-time/ts-text structure

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Chunk 7: Final Polish + PR

**Files:**
- Modify: `static/css/style.css` — accessibility focus rings, button layer system
- Modify: `templates/index.html` — skip link, ARIA improvements

---

### Task 15: Accessibility polish

**Files:**
- Modify: `static/css/style.css`
- Modify: `templates/index.html`
- Modify: `templates/detail.html`

- [ ] **Step 1: Add skip link to both templates** (inside `<body>`, first element):

```html
<a href="#main-content" class="skip-link">跳至主要內容</a>
```

- [ ] **Step 2: Add `id="main-content"` to the `<main>` wrapper in both templates**

- [ ] **Step 3: Add `aria-hidden="true"` to all decorative Lucide icon elements in both templates**

All `<i data-lucide="...">` tags that are decorative (next to visible text, not standalone) must have `aria-hidden="true"`. Find them all:

```bash
grep -n 'data-lucide' templates/index.html templates/detail.html
```

For each icon that is decorative (accompanied by visible text label), add `aria-hidden="true"`. Icons that are the sole content of a button already have `aria-label` on the button — those still need `aria-hidden` on the `<i>` itself so screen readers don't read the SVG title.

Ensure every icon-only button (sidebar-toggle, theme-toggle, toast-close, hamburger) has a descriptive `aria-label` on the `<button>` element. Example:

```html
<button class="icon-btn" onclick="toggleSidebar()" aria-label="收合側欄">
  <i data-lucide="panel-left-close" aria-hidden="true"></i>
</button>
```

- [ ] **Step 4: Add focus ring CSS**

```css
/* ── Focus Accessibility ─────────────────────────────────────────────── */
.skip-link {
  position: absolute;
  top: -100px;
  left: 16px;
  padding: 8px 16px;
  background: var(--primary);
  color: #fff;
  border-radius: var(--radius);
  font-size: var(--text-base);
  font-weight: 600;
  z-index: 9999;
  transition: top .1s;
}
.skip-link:focus { top: 16px; }

:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}
button:focus-visible,
a:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}
```

- [ ] **Step 5: Run full test suite**

```bash
pytest --tb=short -q
# Expected: 325 passed (2 pre-existing Starlette template test failures OK)
```

- [ ] **Step 6: Final commit**

```bash
git add static/css/style.css templates/index.html templates/detail.html
git commit -m "feat(ui): accessibility — skip link, focus rings, decorative icon aria-hidden

- Skip navigation link (visually hidden, visible on focus)
- :focus-visible ring via --focus-ring token for all interactive elements
- aria-hidden='true' on all decorative Lucide <i> elements
- aria-label on all icon-only buttons (sidebar-toggle, theme-toggle, ham-btn, toast-close)

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 16: Create PR

- [ ] **Step 1: Push branch**

```bash
git push origin ui/ux-redesign
```

- [ ] **Step 2: Create PR**

```bash
gh pr create --repo hwchiu/mochia \
  --title "feat(ui): complete UI/UX redesign — Inter, tokens, dark mode, Lucide, collapsible sidebar" \
  --body "## UI/UX Redesign

Spec: docs/superpowers/specs/2026-03-14-ui-ux-redesign-design.md

### Changes
- **Design tokens**: theme.css with 8 semantic colour tokens (light + dark)
- **Typography**: Inter font, 6-level type scale (down from 14 sizes)
- **Icons**: emoji → Lucide Icons SVG (sidebar, toasts, tabs, progress)
- **Sidebar**: collapsible (240 ↔ 60px), state persisted in localStorage
- **Dark mode**: [data-theme=dark] CSS variable overrides, toggle button
- **Toast**: type-coloured left border + icon, slide-in/out animation
- **Badge**: colour dot style, softer backgrounds
- **Tabs**: underline style, no filled background
- **Cards**: hover shadow + translateY(-1px) lift
- **Progress steps**: numbered circles, green connectors, blue pulse
- **Skeleton loaders**: table rows + tab content panels
- **Transcript**: fixed-width timestamp column, full-segment highlight
- **Responsive**: 3-tier breakpoints (1100/768/480px)
- **Accessibility**: skip link, focus rings, ARIA labels
" --base main
```

- [ ] **Step 3: Monitor CI — check all jobs green**

```bash
sleep 90 && gh run list --repo hwchiu/mochia --branch ui/ux-redesign --limit 1
```

- [ ] **Step 4: Merge if CI passes**

```bash
gh pr merge --repo hwchiu/mochia --squash --delete-branch
```

---

## Quick Reference

| Chunk | Tasks | Key files |
|-------|-------|-----------|
| 1 - Token foundation | 1–2 | `theme.css`, `style.css`, both templates |
| 2 - Sidebar | 3–5 | `theme.js`, `index.html`, `detail.html`, `style.css` |
| 3 - Toast/Badge/Tab | 6–8 | `common.js`, `style.css` |
| 4 - Card/Progress | 9–10 | `style.css`, `detail.js` |
| 5 - Dark/Skeleton | 11–12 | `style.css`, `index.js`, `detail.js` |
| 6 - Transcript/Responsive | 13–14 | `style.css`, `detail.js` |
| 7 - A11y + PR | 15–16 | both templates, `style.css` |
