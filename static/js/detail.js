let pollTimer = null;
let videoId = null;
let tabLoaded = {};

async function loadDetail() {
  videoId = document.getElementById("video-id").dataset.id;

  try {
    const v = await api("GET", `/api/videos/${videoId}`);
    document.title = v.original_filename + " - Video Analyzer";
    document.getElementById("video-name").textContent = v.original_filename;
    document.getElementById("kv-status").innerHTML = badge(v.status);
    document.getElementById("kv-source").textContent = v.source === "local_scan" ? "本地掃描" : "手動上傳";
    document.getElementById("kv-size").textContent = fmtSize(v.file_size);
    document.getElementById("kv-duration").textContent = fmtDur(v.duration);
    document.getElementById("kv-path").textContent = v.file_path || "—";
    document.getElementById("kv-date").textContent = v.upload_date
      ? new Date(v.upload_date).toLocaleString("zh-TW") : "—";
    _populateReviewInfo(v);

    if (v.error_message) {
      document.getElementById("error-box").textContent = v.error_message;
      document.getElementById("error-section").classList.remove("hidden");
    } else {
      document.getElementById("error-section").classList.add("hidden");
    }

    const canQueue = ["pending"].includes(v.status);
    const canRetry = v.status === "failed";
    document.getElementById("btn-queue").style.display = canQueue ? "" : "none";
    document.getElementById("btn-retry").style.display = canRetry ? "" : "none";
    document.getElementById("btn-queue").onclick = () => queueVideo(videoId);
    document.getElementById("btn-retry").onclick = () => retryVideo(videoId);

    // Load labels
    loadVideoLabels(videoId);

    // Initialize embedded player — works regardless of analysis status
    initEmbeddedPlayer(v.original_filename || v.filename || "");
  } catch (e) {
    toast("載入影片資訊失敗: " + e.message, "error");
  }

  // Task status + progress — track video_status from API for polling
  let videoStatus = "pending";
  try {
    const s = await api("GET", `/api/analysis/${videoId}/status`);
    videoStatus = s.video_status;

    if (s.task) {
      const t = s.task;
      // 影片已完成時，忽略殘留的 pending/cancelled 任務，顯示為完成
      const displayStatus = s.video_status === "completed"
        ? (["done", "completed"].includes(t.status) ? t.status : "done")
        : t.status;
      document.getElementById("task-status").innerHTML = badge(displayStatus === "done" ? "completed" : displayStatus);
      document.getElementById("task-started").textContent = t.started_at ? new Date(t.started_at).toLocaleString("zh-TW") : "—";
      document.getElementById("task-completed").textContent = t.completed_at ? new Date(t.completed_at).toLocaleString("zh-TW") : "—";
      document.getElementById("task-retries").textContent = t.retry_count;
      document.getElementById("task-section").classList.remove("hidden");
    }

    // Render progress if processing/queued
    if (["queued", "processing"].includes(s.video_status)) {
      renderProgress(s.progress);
    } else if (s.video_status === "completed") {
      renderProgress({ step: 4, sub_percent: 100, message: "分析完成", percent: 100 });
    }
  } catch {}

  // Check if completed and show tabs
  try {
    const results = await api("GET", `/api/analysis/${videoId}/results`);
    document.getElementById("notebooklm-section").classList.remove("hidden");

    // Load summary tab by default
    if (results.summary) document.getElementById("summary-text").textContent = results.summary;
    if (results.key_points && results.key_points.length) {
      renderKeyPoints(results.key_points);
    }
    if (results.category) document.getElementById("kv-category").textContent = results.category;
    if (results.transcript) {
      renderTranscript(results.transcript, results.transcript_segments || null);
    }
    // 案例分析若已包含在 results 中直接渲染，否則等 tab 切換時再 lazy load
    if (results.case_analysis !== undefined) {
      renderCaseAnalysis(results.case_analysis);
      tabLoaded["case-analysis"] = true;
    }
    document.getElementById("btn-reanalyze").style.display = "";

    tabLoaded["summary"] = true;
    tabLoaded["transcript"] = true;

    // Load chat history
    loadChatHistory();

  } catch (e) {
    // Not completed yet — use videoStatus from API (not badge DOM text which is in Chinese)
    if (["queued", "processing"].includes(videoStatus)) {
      if (pollTimer) clearTimeout(pollTimer);
      pollTimer = setTimeout(loadDetail, 3000);
    }
  }
}

function renderProgress(p) {
  if (!p) return;
  document.getElementById("progress-section").classList.remove("hidden");

  const step = p.step || 0;
  const sub = p.sub_percent || 0;

  // Update each step indicator (1-4)
  for (let i = 1; i <= 4; i++) {
    const el = document.getElementById(`pstep-${i}`);
    el.classList.remove("done", "active");
    if (i < step) el.classList.add("done");
    else if (i === step) el.classList.add("active");
  }

  // Update connectors (1-3)
  for (let i = 1; i <= 3; i++) {
    const el = document.getElementById(`pconn-${i}`);
    el.classList.remove("done", "active");
    if (i < step) el.classList.add("done");
    else if (i === step) el.classList.add("active");
  }

  // Overall progress bar: step-level progress + sub-progress contribution
  const overallPct = step === 0 ? 0 : Math.min(
    Math.floor((step - 1) / 4 * 100) + Math.floor(sub / 4),
    100
  );
  document.getElementById("progress-bar-fill").style.width = overallPct + "%";

  // Sub-progress bar (only show when actively processing a step)
  const subTrack = document.getElementById("progress-sub-track");
  if (step > 0 && step <= 4 && sub < 100) {
    subTrack.style.display = "block";
    document.getElementById("progress-sub-fill").style.width = sub + "%";
  } else {
    subTrack.style.display = "none";
  }

  // Message and percent
  document.getElementById("progress-message").textContent = p.message || "等待中...";
  document.getElementById("progress-percent").textContent = overallPct + "%";

  // Elapsed timer — start on first active step, stop when done
  if (step > 0 && step <= 4 && !_elapsedTimer) {
    startElapsedTimer(p.started_at);
  } else if (step === 0 || overallPct >= 100) {
    stopElapsedTimer();
  }
}

// Per-tab scroll position memory: restore reading position when switching back
const _tabScrollPos = {};

function switchTab(tabName) {
  // Save current tab's scroll position before switching away
  const currentPanel = document.querySelector(".tab-panel.active");
  if (currentPanel) {
    _tabScrollPos[currentPanel.id] = window.scrollY;
  }

  // Update buttons
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  // Update panels
  document.querySelectorAll(".tab-panel").forEach(panel => {
    panel.classList.remove("active");
  });
  const panel = document.getElementById("tab-" + tabName);
  if (panel) panel.classList.add("active");

  // Restore saved scroll position for this tab (or scroll to tabs top)
  const saved = _tabScrollPos["tab-" + tabName];
  window.scrollTo({ top: saved !== undefined ? saved : (panel?.offsetTop ?? 0) - 16, behavior: "instant" });

  // Lazy load
  if (!tabLoaded[tabName]) {
    tabLoaded[tabName] = true;
    if (tabName === "mindmap") loadMindmap();
    else if (tabName === "faq") loadFAQ();
    else if (tabName === "case-analysis") loadCaseAnalysis();
    else if (tabName === "notes") loadNote();
    else if (tabName === "qa-chat") { /* chat history already loaded */ }
  }
}

async function loadMindmap() {
  const loadingEl = document.getElementById("mindmap-loading");
  const containerEl = document.getElementById("mindmap-container");
  const errorEl = document.getElementById("mindmap-error");
  const rawEl = document.getElementById("mindmap-raw");

  loadingEl.style.display = "block";
  containerEl.style.display = "none";
  errorEl.classList.add("hidden");

  try {
    const data = await api("GET", `/api/analysis/${videoId}/mindmap`);
    const markdown = data.mindmap;
    rawEl.textContent = markdown;
    loadingEl.style.display = "none";
    containerEl.style.display = "block";
    renderMindmap(markdown);
  } catch (e) {
    loadingEl.style.display = "none";
    errorEl.textContent = e.message.includes("尚未生成") ? "心智圖尚未生成，請點擊「重新生成」" : ("載入失敗: " + e.message);
    errorEl.classList.remove("hidden");
  }
}

let _mindmapInstance = null;
let _mindmapMarkdown = "";   // store raw markdown for fullscreen re-render
let _mindmapFullscreenInstance = null;

function renderMindmap(markdown) {
  _mindmapMarkdown = markdown;
  try {
    if (!window.markmap) {
      document.getElementById("mindmap-error").textContent = "Markmap 庫載入失敗，請檢查網路連線";
      document.getElementById("mindmap-error").classList.remove("hidden");
      document.getElementById("mindmap-container").style.display = "none";
      return;
    }
    const { Transformer, Markmap } = window.markmap;
    const transformer = new Transformer();
    const { root } = transformer.transform(markdown);
    const svg = document.getElementById("mindmap-svg");
    svg.innerHTML = "";
    if (_mindmapInstance) { try { _mindmapInstance.destroy(); } catch(_) {} }
    _mindmapInstance = Markmap.create(svg, {
      zoom: true,      // 滾輪縮放
      pan: true,       // 拖曳移動
      duration: 300,
    });
    _mindmapInstance.setData(root);
    setTimeout(() => _mindmapInstance.fit(), 100);
  } catch (e) {
    document.getElementById("mindmap-error").textContent = "心智圖渲染失敗: " + e.message;
    document.getElementById("mindmap-error").classList.remove("hidden");
    document.getElementById("mindmap-container").style.display = "none";
  }
}

function resetMindmapZoom() {
  if (_mindmapInstance) _mindmapInstance.fit();
}

function openMindmapFullscreen() {
  if (!_mindmapMarkdown) { toast("心智圖尚未載入", "info"); return; }
  const overlay = document.getElementById("mindmap-fullscreen-overlay");
  overlay.classList.remove("hidden");

  // Re-render in fullscreen SVG
  const { Transformer, Markmap } = window.markmap;
  const transformer = new Transformer();
  const { root } = transformer.transform(_mindmapMarkdown);
  const svg = document.getElementById("mindmap-fullscreen-svg");
  svg.innerHTML = "";
  if (_mindmapFullscreenInstance) { try { _mindmapFullscreenInstance.destroy(); } catch(_) {} }
  _mindmapFullscreenInstance = Markmap.create(svg, { zoom: true, pan: true, duration: 200 });
  _mindmapFullscreenInstance.setData(root);
  setTimeout(() => _mindmapFullscreenInstance.fit(), 150);
}

function closeFullscreen() {
  document.getElementById("mindmap-fullscreen-overlay").classList.add("hidden");
}

function downloadMindmap() {
  const svgEl = document.getElementById(
    document.getElementById("mindmap-fullscreen-overlay").classList.contains("hidden")
      ? "mindmap-svg" : "mindmap-fullscreen-svg"
  );
  if (!svgEl || !svgEl.innerHTML) { toast("心智圖尚未載入", "info"); return; }

  // Compute actual SVG bounding box
  const bbox = svgEl.getBBox ? svgEl.getBBox() : null;
  const w = (bbox && bbox.width > 0) ? bbox.width + 40 : svgEl.clientWidth || 1200;
  const h = (bbox && bbox.height > 0) ? bbox.height + 40 : svgEl.clientHeight || 800;

  // Clone SVG and set explicit size
  const clone = svgEl.cloneNode(true);
  clone.setAttribute("width", w);
  clone.setAttribute("height", h);
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");

  const svgData = new XMLSerializer().serializeToString(clone);
  const svgUrl = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svgData);

  const img = new Image();
  img.onload = () => {
    const canvas = document.createElement("canvas");
    const scale = 2;  // retina quality
    canvas.width = w * scale;
    canvas.height = h * scale;
    const ctx = canvas.getContext("2d");
    ctx.scale(scale, scale);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, w, h);
    ctx.drawImage(img, 0, 0, w, h);
    const link = document.createElement("a");
    link.download = "mindmap.png";
    link.href = canvas.toDataURL("image/png");
    link.click();
  };
  img.onerror = () => toast("下載失敗，請嘗試放大後再試", "error");
  img.src = svgUrl;
}

async function loadFAQ() {
  const loadingEl = document.getElementById("faq-loading");
  const listEl = document.getElementById("faq-list");
  const errorEl = document.getElementById("faq-error");

  loadingEl.style.display = "block";
  listEl.innerHTML = "";
  errorEl.classList.add("hidden");

  try {
    const data = await api("GET", `/api/analysis/${videoId}/faq`);
    loadingEl.style.display = "none";
    if (!data.faq || data.faq.length === 0) {
      listEl.innerHTML = "<p style='color:var(--muted)'>暫無 FAQ 資料</p>";
      return;
    }
    listEl.innerHTML = data.faq.map((item, i) => `
      <div class="faq-item" id="faq-${i}">
        <div class="faq-q" onclick="toggleFAQ(${i})">
          <span>${item.question}</span>
          <span class="faq-toggle">▼</span>
        </div>
        <div class="faq-a">${item.answer}</div>
      </div>
    `).join("");
  } catch (e) {
    loadingEl.style.display = "none";
    errorEl.textContent = e.message.includes("尚未生成") ? "FAQ 尚未生成，請點擊「重新生成」" : ("載入失敗: " + e.message);
    errorEl.classList.remove("hidden");
  }
}

function toggleFAQ(i) {
  document.getElementById("faq-" + i).classList.toggle("open");
}

async function loadChatHistory() {
  try {
    const data = await api("GET", `/api/analysis/${videoId}/chat-history`);
    const messagesEl = document.getElementById("chat-messages");
    messagesEl.innerHTML = "";
    if (data.messages && data.messages.length > 0) {
      data.messages.forEach(msg => appendChatBubble(msg.role, msg.content));
      messagesEl.scrollTop = messagesEl.scrollHeight;
    } else {
      messagesEl.innerHTML = "<p style='color:var(--muted);text-align:center;align-self:center'>開始提問吧！</p>";
    }
  } catch (e) {
    console.error("載入對話歷史失敗:", e);
  }
}

function appendChatBubble(role, content) {
  const messagesEl = document.getElementById("chat-messages");
  // Remove placeholder text
  const placeholder = messagesEl.querySelector("p");
  if (placeholder) placeholder.remove();

  const div = document.createElement("div");
  div.className = "chat-bubble " + role;
  div.textContent = content;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function sendMessage() {
  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("send-btn");
  const question = input.value.trim();
  if (!question) return;

  input.value = "";
  sendBtn.disabled = true;
  appendChatBubble("user", question);

  // Show thinking indicator
  const messagesEl = document.getElementById("chat-messages");
  const thinking = document.createElement("div");
  thinking.className = "chat-bubble assistant";
  thinking.style.opacity = "0.6";
  thinking.textContent = "思考中...";
  messagesEl.appendChild(thinking);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  try {
    const data = await api("POST", `/api/analysis/${videoId}/ask`, { question });
    thinking.remove();
    appendChatBubble("assistant", data.answer);
  } catch (e) {
    thinking.remove();
    toast("提問失敗: " + e.message, "error");
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
}

async function clearChatHistory() {
  if (!confirm("確定要清除對話記錄嗎？")) return;
  try {
    await api("DELETE", `/api/analysis/${videoId}/chat-history`);
    const messagesEl = document.getElementById("chat-messages");
    messagesEl.innerHTML = "<p style='color:var(--muted);text-align:center;align-self:center'>開始提問吧！</p>";
    toast("對話記錄已清除", "success");
  } catch (e) {
    toast("清除失敗: " + e.message, "error");
  }
}

async function regenerate(type) {
  const labels = { mindmap: "心智圖", faq: "FAQ" };
  if (!confirm(`確定要重新生成 ${labels[type] || type} 嗎？這需要一些時間。`)) return;

  toast(`正在重新生成 ${labels[type] || type}...`, "info");

  try {
    await api("POST", `/api/analysis/${videoId}/regenerate/${type}`);
    toast(`${labels[type] || type} 已重新生成！`, "success");

    // Reload the relevant tab
    if (type === "mindmap") { tabLoaded["mindmap"] = false; loadMindmap(); }
    else if (type === "faq") { tabLoaded["faq"] = false; loadFAQ(); }
  } catch (e) {
    toast("重新生成失敗: " + e.message, "error");
  }
}

// 12 色主題調色盤，對應 label 的顏色系統
const _KP_COLORS = [
  { bg: "#fef2f2", border: "#ef4444", title: "#b91c1c" },
  { bg: "#fff7ed", border: "#f97316", title: "#c2410c" },
  { bg: "#fefce8", border: "#eab308", title: "#a16207" },
  { bg: "#f0fdf4", border: "#22c55e", title: "#15803d" },
  { bg: "#f0fdfa", border: "#14b8a6", title: "#0f766e" },
  { bg: "#eff6ff", border: "#3b82f6", title: "#1d4ed8" },
  { bg: "#f5f3ff", border: "#8b5cf6", title: "#6d28d9" },
  { bg: "#fdf4ff", border: "#d946ef", title: "#a21caf" },
  { bg: "#ecfeff", border: "#06b6d4", title: "#0e7490" },
  { bg: "#f7fee7", border: "#84cc16", title: "#4d7c0f" },
  { bg: "#fffbeb", border: "#f59e0b", title: "#b45309" },
  { bg: "#eef2ff", border: "#6366f1", title: "#4338ca" },
];

function renderKeyPoints(keyPoints) {
  const container = document.getElementById("key-points-list");
  if (!keyPoints || !keyPoints.length) { container.innerHTML = ""; return; }

  // 相容新格式 [{theme, points}] 和舊格式 ["string"]
  if (typeof keyPoints[0] === "string") {
    const c = _KP_COLORS[0];
    container.innerHTML = `<div class="kp-theme" style="--kp-bg:${c.bg};--kp-border:${c.border};--kp-title:${c.title}"><ul>${keyPoints.map(p => `<li>${p}</li>`).join("")}</ul></div>`;
    return;
  }
  container.innerHTML = keyPoints.map((kp, i) => {
    const c = _KP_COLORS[i % _KP_COLORS.length];
    return `
    <div class="kp-theme" style="--kp-bg:${c.bg};--kp-border:${c.border};--kp-title:${c.title}">
      <div class="kp-theme-title">${kp.theme || ""}</div>
      <ul>${(kp.points || []).map(p => `<li>${p}</li>`).join("")}</ul>
    </div>`;
  }).join("");
}

/**
 * Render transcript in the transcript tab.
 *
 * When Whisper segments are available each line is prefixed with a clickable
 * [MM:SS] timestamp that seeks the embedded player.  Falls back to paragraph-
 * splitting on the raw text string for old videos without segments.
 *
 * @param {string} text - Plain transcript text (always present)
 * @param {Array<{start:number,end:number,text:string}>|null} segments - Whisper segments
 */
function renderTranscript(text, segments) {
  const el = document.getElementById("transcript-text");
  const hint = document.getElementById("transcript-ts-hint");
  if (!el) return;

  if (segments && segments.length > 0) {
    el.innerHTML = segments.map(seg => {
      const mm = String(Math.floor(seg.start / 60)).padStart(2, "0");
      const ss = String(Math.floor(seg.start % 60)).padStart(2, "0");
      const sec = Math.floor(seg.start);
      return `<p class="transcript-seg"><a class="ts-link" data-sec="${sec}" title="跳到 ${mm}:${ss}">[${mm}:${ss}]</a> ${seg.text.trim()}</p>`;
    }).join("");
    if (hint) hint.style.display = "";
    el.querySelectorAll(".ts-link").forEach(link => {
      link.addEventListener("click", () => seekMainPlayer(parseFloat(link.dataset.sec)));
    });
    return;
  }

  // Fallback: wrap plain text into natural paragraphs (~100 chars each)
  if (!text) return;
  const PARA_CHARS = 100;
  const phrases = text.split(/\s+/).filter(Boolean);
  const paragraphs = [];
  let buf = "";
  for (const phrase of phrases) {
    buf += (buf ? " " : "") + phrase;
    const hasSentenceEnd = /[。！？!?]$/.test(phrase);
    if ((hasSentenceEnd && buf.length >= 40) || buf.length >= PARA_CHARS) {
      paragraphs.push(buf);
      buf = "";
    }
  }
  if (buf) paragraphs.push(buf);
  el.innerHTML = paragraphs.map(p => `<p>${p}</p>`).join("");
}

/**
 * Render case analysis markdown with clickable [MM:SS] timestamp links.
 * Timestamp links seek the embedded video player at the top of the page.
 *
 * @param {string|null} text - Markdown case analysis text
 */
function renderCaseAnalysis(text) {
  const el = document.getElementById("case-analysis-content");
  const tsHint = document.getElementById("case-analysis-ts-hint");
  const noTsHint = document.getElementById("case-analysis-no-ts-hint");
  if (!el) return;

  if (!text) {
    el.innerHTML = `<div class="no-case-analysis">
      <span class="no-case-icon">📋</span>
      <p>本影片未包含案例分析內容</p>
    </div>`;
    return;
  }

  const hasTimestamps = /\[\d{1,2}:\d{2}/.test(text);
  if (tsHint) tsHint.style.display = hasTimestamps ? "" : "none";
  if (noTsHint) noTsHint.style.display = hasTimestamps ? "none" : "";

  const html = _injectTimestampLinks(_renderMarkdown(text));
  el.innerHTML = html;

  el.querySelectorAll(".ts-link").forEach(link => {
    link.addEventListener("click", () => seekMainPlayer(parseFloat(link.dataset.sec)));
  });
}

async function loadCaseAnalysis() {
  const el = document.getElementById("case-analysis-content");
  if (!el) return;
  try {
    const data = await api("GET", `/api/analysis/${videoId}/case-analysis`);
    renderCaseAnalysis(data.case_analysis);
  } catch (e) {
    el.innerHTML = `<p style="color:var(--muted)">載入失敗：${e.message}</p>`;
  }
}

function _renderMarkdown(text) {
  if (!text) return "";
  if (window.marked) return marked.parse(text);
  return text
    .replace(/^## (.+)$/gm, '<h2 class="ca-h2">$1</h2>')
    .replace(/^### (.+)$/gm, '<h3 class="ca-h3">$1</h3>')
    .replace(/^\*\*(.+?)\*\*(.*)$/gm, '<p><strong>$1</strong>$2</p>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, m => `<ul>${m}</ul>`)
    .replace(/^(?!<[hpul]).+$/gm, '<p>$&</p>')
    .replace(/<\/ul>\n?<ul>/g, "");
}

function _tsToSec(ts) {
  const parts = ts.split(':').map(Number);
  return parts.length === 3
    ? parts[0] * 3600 + parts[1] * 60 + parts[2]
    : parts[0] * 60 + parts[1];
}

function _injectTimestampLinks(html) {
  return html.replace(/\[(\d{1,2}:\d{2}(?::\d{2})?)\]/g, (_, ts) => {
    const sec = _tsToSec(ts);
    return `<a class="ts-link" data-sec="${sec}" title="跳到 ${ts}">[${ts}]</a>`;
  });
}

async function reanalyze() {
  const btn = document.getElementById("btn-reanalyze");
  btn.disabled = true;
  btn.textContent = "分析中...";
  toast("重新分析中，請稍候...", "info");
  try {
    const data = await api("POST", `/api/analysis/${videoId}/reanalyze`);
    document.getElementById("summary-text").textContent = data.summary;
    renderKeyPoints(data.key_points);
    document.getElementById("kv-category").textContent = data.category;
    renderCaseAnalysis(data.case_analysis);
    tabLoaded["case-analysis"] = true;
    toast("重新分析完成！", "success");
  } catch (e) {
    toast("重新分析失敗: " + e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "🔄 重新分析";
  }
}

/** Confirm before burning GPT tokens on reanalysis */
function confirmReanalyze() {
  if (confirm("重新執行 GPT 分析將消耗 API token，逐字稿不會重新辨識。確定繼續嗎？")) {
    reanalyze();
  }
}

/** Confirm before burning GPT tokens on regeneration */
function confirmRegenerate(type) {
  const label = type === "mindmap" ? "心智圖" : "FAQ";
  if (confirm(`重新生成${label}將消耗 API token。確定繼續嗎？`)) {
    regenerate(type);
  }
}

async function retryVideo(vid) {
  try {
    await api("POST", `/api/analysis/${vid}/retry`);
    toast("已重新加入分析佇列", "success");
    setTimeout(loadDetail, 1000);
  } catch (e) {
    toast("重試失敗: " + e.message, "error");
  }
}

async function queueVideo(vid) {
  try {
    await api("POST", `/api/analysis/${vid}/queue`);
    toast("已加入分析佇列", "success");
    setTimeout(loadDetail, 1000);
  } catch (e) {
    toast("加入佇列失敗: " + e.message, "error");
  }
}

window.addEventListener("load", () => { loadDetail(); loadAllLabels(); });
window.addEventListener("beforeunload", () => { if (pollTimer) clearTimeout(pollTimer); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closeFullscreen(); });

// ─── Keyboard shortcuts ───────────────────────────────────────────────────────
// Space = play/pause · ← → = ±10s · J/L = ±10s · K = play/pause · M = mute · F = fullscreen
document.addEventListener("keydown", e => {
  const tag = e.target.tagName.toLowerCase();
  if (["input", "textarea", "select"].includes(tag)) return;
  const video = document.getElementById("video-player");
  if (!video) return;
  switch (e.key) {
    case " ":
      e.preventDefault();
      video.paused ? video.play() : video.pause();
      break;
    case "ArrowLeft":
    case "j":
      e.preventDefault();
      video.currentTime = Math.max(0, video.currentTime - 10);
      break;
    case "ArrowRight":
    case "l":
      e.preventDefault();
      video.currentTime = Math.min(video.duration || Infinity, video.currentTime + 10);
      break;
    case "k":
      video.paused ? video.play() : video.pause();
      break;
    case "m":
      video.muted = !video.muted;
      toast(video.muted ? "🔇 靜音" : "🔊 取消靜音", "info");
      break;
    case "f":
      e.preventDefault();
      video.requestFullscreen?.() ?? video.webkitRequestFullscreen?.();
      break;
  }
});

// ─── Transcript ↔ video bidirectional sync ────────────────────────────────────
// timeupdate: highlight the segment whose timestamp is closest to currentTime
function initTranscriptSync() {
  const video = document.getElementById("video-player");
  if (!video) return;

  let _lastActiveSeg = null;

  video.addEventListener("timeupdate", () => {
    const segs = document.querySelectorAll(".transcript-seg");
    if (!segs.length) return;

    const t = video.currentTime;
    let bestEl = null;
    let bestSec = -1;

    segs.forEach(seg => {
      const link = seg.querySelector(".ts-link");
      if (!link) return;
      const sec = parseFloat(link.dataset.sec);
      if (sec <= t && sec > bestSec) { bestSec = sec; bestEl = seg; }
    });

    if (bestEl === _lastActiveSeg) return;
    if (_lastActiveSeg) _lastActiveSeg.classList.remove("active");
    if (bestEl) {
      bestEl.classList.add("active");
      // Auto-scroll the transcript body only when that tab is visible
      const transcriptPanel = document.getElementById("tab-transcript");
      if (transcriptPanel?.classList.contains("active")) {
        const body = document.querySelector(".transcript-body");
        if (body) {
          const top = bestEl.offsetTop - body.offsetTop - body.clientHeight / 3;
          body.scrollTo({ top, behavior: "smooth" });
        }
      }
    }
    _lastActiveSeg = bestEl;
  });
}

// ─── Progress elapsed time counter ───────────────────────────────────────────
let _progressStartTime = null;
let _elapsedTimer = null;

function startElapsedTimer(startedAt) {
  _progressStartTime = startedAt ? new Date(startedAt) : new Date();
  if (_elapsedTimer) clearInterval(_elapsedTimer);
  const el = document.getElementById("progress-elapsed");
  if (!el) return;
  const tick = () => {
    const secs = Math.floor((Date.now() - _progressStartTime) / 1000);
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    el.textContent = `⏱ ${m}m ${s}s`;
  };
  tick();
  _elapsedTimer = setInterval(tick, 1000);
}

function stopElapsedTimer() {
  if (_elapsedTimer) { clearInterval(_elapsedTimer); _elapsedTimer = null; }
  const el = document.getElementById("progress-elapsed");
  if (el) el.textContent = "";
}

// ─── Mini floating player ────────────────────────────────────────────────────
// Appears as a compact bottom-right pip when the main player scrolls off screen
let _miniPlayerActive = false;
let _miniPlayerDismissed = false;

function initMiniPlayer() {
  const mainVideo = document.getElementById("video-player");
  const playerCard = document.getElementById("player-card");
  const miniPlayer = document.getElementById("mini-player");
  const miniVideo = document.getElementById("mini-video");
  if (!mainVideo || !playerCard || !miniPlayer || !miniVideo) return;

  // Sync mini video source once main is ready
  mainVideo.addEventListener("loadedmetadata", () => {
    miniVideo.src = mainVideo.currentSrc || mainVideo.src;
    miniVideo.load();
  });

  // Keep mini video in sync with main
  mainVideo.addEventListener("timeupdate", () => {
    if (_miniPlayerActive && Math.abs(miniVideo.currentTime - mainVideo.currentTime) > 1) {
      miniVideo.currentTime = mainVideo.currentTime;
    }
  });
  mainVideo.addEventListener("play", () => { if (_miniPlayerActive) miniVideo.play().catch(() => {}); });
  mainVideo.addEventListener("pause", () => { if (_miniPlayerActive) miniVideo.pause(); });

  // Show/hide mini player based on visibility of main player card
  const observer = new IntersectionObserver(entries => {
    const isVisible = entries[0].isIntersecting;
    if (!isVisible && !_miniPlayerDismissed && !mainVideo.paused) {
      _miniPlayerActive = true;
      miniVideo.currentTime = mainVideo.currentTime;
      miniPlayer.classList.add("visible");
      miniVideo.muted = true;   // mini is muted; audio comes from main
      miniVideo.play().catch(() => {});
    } else if (isVisible) {
      _miniPlayerActive = false;
      miniPlayer.classList.remove("visible");
      miniVideo.pause();
    }
  }, { threshold: 0.1 });

  observer.observe(playerCard);

  // Set title
  const titleEl = document.getElementById("mini-player-title");
  if (titleEl) titleEl.textContent = document.getElementById("video-name")?.textContent || "影片播放中";
}

function miniPlayerJumpBack() {
  const video = document.getElementById("video-player");
  if (video) video.scrollIntoView({ behavior: "smooth", block: "center" });
  _miniPlayerActive = false;
  document.getElementById("mini-player").classList.remove("visible");
}

function closeMiniPlayer() {
  _miniPlayerDismissed = true;
  _miniPlayerActive = false;
  document.getElementById("mini-player").classList.remove("visible");
  document.getElementById("mini-video").pause();
}

// ═══════════════════════════════════════════════════════════════════════════════
// Label 管理
// ═══════════════════════════════════════════════════════════════════════════════
let _allLabels = [];  // 全部標籤庫（用於 autocomplete）

async function loadVideoLabels(videoId) {
  try {
    const labels = await api("GET", `/api/labels/videos/${videoId}`);
    renderVideoLabels(labels);
    // Auto-suggest if completed and no labels yet
    if (!labels.length) {
      const v = await api("GET", `/api/videos/${videoId}`);
      if (v.status === "completed") {
        autoSuggestLabels(videoId);
      }
    }
  } catch (e) {
    console.error("loadVideoLabels error", e);
  }
}

async function autoSuggestLabels(videoId) {
  try {
    const r = await api("POST", `/api/analysis/${videoId}/suggest-labels`);
    const suggestions = r.suggestions || [];
    if (!suggestions.length) return;
    for (const name of suggestions) {
      await api("POST", `/api/labels/videos/${videoId}`, { name });
    }
    await loadVideoLabels(videoId);
    await loadAllLabels();
  } catch (e) {
    // 靜默失敗（摘要可能還不存在）
    console.debug("autoSuggestLabels:", e.message);
  }
}

function renderVideoLabels(labels) {
  const el = document.getElementById("video-labels-list");
  if (!labels.length) {
    el.innerHTML = `<span style="color:var(--muted,#888);font-size:12px">無標籤</span>`;
    return;
  }
  el.innerHTML = labels.map(l => `
    <span class="label-tag" style="background:${l.color}20;color:${l.color};border-color:${l.color}40;display:inline-flex;align-items:center;gap:4px">
      ${escHtml(l.name)}
      <button onclick="removeLabel('${l.id}')" style="border:none;background:none;cursor:pointer;color:${l.color};padding:0;font-size:13px;line-height:1">×</button>
    </span>
  `).join("");
}

async function addLabelFromInput() {
  const input = document.getElementById("label-input");
  const name = input.value.trim();
  if (!name) return;
  const videoId = new URLSearchParams(window.location.search).get("id") ||
                  window.location.pathname.split("/").pop();
  try {
    const r = await api("POST", `/api/labels/videos/${videoId}`, { name });
    input.value = "";
    document.getElementById("label-autocomplete").classList.add("hidden");
    await loadVideoLabels(videoId);
    await loadAllLabels();  // 刷新 autocomplete 庫
  } catch (e) {
    toast("新增標籤失敗: " + e.message, "error");
  }
}

async function removeLabel(labelId) {
  const videoId = new URLSearchParams(window.location.search).get("id") ||
                  window.location.pathname.split("/").pop();
  try {
    await api("DELETE", `/api/labels/videos/${videoId}/${labelId}`);
    await loadVideoLabels(videoId);
  } catch (e) {
    toast("移除標籤失敗: " + e.message, "error");
  }
}

async function suggestLabels() {
  const videoId = new URLSearchParams(window.location.search).get("id") ||
                  window.location.pathname.split("/").pop();
  const btn = document.getElementById("btn-suggest-labels");
  btn.disabled = true; btn.textContent = "建議中...";
  try {
    const r = await api("POST", `/api/analysis/${videoId}/suggest-labels`);
    const suggestions = r.suggestions || [];
    if (!suggestions.length) { toast("GPT 未能生成建議", "info"); return; }

    // 顯示建議讓使用者選
    const existing = [...document.querySelectorAll("#video-labels-list .label-tag")]
      .map(el => el.textContent.trim().replace("×", "").trim());

    const newSuggestions = suggestions.filter(s => !existing.includes(s));
    if (!newSuggestions.length) { toast("建議標籤都已存在", "info"); return; }

    // 快速套用所有建議
    for (const name of newSuggestions) {
      await api("POST", `/api/labels/videos/${videoId}`, { name });
    }
    await loadVideoLabels(videoId);
    await loadAllLabels();
    toast(`已套用 ${newSuggestions.length} 個建議標籤：${newSuggestions.join("、")}`, "success");
  } catch (e) {
    toast("GPT 建議失敗: " + e.message, "error");
  } finally {
    btn.disabled = false; btn.textContent = "✨ GPT 建議";
  }
}

async function loadAllLabels() {
  try {
    _allLabels = await api("GET", "/api/labels/");
  } catch {}
}

function showLabelSuggestions(query) {
  const box = document.getElementById("label-autocomplete");
  const q = query.trim().toLowerCase();
  if (!q) { box.classList.add("hidden"); return; }
  const matches = _allLabels.filter(l => l.name.toLowerCase().includes(q) && l.name !== q).slice(0, 6);
  if (!matches.length) { box.classList.add("hidden"); return; }
  box.innerHTML = matches.map(l =>
    `<div class="autocomplete-item" onclick="selectLabelSuggestion('${escHtml(l.name)}')">`
    + `<span class="label-dot" style="background:${l.color}"></span>${escHtml(l.name)}</div>`
  ).join("");
  box.classList.remove("hidden");
}

function selectLabelSuggestion(name) {
  document.getElementById("label-input").value = name;
  document.getElementById("label-autocomplete").classList.add("hidden");
  addLabelFromInput();
}

function handleLabelKeydown(e) {
  if (e.key === "Enter") { e.preventDefault(); addLabelFromInput(); }
  if (e.key === "Escape") document.getElementById("label-autocomplete").classList.add("hidden");
}

function escHtml(str) {
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// 標籤和全部標籤庫在 window.load 時一起初始化（見下方）

// ═══════════════════════════════════════════════════════════════════════════════
// 複習系統
// ═══════════════════════════════════════════════════════════════════════════════

let _selectedConfidence = null;

function openReviewModal() {
  _selectedConfidence = null;
  document.querySelectorAll(".confidence-btn").forEach(b => b.classList.remove("selected"));
  document.getElementById("confirm-review-btn").disabled = true;
  document.getElementById("review-result-msg").style.display = "none";
  document.getElementById("review-modal-overlay").classList.remove("hidden");
}

function closeReviewModal() {
  document.getElementById("review-modal-overlay").classList.add("hidden");
}

function selectConfidence(level) {
  _selectedConfidence = level;
  document.querySelectorAll(".confidence-btn").forEach(b => {
    b.classList.toggle("selected", parseInt(b.dataset.level) === level);
  });
  document.getElementById("confirm-review-btn").disabled = false;
}

async function confirmReview() {
  if (!_selectedConfidence) return;
  const btn = document.getElementById("confirm-review-btn");
  btn.disabled = true;
  btn.textContent = "記錄中...";
  try {
    const data = await api("POST", `/api/review/${videoId}/mark`, { confidence: _selectedConfidence });
    const msgEl = document.getElementById("review-result-msg");
    msgEl.textContent = `✅ 已記錄！下次複習：${new Date(data.sr_next_review_at).toLocaleDateString("zh-TW")}（${data.sr_interval} 天後）`;
    msgEl.style.display = "block";
    // 更新 kv 欄位
    document.getElementById("kv-review-count").textContent = `${data.review_count} 次`;
    document.getElementById("kv-last-reviewed").textContent = new Date().toLocaleDateString("zh-TW");
    document.getElementById("kv-next-review").textContent = new Date(data.sr_next_review_at).toLocaleDateString("zh-TW");
    setTimeout(closeReviewModal, 1800);
  } catch (e) {
    toast("記錄失敗: " + e.message, "error");
    btn.disabled = false;
    btn.textContent = "確認複習";
  }
}

function _populateReviewInfo(video) {
  const el = document.getElementById("btn-reviewed");
  if (video.status === "completed") el.style.display = "";
  const rc = video.review_count || 0;
  document.getElementById("kv-review-count").textContent = rc ? `${rc} 次` : "尚未複習";
  document.getElementById("kv-last-reviewed").textContent = video.last_reviewed_at
    ? new Date(video.last_reviewed_at).toLocaleDateString("zh-TW") : "—";
  document.getElementById("kv-next-review").textContent = video.sr_next_review_at
    ? new Date(video.sr_next_review_at).toLocaleDateString("zh-TW") : "—";
}

// ═══════════════════════════════════════════════════════════════════════════════
// 個人筆記
// ═══════════════════════════════════════════════════════════════════════════════

let _noteSaveTimer = null;

async function loadNote() {
  try {
    const data = await api("GET", `/api/notes/${videoId}`);
    const editor = document.getElementById("note-editor");
    editor.value = data.content || "";
    renderNotePreview(editor.value);
  } catch (e) {
    console.error("載入筆記失敗:", e);
  }
}

function scheduleNoteSave() {
  if (_noteSaveTimer) clearTimeout(_noteSaveTimer);
  renderNotePreview(document.getElementById("note-editor").value);
  // 自動儲存：停止輸入 2 秒後
  _noteSaveTimer = setTimeout(saveNote, 2000);
}

async function saveNote() {
  if (_noteSaveTimer) clearTimeout(_noteSaveTimer);
  const content = document.getElementById("note-editor").value;
  try {
    await api("PUT", `/api/notes/${videoId}`, { content });
    const ind = document.getElementById("notes-saved-indicator");
    ind.style.display = "";
    setTimeout(() => { ind.style.display = "none"; }, 2000);
  } catch (e) {
    toast("筆記儲存失敗: " + e.message, "error");
  }
}

function renderNotePreview(markdown) {
  const el = document.getElementById("note-preview");
  if (!el) return;
  if (!markdown.trim()) { el.innerHTML = "<span style='color:var(--muted)'>（預覽區）</span>"; return; }
  if (window.marked) {
    el.innerHTML = marked.parse(markdown);
  } else {
    el.textContent = markdown;
  }
}


// ═══════════════════════════════════════════════════════════════════════════════
// 影片播放器
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Initialise the embedded video player card at page load.
 *
 * All formats stream through /api/videos/{id}/stream — the server uses
 * FFmpeg on-the-fly for formats the browser cannot play natively (WMV,
 * AVI, MKV, FLV), so we always set the same src.
 *
 * @param {string} filename - Original video filename (used for format badge)
 */
function initEmbeddedPlayer(filename) {
  const video = document.getElementById("video-player");
  const source = document.getElementById("video-source");
  const badge = document.getElementById("player-format-badge");
  if (!video || !source) return;

  const ext = filename.includes(".") ? filename.split(".").pop().toLowerCase() : "";
  if (badge && ext) badge.textContent = `(${ext.toUpperCase()})`;

  const mimeMap = { mp4: "video/mp4", mov: "video/quicktime", webm: "video/webm", m4v: "video/mp4" };
  source.type = mimeMap[ext] || "video/mp4";
  source.src = `/api/videos/${videoId}/stream`;
  video.load();

  // Start transcript sync and mini player after player is initialised
  initTranscriptSync();
  initMiniPlayer();
}

/**
 * Seek the embedded player to `sec` seconds and resume playback.
 * Scrolls the player into view if it is off-screen.
 *
 * @param {number} sec - Target position in seconds
 */
function seekMainPlayer(sec) {
  const video = document.getElementById("video-player");
  if (!video) return;
  video.currentTime = sec;
  video.scrollIntoView({ behavior: "smooth", block: "center" });
  video.play().catch(() => {
    // Autoplay may be blocked; the user can press play manually
  });
}

async function openLocalPlayer() {
  // 呼叫後端 endpoint，由伺服器端用 open 指令開啟（僅限 macOS/本機）
  try {
    await api("POST", `/api/videos/${videoId}/open-local`);
    toast("已傳送開啟指令給本機播放器", "success");
  } catch (e) {
    toast("無法開啟：" + e.message, "error");
  }
}
