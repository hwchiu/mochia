// ─── State ───
let currentPage = 0;
const PAGE_SIZE = 50;
let filterStatus = "";
let filterSource = "";
let pollTimer = null;

// ─── Stats ───
async function loadStats() {
  try {
    const d = await api("GET", "/api/batch/status");
    const v = d.videos;
    document.getElementById("stat-total").textContent =
      Object.values(v).reduce((a, b) => a + b, 0);
    document.getElementById("stat-pending").textContent = v.pending || 0;
    document.getElementById("stat-queued").textContent = v.queued || 0;
    document.getElementById("stat-processing").textContent = v.processing || 0;
    document.getElementById("stat-completed").textContent = v.completed || 0;
    document.getElementById("stat-failed").textContent = v.failed || 0;

    const t = d.tasks;
    const queuePending = t.pending || 0;
    const queueProcessing = t.processing || 0;
    document.getElementById("queue-info").textContent =
      `佇列：等待 ${queuePending} | 處理中 ${queueProcessing} | 完成 ${t.done || 0} | 失敗 ${t.failed || 0}`;

    // Progress bar: completed / total
    const total = Object.values(v).reduce((a, b) => a + b, 0);
    const pct = total > 0 ? Math.round((v.completed / total) * 100) : 0;
    document.getElementById("progress-bar").style.width = pct + "%";
    document.getElementById("progress-pct").textContent = pct + "%";
  } catch (e) {
    console.error("loadStats error", e);
  }
}

// ─── Video List ───
async function loadVideos() {
  try {
    const params = new URLSearchParams({
      skip: currentPage * PAGE_SIZE,
      limit: PAGE_SIZE,
    });
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

function goPage(p) {
  currentPage = p;
  loadVideos();
}

// ─── Filter ───
document.getElementById("filter-status").addEventListener("change", e => {
  filterStatus = e.target.value;
  currentPage = 0;
  loadVideos();
});
document.getElementById("filter-source").addEventListener("change", e => {
  filterSource = e.target.value;
  currentPage = 0;
  loadVideos();
});

// ─── Bulk select ───
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
  for (const id of ids) {
    try { await api("POST", `/api/analysis/${id}/queue`); ok++; } catch {}
  }
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

// ─── Scan modal ───
document.getElementById("btn-scan").addEventListener("click", () => {
  document.getElementById("scan-overlay").classList.remove("hidden");
});
document.getElementById("scan-cancel").addEventListener("click", () => {
  document.getElementById("scan-overlay").classList.add("hidden");
});
document.getElementById("scan-confirm").addEventListener("click", async () => {
  const path = document.getElementById("scan-path").value.trim();
  if (!path) { toast("請輸入目錄路徑", "info"); return; }
  const btn = document.getElementById("scan-confirm");
  btn.disabled = true;
  btn.textContent = "掃描中...";
  try {
    const d = await api("POST", `/api/batch/scan?path=${encodeURIComponent(path)}`);
    toast(`掃描完成：新登錄 ${d.registered} 支，跳過 ${d.skipped} 支`, "success");
    document.getElementById("scan-overlay").classList.add("hidden");
    loadStats(); loadVideos();
  } catch (e) {
    toast("掃描失敗: " + e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "開始掃描";
  }
});

// ─── Single queue ───
async function queueOne(id) {
  try {
    const d = await api("POST", `/api/analysis/${id}/queue`);
    toast(d.message, "success");
    loadStats(); loadVideos();
  } catch (e) { toast("操作失敗: " + e.message, "error"); }
}

// ─── Auto-refresh ───
function startPoll() {
  pollTimer = setInterval(() => { loadStats(); loadVideos(); }, 8000);
}

// ─── Init ───
loadStats();
loadVideos();
startPoll();
