const config = window.APP_CONFIG || {};
const presetSelect = document.getElementById("preset");
const taskList = document.getElementById("task-list");
const form = document.getElementById("download-form");
const startBtn = document.getElementById("start-btn");
const localAudioForm = document.getElementById("local-audio-form");
const localAudioInput = document.getElementById("local-audio");
const localAudioBtn = document.getElementById("local-audio-btn");
const localAudioHint = document.getElementById("local-audio-hint");
const localAudioSelection = document.getElementById("local-audio-selection");
const localAudioPreset = document.getElementById("local-audio-preset");
const queueCount = document.getElementById("queue-count");
const EMPTY_TASK_HTML = `
  <li class="task-empty">
    暂无任务，去添加一个吧
  </li>`;

(function init() {
  config.presets.forEach((preset) => {
    const opt = document.createElement("option");
    opt.value = opt.textContent = preset;
    presetSelect.appendChild(opt);
  });
  presetSelect.value = config.defaultPreset;
  if (localAudioInput && config.localAudioAccept) {
    localAudioInput.accept = config.localAudioAccept;
  }
  if (localAudioPreset) {
    localAudioPreset.value = config.knowledgeBasePreset || config.defaultPreset;
  }
  if (localAudioHint) {
    localAudioHint.textContent = `支持 ${config.localAudioAccept || ".mp3,.m4a,.wav"}，单次上传大小上限 ${config.localAudioMaxMb || 1024} MB。`;
  }
  setInterval(poll, 1500);
  poll();
})();

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response
    .json()
    .catch(() => ({ error: `Request failed: ${response.status}` }));
  if (!response.ok) {
    throw new Error(data.error || `Request failed: ${response.status}`);
  }
  return data;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = document.getElementById("url").value;
  const preset = presetSelect.value;
  const cookies = document.getElementById("use-cookies").checked;

  startBtn.disabled = true;
  startBtn.textContent = "提交中...";

  try {
    await requestJson("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, preset, use_cookies: cookies }),
    });
    document.getElementById("url").value = "";
    poll();
  } catch (err) {
    alert("提交失败: " + err.message);
  } finally {
    startBtn.disabled = false;
    startBtn.textContent = "开始下载";
  }
});

if (localAudioInput) {
  localAudioInput.addEventListener("change", () => {
    const files = Array.from(localAudioInput.files || []);
    if (!files.length) {
      localAudioSelection.textContent = "未选择文件";
      return;
    }
    const names = files.slice(0, 3).map((file) => file.name);
    const suffix = files.length > 3 ? ` 等 ${files.length} 个文件` : "";
    localAudioSelection.textContent = `已选择: ${names.join(" / ")}${suffix}`;
  });
}

if (localAudioForm) {
  localAudioForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const files = Array.from(localAudioInput.files || []);
    if (!files.length) {
      alert("请先选择至少一个本地音频文件。");
      return;
    }

    const formData = new FormData(localAudioForm);
    localAudioBtn.disabled = true;
    localAudioBtn.textContent = "上传中...";

    try {
      const result = await requestJson("/api/local-audio", {
        method: "POST",
        body: formData,
      });
      localAudioForm.reset();
      localAudioSelection.textContent = `已加入 ${result.count} 个本地转写任务`;
      poll();
    } catch (err) {
      alert("本地转写提交失败: " + err.message);
    } finally {
      localAudioBtn.disabled = false;
      localAudioBtn.textContent = "上传并转写";
    }
  });
}

async function poll() {
  try {
    const data = await requestJson("/api/tasks");
    render(data.tasks);

    const active = data.tasks.filter((task) => !task.done).length;
    queueCount.textContent = active > 0 ? `${active} 正在运行` : "空闲";
  } catch (err) {
    return;
  }
}

function render(tasks) {
  if (!tasks.length) {
    taskList.innerHTML = EMPTY_TASK_HTML;
    return;
  }
  taskList.innerHTML = tasks
    .map((task) => {
      let color = "var(--text-sub)";
      if (task.status === "Done") color = "var(--accent)";
      if (task.error) color = "#d32f2f";
      const sourceLabel = task.source_kind === "local_audio" ? "本地音频" : "链接下载";

      const outputMeta =
        task.done && !task.error && task.output_dir
          ? `
            <div class="task-output">
              目录: ${task.output_dir}
            </div>
            <div class="task-output">
              文件: ${(task.artifacts || []).join(" · ")}
            </div>`
          : "";

      return `
        <li class="task-item">
            <div class="task-info">
                <div class="task-title-row">
                  <div class="task-title" title="${task.title}">${task.title}</div>
                  <span class="task-badge">${sourceLabel}</span>
                </div>
                <div class="task-status" style="color: ${color}">
                    ${task.error ? task.error : task.status}
                </div>
                ${outputMeta}
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
