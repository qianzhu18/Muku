const config = window.APP_CONFIG || {};
config.settings = config.settings || {};
config.platformAuth = config.platformAuth || {};

const urlInput = document.getElementById("url");
const presetSelect = document.getElementById("preset");
const taskList = document.getElementById("task-list");
const form = document.getElementById("download-form");
const startBtn = document.getElementById("start-btn");
const pasteClipboardBtn = document.getElementById("paste-clipboard-btn");
const clearUrlBtn = document.getElementById("clear-url-btn");
const taskFeedback = document.getElementById("task-feedback");
const taskAdvanced = document.getElementById("task-advanced");
const taskEntrySummary = document.getElementById("task-entry-summary");
const taskSubmitHelp = document.getElementById("task-submit-help");
const queueCount = document.getElementById("queue-count");
const modeHint = document.getElementById("mode-hint");
const cookiesHint = document.getElementById("cookies-hint");
const cookiesCheckbox = document.getElementById("use-cookies");
const generateKnowledgeCheckbox = document.getElementById("generate-knowledge");
const knowledgeOptionHint = document.getElementById("knowledge-option-hint");
const downloadDirInput = document.getElementById("download-dir");
const downloadDirHint = document.getElementById("download-dir-hint");
const starterGuide = document.getElementById("starter-guide");
const starterGuideSummary = starterGuide.querySelector("summary");
const starterTitle = document.getElementById("starter-title");
const starterSubtitle = document.getElementById("starter-subtitle");
const starterProgress = document.getElementById("starter-progress");
const starterToggleLabel = document.getElementById("starter-toggle-label");
const starterChecklist = document.getElementById("starter-checklist");
const starterPlatforms = document.getElementById("starter-platforms");
const starterCallout = document.getElementById("starter-callout");
const starterOpenSettings = document.getElementById("starter-open-settings");

const settingsForm = document.getElementById("settings-form");
const saveSettingsBtn = document.getElementById("save-settings-btn");
const settingsStatus = document.getElementById("settings-status");
const settingsFileHint = document.getElementById("settings-file-hint");
const settingsRootHint = document.getElementById("settings-root-hint");
const settingsToggle = document.getElementById("settings-toggle");
const settingsClose = document.getElementById("settings-close");
const settingsBackdrop = document.getElementById("settings-backdrop");
const settingsDrawer = document.getElementById("settings-drawer");

const activeCount = document.getElementById("active-count");
const doneCount = document.getElementById("done-count");
const failedCount = document.getElementById("failed-count");
const summaryDownloadDir = document.getElementById("summary-download-dir");
const summaryModel = document.getElementById("summary-model");
const summaryAuth = document.getElementById("summary-auth");
const detailEmpty = document.getElementById("detail-empty");
const taskDetailContent = document.getElementById("task-detail-content");

const monitorTabs = Array.from(document.querySelectorAll(".monitor-tab"));
const monitorPanels = {
  queue: document.getElementById("queue-panel"),
  detail: document.getElementById("detail-panel"),
};

const settingsElements = {
  downloadDir: document.getElementById("settings-download-dir"),
  openrouterBaseUrl: document.getElementById("settings-openrouter-base-url"),
  openrouterApiKey: document.getElementById("settings-openrouter-api-key"),
  openrouterApiKeyClear: document.getElementById("settings-openrouter-api-key-clear"),
  openrouterSiteUrl: document.getElementById("settings-openrouter-site-url"),
  openrouterAppName: document.getElementById("settings-openrouter-app-name"),
  openrouterTranscriptionModel: document.getElementById("settings-openrouter-transcription-model"),
  openrouterArticleModel: document.getElementById("settings-openrouter-article-model"),
  enableCleanup: document.getElementById("settings-enable-cleanup"),
  cleanupBaseUrl: document.getElementById("settings-cleanup-base-url"),
  cleanupApiKey: document.getElementById("settings-cleanup-api-key"),
  cleanupApiKeyClear: document.getElementById("settings-cleanup-api-key-clear"),
  cleanupModel: document.getElementById("settings-cleanup-model"),
  cleanupPromptText: document.getElementById("settings-cleanup-prompt-text"),
  enableArticle: document.getElementById("settings-enable-article"),
  articleBaseUrl: document.getElementById("settings-article-base-url"),
  articleApiKey: document.getElementById("settings-article-api-key"),
  articleApiKeyClear: document.getElementById("settings-article-api-key-clear"),
  articleModel: document.getElementById("settings-article-model"),
  articlePromptText: document.getElementById("settings-article-prompt-text"),
  enableKnowledge: document.getElementById("settings-enable-knowledge"),
  knowledgeBaseUrl: document.getElementById("settings-knowledge-base-url"),
  knowledgeApiKey: document.getElementById("settings-knowledge-api-key"),
  knowledgeApiKeyClear: document.getElementById("settings-knowledge-api-key-clear"),
  knowledgeModel: document.getElementById("settings-knowledge-model"),
  knowledgePromptText: document.getElementById("settings-knowledge-prompt-text"),
};

const artifactPreviewLabels = {
  article: "解析稿",
  transcript: "逐字稿",
  knowledge: "知识库稿",
  raw: "原始逐字稿",
  metadata: "转写信息",
};

let latestTasks = [];
let selectedTaskId = null;
let activePanel = "queue";
const webTokenStorageKey = "mukuWebToken";
let autoPromptedForWebToken = false;
let selectedArtifactKind = null;
const artifactPreviewCache = new Map();
const artifactPreviewInFlight = new Map();
let isSubmitting = false;
let starterGuideTouched = false;

(function init() {
  hydrateWebTokenFromLocation();
  if (config.webTokenRequired && !readStoredWebToken()) {
    maybePromptForWebToken();
    autoPromptedForWebToken = true;
  }
  config.presets.forEach((preset) => {
    const opt = document.createElement("option");
    opt.value = opt.textContent = preset;
    presetSelect.appendChild(opt);
  });

  presetSelect.value = config.defaultPreset;
  cookiesCheckbox.checked = Boolean(config.cookiesConfigured);
  syncTopLevelConfig();
  hydrateSettings(config.settings);
  updateOverviewSummary();
  updateModeHint();
  updateCookiesHint();
  updateKnowledgeOption();
  updateDownloadDirHint();
  updateSubmitLabel();
  renderStarterGuide();
  bindEvents();
  setMonitorPanel("queue");

  setInterval(poll, 1500);
  poll();
})();

function bindEvents() {
  presetSelect.addEventListener("change", () => {
    updateModeHint();
    updateKnowledgeOption();
    updateSubmitLabel();
  });

  urlInput.addEventListener("input", () => {
    clearTaskFeedback();
    updateSubmitLabel();
  });

  pasteClipboardBtn.addEventListener("click", pasteUrlFromClipboard);
  clearUrlBtn.addEventListener("click", clearUrlField);
  cookiesCheckbox.addEventListener("change", updateSubmitLabel);
  downloadDirInput.addEventListener("input", updateDownloadDirHint);
  starterGuideSummary.addEventListener("click", () => {
    starterGuideTouched = true;
  });
  starterGuide.addEventListener("toggle", updateStarterGuideToggleLabel);

  form.addEventListener("submit", submitDownloadForm);
  settingsForm.addEventListener("submit", submitSettingsForm);
  settingsToggle.addEventListener("click", openSettingsDrawer);
  starterOpenSettings.addEventListener("click", openSettingsDrawer);
  settingsClose.addEventListener("click", closeSettingsDrawer);
  settingsBackdrop.addEventListener("click", closeSettingsDrawer);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && document.body.classList.contains("settings-open")) {
      closeSettingsDrawer();
    }
  });

  taskList.addEventListener("click", (event) => {
    const button = event.target.closest(".task-item-button");
    if (!button) {
      return;
    }
    selectedTaskId = button.dataset.taskId || null;
    selectedArtifactKind = null;
    setMonitorPanel("detail");
    renderTaskDetail();
    renderTaskList();
  });

  taskDetailContent.addEventListener("click", (event) => {
    const button = event.target.closest(".artifact-tab");
    if (!button) {
      return;
    }
    const taskId = button.dataset.taskId || null;
    const artifactKind = button.dataset.artifactKind || null;
    if (!taskId || !artifactKind) {
      return;
    }
    selectedTaskId = taskId;
    selectedArtifactKind = artifactKind;
    renderTaskDetail();
  });

  monitorTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      setMonitorPanel(tab.dataset.panelTarget || "queue");
    });
  });
}

async function submitDownloadForm(event) {
  event.preventDefault();
  const url = urlInput.value;
  const preset = presetSelect.value;
  const cookies = cookiesCheckbox.checked;
  const generateTranscript = preset === config.transcriptPreset;
  const generateKnowledge = generateKnowledgeCheckbox.checked && !generateKnowledgeCheckbox.disabled;
  const downloadDir = downloadDirInput.value.trim();

  isSubmitting = true;
  showTaskFeedback("info", "正在把任务加入队列，马上会切到右侧观察面板。");
  updateSubmitLabel();

  try {
    const res = await apiFetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        preset,
        use_cookies: cookies,
        generate_transcript: generateTranscript,
        generate_knowledge: generateKnowledge,
        download_dir: downloadDir,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    const jobIds = Array.isArray(data.job_ids) ? data.job_ids : [];
    if (jobIds.length) {
      selectedTaskId = jobIds[0];
      selectedArtifactKind = null;
    }
    urlInput.value = "";
    downloadDirInput.value = "";
    generateKnowledgeCheckbox.checked = false;
    taskAdvanced.open = false;
    updateDownloadDirHint();
    updateKnowledgeOption();
    await poll();
    setMonitorPanel(jobIds.length ? "detail" : "queue");
    renderTaskDetail();
    showTaskFeedback(
      "success",
      data.count > 1
        ? `已接收 ${data.count} 条任务，右侧已经切到观察面板。`
        : "任务已加入队列，右侧已经切到观察面板。",
    );
    if (window.innerWidth < 1120) {
      document.querySelector(".monitor-column")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } catch (err) {
    const failure = explainSubmitFailure(err?.message || String(err));
    if (failure.openAdvanced) {
      taskAdvanced.open = true;
    }
    if (failure.openSettings) {
      openSettingsDrawer();
    }
    if (failure.focusUrl) {
      focusUrlInput();
    }
    showTaskFeedback("error", failure.message);
  } finally {
    isSubmitting = false;
    updateSubmitLabel();
  }
}

async function submitSettingsForm(event) {
  event.preventDefault();
  saveSettingsBtn.disabled = true;
  settingsStatus.textContent = "保存中...";

  try {
    const payload = collectSettingsPayload();
    const res = await apiFetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    applySettings(data);
    settingsStatus.textContent = "已保存。新任务会使用这组默认配置。";
  } catch (err) {
    settingsStatus.textContent = "保存失败: " + (err?.message || err);
  } finally {
    saveSettingsBtn.disabled = false;
  }
}

async function poll() {
  try {
    const shouldPromptForToken = !autoPromptedForWebToken;
    autoPromptedForWebToken = true;
    const res = await apiFetch("/api/tasks", {}, { promptForToken: shouldPromptForToken });
    const data = await res.json();
    latestTasks = Array.isArray(data.tasks) ? data.tasks : [];
    if (!selectedTaskId && latestTasks.length) {
      selectedTaskId = latestTasks[0].id;
    }
    if (selectedTaskId && !latestTasks.some((task) => task.id === selectedTaskId)) {
      selectedTaskId = latestTasks[0]?.id || null;
      selectedArtifactKind = null;
    }
    updateQueueSummary(latestTasks);
    renderTaskList();
    renderTaskDetail();
    renderStarterGuide();
  } catch (err) {
    return;
  }
}

async function apiFetch(url, options = {}, authOptions = {}) {
  const promptForToken = authOptions.promptForToken !== false;
  const requestOptions = withAuthHeader(options);
  let res = await fetch(url, requestOptions);

  if (res.status !== 401 || !config.webTokenRequired || !promptForToken) {
    return res;
  }

  if (!maybePromptForWebToken({ force: true })) {
    return res;
  }

  res = await fetch(url, withAuthHeader(options));
  return res;
}

function withAuthHeader(options = {}) {
  const headers = new Headers(options.headers || {});
  const token = readStoredWebToken();
  if (token) {
    headers.set("X-Muku-Web-Token", token);
  }

  return {
    ...options,
    headers,
  };
}

function hydrateWebTokenFromLocation() {
  const hashParams = new URLSearchParams(window.location.hash.slice(1));
  const token = hashParams.get("token") || "";
  if (token) {
    writeStoredWebToken(token);
    hashParams.delete("token");
    const nextHash = hashParams.toString();
    const nextUrl = `${window.location.pathname}${window.location.search}${nextHash ? `#${nextHash}` : ""}`;
    window.history.replaceState(null, "", nextUrl);
    return;
  }

  const params = new URLSearchParams(window.location.search);
  if (params.has("token")) {
    params.delete("token");
    const nextSearch = params.toString();
    const nextUrl = `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ""}${window.location.hash}`;
    window.history.replaceState(null, "", nextUrl);
  }
}

function readStoredWebToken() {
  try {
    return window.sessionStorage.getItem(webTokenStorageKey) || "";
  } catch (err) {
    return "";
  }
}

function writeStoredWebToken(token) {
  try {
    window.sessionStorage.setItem(webTokenStorageKey, token);
  } catch (err) {
    return;
  }
}

function maybePromptForWebToken({ force = false } = {}) {
  if (!config.webTokenRequired) {
    return false;
  }

  const existing = readStoredWebToken();
  if (existing && !force) {
    return true;
  }

  const token = window.prompt("请输入 MUKU_WEB_TOKEN", force ? "" : existing);
  if (!token) {
    return false;
  }

  writeStoredWebToken(token.trim());
  return true;
}

function openSettingsDrawer() {
  document.body.classList.add("settings-open");
  settingsDrawer.setAttribute("aria-hidden", "false");
}

function closeSettingsDrawer() {
  document.body.classList.remove("settings-open");
  settingsDrawer.setAttribute("aria-hidden", "true");
}

function setMonitorPanel(panelName) {
  activePanel = panelName;
  monitorTabs.forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.panelTarget === panelName);
  });
  Object.entries(monitorPanels).forEach(([name, panel]) => {
    panel.classList.toggle("is-active", name === panelName);
  });
}

function updateQueueSummary(tasks) {
  const active = tasks.filter((task) => !task.done).length;
  const failed = tasks.filter((task) => Boolean(task.error)).length;
  const done = tasks.filter((task) => task.done && !task.error).length;

  activeCount.textContent = String(active);
  doneCount.textContent = String(done);
  failedCount.textContent = String(failed);
  queueCount.textContent = active > 0 ? `${active} 正在运行` : "空闲";
}

function renderTaskList() {
  if (!latestTasks.length) {
    taskList.innerHTML = `
      <li class="empty-state">
        暂无下载任务，去上面的入口粘贴一条吧。
      </li>`;
    return;
  }

  taskList.innerHTML = latestTasks
    .map((task) => {
      const selected = task.id === selectedTaskId;
      const toneClass = task.error ? "is-error" : task.done ? "is-done" : "is-running";
      const outputHint = task.knowledge_path
        ? `<div class="task-path">知识库: ${escapeHtml(task.knowledge_path)}</div>`
        : task.transcript_path
        ? `<div class="task-path">逐字稿: ${escapeHtml(task.transcript_path)}</div>`
        : task.download_path
          ? `<div class="task-path">文件: ${escapeHtml(task.download_path)}</div>`
          : "";
      const outputDirHint = task.output_dir
        ? `<div class="task-path">保存到: ${escapeHtml(task.output_dir)}</div>`
        : "";

      return `
        <li>
          <button type="button" class="task-item-button ${selected ? "is-selected" : ""}" data-task-id="${escapeHtml(task.id)}">
            <div class="task-status-dot ${toneClass}"></div>
            <div class="task-info">
              <div class="task-title" title="${escapeHtml(task.title)}">${escapeHtml(task.title)}</div>
              <div class="task-status ${toneClass}">
                ${escapeHtml(task.error ? task.error : task.status)}
              </div>
              <div class="task-path">模式: ${escapeHtml(describeTaskMode(task))}</div>
              ${outputDirHint}
              ${outputHint}
            </div>
            ${
              !task.done && !task.error
                ? `
              <div class="progress-track">
                <div class="progress-fill" style="width: ${task.progress}%"></div>
              </div>`
                : ""
            }
          </button>
        </li>`;
    })
    .join("");
}

function renderTaskDetail() {
  const task = latestTasks.find((item) => item.id === selectedTaskId);
  if (!task) {
    detailEmpty.style.display = "block";
    taskDetailContent.innerHTML = "";
    return;
  }

  detailEmpty.style.display = "none";
  const backendErrorBlock = task.error && task.backend_error
    ? renderDetailBlock("后端报错", task.backend_error)
    : "";
  const knowledgeErrorBlock = task.knowledge_error
    ? renderDetailBlock("知识库报错", task.knowledge_error)
    : "";
  const previewSection = renderArtifactPreviewSection(task);
  taskDetailContent.innerHTML = `
    <article class="detail-card">
      <div class="detail-head">
        <div>
          <p class="eyebrow">Selected Task</p>
          <h3>${escapeHtml(task.title || "未命名任务")}</h3>
        </div>
        <span class="detail-badge ${task.error ? "is-error" : task.done ? "is-done" : "is-running"}">
          ${escapeHtml(task.error ? "失败" : task.done ? "完成" : "运行中")}
        </span>
      </div>

      <div class="detail-grid">
        ${renderDetailItem("状态", task.error ? task.error : task.status)}
        ${renderDetailItem("模式", describeTaskMode(task))}
        ${renderDetailItem("进度", `${task.progress || 0}%`)}
        ${renderDetailItem("Provider", task.provider || "待定")}
      </div>

      <div class="detail-stack">
        ${renderDetailBlock("来源链接", task.source_url, true)}
        ${renderDetailBlock("保存目录", task.output_dir || config.settings.download_dir || "未显式指定")}
        ${renderDetailBlock("下载文件", task.download_path || "尚未生成")}
        ${renderDetailBlock("原始逐字稿", task.raw_path || "尚未生成")}
        ${renderDetailBlock("逐字稿", task.transcript_path || "尚未生成")}
        ${renderDetailBlock("解析稿", task.article_path || "尚未生成")}
        ${renderDetailBlock("知识库稿", task.generate_knowledge ? (task.knowledge_path || (task.knowledge_error ? "生成失败" : "尚未生成")) : "本次未请求")}
        ${renderDetailBlock("转写信息", task.metadata_path || "尚未生成")}
        ${renderDetailBlock("产物目录", task.artifact_dir || "尚未生成")}
        ${backendErrorBlock}
        ${knowledgeErrorBlock}
      </div>

      ${previewSection}
    </article>`;
}

function renderDetailItem(label, value) {
  return `
    <div class="detail-item">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value || "-")}</strong>
    </div>`;
}

function renderDetailBlock(label, value, isLink = false) {
  const content = isLink && value
    ? `<a href="${escapeHtml(value)}" target="_blank" rel="noreferrer">${escapeHtml(value)}</a>`
    : escapeHtml(value || "-");
  return `
    <div class="detail-block">
      <span>${escapeHtml(label)}</span>
      <div class="detail-block-value">${content}</div>
    </div>`;
}

function getAvailablePreviewArtifacts(task) {
  return [
    { kind: "article", path: task.article_path },
    { kind: "transcript", path: task.transcript_path },
    { kind: "knowledge", path: task.knowledge_path },
    { kind: "raw", path: task.raw_path },
    { kind: "metadata", path: task.metadata_path },
  ].filter((artifact) => Boolean(artifact.path));
}

function previewCacheKey(taskId, artifactKind, path) {
  return `${taskId}:${artifactKind}:${path}`;
}

function ensureSelectedArtifact(task, artifacts) {
  if (!artifacts.length) {
    selectedArtifactKind = null;
    return null;
  }

  if (!artifacts.some((artifact) => artifact.kind === selectedArtifactKind)) {
    selectedArtifactKind = artifacts[0].kind;
  }

  const selected = artifacts.find((artifact) => artifact.kind === selectedArtifactKind) || artifacts[0];
  loadArtifactPreview(task, selected);
  return selected;
}

function renderArtifactPreviewSection(task) {
  const artifacts = getAvailablePreviewArtifacts(task);
  if (!artifacts.length) {
    return `
      <section class="detail-preview-card">
        <div class="detail-preview-head">
          <span class="detail-preview-label">产物预览</span>
        </div>
        <div class="detail-preview-empty">当前还没有可预览的文本产物。等逐字稿或解析稿生成后，这里会直接展示内容。</div>
      </section>`;
  }

  const selected = ensureSelectedArtifact(task, artifacts);
  const previewState = getArtifactPreviewState(task, selected);
  const selectedLabel = artifactPreviewLabels[selected.kind] || selected.kind;
  const previewStatus = previewState
    ? previewState.status
    : "idle";
  let previewBody = "正在加载预览...";

  if (previewStatus === "ready") {
    previewBody = escapeHtml(previewState.content || "");
  } else if (previewStatus === "error") {
    previewBody = `预览失败：${escapeHtml(previewState.error || "unknown error")}`;
  }

  const truncatedNote = previewStatus === "ready" && previewState.truncated
    ? `<p class="detail-preview-note">内容较长，当前只展示前一部分。</p>`
    : "";
  const pathHint = previewState && previewState.path
    ? `<div class="detail-preview-path">${escapeHtml(previewState.path)}</div>`
    : selected.path
      ? `<div class="detail-preview-path">${escapeHtml(selected.path)}</div>`
      : "";

  return `
    <section class="detail-preview-card">
      <div class="detail-preview-head">
        <span class="detail-preview-label">产物预览</span>
        <div class="detail-preview-tabs">
          ${artifacts
            .map((artifact) => `
              <button
                type="button"
                class="artifact-tab ${artifact.kind === selected.kind ? "is-active" : ""}"
                data-task-id="${escapeHtml(task.id)}"
                data-artifact-kind="${escapeHtml(artifact.kind)}"
              >
                ${escapeHtml(artifactPreviewLabels[artifact.kind] || artifact.kind)}
              </button>
            `)
            .join("")}
        </div>
      </div>
      <div class="detail-preview-meta">
        <strong>${escapeHtml(selectedLabel)}</strong>
        ${pathHint}
      </div>
      ${truncatedNote}
      <pre class="detail-preview-body is-${escapeHtml(previewStatus)}">${previewBody}</pre>
    </section>`;
}

function getArtifactPreviewState(task, artifact) {
  if (!task || !artifact || !artifact.path) {
    return null;
  }
  return artifactPreviewCache.get(previewCacheKey(task.id, artifact.kind, artifact.path)) || null;
}

function loadArtifactPreview(task, artifact) {
  if (!task || !artifact || !artifact.path) {
    return;
  }

  const key = previewCacheKey(task.id, artifact.kind, artifact.path);
  const existing = artifactPreviewCache.get(key);
  if (existing && (existing.status === "ready" || existing.status === "loading" || existing.status === "error")) {
    return;
  }
  if (artifactPreviewInFlight.has(key)) {
    return;
  }

  artifactPreviewCache.set(key, {
    status: "loading",
    content: "",
    path: artifact.path,
    truncated: false,
  });

  const request = apiFetch(`/api/tasks/${encodeURIComponent(task.id)}/artifacts/${encodeURIComponent(artifact.kind)}`)
    .then(async (res) => {
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.error || `HTTP ${res.status}`);
      }
      artifactPreviewCache.set(key, {
        status: "ready",
        content: data.content || "",
        path: data.path || artifact.path,
        truncated: Boolean(data.truncated),
      });
    })
    .catch((error) => {
      artifactPreviewCache.set(key, {
        status: "error",
        error: error?.message || String(error),
        path: artifact.path,
        truncated: false,
      });
    })
    .finally(() => {
      artifactPreviewInFlight.delete(key);
      if (selectedTaskId === task.id && selectedArtifactKind === artifact.kind) {
        renderTaskDetail();
      }
    });

  artifactPreviewInFlight.set(key, request);
}

function collectSettingsPayload() {
  const payload = {
    download_dir: settingsElements.downloadDir.value.trim(),
    openrouter_base_url: settingsElements.openrouterBaseUrl.value.trim(),
    openrouter_site_url: settingsElements.openrouterSiteUrl.value.trim(),
    openrouter_app_name: settingsElements.openrouterAppName.value.trim(),
    openrouter_transcription_model: settingsElements.openrouterTranscriptionModel.value.trim(),
    openrouter_article_model: settingsElements.openrouterArticleModel.value.trim(),
    enable_ai_cleanup: settingsElements.enableCleanup.checked,
    ai_cleanup_base_url: settingsElements.cleanupBaseUrl.value.trim(),
    ai_cleanup_model: settingsElements.cleanupModel.value.trim(),
    ai_cleanup_prompt_text: settingsElements.cleanupPromptText.value.trim(),
    enable_article_draft: settingsElements.enableArticle.checked,
    article_draft_base_url: settingsElements.articleBaseUrl.value.trim(),
    article_draft_model: settingsElements.articleModel.value.trim(),
    article_draft_prompt_text: settingsElements.articlePromptText.value.trim(),
    enable_knowledge_draft: settingsElements.enableKnowledge.checked,
    knowledge_draft_base_url: settingsElements.knowledgeBaseUrl.value.trim(),
    knowledge_draft_model: settingsElements.knowledgeModel.value.trim(),
    knowledge_draft_prompt_text: settingsElements.knowledgePromptText.value.trim(),
  };
  addSecretSetting(
    payload,
    "openrouter_api_key",
    settingsElements.openrouterApiKey,
    settingsElements.openrouterApiKeyClear,
  );
  addSecretSetting(
    payload,
    "ai_cleanup_api_key",
    settingsElements.cleanupApiKey,
    settingsElements.cleanupApiKeyClear,
  );
  addSecretSetting(
    payload,
    "article_draft_api_key",
    settingsElements.articleApiKey,
    settingsElements.articleApiKeyClear,
  );
  addSecretSetting(
    payload,
    "knowledge_draft_api_key",
    settingsElements.knowledgeApiKey,
    settingsElements.knowledgeApiKeyClear,
  );
  return payload;
}

function addSecretSetting(payload, key, input, clearCheckbox) {
  if (clearCheckbox.checked) {
    payload[key] = "";
    return;
  }
  const value = input.value.trim();
  if (value) {
    payload[key] = value;
  }
}

function applySettings(settings) {
  config.settings = settings || {};
  syncTopLevelConfig(settings);
  hydrateSettings(config.settings);
  updateOverviewSummary();
  updateModeHint();
  updateCookiesHint();
  updateKnowledgeOption();
  updateDownloadDirHint();
  updateSubmitLabel();
  renderStarterGuide();
}

function hydrateSettings(settings) {
  settingsElements.downloadDir.value = settings.download_dir || "";
  settingsElements.openrouterBaseUrl.value = settings.openrouter_base_url || "";
  hydrateSecretSetting(
    settingsElements.openrouterApiKey,
    settingsElements.openrouterApiKeyClear,
    settings.openrouter_api_key_configured,
  );
  settingsElements.openrouterSiteUrl.value = settings.openrouter_site_url || "";
  settingsElements.openrouterAppName.value = settings.openrouter_app_name || "幕库 Muku";
  settingsElements.openrouterTranscriptionModel.value = settings.openrouter_transcription_model || "";
  settingsElements.openrouterArticleModel.value = settings.openrouter_article_model || "";
  settingsElements.enableCleanup.checked = Boolean(settings.enable_ai_cleanup);
  settingsElements.cleanupBaseUrl.value = settings.ai_cleanup_base_url || "";
  hydrateSecretSetting(
    settingsElements.cleanupApiKey,
    settingsElements.cleanupApiKeyClear,
    settings.ai_cleanup_api_key_configured,
  );
  settingsElements.cleanupModel.value = settings.ai_cleanup_model || "";
  settingsElements.cleanupPromptText.value = settings.ai_cleanup_prompt_text || "";
  settingsElements.enableArticle.checked = Boolean(settings.enable_article_draft);
  settingsElements.articleBaseUrl.value = settings.article_draft_base_url || "";
  hydrateSecretSetting(
    settingsElements.articleApiKey,
    settingsElements.articleApiKeyClear,
    settings.article_draft_api_key_configured,
  );
  settingsElements.articleModel.value = settings.article_draft_model || "";
  settingsElements.articlePromptText.value = settings.article_draft_prompt_text || "";
  settingsElements.enableKnowledge.checked = Boolean(settings.enable_knowledge_draft);
  settingsElements.knowledgeBaseUrl.value = settings.knowledge_draft_base_url || "";
  hydrateSecretSetting(
    settingsElements.knowledgeApiKey,
    settingsElements.knowledgeApiKeyClear,
    settings.knowledge_draft_api_key_configured,
  );
  settingsElements.knowledgeModel.value = settings.knowledge_draft_model || "";
  settingsElements.knowledgePromptText.value = settings.knowledge_draft_prompt_text || "";

  settingsFileHint.textContent = `配置文件: ${settings.settings_path || "未初始化"}`;
  if (settings.download_root_locked && settings.download_root_dir) {
    settingsRootHint.textContent =
      `当前下载根目录锁定为 ${settings.download_root_dir}。网页里可以改默认目录和本次任务目录，但都必须位于这个根目录内；要改宿主机真实映射目录，请调整 Docker 的 DOCKER_DOWNLOADS_DIR。`;
  } else if (settings.download_dir) {
    settingsRootHint.textContent = `当前默认下载目录: ${settings.download_dir}。macOS 和 Windows 本地运行时，建议使用绝对路径。`;
  } else {
    settingsRootHint.textContent = "当前未设置默认下载目录，系统会回退到用户下载文件夹。";
  }
}

function hydrateSecretSetting(input, clearCheckbox, configured) {
  input.value = "";
  input.placeholder = configured ? "已配置，留空不变" : "未配置，粘贴新 key";
  clearCheckbox.checked = false;
  clearCheckbox.disabled = !configured;
}

function syncTopLevelConfig(settings = config.settings) {
  config.transcriptionModel = settings.openrouter_transcription_model || config.transcriptionModel;
  config.aiCleanupEnabled = Boolean(settings.enable_ai_cleanup);
  config.aiCleanupModel = settings.ai_cleanup_model || config.aiCleanupModel;
  config.articleDraftEnabled = Boolean(settings.enable_article_draft);
  config.articleDraftModel = settings.article_draft_model || config.articleDraftModel;
  config.runtimeEnvironment = settings.runtime_environment || config.runtimeEnvironment || "local";
  if (settings.platform_auth) {
    config.platformAuth = settings.platform_auth;
  } else if (settings.platformAuth) {
    config.platformAuth = settings.platformAuth;
  }
  if ("cookiesConfigured" in settings) {
    config.cookiesConfigured = Boolean(settings.cookiesConfigured);
  }
  if ("cookiesVerified" in settings) {
    config.cookiesVerified = Boolean(settings.cookiesVerified);
  }
  if ("youtube_auth_configured" in settings) {
    config.youtubeAuthConfigured = Boolean(settings.youtube_auth_configured);
  }
  if ("youtube_auth_verified" in settings) {
    config.youtubeAuthVerified = Boolean(settings.youtube_auth_verified);
  }
  if ("bilibili_auth_configured" in settings) {
    config.bilibiliAuthConfigured = Boolean(settings.bilibili_auth_configured);
  }
  if ("bilibili_auth_verified" in settings) {
    config.bilibiliAuthVerified = Boolean(settings.bilibili_auth_verified);
  }
  if ("douyin_auth_configured" in settings) {
    config.douyinAuthConfigured = Boolean(settings.douyin_auth_configured);
  }
  if ("douyin_auth_verified" in settings) {
    config.douyinAuthVerified = Boolean(settings.douyin_auth_verified);
  }
}

function updateOverviewSummary() {
  summaryDownloadDir.textContent = config.settings.download_dir || "系统默认下载目录";
  summaryModel.textContent = config.transcriptionModel || "未设置";

  const configuredPlatforms = collectAuthPlatforms();
  const verifiedPlatforms = collectAuthPlatforms({ verifiedOnly: true });
  const configuredOnlyPlatforms = configuredPlatforms.filter((platform) => !verifiedPlatforms.includes(platform));

  if (!configuredPlatforms.length) {
    summaryAuth.textContent = "未配置";
    return;
  }

  if (!configuredOnlyPlatforms.length) {
    summaryAuth.textContent = `已验证 ${verifiedPlatforms.join(" / ")}`;
    return;
  }

  if (!verifiedPlatforms.length) {
    summaryAuth.textContent = `已配置 ${configuredPlatforms.join(" / ")}`;
    return;
  }

  summaryAuth.textContent = `已验证 ${verifiedPlatforms.join(" / ")}；仅配置 ${configuredOnlyPlatforms.join(" / ")}`;
}

function updateSubmitLabel() {
  const preset = presetSelect.value;
  let nextAction = "开始下载视频";
  let readyHint = "会直接下载最高画质视频。";
  if (preset === config.transcriptPreset) {
    nextAction = "开始提取逐字稿";
    readyHint = "会先尝试平台字幕，失败后再自动回退到音频转写。";
  } else if (preset === config.audioPreset) {
    nextAction = "开始下载 MP3";
    readyHint = "只下载 MP3 音频，不会自动生成 Markdown。";
  }
  startBtn.textContent = isSubmitting ? "提交中..." : nextAction;
  startBtn.disabled = isSubmitting || !urlInput.value.trim();
  if (isSubmitting) {
    taskSubmitHelp.textContent = "正在把任务加入队列，右侧马上会显示新状态。";
  } else if (urlInput.value.trim()) {
    taskSubmitHelp.textContent = `${readyHint} 提交后右侧会自动切到观察面板。`;
  } else {
    taskSubmitHelp.textContent = "先把链接贴进上面的输入框；支持直接粘贴整段分享文案。";
  }
  updateTaskEntrySummary();
}

function renderStarterGuide() {
  const state = buildStarterGuideState();
  starterGuide.classList.toggle("is-ready", state.coreReady);
  starterGuide.classList.toggle("is-setup", !state.coreReady);
  if (!starterGuideTouched) {
    starterGuide.open = !state.coreReady && latestTasks.length === 0;
  }
  starterTitle.textContent = state.title;
  starterSubtitle.textContent = state.subtitle;
  starterProgress.textContent = `${state.completed} / ${state.total}`;
  starterChecklist.innerHTML = state.steps.map(renderStarterStep).join("");
  starterPlatforms.innerHTML = state.platforms.map(renderPlatformPill).join("");
  starterCallout.innerHTML = `
    <strong>${escapeHtml(state.callout.title)}</strong>
    <p>${escapeHtml(state.callout.body)}</p>
  `;
  starterOpenSettings.textContent = state.primaryActionLabel;
  updateStarterGuideToggleLabel();
}

function buildStarterGuideState() {
  const authPlatforms = collectAuthPlatforms();
  const verifiedPlatforms = collectAuthPlatforms({ verifiedOnly: true });
  const configuredOnlyPlatforms = authPlatforms.filter((platform) => !verifiedPlatforms.includes(platform));
  const hasDownloadDir = Boolean(config.settings.download_dir || config.settings.download_root_dir);
  const transcriptionReady = Boolean(
    config.transcriptionEnabled &&
      config.settings.openrouter_api_key_configured &&
      (config.transcriptionModel || config.settings.openrouter_transcription_model),
  );
  const cleanupReady = !config.aiCleanupEnabled || Boolean(config.settings.ai_cleanup_api_key_configured);
  const articleReady = !config.articleDraftEnabled || Boolean(config.settings.article_draft_api_key_configured);
  const knowledgeEnabled = Boolean(config.settings.enable_knowledge_draft);
  const knowledgeReady = !knowledgeEnabled || Boolean(config.settings.knowledge_draft_api_key_configured);
  const webPipelineReady = cleanupReady && articleReady;
  const hasRunTask = latestTasks.length > 0;

  const steps = [
    {
      title: "确认默认下载目录",
      detail: hasDownloadDir
        ? `当前默认目录：${config.settings.download_dir || config.settings.download_root_dir}`
        : "建议先在设置里保存默认下载目录；Docker 推荐 /downloads/default。",
      done: hasDownloadDir,
      tone: hasDownloadDir ? "done" : "todo",
      badge: hasDownloadDir ? "已就绪" : "必需",
    },
    {
      title: "配置转写服务",
      detail: transcriptionReady
        ? `当前转写模型：${config.transcriptionModel || config.settings.openrouter_transcription_model}`
        : "先配置转写 API Key 和模型；逐字稿模式更稳。",
      done: transcriptionReady,
      tone: transcriptionReady ? "done" : "todo",
      badge: transcriptionReady ? "已就绪" : "必需",
    },
    {
      title: "检查整理链路",
      detail: webPipelineReady
        ? (
          knowledgeReady
            ? "Web 默认会直接使用清洗稿 / 解析稿配置；如果你勾选知识库稿，也会继续使用当前知识库整理配置。"
            : "Web 默认会直接使用清洗稿 / 解析稿配置；知识库整理配置还没配齐，但这不会阻止网页任务先跑通。"
        )
        : "如果你只想先验证 Web 能跑通，可以先保留逐字稿和解析稿链路，知识库整理稍后再补。",
      done: webPipelineReady,
      tone: webPipelineReady ? "done" : "warn",
      badge: webPipelineReady ? "已就绪" : "推荐",
    },
    {
      title: "发起第一条任务",
      detail: hasRunTask
        ? `当前工作台已经收到 ${latestTasks.length} 条任务，可以继续观察结果。`
        : "先试一条公开的 Bilibili / YouTube / Douyin 链接，验证链路跑通。",
      done: hasRunTask,
      tone: hasRunTask ? "done" : hasDownloadDir && transcriptionReady ? "ready" : "todo",
      badge: hasRunTask ? "已开始" : "下一步",
    },
  ];

  let title = "第一次使用导航";
  let subtitle = "先完成核心配置，再发起第一条任务。";
  let callout = {
    title: "建议先做什么",
    body: "打开设置，先保存默认下载目录和转写服务配置；你不需要第一次就把所有模型都配满。",
  };
  let primaryActionLabel = "打开设置";

  if (hasDownloadDir && transcriptionReady && !hasRunTask) {
    title = "核心配置已就绪";
    subtitle = "现在可以直接在上面的输入框里粘贴一条链接，先验证第一次逐字稿任务。";
    callout = {
      title: verifiedPlatforms.length
        ? "可以开始第一次任务"
        : "可以先试公开视频",
      body: verifiedPlatforms.length
        ? configuredOnlyPlatforms.length
          ? `已验证 ${verifiedPlatforms.join(" / ")}，另外 ${configuredOnlyPlatforms.join(" / ")} 目前只是已配置，建议先拿一条真实链接试跑。`
          : `已验证 ${verifiedPlatforms.join(" / ")} 登录态，优先试一条你最常用平台的链接。`
        : authPlatforms.length
          ? config.runtimeEnvironment === "container"
            ? `已检测到 ${authPlatforms.join(" / ")} 登录态配置，但容器里浏览器登录态仍需要实测。Docker 更稳的默认方案仍是平台专用 cookies.txt。`
            : `已检测到 ${authPlatforms.join(" / ")} 登录态配置，但浏览器登录态仍需要实测；如果你想要更强的可验证性，可以改用对应平台的 cookies.txt。`
          : "核心配置已经到位。公开视频通常可以先试跑；受限内容再补对应平台的 cookies.txt。",
    };
    primaryActionLabel = "查看设置";
  }

  if (hasRunTask) {
    title = "工作台已启动";
    subtitle = "你已经不是第一次使用状态了，后续可以继续批量导入，或补齐平台专用 cookies / 本机登录态。";
    callout = {
      title: "下一步建议",
      body: verifiedPlatforms.length || authPlatforms.length
        ? configuredOnlyPlatforms.length
          ? config.runtimeEnvironment === "container"
            ? `如果你准备提高多平台稳定性，下一步优先把 ${configuredOnlyPlatforms.join(" / ")} 改成可验证的 cookies.txt，或至少跑一条真实链接做实测。`
            : `如果你准备提高多平台稳定性，下一步优先把 ${configuredOnlyPlatforms.join(" / ")} 从浏览器登录态补成可复用的 cookies.txt，或至少跑一条真实链接做实测。`
          : "如果你准备提高多平台稳定性，可以继续把没配齐的平台专用 cookies 或本机登录态补完整。"
        : "如果后续要跑 YouTube / Douyin 或受限内容，优先补对应平台的专用 cookies.txt。",
    };
    primaryActionLabel = "继续完善设置";
  }

  const platforms = [
    {
      name: "YouTube",
      ready: getPlatformAuthState("youtube").verified,
      summary: summarizePlatformAuth(getPlatformAuthState("youtube")),
    },
    {
      name: "Bilibili",
      ready: getPlatformAuthState("bilibili").verified,
      summary: summarizePlatformAuth(getPlatformAuthState("bilibili")),
    },
    {
      name: "Douyin",
      ready: getPlatformAuthState("douyin").verified,
      summary: summarizePlatformAuth(getPlatformAuthState("douyin")),
    },
  ];

  return {
    title,
    subtitle,
    callout,
    primaryActionLabel,
    steps,
    platforms,
    completed: steps.filter((step) => step.done).length,
    total: steps.length,
    coreReady: hasDownloadDir && transcriptionReady,
  };
}

function renderStarterStep(step) {
  return `
    <li class="starter-step is-${escapeHtml(step.tone)}">
      <div class="starter-step-copy">
        <strong>${escapeHtml(step.title)}</strong>
        <p>${escapeHtml(step.detail)}</p>
      </div>
      <span class="starter-step-badge">${escapeHtml(step.badge)}</span>
    </li>`;
}

function renderPlatformPill(platform) {
  return `
    <article class="platform-pill ${platform.ready ? "is-ready" : "is-idle"}">
      <span>${escapeHtml(platform.name)}</span>
      <strong>${escapeHtml(platform.summary)}</strong>
    </article>`;
}

function updateStarterGuideToggleLabel() {
  starterToggleLabel.textContent = starterGuide.open ? "收起详情" : "展开详情";
}

function updateModeHint() {
  const preset = presetSelect.value;
  const modelHint = config.transcriptionModel ? `当前默认转写模型：${config.transcriptionModel}。` : "";

  if (preset === config.transcriptPreset) {
    if (!config.transcriptionEnabled || !config.settings.openrouter_api_key_configured) {
      modeHint.textContent =
        "当前处于逐字稿模式，但还没完成转写服务配置。你仍然可以先试平台直提字幕；如果要稳定跑通第一次任务，建议先打开设置补齐转写 API Key。";
      return;
    }

    const authPlatforms = collectAuthPlatforms();
    const verifiedPlatforms = collectAuthPlatforms({ verifiedOnly: true });
    const configuredOnlyPlatforms = authPlatforms.filter((platform) => !verifiedPlatforms.includes(platform));

    let cookiesNote = "当前未检测到平台登录态，YouTube、Douyin 和部分 B 站视频在受限场景下更可能回退到音频转写。";
    if (verifiedPlatforms.length === 3) {
      cookiesNote = "已验证 YouTube / Bilibili / Douyin 登录态，平台读取成功率会更高。";
    } else if (verifiedPlatforms.length >= 1 && configuredOnlyPlatforms.length === 0) {
      cookiesNote = `当前已验证 ${verifiedPlatforms.join(" / ")} 登录态，对应平台会更稳。`;
    } else if (verifiedPlatforms.length >= 1) {
      cookiesNote = `当前已验证 ${verifiedPlatforms.join(" / ")}，另外 ${configuredOnlyPlatforms.join(" / ")} 还只是已配置，仍建议先做一次真实链接实测。`;
    } else if (authPlatforms.length >= 1) {
      cookiesNote = config.runtimeEnvironment === "container"
        ? `当前已检测到 ${authPlatforms.join(" / ")} 登录态配置，但容器里浏览器登录态无法预检；更稳的默认方案仍是平台专用 cookies.txt。`
        : `当前已检测到 ${authPlatforms.join(" / ")} 登录态配置，但浏览器登录态仍需要实测；如果你想要更强的可验证性，可以改用对应平台的 cookies.txt。`;
    }

    modeHint.textContent =
      `当前会先尝试直接提取平台字幕；如果没有可用字幕，再自动下载 MP3 并转写，最后生成逐字稿和解析稿。若你勾选知识库稿，还会继续生成 \`知识库.md\`。${modelHint}${cookiesNote}`;
    return;
  }

  if (preset === config.audioPreset) {
    modeHint.textContent = "当前只下载 MP3 音频，不自动生成 Markdown 逐字稿。";
    return;
  }

  modeHint.textContent = "当前下载最高画质视频，优先保留高分辨率并合并为 MP4。";
}

function updateTaskEntrySummary() {
  const preset = presetSelect.value;
  const verifiedPlatforms = collectAuthPlatforms({ verifiedOnly: true });
  const configuredPlatforms = collectAuthPlatforms();
  let modeSummary = "默认模式：逐字稿优先，先试平台字幕，再自动回退到音频转写。";
  if (preset === config.audioPreset) {
    modeSummary = "当前模式：只下载 MP3 音频，不会自动生成 Markdown。";
  } else {
    modeSummary = "当前模式：下载最高画质视频，适合先把素材保存下来。";
  }

  let authSummary = "当前没有已验证登录态，先试一条公开视频即可。";
  if (verifiedPlatforms.length) {
    authSummary = `已验证 ${verifiedPlatforms.join(" / ")}，遇到受限内容时更稳。`;
  } else if (configuredPlatforms.length) {
    authSummary = `已检测到 ${configuredPlatforms.join(" / ")} 配置，真实可用性仍要拿一条链接实测。`;
  }

  const cookiesSummary = cookiesCheckbox.checked
    ? "这次会优先带上可用 Cookies。"
    : "如果链接受限，再打开 Cookies 即可。";
  taskEntrySummary.textContent = `${modeSummary} ${authSummary} ${cookiesSummary}`;
}

function updateKnowledgeOption() {
  const preset = presetSelect.value;
  const knowledgeEnabled = Boolean(config.settings.enable_knowledge_draft);
  const knowledgeConfigured = Boolean(config.settings.knowledge_draft_api_key_configured);
  const knowledgeReady = knowledgeEnabled && knowledgeConfigured;

  if (preset !== config.transcriptPreset) {
    generateKnowledgeCheckbox.checked = false;
    generateKnowledgeCheckbox.disabled = true;
    knowledgeOptionHint.textContent = "知识库稿依赖 Markdown 逐字稿模式。";
    return;
  }

  if (!knowledgeEnabled) {
    generateKnowledgeCheckbox.checked = false;
    generateKnowledgeCheckbox.disabled = true;
    knowledgeOptionHint.textContent = "当前还没有启用知识库整理配置；如需网页直接生成知识库稿，请先在设置里开启。";
    return;
  }

  if (!knowledgeConfigured) {
    generateKnowledgeCheckbox.checked = false;
    generateKnowledgeCheckbox.disabled = true;
    knowledgeOptionHint.textContent = "当前还没有配置知识库 API Key；补齐后才能在网页里直接生成知识库稿。";
    return;
  }

  generateKnowledgeCheckbox.disabled = false;
  knowledgeOptionHint.textContent = "可选：逐字稿和解析稿完成后，继续生成 `知识库.md`。";
}

function updateDownloadDirHint() {
  const defaultDir = config.settings.download_dir || "系统默认下载目录";
  const taskDir = downloadDirInput.value.trim();
  downloadDirInput.placeholder = defaultDir;

  if (taskDir) {
    downloadDirHint.textContent = `这次任务将保存到 ${taskDir}。`;
    return;
  }

  if (config.settings.download_root_locked && config.settings.download_root_dir) {
    downloadDirHint.textContent = `留空时会写入默认目录 ${defaultDir}。Docker 模式下可填写 ${config.settings.download_root_dir} 里的子目录。`;
    return;
  }

  downloadDirHint.textContent = `留空时会写入默认目录 ${defaultDir}。`;
}

function updateCookiesHint() {
  const authPlatforms = collectAuthPlatforms();
  const verifiedPlatforms = collectAuthPlatforms({ verifiedOnly: true });
  const configuredOnlyPlatforms = authPlatforms.filter((platform) => !verifiedPlatforms.includes(platform));

  if (!authPlatforms.length) {
    cookiesHint.textContent =
      "当前未检测到平台登录态。Docker / 容器环境更稳的默认方案是对应平台的 cookies.txt；本地 Python 运行时也可以尝试 *_COOKIES_FROM_BROWSER。";
    return;
  }

  if (verifiedPlatforms.length && configuredOnlyPlatforms.length) {
    cookiesHint.textContent = `当前已验证 ${verifiedPlatforms.join("、")}；${configuredOnlyPlatforms.join("、")} 还只是已配置。勾选“启用 Cookies”后，会按平台优先使用对应来源。`;
    return;
  }

  if (verifiedPlatforms.length > 1) {
    cookiesHint.textContent = `当前已验证 ${verifiedPlatforms.join("、")} 登录态。勾选“启用 Cookies”后，会按平台优先选择对应登录态。`;
    return;
  }

  if (!verifiedPlatforms.length) {
    cookiesHint.textContent = config.runtimeEnvironment === "container"
      ? `当前已检测到 ${authPlatforms.join("、")} 登录态配置，但容器里浏览器登录态无法预检。更稳的默认方案仍是对应平台的 cookies.txt。`
      : `当前已检测到 ${authPlatforms.join("、")} 登录态配置，但 doctor 只能确认“已配置”，是否可用仍需要拿真实链接实测。`;
    return;
  }

  if (getPlatformAuthState("youtube").verified) {
    cookiesHint.textContent = "当前已验证 YouTube 登录态。勾选“启用 Cookies”后，会优先用 YouTube 登录态访问下载和字幕接口。";
    return;
  }
  if (getPlatformAuthState("bilibili").verified) {
    cookiesHint.textContent = "当前已验证 Bilibili 登录态。勾选“启用 Cookies”后，会优先用 Bilibili 登录态访问平台字幕接口。";
    return;
  }
  cookiesHint.textContent = "当前已验证 Douyin 登录态。勾选“启用 Cookies”后，会优先用 Douyin 登录态访问抖音下载接口。";
}

function showTaskFeedback(tone, message) {
  taskFeedback.textContent = message;
  taskFeedback.className = `task-feedback is-${tone}`;
}

function clearTaskFeedback() {
  taskFeedback.textContent = "";
  taskFeedback.className = "task-feedback is-hidden";
}

function focusUrlInput() {
  urlInput.focus();
  const cursor = urlInput.value.length;
  urlInput.setSelectionRange(cursor, cursor);
}

function clearUrlField() {
  urlInput.value = "";
  clearTaskFeedback();
  updateSubmitLabel();
  focusUrlInput();
}

async function pasteUrlFromClipboard() {
  if (!navigator.clipboard?.readText) {
    showTaskFeedback("error", "当前浏览器不允许自动读取剪贴板，请直接按 Cmd+V / Ctrl+V 粘贴。");
    focusUrlInput();
    return;
  }

  try {
    const clipText = (await navigator.clipboard.readText()).trim();
    if (!clipText) {
      showTaskFeedback("error", "剪贴板现在是空的。先复制一条链接，再回来点“从剪贴板粘贴”。");
      focusUrlInput();
      return;
    }
    urlInput.value = clipText;
    updateSubmitLabel();
    showTaskFeedback("success", "已经把剪贴板内容填进输入框了，确认无误后直接开始即可。");
    focusUrlInput();
  } catch (err) {
    showTaskFeedback("error", "没能读取剪贴板。你可以直接按 Cmd+V / Ctrl+V 粘贴，或者检查浏览器权限。");
    focusUrlInput();
  }
}

function explainSubmitFailure(message) {
  const text = String(message || "").trim() || "unknown error";
  const lower = text.toLowerCase();

  if (text.includes("没有识别到可用链接") || text.includes("请输入有效的视频链接")) {
    return {
      message: `${text} 你可以直接粘贴原始 URL，也可以把整段分享文案原样贴进来。`,
      focusUrl: true,
    };
  }

  if (text.includes("最多提交")) {
    return {
      message: `${text} 先减少这次提交的链接数量，跑通后再继续批量导入。`,
      focusUrl: true,
    };
  }

  if (text.includes("下载根目录") || text.includes("download")) {
    return {
      message: `${text} 你可以先把“本次保存到”清空，先用默认目录试一次。`,
      openAdvanced: true,
    };
  }

  if (text.includes("知识库") || text.includes("API Key") || lower.includes("invalid preset")) {
    return {
      message: `${text} 我已经帮你保留当前输入，先补齐设置后再重试。`,
      openAdvanced: true,
      openSettings: text.includes("API Key") || text.includes("知识库"),
    };
  }

  return {
    message: `提交没有成功：${text}。先检查链接是否能打开；如果是受限内容，再勾选 Cookies 试一次。`,
  };
}

function getPlatformAuthState(platformKey) {
  const state = (config.platformAuth && config.platformAuth[platformKey]) || {};
  const legacyConfigured = {
    youtube: Boolean(config.youtubeAuthConfigured),
    bilibili: Boolean(config.bilibiliAuthConfigured),
    douyin: Boolean(config.douyinAuthConfigured),
  };
  const legacyVerified = {
    youtube: Boolean(config.youtubeAuthVerified),
    bilibili: Boolean(config.bilibiliAuthVerified),
    douyin: Boolean(config.douyinAuthVerified),
  };

  return {
    configured: Boolean("configured" in state ? state.configured : legacyConfigured[platformKey]),
    verified: Boolean("verified" in state ? state.verified : legacyVerified[platformKey]),
    status: state.status || "missing",
    source_kind: state.source_kind || "none",
    docker_risky: Boolean(state.docker_risky),
  };
}

function summarizePlatformAuth(state) {
  if (state.verified) {
    return "已验证";
  }
  if (state.configured) {
    if (state.status === "missing_file") {
      return "文件缺失";
    }
    return state.source_kind === "browser" ? "仅配置" : "待确认";
  }
  return "未配置";
}

function collectAuthPlatforms(options = {}) {
  const verifiedOnly = Boolean(options.verifiedOnly);
  const authPlatforms = [];
  [
    ["YouTube", "youtube"],
    ["Bilibili", "bilibili"],
    ["Douyin", "douyin"],
  ].forEach(([label, key]) => {
    const state = getPlatformAuthState(key);
    if (verifiedOnly ? state.verified : state.configured) {
      authPlatforms.push(label);
    }
  });
  return authPlatforms;
}

function describePreset(preset, route) {
  if (preset === config.transcriptPreset) {
    if (route === "direct_subtitles") {
      return "MD 逐字稿（直提字幕）";
    }
    if (route === "subtitle_probe_fallback_to_audio") {
      return "MD 逐字稿（字幕失败后回退音频转写）";
    }
    if (route === "douyin_audio_transcription") {
      return "MD 逐字稿（Douyin 音频转写）";
    }
    return "MD 逐字稿（字幕优先）";
  }
  if (preset === config.audioPreset) {
    return "MP3 音频";
  }
  return "最高画质视频";
}

function describeTaskMode(task) {
  const base = describePreset(task.preset, task.transcript_route);
  if (task.generate_knowledge) {
    return `${base} + 知识库稿`;
  }
  return base;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
