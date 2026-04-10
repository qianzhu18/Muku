const config = window.APP_CONFIG || {};
config.settings = config.settings || {};

const presetSelect = document.getElementById("preset");
const taskList = document.getElementById("task-list");
const form = document.getElementById("download-form");
const startBtn = document.getElementById("start-btn");
const queueCount = document.getElementById("queue-count");
const modeHint = document.getElementById("mode-hint");
const cookiesHint = document.getElementById("cookies-hint");
const cookiesCheckbox = document.getElementById("use-cookies");
const downloadDirInput = document.getElementById("download-dir");
const downloadDirHint = document.getElementById("download-dir-hint");

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
  openrouterSiteUrl: document.getElementById("settings-openrouter-site-url"),
  openrouterAppName: document.getElementById("settings-openrouter-app-name"),
  openrouterTranscriptionModel: document.getElementById("settings-openrouter-transcription-model"),
  openrouterArticleModel: document.getElementById("settings-openrouter-article-model"),
  enableCleanup: document.getElementById("settings-enable-cleanup"),
  cleanupBaseUrl: document.getElementById("settings-cleanup-base-url"),
  cleanupApiKey: document.getElementById("settings-cleanup-api-key"),
  cleanupModel: document.getElementById("settings-cleanup-model"),
  cleanupPromptText: document.getElementById("settings-cleanup-prompt-text"),
  enableArticle: document.getElementById("settings-enable-article"),
  articleBaseUrl: document.getElementById("settings-article-base-url"),
  articleApiKey: document.getElementById("settings-article-api-key"),
  articleModel: document.getElementById("settings-article-model"),
  articlePromptText: document.getElementById("settings-article-prompt-text"),
  enableKnowledge: document.getElementById("settings-enable-knowledge"),
  knowledgeBaseUrl: document.getElementById("settings-knowledge-base-url"),
  knowledgeApiKey: document.getElementById("settings-knowledge-api-key"),
  knowledgeModel: document.getElementById("settings-knowledge-model"),
  knowledgePromptText: document.getElementById("settings-knowledge-prompt-text"),
};

let latestTasks = [];
let selectedTaskId = null;
let activePanel = "queue";

(function init() {
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
  updateDownloadDirHint();
  updateSubmitLabel();
  bindEvents();
  setMonitorPanel("queue");

  setInterval(poll, 1500);
  poll();
})();

function bindEvents() {
  presetSelect.addEventListener("change", () => {
    updateModeHint();
    updateSubmitLabel();
  });

  downloadDirInput.addEventListener("input", updateDownloadDirHint);

  form.addEventListener("submit", submitDownloadForm);
  settingsForm.addEventListener("submit", submitSettingsForm);
  settingsToggle.addEventListener("click", openSettingsDrawer);
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
    setMonitorPanel("detail");
    renderTaskDetail();
    renderTaskList();
  });

  monitorTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      setMonitorPanel(tab.dataset.panelTarget || "queue");
    });
  });
}

async function submitDownloadForm(event) {
  event.preventDefault();
  const url = document.getElementById("url").value;
  const preset = presetSelect.value;
  const cookies = cookiesCheckbox.checked;
  const generateTranscript = preset === config.transcriptPreset;
  const downloadDir = downloadDirInput.value.trim();

  startBtn.disabled = true;
  startBtn.textContent = "提交中...";

  try {
    const res = await fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        preset,
        use_cookies: cookies,
        generate_transcript: generateTranscript,
        download_dir: downloadDir,
      }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    document.getElementById("url").value = "";
    downloadDirInput.value = "";
    updateDownloadDirHint();
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
    const res = await fetch("/api/settings", {
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
    const res = await fetch("/api/tasks");
    const data = await res.json();
    latestTasks = Array.isArray(data.tasks) ? data.tasks : [];
    if (!selectedTaskId && latestTasks.length) {
      selectedTaskId = latestTasks[0].id;
    }
    if (selectedTaskId && !latestTasks.some((task) => task.id === selectedTaskId)) {
      selectedTaskId = latestTasks[0]?.id || null;
    }
    updateQueueSummary(latestTasks);
    renderTaskList();
    renderTaskDetail();
  } catch (err) {
    return;
  }
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
      const outputHint = task.transcript_path
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
              <div class="task-path">模式: ${escapeHtml(describePreset(task.preset, task.transcript_route))}</div>
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
        ${renderDetailItem("模式", describePreset(task.preset, task.transcript_route))}
        ${renderDetailItem("进度", `${task.progress || 0}%`)}
        ${renderDetailItem("Provider", task.provider || "待定")}
      </div>

      <div class="detail-stack">
        ${renderDetailBlock("来源链接", task.source_url, true)}
        ${renderDetailBlock("保存目录", task.output_dir || config.settings.download_dir || "未显式指定")}
        ${renderDetailBlock("下载文件", task.download_path || "尚未生成")}
        ${renderDetailBlock("逐字稿", task.transcript_path || "尚未生成")}
        ${renderDetailBlock("产物目录", task.artifact_dir || "尚未生成")}
        ${renderDetailBlock("后端报错", task.backend_error || "当前无额外后端报错")}
      </div>
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

function collectSettingsPayload() {
  return {
    download_dir: settingsElements.downloadDir.value.trim(),
    openrouter_base_url: settingsElements.openrouterBaseUrl.value.trim(),
    openrouter_api_key: settingsElements.openrouterApiKey.value.trim(),
    openrouter_site_url: settingsElements.openrouterSiteUrl.value.trim(),
    openrouter_app_name: settingsElements.openrouterAppName.value.trim(),
    openrouter_transcription_model: settingsElements.openrouterTranscriptionModel.value.trim(),
    openrouter_article_model: settingsElements.openrouterArticleModel.value.trim(),
    enable_ai_cleanup: settingsElements.enableCleanup.checked,
    ai_cleanup_base_url: settingsElements.cleanupBaseUrl.value.trim(),
    ai_cleanup_api_key: settingsElements.cleanupApiKey.value.trim(),
    ai_cleanup_model: settingsElements.cleanupModel.value.trim(),
    ai_cleanup_prompt_text: settingsElements.cleanupPromptText.value.trim(),
    enable_article_draft: settingsElements.enableArticle.checked,
    article_draft_base_url: settingsElements.articleBaseUrl.value.trim(),
    article_draft_api_key: settingsElements.articleApiKey.value.trim(),
    article_draft_model: settingsElements.articleModel.value.trim(),
    article_draft_prompt_text: settingsElements.articlePromptText.value.trim(),
    enable_knowledge_draft: settingsElements.enableKnowledge.checked,
    knowledge_draft_base_url: settingsElements.knowledgeBaseUrl.value.trim(),
    knowledge_draft_api_key: settingsElements.knowledgeApiKey.value.trim(),
    knowledge_draft_model: settingsElements.knowledgeModel.value.trim(),
    knowledge_draft_prompt_text: settingsElements.knowledgePromptText.value.trim(),
  };
}

function applySettings(settings) {
  config.settings = settings || {};
  syncTopLevelConfig(settings);
  hydrateSettings(config.settings);
  updateOverviewSummary();
  updateModeHint();
  updateCookiesHint();
  updateDownloadDirHint();
}

function hydrateSettings(settings) {
  settingsElements.downloadDir.value = settings.download_dir || "";
  settingsElements.openrouterBaseUrl.value = settings.openrouter_base_url || "";
  settingsElements.openrouterApiKey.value = settings.openrouter_api_key || "";
  settingsElements.openrouterSiteUrl.value = settings.openrouter_site_url || "";
  settingsElements.openrouterAppName.value = settings.openrouter_app_name || "幕库 Muku";
  settingsElements.openrouterTranscriptionModel.value = settings.openrouter_transcription_model || "";
  settingsElements.openrouterArticleModel.value = settings.openrouter_article_model || "";
  settingsElements.enableCleanup.checked = Boolean(settings.enable_ai_cleanup);
  settingsElements.cleanupBaseUrl.value = settings.ai_cleanup_base_url || "";
  settingsElements.cleanupApiKey.value = settings.ai_cleanup_api_key || "";
  settingsElements.cleanupModel.value = settings.ai_cleanup_model || "";
  settingsElements.cleanupPromptText.value = settings.ai_cleanup_prompt_text || "";
  settingsElements.enableArticle.checked = Boolean(settings.enable_article_draft);
  settingsElements.articleBaseUrl.value = settings.article_draft_base_url || "";
  settingsElements.articleApiKey.value = settings.article_draft_api_key || "";
  settingsElements.articleModel.value = settings.article_draft_model || "";
  settingsElements.articlePromptText.value = settings.article_draft_prompt_text || "";
  settingsElements.enableKnowledge.checked = Boolean(settings.enable_knowledge_draft);
  settingsElements.knowledgeBaseUrl.value = settings.knowledge_draft_base_url || "";
  settingsElements.knowledgeApiKey.value = settings.knowledge_draft_api_key || "";
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

function syncTopLevelConfig(settings = config.settings) {
  config.transcriptionModel = settings.openrouter_transcription_model || config.transcriptionModel;
  config.aiCleanupEnabled = Boolean(settings.enable_ai_cleanup);
  config.aiCleanupModel = settings.ai_cleanup_model || config.aiCleanupModel;
  config.articleDraftEnabled = Boolean(settings.enable_article_draft);
  config.articleDraftModel = settings.article_draft_model || config.articleDraftModel;
  if ("youtube_auth_configured" in settings) {
    config.youtubeAuthConfigured = Boolean(settings.youtube_auth_configured);
  }
  if ("bilibili_auth_configured" in settings) {
    config.bilibiliAuthConfigured = Boolean(settings.bilibili_auth_configured);
  }
  if ("douyin_auth_configured" in settings) {
    config.douyinAuthConfigured = Boolean(settings.douyin_auth_configured);
  }
}

function updateOverviewSummary() {
  summaryDownloadDir.textContent = config.settings.download_dir || "系统默认下载目录";
  summaryModel.textContent = config.transcriptionModel || "未设置";

  const authPlatforms = collectAuthPlatforms();
  if (!authPlatforms.length) {
    summaryAuth.textContent = "未配置";
    return;
  }
  summaryAuth.textContent = authPlatforms.join(" / ");
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

function updateModeHint() {
  const preset = presetSelect.value;
  const modelHint = config.transcriptionModel ? `当前默认转写模型：${config.transcriptionModel}。` : "";

  if (preset === config.transcriptPreset) {
    const authPlatforms = collectAuthPlatforms();

    let cookiesNote = "当前未检测到 Cookies，YouTube、Douyin 和部分 B 站视频在受限场景下更可能回退到音频转写。";
    if (authPlatforms.length === 3) {
      cookiesNote = "已检测到 YouTube / Bilibili / Douyin 登录态配置，平台读取成功率会更高。";
    } else if (authPlatforms.length === 2) {
      cookiesNote = `当前已检测到 ${authPlatforms.join(" / ")} 登录态配置，对应平台会更稳。`;
    } else if (config.bilibiliAuthConfigured) {
      cookiesNote = "当前只检测到 Bilibili 登录态。B 站更稳，但 YouTube 或 Douyin 若遇到校验，仍需要单独配置对应平台登录态。";
    } else if (config.youtubeAuthConfigured) {
      cookiesNote = "当前已检测到 YouTube 登录态配置，YouTube 下载和字幕直提会更稳。";
    } else if (config.douyinAuthConfigured) {
      cookiesNote = "当前已检测到 Douyin 登录态配置。若抖音后续出现验证或访问限制，这套登录态会更稳。";
    }

    modeHint.textContent =
      `当前会先尝试直接提取平台字幕；如果没有可用字幕，再自动下载 MP3 并转写，最后生成逐字稿和解析稿。${modelHint}${cookiesNote}`;
    return;
  }

  if (preset === config.audioPreset) {
    modeHint.textContent = "当前只下载 MP3 音频，不自动生成 Markdown 逐字稿。";
    return;
  }

  modeHint.textContent = "当前下载最高画质视频，优先保留高分辨率并合并为 MP4。";
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

  if (!authPlatforms.length) {
    cookiesHint.textContent =
      "当前未检测到平台登录态。建议优先配置 YOUTUBE_COOKIES_FROM_BROWSER=chrome，或补齐 BILIBILI / DOUYIN 对应平台专用登录态。";
    return;
  }

  if (authPlatforms.length > 1) {
    cookiesHint.textContent = `当前已检测到 ${authPlatforms.join("、")} 登录态配置。勾选“启用 Cookies”后，会按平台优先选择对应登录态。`;
    return;
  }

  if (config.youtubeAuthConfigured) {
    cookiesHint.textContent = "当前已检测到 YouTube 登录态配置。勾选“启用 Cookies”后，会优先用 YouTube 登录态访问下载和字幕接口。";
    return;
  }
  if (config.bilibiliAuthConfigured) {
    cookiesHint.textContent = "当前已检测到 Bilibili 登录态配置。勾选“启用 Cookies”后，会优先用 Bilibili 登录态访问平台字幕接口。";
    return;
  }
  cookiesHint.textContent = "当前已检测到 Douyin 登录态配置。勾选“启用 Cookies”后，会优先用 Douyin 登录态访问抖音下载接口。";
}

function collectAuthPlatforms() {
  const authPlatforms = [];
  if (config.youtubeAuthConfigured) authPlatforms.push("YouTube");
  if (config.bilibiliAuthConfigured) authPlatforms.push("Bilibili");
  if (config.douyinAuthConfigured) authPlatforms.push("Douyin");
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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
