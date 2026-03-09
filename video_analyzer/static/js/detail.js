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

    if (v.error_message) {
      document.getElementById("error-box").textContent = v.error_message;
      document.getElementById("error-section").classList.remove("hidden");
    } else {
      document.getElementById("error-section").classList.add("hidden");
    }

    const canQueue = ["pending", "failed"].includes(v.status);
    document.getElementById("btn-queue").style.display = canQueue ? "" : "none";
    document.getElementById("btn-queue").onclick = () => queueVideo(videoId);
  } catch (e) {
    toast("載入影片資訊失敗: " + e.message, "error");
  }

  // Task status
  try {
    const s = await api("GET", `/api/analysis/${videoId}/status`);
    if (s.task) {
      const t = s.task;
      document.getElementById("task-status").innerHTML = badge(t.status === "done" ? "completed" : t.status);
      document.getElementById("task-started").textContent = t.started_at ? new Date(t.started_at).toLocaleString("zh-TW") : "—";
      document.getElementById("task-completed").textContent = t.completed_at ? new Date(t.completed_at).toLocaleString("zh-TW") : "—";
      document.getElementById("task-retries").textContent = t.retry_count;
      document.getElementById("task-section").classList.remove("hidden");
    }
  } catch {}

  // Check if completed and show tabs
  try {
    const results = await api("GET", `/api/analysis/${videoId}/results`);
    document.getElementById("notebooklm-section").classList.remove("hidden");

    // Load summary tab by default
    if (results.summary) document.getElementById("summary-text").textContent = results.summary;
    if (results.key_points && results.key_points.length) {
      const ul = document.getElementById("key-points-list");
      ul.innerHTML = results.key_points.map(p => `<li>${p}</li>`).join("");
    }
    if (results.category) document.getElementById("kv-category").textContent = results.category;
    if (results.transcript) {
      document.getElementById("transcript-text").textContent = results.transcript;
    }

    tabLoaded["summary"] = true;
    tabLoaded["transcript"] = true;

    // Load chat history
    loadChatHistory();

  } catch (e) {
    // Not completed yet, poll
    const statusEl = document.getElementById("kv-status").textContent;
    const inProgress = statusEl.includes("queued") || statusEl.includes("processing");
    if (inProgress) {
      pollTimer = setTimeout(loadDetail, 5000);
    }
  }
}

function switchTab(tabName) {
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

  // Lazy load
  if (!tabLoaded[tabName]) {
    tabLoaded[tabName] = true;
    if (tabName === "mindmap") loadMindmap();
    else if (tabName === "faq") loadFAQ();
    else if (tabName === "study-notes") loadStudyNotes();
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

function renderMindmap(markdown) {
  try {
    if (!window.markmap) {
      document.getElementById("mindmap-error").textContent = "Markmap 庫載入失敗，請檢查網路連線";
      document.getElementById("mindmap-error").classList.remove("hidden");
      document.getElementById("mindmap-container").style.display = "none";
      return;
    }
    const { Transformer } = window.markmap;
    const { Markmap } = window.markmap;
    const transformer = new Transformer();
    const { root } = transformer.transform(markdown);
    const svg = document.getElementById("mindmap-svg");
    svg.innerHTML = "";
    const mm = Markmap.create(svg);
    mm.setData(root);
    mm.fit();
  } catch (e) {
    document.getElementById("mindmap-error").textContent = "心智圖渲染失敗: " + e.message;
    document.getElementById("mindmap-error").classList.remove("hidden");
    document.getElementById("mindmap-container").style.display = "none";
  }
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

async function loadStudyNotes() {
  const loadingEl = document.getElementById("study-notes-loading");
  const contentEl = document.getElementById("study-notes-content");
  const errorEl = document.getElementById("study-notes-error");

  loadingEl.style.display = "block";
  contentEl.innerHTML = "";
  errorEl.classList.add("hidden");

  try {
    const data = await api("GET", `/api/analysis/${videoId}/study-notes`);
    loadingEl.style.display = "none";
    if (window.marked) {
      contentEl.innerHTML = marked.parse(data.study_notes);
    } else {
      contentEl.textContent = data.study_notes;
    }
  } catch (e) {
    loadingEl.style.display = "none";
    errorEl.textContent = e.message.includes("尚未生成") ? "學習筆記尚未生成，請點擊「重新生成」" : ("載入失敗: " + e.message);
    errorEl.classList.remove("hidden");
  }
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
  const labels = { mindmap: "心智圖", faq: "FAQ", study_notes: "學習筆記" };
  if (!confirm(`確定要重新生成 ${labels[type] || type} 嗎？這需要一些時間。`)) return;

  toast(`正在重新生成 ${labels[type] || type}...`, "info");

  try {
    await api("POST", `/api/analysis/${videoId}/regenerate/${type}`);
    toast(`${labels[type] || type} 已重新生成！`, "success");

    // Reload the relevant tab
    if (type === "mindmap") { tabLoaded["mindmap"] = false; loadMindmap(); }
    else if (type === "faq") { tabLoaded["faq"] = false; loadFAQ(); }
    else if (type === "study_notes") { tabLoaded["study-notes"] = false; loadStudyNotes(); }
  } catch (e) {
    toast("重新生成失敗: " + e.message, "error");
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

window.addEventListener("load", loadDetail);
window.addEventListener("beforeunload", () => { if (pollTimer) clearTimeout(pollTimer); });
