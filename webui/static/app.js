const config = window.APP_CONFIG || {};
const presetSelect = document.getElementById("preset");
const taskList = document.getElementById("task-list");
const form = document.getElementById("download-form");
const startBtn = document.getElementById("start-btn");
const queueCount = document.getElementById("queue-count");

(function init() {
  config.presets.forEach((preset) => {
    const opt = document.createElement("option");
    opt.value = opt.textContent = preset;
    presetSelect.appendChild(opt);
  });
  presetSelect.value = config.defaultPreset;
  updateSubmitLabel();
  presetSelect.addEventListener("change", updateSubmitLabel);
  setInterval(poll, 1500);
  poll();
})();

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = document.getElementById("url").value;
  const preset = presetSelect.value;
  const cookies = document.getElementById("use-cookies").checked;

  startBtn.disabled = true;
  startBtn.textContent = "提交中...";

  try {
    await fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, preset, use_cookies: cookies }),
    });
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

      return `
        <li class="task-item">
            <div class="task-info">
                <div class="task-title" title="${escapeHtml(task.title)}">${escapeHtml(task.title)}</div>
                <div class="task-status" style="color: ${color}">
                    ${escapeHtml(task.error ? task.error : task.status)}
                </div>
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
  const isAudioPreset = preset === "Best Audio (MP3)";
  if (isAudioPreset && config.transcriptionEnabled) {
    startBtn.textContent = "开始下载并转写";
    return;
  }
  startBtn.textContent = "开始下载";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
