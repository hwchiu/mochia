// ─── Toast ───
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

// ─── API helpers ───
async function api(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
  return data;
}

// ─── Badge helper ───
function badge(status) {
  const map = {
    pending:    ['pending',    '等待中'],
    queued:     ['queued',     '排隊中'],
    processing: ['processing', '分析中'],
    completed:  ['completed',  '已完成'],
    failed:     ['failed',     '失敗'],
  };
  const [cls, label] = map[status] || ['pending', status];
  return `<span class="badge badge-${cls}"><span class="badge-dot"></span>${label}</span>`;
}

function fmtSize(b) {
  if (!b) return "—";
  if (b < 1024) return b + " B";
  if (b < 1048576) return (b / 1024).toFixed(1) + " KB";
  if (b < 1073741824) return (b / 1048576).toFixed(1) + " MB";
  return (b / 1073741824).toFixed(2) + " GB";
}
function fmtDur(s) {
  if (!s) return "—";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60);
  return h > 0 ? `${h}h${String(m).padStart(2,"0")}m` : `${m}m${String(sec).padStart(2,"0")}s`;
}
