const config = window.APP_CONFIG || {};
const presetSelect = document.getElementById("preset");
const taskList = document.getElementById("task-list");
const form = document.getElementById("download-form");
const startBtn = document.getElementById("start-btn");
const queueCount = document.getElementById("queue-count");
const modeHint = document.getElementById("mode-hint");
const cookiesHint = document.getElementById("cookies-hint");
const cookiesCheckbox = document.getElementById("use-cookies");

(function init() {
  config.presets.forEach((preset) => {
    const opt = document.createElement("option");
    opt.value = opt.textContent = preset;
    presetSelect.appendChild(opt);
  });
  presetSelect.value = config.defaultPreset;
  cookiesCheckbox.checked = Boolean(config.cookiesConfigured);
  updateSubmitLabel();
  presetSelect.addEventListener("change", () => {
    updateModeHint();
    updateSubmitLabel();
  });
  updateModeHint();
  updateCookiesHint();
  setInterval(poll, 1500);
  poll();
})();

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = document.getElementById("url").value;
  const preset = presetSelect.value;
  const cookies = document.getElementById("use-cookies").checked;
  const generateTranscript = preset === config.transcriptPreset;

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
      }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    document.getElementById("url").value = "";
    poll();
  } catch (err) {
    alert("提交失败: " + err);
  } finally {
    startBtn.disabled = false;
    updateSubmitLabel();
  }
});

async function poll() {
  try {
    const res = await fetch("/api/tasks");
    const data = await res.json();
    render(data.tasks);

    const active = data.tasks.filter((task) => !task.done).length;
    queueCount.textContent = active > 0 ? `${active} 正在运行` : "空闲";
  } catch (err) {
    return;
  }
}

function render(tasks) {
  if (!tasks.length) {
    taskList.innerHTML = `
      <li style="padding: 20px; text-align: center; color: var(--text-light); font-size: 0.9rem;">
        暂无下载任务，去添加一个吧 🍃
      </li>`;
    return;
  }
  taskList.innerHTML = tasks
    .map((task) => {
      let color = "var(--text-sub)";
      if (task.status === "Done" || task.status === "Done · transcript ready") color = "var(--accent)";
      if (task.error) color = "#d32f2f";
      const outputHint = task.transcript_path
        ? `<div class="task-path">逐字稿: ${escapeHtml(task.transcript_path)}</div>`
        : task.download_path
          ? `<div class="task-path">文件: ${escapeHtml(task.download_path)}</div>`
          : "";
      const taskModeHint = `<div class="task-path">模式: ${escapeHtml(describePreset(task.preset, task.transcript_route))}</div>`;

      return `
        <li class="task-item">
            <div class="task-info">
                <div class="task-title" title="${escapeHtml(task.title)}">${escapeHtml(task.title)}</div>
                <div class="task-status" style="color: ${color}">
                    ${escapeHtml(task.error ? task.error : task.status)}
                </div>
                ${taskModeHint}
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
        </li>`;
    })
    .join("");
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
  if (preset === config.transcriptPreset) {
    let cookiesNote = "当前未检测到 Cookies，YouTube 和部分 B 站视频更可能直接回退到 MP3 转写。";
    if (config.youtubeAuthConfigured && config.bilibiliAuthConfigured) {
      cookiesNote = "已检测到 YouTube / Bilibili 登录态配置，字幕直提命中率会更高。";
    } else if (config.bilibiliAuthConfigured) {
      cookiesNote = "当前只检测到 Bilibili 登录态。B 站更稳，但 YouTube 若报 bot 校验，仍需要单独配置 YouTube 登录态。";
    } else if (config.youtubeAuthConfigured) {
      cookiesNote = "当前已检测到 YouTube 登录态配置，YouTube 下载和字幕直提会更稳。";
    }
    modeHint.textContent =
      `当前会先尝试直接提取平台字幕；如果没有可用字幕，再自动下载 MP3 并转写，最后生成逐字稿和解析稿。${cookiesNote}`;
    return;
  }
  if (preset === config.audioPreset) {
    modeHint.textContent = "当前只下载 MP3 音频，不自动生成 Markdown 逐字稿。";
    return;
  }
  modeHint.textContent = "当前下载最高画质视频，优先保留高分辨率并合并为 MP4。";
}

function updateCookiesHint() {
  if (!config.youtubeAuthConfigured && !config.bilibiliAuthConfigured) {
    cookiesHint.textContent =
      "当前未检测到平台登录态。建议在 .env 里配置 YOUTUBE_COOKIES_FROM_BROWSER=chrome，或填写 YOUTUBE_COOKIES_PATH / BILIBILI_COOKIES_PATH。";
    return;
  }
  if (config.youtubeAuthConfigured && config.bilibiliAuthConfigured) {
    cookiesHint.textContent = "当前已检测到 YouTube 和 Bilibili 登录态配置。勾选“启用 Cookies”后，会按平台优先选择对应登录态。";
    return;
  }
  if (config.youtubeAuthConfigured) {
    cookiesHint.textContent = "当前已检测到 YouTube 登录态配置。勾选“启用 Cookies”后，会优先用 YouTube 登录态访问下载和字幕接口。";
    return;
  }
  cookiesHint.textContent = "当前已检测到 Bilibili 登录态配置。勾选“启用 Cookies”后，会优先用 Bilibili 登录态访问平台字幕接口。";
}

function describePreset(preset, route) {
  if (preset === config.transcriptPreset) {
    if (route === "direct_subtitles") {
      return "MD 逐字稿（直提字幕）";
    }
    if (route === "subtitle_probe_fallback_to_audio") {
      return "MD 逐字稿（字幕失败后回退音频转写）";
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
