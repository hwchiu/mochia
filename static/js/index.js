// ─── Sidebar Navigation ───────────────────────────────────────────────────────
let currentSection = "analysis";
let currentMode = "review";

function showSection(name) {
  currentSection = name;
  document.querySelectorAll(".app-section").forEach(s => {
    s.classList.toggle("active", s.id === `section-${name}`);
    s.classList.toggle("hidden", s.id !== `section-${name}`);
  });
  document.querySelectorAll(".nav-item").forEach(a => {
    a.classList.toggle("active", a.dataset.section === name);
  });
  if (name === "review") { reviewPage = 0; loadReview(); loadLabelFilters(); loadDueReviews(); loadWrongAnswers(); }
  if (name === "labels") loadLabelsPage();
  if (name === "search") document.getElementById("fts-input").focus();
  if (name === "stats") loadStatsPage();
  if (name === "wiki-home") loadWikiHome();
  if (name === "wiki-pages") loadWikiPages();
  // Update hash for wiki sections (but not wiki-topics — loadWikiTopic manages it)
  if (name.startsWith("wiki-") && name !== "wiki-topics") {
    history.replaceState(null, "", `#${name}`);
  }
}

function switchMode(mode) {
  currentMode = mode;
  const reviewNav = document.getElementById("review-nav");
  const wikiNav = document.getElementById("wiki-nav");
  const tabReview = document.getElementById("mode-tab-review");
  const tabWiki = document.getElementById("mode-tab-wiki");

  if (mode === "wiki") {
    reviewNav.classList.add("hidden");
    wikiNav.classList.remove("hidden");
    tabReview.classList.remove("active");
    tabWiki.classList.add("active");
    showSection("wiki-home");
  } else {
    wikiNav.classList.add("hidden");
    reviewNav.classList.remove("hidden");
    tabWiki.classList.remove("active");
    tabReview.classList.add("active");
    showSection("analysis");
  }
  try { localStorage.setItem("sidebarMode", mode); } catch (_) {}
}

document.getElementById("review-nav").querySelectorAll(".nav-item").forEach(a => {
  a.addEventListener("click", e => {
    e.preventDefault();
    showSection(a.dataset.section);
  });
});

document.getElementById("wiki-nav").querySelectorAll(".nav-item").forEach(a => {
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

    // 今日待複習
    try {
      const rs = await api("GET", "/api/review/stats");
      document.getElementById("sb-stat-due").textContent = rs.due_today || 0;
    } catch(_) {}

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
let filterSearch = "";
let _searchDebounceTimer = null;

function _tableSkeletonHtml(rows = 6) {
  return Array.from({ length: rows }, () =>
    `<tr>${Array.from({ length: 6 }, () =>
      `<td><div class="skeleton skel-text"></div></td>`
    ).join('')}</tr>`
  ).join('');
}

async function loadVideos() {
  const tbody = document.querySelector('#video-table tbody');
  if (tbody) tbody.innerHTML = _tableSkeletonHtml();
  try {
    const params = new URLSearchParams({ skip: currentPage * PAGE_SIZE, limit: PAGE_SIZE });
    if (filterStatus) params.set("status", filterStatus);
    if (filterSource) params.set("source", filterSource);
    if (filterSearch) params.set("search", filterSearch);
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
          ? `<button class="btn btn-sm btn-primary" onclick="queueOne('${v.id}', this)">加入佇列</button>`
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

  const cur = currentPage;
  // 計算要顯示的頁碼集合（首尾各1頁 + 當前頁 ±2）
  const show = new Set([0, pages - 1]);
  for (let i = Math.max(0, cur - 2); i <= Math.min(pages - 1, cur + 2); i++) show.add(i);

  let html = `<button class="btn btn-sm btn-ghost" onclick="goPage(${cur - 1})" ${cur === 0 ? "disabled" : ""}>‹</button>`;
  let prev = -1;
  for (const i of [...show].sort((a, b) => a - b)) {
    if (i - prev > 1) html += `<span class="pag-ellipsis">…</span>`;
    html += `<button class="btn btn-sm btn-ghost ${i === cur ? "current" : ""}" onclick="goPage(${i})">${i + 1}</button>`;
    prev = i;
  }
  html += `<button class="btn btn-sm btn-ghost" onclick="goPage(${cur + 1})" ${cur >= pages - 1 ? "disabled" : ""}>›</button>`;
  html += `<span class="pag-info">第 ${cur + 1} / ${pages} 頁，共 ${total} 支</span>`;
  if (pages > 2) {
    html += `
    <span style="margin-left:8px;display:inline-flex;align-items:center;gap:4px;font-size:13px">
      跳至
      <input type="number" id="page-jump-input" min="1" max="${pages}"
             style="width:50px;padding:4px 6px;border:1px solid var(--border,#ddd);border-radius:4px;font-size:13px;text-align:center"
             onkeydown="if(event.key==='Enter') jumpToPage(${pages})">
      <span style="color:var(--muted)">/ ${pages}</span>
      <button class="btn btn-ghost btn-sm" onclick="jumpToPage(${pages})">前往</button>
    </span>`;
  }
  el.innerHTML = html;
}

function goPage(p) { currentPage = p; loadVideos(); }

function jumpToPage(totalPages) {
  const input = document.getElementById("page-jump-input");
  if (!input) return;
  const page = parseInt(input.value, 10);
  if (isNaN(page) || page < 1 || page > totalPages) {
    toast(`請輸入 1 到 ${totalPages} 之間的頁碼`, "warning");
    return;
  }
  currentPage = page - 1;
  loadVideos();
}

document.getElementById("filter-status").addEventListener("change", e => { filterStatus = e.target.value; currentPage = 0; loadVideos(); });
document.getElementById("filter-source").addEventListener("change", e => { filterSource = e.target.value; currentPage = 0; loadVideos(); });
document.getElementById("filter-search").addEventListener("input", e => {
  clearTimeout(_searchDebounceTimer);
  _searchDebounceTimer = setTimeout(() => { filterSearch = e.target.value.trim(); currentPage = 0; loadVideos(); }, 300);
});
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

async function queueOne(id, btnEl) {
  if (btnEl) { btnEl.disabled = true; btnEl.textContent = "..."; }
  try {
    await api("POST", `/api/analysis/${id}/queue`);
    toast("已加入佇列", "success");
    loadVideos();
  } catch (e) {
    toast("加入佇列失敗: " + e.message, "error");
  } finally {
    if (btnEl) { btnEl.disabled = false; btnEl.textContent = "加入佇列"; }
  }
}

// ─── Scan Modal ───────────────────────────────────────────────────────────────
const scanModal     = document.getElementById("scan-modal");
const scanPathInput = document.getElementById("scan-path-input");

function openScanModal() {
  scanModal.style.display = "flex";
  scanPathInput.value = "";
  loadVideoSources();
}

function closeScanModal() {
  scanModal.style.display = "none";
}

async function loadVideoSources() {
  const list = document.getElementById("scan-sources-list");
  list.innerHTML = '<div class="loading-text">偵測中...</div>';
  try {
    const { sources } = await api("GET", "/api/batch/sources");
    if (!sources.length) {
      list.innerHTML = '<div class="scan-source-empty">⚠️ 尚未掛載任何影片來源。<br>請在 .env 設定 VIDEO_DIR_1 後重啟容器。</div>';
      return;
    }
    // 立即渲染卡片（video_count 先顯示 "計算中..."）
    list.innerHTML = sources.map(s => `
      <div class="scan-source-card" id="source-card-${s.slot}" data-path="${s.container_path}"
           onclick="selectSource(this)">
        <span class="scan-source-icon">📂</span>
        <div class="scan-source-info">
          <div style="font-weight:600;font-size:14px">${s.display_name}</div>
          <div class="scan-source-path">${s.container_path}</div>
        </div>
        <span class="scan-source-count" id="count-${s.slot}">計算中...</span>
      </div>
    `).join("");
    // 非同步逐一載入每個來源的影片數量（不阻塞 UI）
    sources.forEach(s => loadSourceCount(s.slot));
  } catch {
    list.innerHTML = '<div class="scan-source-empty">無法取得來源資訊</div>';
  }
}

async function loadSourceCount(slot) {
  try {
    const { video_count } = await api("GET", `/api/batch/sources/${slot}/count`);
    const el = document.getElementById(`count-${slot}`);
    if (el) el.textContent = `${video_count} 支影片`;
  } catch {
    const el = document.getElementById(`count-${slot}`);
    if (el) el.textContent = "無法取得";
  }
}

function selectSource(card) {
  document.querySelectorAll(".scan-source-card").forEach(c => c.classList.remove("selected"));
  card.classList.add("selected");
  scanPathInput.value = card.dataset.path;
}

async function runScan() {
  const path = scanPathInput.value.trim();
  if (!path) { toast("請選擇或輸入目錄路徑", "error"); return; }

  const btn = document.getElementById("scan-confirm-btn");
  const progressBox = document.getElementById("scan-progress");
  const statsEl = document.getElementById("scan-progress-stats");
  const dirEl = document.getElementById("scan-progress-dir");

  btn.disabled = true; btn.textContent = "掃描中...";
  progressBox.style.display = "block";
  statsEl.textContent = "啟動掃描...";
  dirEl.textContent = "";

  try {
    await api("POST", `/api/batch/scan?path=${encodeURIComponent(path)}`);
    await _pollManualScan(statsEl, dirEl);
  } catch (e) {
    toast("掃描失敗: " + e.message, "error");
    progressBox.style.display = "none";
    btn.disabled = false; btn.textContent = "掃描";
  }
}

function _pollManualScan(statsEl, dirEl) {
  return new Promise((resolve) => {
    const tid = setInterval(async () => {
      try {
        const s = await api("GET", "/api/batch/manual-scan-status");
        if (s.status === "running" || s.status === "done") {
          statsEl.textContent =
            `已掃描 ${s.files_scanned.toLocaleString()} 個檔案` +
            ` ／ 發現 ${s.files_found} 支影片` +
            ` ／ 新登錄 ${s.registered} 支` +
            ` ／ 跳過 ${s.skipped} 支`;
          if (s.current_dir) dirEl.textContent = s.current_dir;
        }
        if (s.status === "done") {
          clearInterval(tid);
          document.getElementById("scan-progress").style.display = "none";
          const btn = document.getElementById("scan-confirm-btn");
          btn.disabled = false; btn.textContent = "掃描";
          toast(`掃描完成：新登錄 ${s.registered} 支，跳過 ${s.skipped} 支`, "success");
          closeScanModal();
          loadStats(); loadVideos();
          resolve();
        } else if (s.status === "error") {
          clearInterval(tid);
          document.getElementById("scan-progress").style.display = "none";
          const btn = document.getElementById("scan-confirm-btn");
          btn.disabled = false; btn.textContent = "掃描";
          toast("掃描失敗：" + (s.error || "未知錯誤"), "error");
          resolve();
        }
      } catch {
        clearInterval(tid);
        resolve();
      }
    }, 800);
  });
}

document.getElementById("btn-scan").addEventListener("click", openScanModal);
document.getElementById("scan-modal-close").addEventListener("click", closeScanModal);
document.getElementById("scan-confirm-btn").addEventListener("click", runScan);
document.getElementById("scan-modal").addEventListener("click", e => {
  if (e.target === scanModal) closeScanModal();
});
scanPathInput.addEventListener("keydown", e => { if (e.key === "Enter") runScan(); });

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
    // 一次抓足夠多筆，客戶端排序後再分頁（避免後端排序限制）
    const params = new URLSearchParams({
      status: "completed",
      skip: 0,
      limit: 500,
    });
    if (activeFilterLabels.size > 0) {
      params.set("labels", [...activeFilterLabels].join(","));
    }
    const d = await api("GET", `/api/videos/?${params}`);

    // 客戶端搜尋過濾
    let items = d.items;
    if (reviewSearchQuery) {
      const q = reviewSearchQuery.toLowerCase();
      items = items.filter(v => (v.original_filename || "").toLowerCase().includes(q));
    }

    // 客戶端排序
    const sortEl = document.getElementById("review-sort");
    const sortMode = sortEl ? sortEl.value : "due";
    const now = new Date();
    items.sort((a, b) => {
      if (sortMode === "due") {
        // 未複習 → 到期 → 未來排程（越近越前）
        const aOverdue = !a.sr_next_review_at || new Date(a.sr_next_review_at) <= now;
        const bOverdue = !b.sr_next_review_at || new Date(b.sr_next_review_at) <= now;
        if (aOverdue !== bOverdue) return aOverdue ? -1 : 1;
        const aT = a.sr_next_review_at ? new Date(a.sr_next_review_at) : new Date(0);
        const bT = b.sr_next_review_at ? new Date(b.sr_next_review_at) : new Date(0);
        return aT - bT;
      } else if (sortMode === "never") {
        if ((a.review_count === 0) !== (b.review_count === 0))
          return a.review_count === 0 ? -1 : 1;
        return (a.review_count || 0) - (b.review_count || 0);
      } else if (sortMode === "count_asc") {
        return (a.review_count || 0) - (b.review_count || 0);
      } else if (sortMode === "count_desc") {
        return (b.review_count || 0) - (a.review_count || 0);
      } else if (sortMode === "name") {
        return (a.original_filename || "").localeCompare(b.original_filename || "", "zh-TW");
      }
      return 0;
    });

    if (!items.length) {
      grid.innerHTML = `<div style="color:var(--muted);text-align:center;padding:60px;font-size:15px">（無已完成的影片）</div>`;
      document.getElementById("review-pagination").innerHTML = "";
      return;
    }

    // 分頁切割
    const total = items.length;
    const pageItems = items.slice(reviewPage * REVIEW_PAGE_SIZE, (reviewPage + 1) * REVIEW_PAGE_SIZE);
    grid.innerHTML = pageItems.map(v => renderVideoCard(v)).join("");
    renderReviewPagination(total);
  } catch (e) {
    grid.innerHTML = `<div style="color:var(--danger);text-align:center;padding:40px">載入失敗: ${e.message}</div>`;
  }
}

function renderVideoCard(v) {
  const labels = (v.labels || []).map(l =>
    `<span class="label-tag" style="background:${l.color}20;color:${l.color};border-color:${l.color}40">${escapeHtml(l.name)}</span>`
  ).join("");

  const now = new Date();
  const nextReview = v.sr_next_review_at ? new Date(v.sr_next_review_at) : null;
  const isDue = !nextReview || nextReview <= now;
  const reviewCount = v.review_count || 0;

  // 複習狀態標示
  let reviewBadge = "";
  if (reviewCount === 0) {
    reviewBadge = `<span style="background:#fef3c7;color:#d97706;border:1px solid #fbbf24;border-radius:6px;font-size:11px;padding:2px 7px;font-weight:600">未複習</span>`;
  } else if (isDue) {
    reviewBadge = `<span style="background:#fee2e2;color:#dc2626;border:1px solid #fca5a5;border-radius:6px;font-size:11px;padding:2px 7px;font-weight:600">⚡ 待複習</span>`;
  } else {
    const days = Math.ceil((nextReview - now) / 86400000);
    reviewBadge = `<span style="background:#dcfce7;color:#16a34a;border:1px solid #86efac;border-radius:6px;font-size:11px;padding:2px 7px">${days} 天後複習</span>`;
  }

  const lastReviewedText = v.last_reviewed_at
    ? `上次：${new Date(v.last_reviewed_at).toLocaleDateString("zh-TW")}`
    : "尚未複習";

  return `
    <div class="video-card" onclick="location.href='/video/${v.id}'">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:6px;margin-bottom:4px">
        <div class="video-card-title" title="${escapeHtml(v.original_filename)}" style="flex:1">${escapeHtml(v.original_filename)}</div>
        ${reviewBadge}
      </div>
      <div class="video-card-meta">
        <span>${fmtDur(v.duration)}</span>
        <span>複習 ${reviewCount} 次</span>
        <span style="color:var(--muted)">${lastReviewedText}</span>
      </div>
      <div class="video-card-labels" style="margin-top:6px">${labels || '<span style="color:var(--muted);font-size:12px">無標籤</span>'}</div>
    </div>
  `;
}

function renderReviewPagination(total) {
  const pages = Math.ceil(total / REVIEW_PAGE_SIZE);
  const el = document.getElementById("review-pagination");
  if (pages <= 1) { el.innerHTML = ""; return; }

  const cur = reviewPage;
  const show = new Set([0, pages - 1]);
  for (let i = Math.max(0, cur - 2); i <= Math.min(pages - 1, cur + 2); i++) show.add(i);

  let html = `<button class="btn btn-sm btn-ghost" onclick="goReviewPage(${cur - 1})" ${cur === 0 ? "disabled" : ""}>‹</button>`;
  let prev = -1;
  for (const i of [...show].sort((a, b) => a - b)) {
    if (i - prev > 1) html += `<span class="pag-ellipsis">…</span>`;
    html += `<button class="btn btn-sm btn-ghost ${i === cur ? "current" : ""}" onclick="goReviewPage(${i})">${i + 1}</button>`;
    prev = i;
  }
  html += `<button class="btn btn-sm btn-ghost" onclick="goReviewPage(${cur + 1})" ${cur >= pages - 1 ? "disabled" : ""}>›</button>`;
  html += `<span class="pag-info">第 ${cur + 1} / ${pages} 頁，共 ${total} 支</span>`;
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
    if (currentSection === "review") { loadReview(); loadDueReviews(); }
    if (currentSection === "stats") loadStatsPage();
  }, 8000);
}

// ─── Init ─────────────────────────────────────────────────────────────────────
loadStats();
loadVideos();
startPoll();
startAutoScanPoll();

// Restore mode from localStorage
(function initMode() {
  const saved = (() => { try { return localStorage.getItem("sidebarMode"); } catch (_) { return null; } })();
  if (saved === "wiki") {
    switchMode("wiki");
  }
})();

// 從 URL ?section= 恢復選中的頁面（從 detail 頁返回時）
const _initSection = new URLSearchParams(window.location.search).get("section");
if (_initSection) showSection(_initSection);

// Hash routing
function applyHash() {
  const h = location.hash.slice(1);
  if (!h) return;
  if (h.startsWith("wiki-topic-")) {
    switchMode("wiki");
    loadWikiTopic(h.replace("wiki-topic-", ""));
    showSection("wiki-topics");
  } else if (h.startsWith("wiki-")) {
    switchMode("wiki");
    showSection(h);
  } else {
    showSection(h);
  }
}

// ─── DOMContentLoaded: Initialize page ─────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  applyHash();
});

// ─── 鍵盤快捷鍵：按 / 跳至全文搜尋 ──────────────────────────────────────────
document.addEventListener("keydown", e => {
  const tag = (e.target.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable) return;
  if (e.key === "/" && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    showSection("search");
    setTimeout(() => document.getElementById("fts-input")?.focus(), 50);
  }
});

// ═══════════════════════════════════════════════════════════════════════════════
// 今日待複習
// ═══════════════════════════════════════════════════════════════════════════════
async function loadDueReviews() {
  const el = document.getElementById("due-cards-list");
  const badge = document.getElementById("due-count-badge");
  if (!el) return;
  try {
    const data = await api("GET", "/api/review/due?limit=10");
    badge.textContent = data.total;
    if (!data.items.length) {
      el.innerHTML = `<div style="color:var(--success,#22c55e);font-size:14px">🎉 今日複習任務全部完成！</div>`;
      return;
    }
    el.innerHTML = data.items.map(v => `
      <div style="display:flex;align-items:center;gap:10px;padding:10px 12px;background:var(--surface,#f8f9fa);border-radius:8px;border-left:3px solid var(--warning,#f59e0b)">
        <div style="flex:1;min-width:0">
          <a href="/video/${v.id}" style="font-weight:600;font-size:13px;color:var(--text);text-decoration:none;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
             title="${escapeHtml(v.filename)}">${escapeHtml(v.filename)}</a>
          <div style="font-size:11px;color:var(--muted);margin-top:2px">
            ${v.category ? `<span style="margin-right:8px">📂 ${v.category}</span>` : ""}
            <span>複習 ${v.review_count} 次</span>
            ${v.sr_next_review_at ? `<span style="margin-left:8px;color:var(--danger,#ef4444)">到期：${new Date(v.sr_next_review_at).toLocaleDateString("zh-TW")}</span>` : '<span style="color:var(--warning,#f59e0b);margin-left:8px">尚未複習</span>'}
          </div>
        </div>
        <a href="/video/${v.id}" class="btn btn-primary btn-xs">開始複習</a>
      </div>
    `).join("");
  } catch (e) {
    el.innerHTML = `<div style="color:var(--muted)">載入失敗</div>`;
  }
}

async function loadWrongAnswers() {
  const listEl = document.getElementById("wrong-answers-list");
  const badgeEl = document.getElementById("wrong-answers-count-badge");
  if (!listEl) return;

  listEl.innerHTML = `<div style="color:var(--muted);font-size:13px">載入中...</div>`;

  try {
    const data = await api("GET", "/api/quiz/wrong-answers/list?limit=20");
    if (badgeEl) badgeEl.textContent = data.total;

    if (!data.items || data.items.length === 0) {
      listEl.innerHTML = `<div style="color:var(--muted);font-size:13px;padding:12px 0">🎉 目前沒有錯題！繼續保持！</div>`;
      return;
    }

    const typeLabels = { mcq: "選擇", truefalse: "是非", fillblank: "填空" };

    listEl.innerHTML = data.items.map(item => {
      const typeLabel = typeLabels[item.question_type] || item.question_type;
      const tsHtml = item.source_start_sec != null
        ? `<a href="/video/${item.video_id}?t=${Math.floor(item.source_start_sec)}" style="font-size:11px;color:var(--primary,#4f46e5);text-decoration:none">⏱ 回看片段</a>`
        : "";
      const conceptHtml = item.concept_name
        ? `<span style="font-size:11px;padding:2px 6px;border-radius:10px;background:var(--border,#eee);color:var(--muted,#666)">${escapeHtml(item.concept_name)}</span>`
        : "";
      const optionsHtml = item.options
        ? `<div style="font-size:12px;color:var(--muted,#888);margin-top:4px">${item.options.map(o => escapeHtml(o)).join(" · ")}</div>`
        : "";
      return `
        <div style="padding:14px 16px;background:var(--surface,#f9f9f9);border-radius:10px;border-left:3px solid var(--danger,#ef4444)">
          <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:8px">
            <div style="flex:1">
              <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:6px">
                <span style="font-size:11px;padding:2px 7px;border-radius:10px;background:var(--danger,#ef4444);color:#fff">${typeLabel}</span>
                ${conceptHtml}
                ${tsHtml}
              </div>
              <div style="font-size:14px;font-weight:600;line-height:1.5;color:var(--text,#333)">${escapeHtml(item.question)}</div>
              ${optionsHtml}
            </div>
            <a href="/video/${item.video_id}" style="font-size:11px;color:var(--primary,#4f46e5);white-space:nowrap;text-decoration:none;padding-top:2px">查看影片</a>
          </div>
          <div style="display:flex;gap:16px;font-size:13px;flex-wrap:wrap">
            <span>我的答案：<span style="color:var(--danger,#ef4444);font-weight:600">${escapeHtml(item.user_answer)}</span></span>
            <span>正確答案：<span style="color:var(--success,#22c55e);font-weight:600">${escapeHtml(item.correct_answer)}</span></span>
          </div>
          ${item.explanation ? `<div style="margin-top:8px;font-size:13px;color:var(--muted,#666);line-height:1.5;border-top:1px solid var(--border,#eee);padding-top:8px">💡 ${escapeHtml(item.explanation)}</div>` : ""}
        </div>
      `;
    }).join("");
  } catch (e) {
    listEl.innerHTML = `<div style="color:var(--danger,#ef4444);font-size:13px">載入失敗：${e.message}</div>`;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 全文搜尋
// ═══════════════════════════════════════════════════════════════════════════════
function buildSearchResultVideoUrl(item) {
  return `/video/${item.id}${item.start_sec != null ? `?t=${encodeURIComponent(item.start_sec)}` : ""}`;
}

async function doSearch() {
  const q = document.getElementById("fts-input").value.trim();
  const statusEl = document.getElementById("search-status");
  const resultsEl = document.getElementById("search-results");
  if (!q) { statusEl.textContent = "請輸入搜尋關鍵字"; return; }

  statusEl.textContent = "搜尋中...";
  resultsEl.innerHTML = "";
  try {
    const data = await api("GET", `/api/search/?q=${encodeURIComponent(q)}`);
    statusEl.textContent = `共找到 ${data.total} 筆結果`;
    if (!data.items.length) {
      resultsEl.innerHTML = `<div class="card" style="text-align:center;color:var(--muted);padding:32px">找不到符合「${escapeHtml(q)}」的影片</div>`;
      return;
    }
    resultsEl.innerHTML = data.items.map(item => `
      <div class="card" style="margin-bottom:12px">
        <div style="display:flex;align-items:flex-start;gap:12px">
          <div style="flex:1;min-width:0">
            <a href="${buildSearchResultVideoUrl(item)}" style="font-weight:700;font-size:14px;color:var(--primary,#4f46e5);text-decoration:none">
              ${item.title_highlight || escapeHtml(item.filename)}
            </a>
            ${item.category ? `<span style="margin-left:8px;font-size:12px;color:var(--muted)">${item.category}</span>` : ""}
            ${item.timestamp ? `<span style="margin-left:8px;font-size:12px;color:var(--primary,#4f46e5);font-weight:600">[${item.timestamp}]</span>` : ""}
            <div style="margin-top:6px;font-size:13px;color:var(--text,#333);line-height:1.6">
              ${item.snippet || ""}
            </div>
            <div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">
              ${(item.labels||[]).map(l => `<span class="label-chip" style="background:${l.color}22;color:${l.color};border:1px solid ${l.color}">${escapeHtml(l.name)}</span>`).join("")}
            </div>
          </div>
          <a href="${buildSearchResultVideoUrl(item)}" class="btn btn-ghost btn-sm" style="white-space:nowrap">${item.timestamp ? "跳到片段 →" : "查看 →"}</a>
        </div>
      </div>
    `).join("");
  } catch (e) {
    statusEl.textContent = "搜尋失敗: " + e.message;
  }
}

async function reindexFTS() {
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = "重建中...";
  try {
    const d = await api("POST", "/api/search/reindex");
    toast(d.message, "success");
  } catch(e) {
    toast("重建失敗: " + e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "⟳ 重建索引";
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 學習統計
// ═══════════════════════════════════════════════════════════════════════════════
async function loadStatsPage() {
  try {
    const [overview, daily, confidence, topReviewed, heatmap] = await Promise.all([
      api("GET", "/api/stats/overview"),
      api("GET", "/api/stats/daily?days=7"),
      api("GET", "/api/stats/confidence"),
      api("GET", "/api/stats/top-reviewed?limit=8"),
      api("GET", "/api/stats/heatmap?days=365"),
    ]);

    // KPI cards
    document.getElementById("skpi-completed").querySelector(".skpi-num").textContent = overview.completed;
    document.getElementById("skpi-reviewed").querySelector(".skpi-num").textContent = overview.reviewed;
    document.getElementById("skpi-never").querySelector(".skpi-num").textContent = overview.never_reviewed;
    document.getElementById("skpi-due").querySelector(".skpi-num").textContent = overview.due_today;
    document.getElementById("skpi-today").querySelector(".skpi-num").textContent = overview.reviewed_today;
    document.getElementById("skpi-total-sessions").querySelector(".skpi-num").textContent = overview.total_review_sessions;

    // Daily bar chart (simple CSS bars)
    const maxCount = Math.max(...daily.data.map(d => d.reviews), 1);
    document.getElementById("daily-chart").innerHTML = daily.data.map(d => `
      <div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:4px">
        <div style="font-size:11px;color:var(--muted);font-weight:600">${d.reviews || ""}</div>
        <div style="width:100%;background:var(--primary,#4f46e5);border-radius:4px 4px 0 0;height:${Math.max(d.reviews/maxCount*80,2)}px;opacity:${d.reviews?1:0.2}"></div>
        <div style="font-size:10px;color:var(--muted)">${d.date.slice(5)}</div>
      </div>
    `).join("");

    // Confidence distribution
    const confLabels = ["😰完全不懂","😕模糊記得","😐大致理解","😊掌握良好","🤩完全掌握"];
    const confColors = ["#ef4444","#f97316","#eab308","#22c55e","#3b82f6"];
    const maxConf = Math.max(...confidence.distribution.map(d => d.count), 1);
    document.getElementById("confidence-chart").innerHTML = confidence.distribution.map((d,i) => `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
        <div style="font-size:11px;width:90px;color:var(--text)">${confLabels[i]}</div>
        <div style="flex:1;height:18px;background:${confColors[i]};border-radius:4px;width:${d.count/maxConf*100}%;min-width:${d.count?4:0}px;opacity:${d.count?1:0.2}"></div>
        <div style="font-size:11px;color:var(--muted);width:24px;text-align:right">${d.count}</div>
      </div>
    `).join("");

    // Top reviewed
    const trEl = document.getElementById("top-reviewed-list");
    if (!topReviewed.items.length) {
      trEl.innerHTML = `<div style="color:var(--muted);padding:16px 0">尚無複習紀錄</div>`;
    } else {
      trEl.innerHTML = `<div style="display:flex;flex-direction:column;gap:8px">${topReviewed.items.map((v,i) => `
        <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;background:var(--surface,#f5f5f5);border-radius:6px">
          <span style="font-weight:700;color:var(--muted);width:20px;text-align:right">${i+1}</span>
          <a href="/video/${v.id}" style="flex:1;font-size:13px;font-weight:600;color:var(--text);text-decoration:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(v.filename)}</a>
          <span style="font-size:12px;color:var(--muted)">複習 ${v.review_count} 次</span>
          <span style="font-size:11px;color:var(--muted)">EF:${v.sr_ease_factor}</span>
        </div>
      `).join("")}</div>`;
    }

    // Activity Heatmap (GitHub-style)
    renderActivityHeatmap(heatmap.data);

  } catch (e) {
    console.error("loadStatsPage error:", e);
  }

  // Load quiz stats separately — non-critical, fails gracefully
  try {
    const quizStats = await api("GET", "/api/quiz/stats/overview");
    document.getElementById("qstat-total-items").textContent = quizStats.total_items ?? "—";
    document.getElementById("qstat-attempts").textContent = quizStats.total_attempts ?? "—";
    document.getElementById("qstat-correct").textContent = quizStats.correct_attempts ?? "—";
    document.getElementById("qstat-wrong").textContent = quizStats.wrong_attempts ?? "—";
    document.getElementById("qstat-accuracy").textContent =
      quizStats.total_attempts ? `${quizStats.accuracy_percent}%` : "—";
  } catch (e) {
    console.warn("Quiz stats load failed (non-critical):", e.message);
    // Leave the "—" placeholders from HTML
  }
}

// ─── Activity Heatmap ────────────────────────────────────────────────────────

function renderActivityHeatmap(data) {
  const el = document.getElementById("activity-heatmap");
  if (!el) return;

  const heatColors = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"];
  function colorForCount(n) {
    if (n === 0) return heatColors[0];
    if (n === 1) return heatColors[1];
    if (n <= 3) return heatColors[2];
    if (n <= 6) return heatColors[3];
    return heatColors[4];
  }

  // Group days into weeks (columns), Sunday-first
  const weeks = [];
  let week = [];
  data.forEach((d, i) => {
    const dow = new Date(d.date + "T00:00:00").getDay(); // 0=Sun
    if (i === 0) {
      // Pad start of first week
      for (let p = 0; p < dow; p++) week.push(null);
    }
    week.push(d);
    if (week.length === 7) { weeks.push(week); week = []; }
  });
  if (week.length) {
    while (week.length < 7) week.push(null);
    weeks.push(week);
  }

  // Render: rows = days of week (0=Sun..6=Sat), cols = weeks
  const dayLabels = ["", "一", "", "三", "", "五", ""];
  let html = "";
  for (let row = 0; row < 7; row++) {
    html += `<div style="display:flex;gap:3px;align-items:center">`;
    html += `<span style="font-size:10px;color:var(--muted,#888);width:14px;text-align:right">${dayLabels[row]}</span>`;
    for (const wk of weeks) {
      const day = wk[row];
      if (!day) {
        html += `<div style="width:12px;height:12px"></div>`;
      } else {
        const c = colorForCount(day.count);
        const title = `${day.date}: ${day.count} 次複習`;
        html += `<div title="${title}" style="width:12px;height:12px;background:${c};border-radius:2px;cursor:default"></div>`;
      }
    }
    html += `</div>`;
  }
  el.innerHTML = html;
}

// ─── 自動掃描狀態 Banner ──────────────────────────────────────────────────────
let _autoScanDone = false;

async function pollAutoScan() {
  if (_autoScanDone) return;
  try {
    const d = await api("GET", "/api/batch/scan-status");
    const banner = document.getElementById("auto-scan-banner");
    const icon   = document.getElementById("auto-scan-icon");
    const msg    = document.getElementById("auto-scan-msg");
    const prog   = document.getElementById("auto-scan-progress");

    if (d.status === "idle") {
      // 尚未啟動（測試環境 / 沒有 /videos）
      banner.style.display = "none";
      _autoScanDone = true;
      return;
    }

    banner.style.display = "flex";

    if (d.status === "running") {
      icon.textContent = "⏳";
      const src = d.current_source ? d.current_source.split("/").pop() : "...";
      msg.textContent  = `掃描中：${src}`;
      prog.textContent = `${d.sources_done} / ${d.sources_total} 個來源`;
    } else if (d.status === "done") {
      icon.textContent = "✅";
      msg.textContent  = `掃描完成：發現 ${d.total_found} 支影片，新登錄 ${d.total_registered} 支，跳過 ${d.total_skipped} 支`;
      prog.textContent = "";
      _autoScanDone = true;
      // 更新影片列表
      loadStats(); loadVideos();
      // 3 秒後收起 banner
      setTimeout(() => { banner.style.display = "none"; }, 3000);
    } else if (d.status === "error") {
      icon.textContent = "❌";
      msg.textContent  = `掃描失敗：${d.error}`;
      _autoScanDone = true;
    }
  } catch (e) {
    console.warn("auto-scan poll error", e);
  }
}

function startAutoScanPoll() {
  pollAutoScan();
  const t = setInterval(async () => {
    await pollAutoScan();
    if (_autoScanDone) clearInterval(t);
  }, 2000);
}

// ═══════════════════════════════════════════════════════════════════════════════
// 知識庫 (Wiki) Functions
// ═══════════════════════════════════════════════════════════════════════════════

async function loadWikiHome() {
  // Load stats
  const statsGrid = document.getElementById("wiki-stats-grid");
  if (!statsGrid) return;
  statsGrid.innerHTML = "";
  try {
    const s = await api("GET", "/api/wiki/stats");
    const items = [
      { label: "主題數", value: s.total_topics ?? 0 },
      { label: "領域數", value: s.total_domains ?? 0 },
      { label: "知識頁面", value: s.total_wiki_pages ?? 0 },
      { label: "已發布", value: s.published_wiki_pages ?? 0 },
    ];
    statsGrid.innerHTML = items.map(i => `
      <div class="stats-kpi-card">
        <div class="skpi-num">${i.value}</div>
        <div class="skpi-label">${i.label}</div>
      </div>`).join("");
  } catch (e) {
    statsGrid.innerHTML = `<div style="color:var(--muted);font-size:13px">無法載入統計資料</div>`;
  }

  // Load topic tree
  const treeEl = document.getElementById("wiki-topic-tree");
  if (!treeEl) return;
  treeEl.innerHTML = `<div style="color:var(--muted);font-size:13px;padding:20px 0;text-align:center">載入中...</div>`;
  try {
    const d = await api("GET", "/api/wiki/topics");
    if (!d.tree || !d.tree.length) {
      treeEl.innerHTML = `<div style="color:var(--muted);font-size:13px;padding:20px 0;text-align:center">尚無分類。請先分析影片後使用建置工具。</div>`;
      return;
    }
    treeEl.innerHTML = d.tree.map(topic => renderTopicTreeItem(topic)).join("");
  } catch (e) {
    treeEl.innerHTML = `<div style="color:var(--danger);font-size:13px;padding:12px 0">載入失敗：${escapeHtml(e.message)}</div>`;
  }
}

function renderTopicTreeItem(topic) {
  const childrenHtml = (topic.children && topic.children.length)
    ? `<div style="padding-left:20px;border-left:2px solid var(--border-subtle);margin-left:12px;margin-top:4px">${topic.children.map(c => renderTopicTreeItem(c)).join("")}</div>`
    : "";
  return `
    <div>
      <button type="button" class="wiki-topic-tree-item" onclick="loadWikiTopic('${escapeHtml(String(topic.id))}');showSection('wiki-topics')">
        <span style="flex:1;font-weight:500">${escapeHtml(topic.name)}</span>
        ${topic.domain ? `<span class="wiki-domain-badge">${escapeHtml(topic.domain)}</span>` : ""}
        ${(topic.children && topic.children.length) ? `<span style="font-size:11px;color:var(--muted)">${topic.children.length} 子主題</span>` : ""}
      </button>
      ${childrenHtml}
    </div>`;
}

async function loadWikiTopic(topicId) {
  history.replaceState(null, "", `#wiki-topic-${topicId}`);
  const el = document.getElementById("wiki-topic-detail");
  if (!el) return;
  el.innerHTML = `<div style="color:var(--muted);font-size:13px;padding:20px 0;text-align:center">載入中...</div>`;
  try {
    const t = await api("GET", `/api/wiki/topics/${topicId}`);
    const childrenHtml = (t.children && t.children.length)
      ? t.children.map(c => `
          <button type="button" class="wiki-topic-tree-item" onclick="loadWikiTopic('${escapeHtml(String(c.id))}')">
            <span style="flex:1;font-weight:500">${escapeHtml(c.name)}</span>
            ${c.domain ? `<span class="wiki-domain-badge">${escapeHtml(c.domain)}</span>` : ""}
          </button>`).join("")
      : `<div style="color:var(--muted);font-size:13px;padding:8px 0">（無子主題）</div>`;

    el.innerHTML = `
      <div class="card">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
          <button class="btn btn-ghost btn-sm" onclick="showSection('wiki-home')">← 返回</button>
          ${t.domain ? `<span class="wiki-domain-badge">${escapeHtml(t.domain)}</span>` : ""}
          ${t.concept_count != null ? `<span style="font-size:12px;color:var(--muted)">${t.concept_count} 概念</span>` : ""}
        </div>
        <h3 style="font-size:18px;margin-bottom:8px">${escapeHtml(t.name)}</h3>
        ${t.description ? `<p style="font-size:13px;color:var(--muted);margin-bottom:16px">${escapeHtml(t.description)}</p>` : ""}
        <div class="card-title" style="margin-top:16px">子主題</div>
        ${childrenHtml}
      </div>`;
  } catch (e) {
    el.innerHTML = `<div style="color:var(--danger);font-size:13px;padding:12px 0">載入失敗：${escapeHtml(e.message)}</div>`;
  }
}

async function loadWikiPages() {
  const listEl = document.getElementById("wiki-pages-list");
  const detailEl = document.getElementById("wiki-page-detail");
  if (!listEl) return;
  detailEl.style.display = "none";
  listEl.innerHTML = `<div style="color:var(--muted);font-size:13px;padding:20px 0;text-align:center">載入中...</div>`;
  try {
    const d = await api("GET", "/api/wiki/pages");
    if (!d.items || !d.items.length) {
      listEl.innerHTML = `<div style="color:var(--muted);font-size:13px;padding:20px 0;text-align:center">尚無知識頁面。請先使用建置工具合成。</div>`;
      return;
    }
    listEl.innerHTML = d.items.map(p => {
      const statusClass = p.status === "published" ? "wiki-status-published" : "wiki-status-stale";
      const statusLabel = p.status === "published" ? "已發布" : "過期";
      const date = p.last_synthesized_at ? new Date(p.last_synthesized_at).toLocaleDateString("zh-TW") : "—";
      return `
        <button type="button" class="wiki-page-item" onclick="loadWikiPage('${escapeHtml(String(p.id))}')">
          <div style="flex:1">
            <div style="font-weight:600;margin-bottom:4px">${escapeHtml(p.title)}</div>
            <div style="font-size:12px;color:var(--muted)">來源影片：${p.source_video_count ?? 0} · 最後合成：${date}</div>
          </div>
          <span class="wiki-status-badge ${statusClass}">${statusLabel}</span>
        </button>`;
    }).join("");
  } catch (e) {
    listEl.innerHTML = `<div style="color:var(--danger);font-size:13px;padding:12px 0">載入失敗：${escapeHtml(e.message)}</div>`;
  }
}

async function loadWikiPage(id) {
  const detailEl = document.getElementById("wiki-page-detail");
  if (!detailEl) return;
  detailEl.style.display = "block";
  detailEl.innerHTML = `<div style="color:var(--muted);font-size:13px;padding:20px 0;text-align:center">載入中...</div>`;
  try {
    const p = await api("GET", `/api/wiki/pages/${id}`);
    const sourcesHtml = (p.sources && p.sources.length)
      ? p.sources.map(s => `
          <div style="padding:8px 12px;border-left:3px solid var(--primary);margin-bottom:8px;background:var(--bg);border-radius:4px">
            <div style="font-weight:600;font-size:12px;margin-bottom:4px">${escapeHtml(s.video_title || "—")}${s.timestamp ? ` · ${escapeHtml(s.timestamp)}` : ""}</div>
            <div style="font-size:12px;color:var(--muted)">${escapeHtml(s.excerpt || "")}</div>
          </div>`).join("")
      : `<div style="color:var(--muted);font-size:13px">（無來源）</div>`;

    detailEl.innerHTML = `
      <div class="card">
        <div style="margin-bottom:12px">
          <button class="btn btn-ghost btn-sm" onclick="loadWikiPages()">← 返回列表</button>
        </div>
        <h3 style="font-size:18px;margin-bottom:16px">${escapeHtml(p.title)}</h3>
        <div class="wiki-page-content">${escapeHtml(p.synthesized_content || "（無內容）")}</div>
        <div class="card-title" style="margin-top:20px">📎 來源</div>
        ${sourcesHtml}
      </div>`;
  } catch (e) {
    detailEl.innerHTML = `<div style="color:var(--danger);font-size:13px;padding:12px 0">載入失敗：${escapeHtml(e.message)}</div>`;
  }
}

// ─── Wiki Tools ───────────────────────────────────────────────────────────────
(function initWikiTools() {
  const btnTaxonomy = document.getElementById("btn-build-taxonomy");
  const btnSynthesize = document.getElementById("btn-synthesize-wiki");
  if (btnTaxonomy) {
    btnTaxonomy.addEventListener("click", async () => {
      const resultEl = document.getElementById("build-taxonomy-result");
      btnTaxonomy.disabled = true;
      btnTaxonomy.textContent = "建立中...";
      resultEl.textContent = "";
      try {
        const d = await api("POST", "/api/wiki/build-taxonomy");
        resultEl.style.color = "var(--success)";
        resultEl.textContent = `✅ ${d.message || "完成"}（領域 ${d.domains_created ?? "?"} · 主題 ${d.topics_created ?? "?"} · 概念連結 ${d.concept_links_created ?? "?"}）`;
        showToast("分類樹建立完成", "success");
      } catch (e) {
        resultEl.style.color = "var(--danger)";
        resultEl.textContent = `❌ 失敗：${e.message}`;
        showToast("建立分類樹失敗", "error");
      } finally {
        btnTaxonomy.disabled = false;
        btnTaxonomy.textContent = "🏗️ 建立分類樹";
      }
    });
  }
  if (btnSynthesize) {
    btnSynthesize.addEventListener("click", async () => {
      const resultEl = document.getElementById("synthesize-result");
      const force = document.getElementById("synthesize-force")?.checked ?? false;
      btnSynthesize.disabled = true;
      btnSynthesize.textContent = "合成中...";
      resultEl.textContent = "";
      try {
        const d = await api("POST", `/api/wiki/synthesize?force=${force}`);
        resultEl.style.color = "var(--success)";
        resultEl.textContent = `✅ ${d.message || "完成"}（合成 ${d.synthesized ?? "?"} · 跳過 ${d.skipped ?? "?"} · 錯誤 ${d.errors ?? "?"}）`;
        showToast("知識頁面合成完成", "success");
      } catch (e) {
        resultEl.style.color = "var(--danger)";
        resultEl.textContent = `❌ 失敗：${e.message}`;
        showToast("合成知識頁面失敗", "error");
      } finally {
        btnSynthesize.disabled = false;
        btnSynthesize.textContent = "✨ 合成知識頁面";
      }
    });
  }
})();
