// ─── Sidebar Navigation ───────────────────────────────────────────────────────
let currentSection = "analysis";

function showSection(name) {
  currentSection = name;
  document.querySelectorAll(".app-section").forEach(s => {
    s.classList.toggle("active", s.id === `section-${name}`);
    s.classList.toggle("hidden", s.id !== `section-${name}`);
  });
  document.querySelectorAll(".nav-item").forEach(a => {
    a.classList.toggle("active", a.dataset.section === name);
  });
  if (name === "review") { reviewPage = 0; loadReview(); loadLabelFilters(); }
  if (name === "labels") loadLabelsPage();
}

document.querySelectorAll(".nav-item").forEach(a => {
  a.addEventListener("click", e => {
    e.preventDefault();
    showSection(a.dataset.section);
  });
});

// ─── Stats (sidebar) ─────────────────────────────────────────────────────────
let pollTimer = null;

async function loadStats() {
  try {
    const d = await api("GET", "/api/batch/status");
    const v = d.videos;
    const total = Object.values(v).reduce((a, b) => a + b, 0);
    document.getElementById("sb-stat-total").textContent = total;
    document.getElementById("sb-stat-pending").textContent = v.pending || 0;
    document.getElementById("sb-stat-queued").textContent = v.queued || 0;
    document.getElementById("sb-stat-processing").textContent = v.processing || 0;
    document.getElementById("sb-stat-completed").textContent = v.completed || 0;
    document.getElementById("sb-stat-failed").textContent = v.failed || 0;

    const t = d.tasks;
    document.getElementById("queue-info").textContent =
      `佇列：等待 ${t.pending || 0} | 處理中 ${t.processing || 0} | 完成 ${t.done || 0} | 失敗 ${t.failed || 0}`;

    const pct = total > 0 ? Math.round(((v.completed || 0) / total) * 100) : 0;
    document.getElementById("progress-bar").style.width = pct + "%";
    document.getElementById("progress-pct").textContent = pct + "%";
  } catch (e) {
    console.error("loadStats error", e);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 分析中心
// ═══════════════════════════════════════════════════════════════════════════════
let currentPage = 0;
const PAGE_SIZE = 50;
let filterStatus = "";
let filterSource = "";

async function loadVideos() {
  try {
    const params = new URLSearchParams({ skip: currentPage * PAGE_SIZE, limit: PAGE_SIZE });
    if (filterStatus) params.set("status", filterStatus);
    if (filterSource) params.set("source", filterSource);
    const d = await api("GET", `/api/videos/?${params}`);
    renderTable(d.items);
    renderPagination(d.total);
  } catch (e) {
    toast("載入影片列表失敗: " + e.message, "error");
  }
}

function renderTable(videos) {
  const tbody = document.getElementById("video-tbody");
  if (!videos.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--muted);padding:32px">（無影片）</td></tr>`;
    return;
  }
  tbody.innerHTML = videos.map(v => `
    <tr>
      <td><input type="checkbox" class="row-check" data-id="${v.id}" data-status="${v.status}"></td>
      <td class="name" title="${v.original_filename}">
        <a href="/video/${v.id}">${v.original_filename}</a>
      </td>
      <td>${badge(v.status)}</td>
      <td>${fmtSize(v.file_size)}</td>
      <td>${fmtDur(v.duration)}</td>
      <td><span class="badge badge-pending" style="text-transform:none;letter-spacing:0">${v.source === "local_scan" ? "本地" : "上傳"}</span></td>
      <td>
        ${v.status === "pending" || v.status === "failed"
          ? `<button class="btn btn-sm btn-primary" onclick="queueOne('${v.id}')">加入佇列</button>`
          : ""}
        ${v.status === "completed"
          ? `<a class="btn btn-sm btn-ghost" href="/video/${v.id}">查看結果</a>`
          : ""}
      </td>
    </tr>
  `).join("");
}

function renderPagination(total) {
  const pages = Math.ceil(total / PAGE_SIZE);
  const el = document.getElementById("pagination");
  if (pages <= 1) { el.innerHTML = ""; return; }
  let html = `<button class="btn btn-sm btn-ghost" onclick="goPage(${currentPage - 1})" ${currentPage === 0 ? "disabled" : ""}>‹</button>`;
  for (let i = 0; i < pages; i++) {
    html += `<button class="btn btn-sm btn-ghost ${i === currentPage ? "current" : ""}" onclick="goPage(${i})">${i + 1}</button>`;
  }
  html += `<button class="btn btn-sm btn-ghost" onclick="goPage(${currentPage + 1})" ${currentPage >= pages - 1 ? "disabled" : ""}>›</button>`;
  el.innerHTML = html;
}

function goPage(p) { currentPage = p; loadVideos(); }

document.getElementById("filter-status").addEventListener("change", e => { filterStatus = e.target.value; currentPage = 0; loadVideos(); });
document.getElementById("filter-source").addEventListener("change", e => { filterSource = e.target.value; currentPage = 0; loadVideos(); });
document.getElementById("select-all").addEventListener("change", e => {
  document.querySelectorAll(".row-check").forEach(cb => cb.checked = e.target.checked);
});

function getSelected() {
  return [...document.querySelectorAll(".row-check:checked")].map(cb => cb.dataset.id);
}

document.getElementById("btn-queue-selected").addEventListener("click", async () => {
  const ids = getSelected();
  if (!ids.length) { toast("請先選擇影片", "info"); return; }
  let ok = 0;
  for (const id of ids) { try { await api("POST", `/api/analysis/${id}/queue`); ok++; } catch {} }
  toast(`已加入佇列 ${ok} 支`, "success");
  loadStats(); loadVideos();
});

document.getElementById("btn-queue-all").addEventListener("click", async () => {
  if (!confirm("將所有「待處理」影片加入分析佇列？")) return;
  try {
    const d = await api("POST", "/api/batch/queue-all");
    toast(d.message, "success");
    loadStats(); loadVideos();
  } catch (e) { toast("操作失敗: " + e.message, "error"); }
});

document.getElementById("btn-retry-failed").addEventListener("click", async () => {
  try {
    const d = await api("POST", "/api/batch/retry-failed");
    toast(d.message, "success");
    loadStats(); loadVideos();
  } catch (e) { toast("操作失敗: " + e.message, "error"); }
});

document.getElementById("btn-cancel-queue").addEventListener("click", async () => {
  if (!confirm("取消所有等待中的任務？")) return;
  try {
    const d = await api("POST", "/api/batch/cancel-all");
    toast(d.message, "success");
    loadStats(); loadVideos();
  } catch (e) { toast("操作失敗: " + e.message, "error"); }
});

async function queueOne(id) {
  try {
    const d = await api("POST", `/api/analysis/${id}/queue`);
    toast(d.message, "success");
    loadStats(); loadVideos();
  } catch (e) { toast("操作失敗: " + e.message, "error"); }
}

// ─── Scan (native folder picker) ───
document.getElementById("btn-scan").addEventListener("click", async () => {
  const btn = document.getElementById("btn-scan");
  btn.disabled = true; btn.textContent = "請選擇目錄...";
  try {
    const picked = await api("GET", "/api/batch/pick-directory");
    if (picked.cancelled || !picked.path) {
      return;  // 使用者取消，靜默忽略
    }
    btn.textContent = "掃描中...";
    const d = await api("POST", `/api/batch/scan?path=${encodeURIComponent(picked.path)}`);
    toast(`掃描完成：新登錄 ${d.registered} 支，跳過 ${d.skipped} 支`, "success");
    loadStats(); loadVideos();
  } catch (e) {
    toast("掃描失敗: " + e.message, "error");
  } finally {
    btn.disabled = false; btn.textContent = "📁 掃描目錄";
  }
});

// ═══════════════════════════════════════════════════════════════════════════════
// 複習中心
// ═══════════════════════════════════════════════════════════════════════════════
let reviewPage = 0;
const REVIEW_PAGE_SIZE = 12;
let activeFilterLabels = new Set();  // label names (AND logic)
let reviewSearchQuery = "";
let reviewSearchTimer = null;

async function loadLabelFilters() {
  try {
    const labels = await api("GET", "/api/labels/");
    const el = document.getElementById("label-filter-list");
    if (!labels.length) {
      el.innerHTML = `<div style="color:var(--muted);font-size:13px;padding:8px 0">尚無標籤</div>`;
      return;
    }
    el.innerHTML = labels.map(l => `
      <div class="label-filter-item ${activeFilterLabels.has(l.name) ? "active" : ""}"
           data-name="${escapeHtml(l.name)}" onclick="toggleLabelFilter('${escapeHtml(l.name)}')">
        <span class="label-dot" style="background:${l.color}"></span>
        <span class="label-filter-name">${escapeHtml(l.name)}</span>
        <span class="label-filter-count">${l.video_count}</span>
      </div>
    `).join("");
  } catch (e) {
    console.error("loadLabelFilters error", e);
  }
}

function toggleLabelFilter(name) {
  if (activeFilterLabels.has(name)) {
    activeFilterLabels.delete(name);
  } else {
    activeFilterLabels.add(name);
  }
  reviewPage = 0;
  loadLabelFilters();
  loadReview();
}

document.getElementById("btn-clear-filter").addEventListener("click", () => {
  activeFilterLabels.clear();
  reviewPage = 0;
  loadLabelFilters();
  loadReview();
});

document.getElementById("review-search").addEventListener("input", e => {
  clearTimeout(reviewSearchTimer);
  reviewSearchTimer = setTimeout(() => {
    reviewSearchQuery = e.target.value.trim();
    reviewPage = 0;
    loadReview();
  }, 300);
});

async function loadReview() {
  const grid = document.getElementById("review-cards-grid");
  grid.innerHTML = `<div style="color:var(--muted);text-align:center;padding:40px">載入中...</div>`;
  try {
    const params = new URLSearchParams({
      status: "completed",
      skip: reviewPage * REVIEW_PAGE_SIZE,
      limit: REVIEW_PAGE_SIZE,
    });
    if (activeFilterLabels.size > 0) {
      params.set("labels", [...activeFilterLabels].join(","));
    }
    const d = await api("GET", `/api/videos/?${params}`);

    // Client-side search filter
    let items = d.items;
    if (reviewSearchQuery) {
      const q = reviewSearchQuery.toLowerCase();
      items = items.filter(v => v.original_filename.toLowerCase().includes(q));
    }

    if (!items.length) {
      grid.innerHTML = `<div style="color:var(--muted);text-align:center;padding:60px;font-size:15px">（無已完成的影片）</div>`;
      document.getElementById("review-pagination").innerHTML = "";
      return;
    }

    grid.innerHTML = items.map(v => renderVideoCard(v)).join("");
    renderReviewPagination(d.total);
  } catch (e) {
    grid.innerHTML = `<div style="color:var(--danger);text-align:center;padding:40px">載入失敗: ${e.message}</div>`;
  }
}

function renderVideoCard(v) {
  const labels = (v.labels || []).map(l =>
    `<span class="label-tag" style="background:${l.color}20;color:${l.color};border-color:${l.color}40">${escapeHtml(l.name)}</span>`
  ).join("");

  return `
    <div class="video-card" onclick="location.href='/video/${v.id}'">
      <div class="video-card-title" title="${escapeHtml(v.original_filename)}">${escapeHtml(v.original_filename)}</div>
      <div class="video-card-meta">
        <span>${fmtDur(v.duration)}</span>
        <span>${fmtSize(v.file_size)}</span>
        <span>${v.source === "local_scan" ? "本地" : "上傳"}</span>
      </div>
      <div class="video-card-labels">${labels || '<span style="color:var(--muted);font-size:12px">無標籤</span>'}</div>
    </div>
  `;
}

function renderReviewPagination(total) {
  const pages = Math.ceil(total / REVIEW_PAGE_SIZE);
  const el = document.getElementById("review-pagination");
  if (pages <= 1) { el.innerHTML = ""; return; }
  let html = `<button class="btn btn-sm btn-ghost" onclick="goReviewPage(${reviewPage - 1})" ${reviewPage === 0 ? "disabled" : ""}>‹</button>`;
  for (let i = 0; i < Math.min(pages, 10); i++) {
    html += `<button class="btn btn-sm btn-ghost ${i === reviewPage ? "current" : ""}" onclick="goReviewPage(${i})">${i + 1}</button>`;
  }
  if (pages > 10) html += `<span style="padding:0 8px;color:var(--muted)">... ${pages} 頁</span>`;
  html += `<button class="btn btn-sm btn-ghost" onclick="goReviewPage(${reviewPage + 1})" ${reviewPage >= pages - 1 ? "disabled" : ""}>›</button>`;
  el.innerHTML = html;
}

function goReviewPage(p) { reviewPage = p; loadReview(); }

// ═══════════════════════════════════════════════════════════════════════════════
// 標籤管理
// ═══════════════════════════════════════════════════════════════════════════════
async function loadLabelsPage() {
  try {
    const labels = await api("GET", "/api/labels/");
    const el = document.getElementById("labels-grid");
    if (!labels.length) {
      el.innerHTML = `<div style="color:var(--muted);padding:20px">尚無標籤，請在上方建立</div>`;
      return;
    }
    el.innerHTML = `<div class="labels-manage-grid">${labels.map(l => `
      <div class="label-manage-item">
        <span class="label-color-swatch" style="background:${l.color}"></span>
        <span class="label-manage-name">${escapeHtml(l.name)}</span>
        <span class="label-manage-count">${l.video_count} 支影片</span>
        <button class="btn btn-ghost btn-xs" style="color:var(--danger)" onclick="deleteLabel('${l.id}', '${escapeHtml(l.name)}')">刪除</button>
      </div>
    `).join("")}</div>`;
  } catch (e) {
    toast("載入標籤失敗: " + e.message, "error");
  }
}

document.getElementById("btn-create-label").addEventListener("click", async () => {
  const input = document.getElementById("new-label-input");
  const name = input.value.trim();
  if (!name) { toast("請輸入標籤名稱", "info"); return; }
  try {
    const r = await api("POST", "/api/labels/", { name });
    if (r.created) {
      toast(`標籤「${name}」已建立`, "success");
    } else {
      toast(`標籤「${name}」已存在`, "info");
    }
    input.value = "";
    loadLabelsPage();
  } catch (e) { toast("建立失敗: " + e.message, "error"); }
});

async function deleteLabel(id, name) {
  if (!confirm(`確定要刪除標籤「${name}」？這將移除所有影片的此標籤。`)) return;
  try {
    await api("DELETE", `/api/labels/${id}`);
    toast(`標籤「${name}」已刪除`, "success");
    loadLabelsPage();
  } catch (e) { toast("刪除失敗: " + e.message, "error"); }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function escapeHtml(str) {
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ─── Auto-refresh ─────────────────────────────────────────────────────────────
function startPoll() {
  pollTimer = setInterval(() => {
    loadStats();
    if (currentSection === "analysis") loadVideos();
    if (currentSection === "review") loadReview();
  }, 8000);
}

// ─── Init ─────────────────────────────────────────────────────────────────────
loadStats();
loadVideos();
startPoll();

// 從 URL ?section= 恢復選中的頁面（從 detail 頁返回時）
const _initSection = new URLSearchParams(window.location.search).get("section");
if (_initSection) showSection(_initSection);
