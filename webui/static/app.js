const config = window.APP_CONFIG || {};
config.settings = config.settings || {};
config.platformAuth = config.platformAuth || {};

const presetSelect = document.getElementById("preset");
const taskList = document.getElementById("task-list");
const form = document.getElementById("download-form");
const urlInput = document.getElementById("url");
const startBtn = document.getElementById("start-btn");
const queueCount = document.getElementById("queue-count");
const modeHint = document.getElementById("mode-hint");
const cookiesHint = document.getElementById("cookies-hint");
const cookiesCheckbox = document.getElementById("use-cookies");
const generateKnowledgeCheckbox = document.getElementById("generate-knowledge");
const knowledgeOptionHint = document.getElementById("knowledge-option-hint");
const downloadDirInput = document.getElementById("download-dir");
const downloadDirHint = document.getElementById("download-dir-hint");
const starterGuide = document.getElementById("starter-guide");
const starterTitle = document.getElementById("starter-title");
const starterSubtitle = document.getElementById("starter-subtitle");
const starterProgress = document.getElementById("starter-progress");
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
  cookiesPath: document.getElementById("settings-cookies-path"),
  cookiesFromBrowser: document.getElementById("settings-cookies-from-browser"),
  youtubeCookiesPath: document.getElementById("settings-youtube-cookies-path"),
  youtubeCookiesFromBrowser: document.getElementById("settings-youtube-cookies-from-browser"),
  bilibiliCookiesPath: document.getElementById("settings-bilibili-cookies-path"),
  bilibiliCookiesFromBrowser: document.getElementById("settings-bilibili-cookies-from-browser"),
  douyinCookiesPath: document.getElementById("settings-douyin-cookies-path"),
  douyinCookiesFromBrowser: document.getElementById("settings-douyin-cookies-from-browser"),
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

const platformCookiePanels = {
  generic: {
    label: "其他平台",
    filename: "cookies.txt",
    status: document.getElementById("settings-generic-cookie-status"),
    help: document.getElementById("settings-generic-cookies-help"),
  },
  youtube: {
    label: "YouTube",
    filename: "youtube.cookies.txt",
    status: document.getElementById("settings-youtube-cookie-status"),
    help: document.getElementById("settings-youtube-cookies-help"),
  },
  bilibili: {
    label: "Bilibili",
    filename: "bilibili.cookies.txt",
    status: document.getElementById("settings-bilibili-cookie-status"),
    help: document.getElementById("settings-bilibili-cookies-help"),
  },
  douyin: {
    label: "Douyin",
    filename: "douyin.cookies.txt",
    status: document.getElementById("settings-douyin-cookie-status"),
    help: document.getElementById("settings-douyin-cookies-help"),
  },
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
let pendingPrefillText = "";
let pendingAutoSubmit = false;

(function init() {
  hydrateLaunchPayloadFromLocation();
  if (config.webTokenRequired && !readStoredWebToken()) {
    maybePromptForWebToken();
    autoPromptedForWebToken = true;
  }
  (config.presets || []).forEach((preset) => {
    const opt = document.createElement("option");
    opt.value = opt.textContent = preset;
    presetSelect.appendChild(opt);
  });

  presetSelect.value = config.defaultPreset || presetSelect.options[0]?.value || "";
  cookiesCheckbox.checked = Boolean(config.cookiesConfigured);
  syncTopLevelConfig();
  hydrateSettings(config.settings);
  updatePlatformCookieSettings();
  updateOverviewSummary();
  updateModeHint();
  updateCookiesHint();
  updateKnowledgeOption();
  updateDownloadDirHint();
  updateSubmitLabel();
  renderStarterGuide();
  bindEvents();
  applyPrefillPayload();
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

  downloadDirInput.addEventListener("input", updateDownloadDirHint);

  form.addEventListener("submit", submitDownloadForm);
  settingsForm.addEventListener("submit", submitSettingsForm);
  settingsToggle.addEventListener("click", openSettingsDrawer);
  starterOpenSettings?.addEventListener("click", openSettingsDrawer);
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
  const generateKnowledge = Boolean(
    generateKnowledgeCheckbox &&
      generateKnowledgeCheckbox.checked &&
      !generateKnowledgeCheckbox.disabled,
  );
  const downloadDir = downloadDirInput.value.trim();

  startBtn.disabled = true;
  startBtn.textContent = "提交中...";

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
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    urlInput.value = "";
    downloadDirInput.value = "";
    if (generateKnowledgeCheckbox) {
      generateKnowledgeCheckbox.checked = false;
    }
    updateDownloadDirHint();
    updateKnowledgeOption();
    poll();
  } catch (err) {
    alert("提交失败: " + (err?.message || err));
  } finally {
    startBtn.disabled = false;
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
    settingsStatus.textContent = "已保存。新任务会使用这组默认配置和平台 Cookies。";
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

function hydrateLaunchPayloadFromLocation() {
  const hashParams = new URLSearchParams(window.location.hash.slice(1));
  const searchParams = new URLSearchParams(window.location.search);
  const token = hashParams.get("token") || searchParams.get("token") || "";
  const prefillText = hashParams.get("prefill") || searchParams.get("prefill") || "";
  const autoSubmitValue = hashParams.get("auto_submit") || searchParams.get("auto_submit") || "";

  if (token) {
    writeStoredWebToken(token);
  }
  if (prefillText) {
    pendingPrefillText = prefillText;
  }
  pendingAutoSubmit = autoSubmitValue === "1" || autoSubmitValue.toLowerCase() === "true";

  const removedHash = [
    hashParams.delete("token"),
    hashParams.delete("prefill"),
    hashParams.delete("auto_submit"),
  ].some(Boolean);
  const removedSearch = [
    searchParams.delete("token"),
    searchParams.delete("prefill"),
    searchParams.delete("auto_submit"),
  ].some(Boolean);

  if (removedHash || removedSearch) {
    const nextSearch = searchParams.toString();
    const nextHash = hashParams.toString();
    const nextUrl = `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ""}${nextHash ? `#${nextHash}` : ""}`;
    window.history.replaceState(null, "", nextUrl);
  }
}

function applyPrefillPayload() {
  if (!pendingPrefillText) {
    return;
  }

  urlInput.value = pendingPrefillText;
  pendingPrefillText = "";

  if (pendingAutoSubmit) {
    pendingAutoSubmit = false;
    window.setTimeout(() => {
      if (!startBtn.disabled && urlInput.value.trim()) {
        form.requestSubmit();
      }
    }, 0);
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
        暂无下载任务，去左侧添加一个吧。
      </li>`;
    return;
  }

  taskList.innerHTML = latestTasks
    .map((task) => {
      const selected = task.id === selectedTaskId;
      const toneClass = task.error ? "is-error" : task.done ? "is-done" : "is-running";
      const outputHint = task.host_knowledge_path || task.knowledge_path
        ? `<div class="task-path">知识库: ${escapeHtml(task.host_knowledge_path || task.knowledge_path)}</div>`
        : task.host_transcript_path || task.transcript_path
        ? `<div class="task-path">逐字稿: ${escapeHtml(task.host_transcript_path || task.transcript_path)}</div>`
        : task.host_download_path || task.download_path
          ? `<div class="task-path">文件: ${escapeHtml(task.host_download_path || task.download_path)}</div>`
          : "";
      const outputDirHint = task.host_output_dir || task.output_dir
        ? `<div class="task-path">保存到: ${escapeHtml(task.host_output_dir || task.output_dir)}</div>`
        : "";
      const resumedHint = task.resumed_from_state
        ? `<div class="task-path">已从上次中断状态恢复</div>`
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
              ${resumedHint}
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
  const outputDirDisplay = task.host_output_dir || task.output_dir || config.settings.download_dir || "未显式指定";
  const downloadPathDisplay = task.host_download_path || task.download_path || "尚未生成";
  const rawPathDisplay = task.host_raw_path || task.raw_path || "尚未生成";
  const transcriptPathDisplay = task.host_transcript_path || task.transcript_path || "尚未生成";
  const articlePathDisplay = task.host_article_path || task.article_path || "尚未生成";
  const knowledgePathDisplay = task.generate_knowledge
    ? (task.host_knowledge_path || task.knowledge_path || (task.knowledge_error ? "生成失败" : "尚未生成"))
    : "本次未请求";
  const metadataPathDisplay = task.host_metadata_path || task.metadata_path || "尚未生成";
  const artifactDirDisplay = task.host_artifact_dir || task.artifact_dir || "尚未生成";
  const showRuntimePaths = task.host_output_dir && task.host_output_dir !== task.output_dir;
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
        ${renderDetailBlock("保存目录", outputDirDisplay)}
        ${renderDetailBlock("下载文件", downloadPathDisplay)}
        ${renderDetailBlock("原始逐字稿", rawPathDisplay)}
        ${renderDetailBlock("逐字稿", transcriptPathDisplay)}
        ${renderDetailBlock("解析稿", articlePathDisplay)}
        ${renderDetailBlock("知识库稿", knowledgePathDisplay)}
        ${renderDetailBlock("转写信息", metadataPathDisplay)}
        ${renderDetailBlock("产物目录", artifactDirDisplay)}
        ${showRuntimePaths ? renderDetailBlock("容器保存目录", task.output_dir || "未显式指定") : ""}
        ${showRuntimePaths && task.download_path ? renderDetailBlock("容器下载文件", task.download_path) : ""}
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
    cookies_path: settingsElements.cookiesPath.value.trim(),
    cookies_from_browser: settingsElements.cookiesFromBrowser.value.trim(),
    youtube_cookies_path: settingsElements.youtubeCookiesPath.value.trim(),
    youtube_cookies_from_browser: settingsElements.youtubeCookiesFromBrowser.value.trim(),
    bilibili_cookies_path: settingsElements.bilibiliCookiesPath.value.trim(),
    bilibili_cookies_from_browser: settingsElements.bilibiliCookiesFromBrowser.value.trim(),
    douyin_cookies_path: settingsElements.douyinCookiesPath.value.trim(),
    douyin_cookies_from_browser: settingsElements.douyinCookiesFromBrowser.value.trim(),
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
  updatePlatformCookieSettings();
  updateOverviewSummary();
  updateModeHint();
  updateCookiesHint();
  updateKnowledgeOption();
  updateDownloadDirHint();
  renderStarterGuide();
}

function hydrateSettings(settings) {
  settingsElements.downloadDir.value = settings.download_dir || "";
  settingsElements.cookiesPath.value = settings.cookies_path || "";
  settingsElements.cookiesFromBrowser.value = settings.cookies_from_browser || "";
  settingsElements.youtubeCookiesPath.value = settings.youtube_cookies_path || "";
  settingsElements.youtubeCookiesFromBrowser.value = settings.youtube_cookies_from_browser || "";
  settingsElements.bilibiliCookiesPath.value = settings.bilibili_cookies_path || "";
  settingsElements.bilibiliCookiesFromBrowser.value = settings.bilibili_cookies_from_browser || "";
  settingsElements.douyinCookiesPath.value = settings.douyin_cookies_path || "";
  settingsElements.douyinCookiesFromBrowser.value = settings.douyin_cookies_from_browser || "";
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
    const hostHint = settings.host_downloads_dir
      ? ` 当前宿主机映射目录是 ${settings.host_downloads_dir}。`
      : "";
    settingsRootHint.textContent =
      `当前下载根目录锁定为 ${settings.download_root_dir}。网页里可以改默认目录和本次任务目录，但都必须位于这个根目录内；要改宿主机真实映射目录，请调整 Docker 的 DOCKER_DOWNLOADS_DIR。${hostHint}`;
  } else if (settings.download_dir) {
    settingsRootHint.textContent = `当前默认下载目录: ${settings.download_dir}。macOS 和 Windows 本地运行时，建议使用绝对路径。`;
  } else {
    settingsRootHint.textContent = "当前未设置默认下载目录，系统会回退到用户下载文件夹。";
  }
}

function updatePlatformCookieSettings() {
  Object.entries(platformCookiePanels).forEach(([platformKey, panel]) => {
    const state = getPlatformAuthState(platformKey);
    const pathValue = platformKey === "generic"
      ? config.settings.cookies_path || ""
      : config.settings[`${platformKey}_cookies_path`] || "";
    const browserValue = platformKey === "generic"
      ? config.settings.cookies_from_browser || ""
      : config.settings[`${platformKey}_cookies_from_browser`] || "";
    const statusLabel = summarizePlatformAuth(state);

    if (panel.status) {
      panel.status.textContent = statusLabel;
      panel.status.classList.remove("is-verified", "is-configured", "is-missing");
      if (state.verified) {
        panel.status.classList.add("is-verified");
      } else if (state.configured) {
        panel.status.classList.add("is-configured");
      } else {
        panel.status.classList.add("is-missing");
      }
    }

    if (!panel.help) {
      return;
    }

    const sourceSummary = state.verified
      ? `${panel.label} 登录态已经验证通过。`
      : state.configured
        ? `${panel.label} 登录态已配置，建议拿一条真实链接试跑。`
        : `${panel.label} 还没配置登录态。`;
    const pathSummary = pathValue
      ? `当前 cookies.txt: ${pathValue}`
      : `留空时会自动尝试 cookies/${panel.filename} 和 /cookies/${panel.filename}`;
    const browserSummary = browserValue
      ? `浏览器来源: ${browserValue}`
      : "本地调试可填 chrome 或 chrome:Profile 1";
    panel.help.textContent = `${sourceSummary} ${pathSummary}。${browserSummary}。`;
  });
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
  if ("generic_auth_configured" in settings) {
    config.genericAuthConfigured = Boolean(settings.generic_auth_configured);
  }
  if ("generic_auth_verified" in settings) {
    config.genericAuthVerified = Boolean(settings.generic_auth_verified);
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
  const hostDir = config.settings.host_downloads_dir;
  summaryDownloadDir.textContent = hostDir
    ? `${config.settings.download_dir || "系统默认下载目录"} -> ${hostDir}`
    : config.settings.download_dir || "系统默认下载目录";
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
  if (preset === config.transcriptPreset) {
    startBtn.textContent = "开始提取逐字稿";
    return;
  }
  if (preset === config.audioPreset) {
    startBtn.textContent = "开始下载 MP3";
    return;
  }
  startBtn.textContent = "开始下载视频";
}

function renderStarterGuide() {
  if (
    !starterGuide ||
    !starterTitle ||
    !starterSubtitle ||
    !starterProgress ||
    !starterChecklist ||
    !starterPlatforms ||
    !starterCallout
  ) {
    return;
  }

  const state = buildStarterGuideState();
  starterGuide.classList.toggle("is-ready", state.coreReady);
  starterGuide.classList.toggle("is-setup", !state.coreReady);
  starterTitle.textContent = state.title;
  starterSubtitle.textContent = state.subtitle;
  starterProgress.textContent = `${state.completed} / ${state.total}`;
  starterChecklist.innerHTML = state.steps.map(renderStarterStep).join("");
  starterPlatforms.innerHTML = state.platforms.map(renderPlatformPill).join("");
  starterCallout.innerHTML = `
    <strong>${escapeHtml(state.callout.title)}</strong>
    <p>${escapeHtml(state.callout.body)}</p>
  `;
  if (starterOpenSettings) {
    starterOpenSettings.textContent = state.primaryActionLabel;
  }
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
      title: "补平台登录态",
      detail: verifiedPlatforms.length
        ? configuredOnlyPlatforms.length
          ? `已验证 ${verifiedPlatforms.join(" / ")}；${configuredOnlyPlatforms.join(" / ")} 仍建议补成平台专用 cookies.txt。`
          : `当前常用平台登录态已经就绪，后续可以直接试受限内容。`
        : authPlatforms.length
          ? "已检测到平台登录态配置。推荐优先用平台专用 cookies.txt，浏览器登录态更适合本地调试。"
          : "先在设置里补 YouTube / Bilibili / Douyin 的 cookies；Douyin 默认会优先尝试平台专用 cookies.txt。",
      done: authPlatforms.length > 0,
      tone: verifiedPlatforms.length ? "done" : authPlatforms.length ? "warn" : "todo",
      badge: verifiedPlatforms.length ? "已就绪" : "推荐",
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
    subtitle = "现在可以直接在下面粘贴一条链接，先验证第一次逐字稿任务。";
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

    let cookiesNote = "当前未检测到登录态。公开视频通常可以直接处理；受限平台或需要登录的网站更建议先补 cookies。";
    if (verifiedPlatforms.length >= 1 && configuredOnlyPlatforms.length === 0) {
      cookiesNote = `当前已验证 ${verifiedPlatforms.join(" / ")} 登录态，对应平台会更稳。`;
    } else if (verifiedPlatforms.length >= 1) {
      cookiesNote = `当前已验证 ${verifiedPlatforms.join(" / ")}，另外 ${configuredOnlyPlatforms.join(" / ")} 还只是已配置，仍建议先做一次真实链接实测。`;
    } else if (authPlatforms.length >= 1) {
      cookiesNote = config.runtimeEnvironment === "container"
        ? `当前已检测到 ${authPlatforms.join(" / ")} 登录态配置，但容器里浏览器登录态无法预检；主流平台更稳的默认方案仍是平台专用 cookies.txt。`
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

function updateKnowledgeOption() {
  if (!generateKnowledgeCheckbox) {
    return;
  }

  const preset = presetSelect.value;
  const knowledgeEnabled = Boolean(config.settings.enable_knowledge_draft);
  const knowledgeConfigured = Boolean(config.settings.knowledge_draft_api_key_configured);
  const knowledgeReady = knowledgeEnabled && knowledgeConfigured;

  if (preset !== config.transcriptPreset) {
    generateKnowledgeCheckbox.checked = false;
    generateKnowledgeCheckbox.disabled = true;
    if (knowledgeOptionHint) {
      knowledgeOptionHint.textContent = "知识库稿依赖 Markdown 逐字稿模式。";
    }
    return;
  }

  if (!knowledgeEnabled) {
    generateKnowledgeCheckbox.checked = false;
    generateKnowledgeCheckbox.disabled = true;
    if (knowledgeOptionHint) {
      knowledgeOptionHint.textContent = "当前还没有启用知识库整理配置；如需网页直接生成知识库稿，请先在设置里开启。";
    }
    return;
  }

  if (!knowledgeConfigured) {
    generateKnowledgeCheckbox.checked = false;
    generateKnowledgeCheckbox.disabled = true;
    if (knowledgeOptionHint) {
      knowledgeOptionHint.textContent = "当前还没有配置知识库 API Key；补齐后才能在网页里直接生成知识库稿。";
    }
    return;
  }

  generateKnowledgeCheckbox.disabled = false;
  if (knowledgeOptionHint) {
    knowledgeOptionHint.textContent = "可选：逐字稿和解析稿完成后，继续生成 `知识库.md`。";
  }
}

function updateDownloadDirHint() {
  const defaultDir = config.settings.download_dir || "系统默认下载目录";
  const taskDir = downloadDirInput.value.trim();
  downloadDirInput.placeholder = defaultDir;

  if (taskDir) {
    if (config.settings.host_downloads_dir && config.settings.download_root_dir) {
      const mappedDir = taskDir.startsWith(config.settings.download_root_dir)
        ? taskDir.replace(config.settings.download_root_dir, config.settings.host_downloads_dir)
        : `${config.settings.host_downloads_dir}/${taskDir.replace(/^\/+/, "")}`;
      downloadDirHint.textContent = `这次任务将保存到 ${taskDir}，宿主机里对应 ${mappedDir}。`;
      return;
    }
    downloadDirHint.textContent = `这次任务将保存到 ${taskDir}。`;
    return;
  }

  if (config.settings.download_root_locked && config.settings.download_root_dir) {
    const hostHint = config.settings.host_downloads_dir
      ? ` 宿主机对应目录: ${config.settings.host_downloads_dir}。`
      : "";
    downloadDirHint.textContent = `留空时会写入默认目录 ${defaultDir}。Docker 模式下可填写 ${config.settings.download_root_dir} 里的子目录。${hostHint}`;
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
      "当前未检测到登录态。Docker / 容器环境更稳的默认方案是主流平台的专用 cookies.txt；其他平台也可以先试通用 cookies.txt 或 *_COOKIES_FROM_BROWSER。";
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
      ? `当前已检测到 ${authPlatforms.join("、")} 登录态配置，但容器里浏览器登录态无法预检。主流平台更稳的默认方案仍是对应平台的 cookies.txt。`
      : `当前已检测到 ${authPlatforms.join("、")} 登录态配置，但 doctor 只能确认“已配置”，是否可用仍需要拿真实链接实测。`;
    return;
  }

  if (getPlatformAuthState("generic").verified) {
    cookiesHint.textContent = "当前已验证通用登录态。勾选“启用 Cookies”后，其他 yt-dlp 支持的平台会优先尝试通用 cookies 来源。";
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

function getPlatformAuthState(platformKey) {
  const state = (config.platformAuth && config.platformAuth[platformKey]) || {};
  const legacyConfigured = {
    generic: Boolean(config.genericAuthConfigured),
    youtube: Boolean(config.youtubeAuthConfigured),
    bilibili: Boolean(config.bilibiliAuthConfigured),
    douyin: Boolean(config.douyinAuthConfigured),
  };
  const legacyVerified = {
    generic: Boolean(config.genericAuthVerified),
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
    ["其他平台", "generic"],
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
