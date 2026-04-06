# ytdlp-webui

一个本地化的网页视频下载与转写整理工具，基于 `yt-dlp + Flask + faster-whisper`，支持多平台链接输入、批量队列、进度展示，并能把下载得到的音频直接整理成适合 Markdown 知识库入库的逐字稿。

> 当前仓库的主转写后端仍是 `faster-whisper`。如果你的部署机器是 Apple Silicon Mac，推荐采用“Docker WebUI + 宿主机 MLX 转写服务”的双服务架构，而不是试图把 MLX 直接塞进现有 Linux 容器。

## 功能特性

- Web UI 界面：输入链接即可下载
- 支持批量下载（多行链接）
- 下载格式预设（视频/音频/高分辨率）
- 知识库转写模式：自动产出 `MP3 + Markdown + TXT + SRT`
- Apple Silicon 加速：可选接入宿主机 `mlx-whisper` / `lightning-whisper-mlx` 远程转写服务
- 平台字幕优先：YouTube / Bilibili 有字幕时优先使用字幕，缺失时再回退 Whisper
- Web 本地音频转写：可直接在页面里选择本地 `mp3/m4a/wav` 进入转写队列
- Raw / Clean 双稿：同时保留原始逐字稿与清洗后的知识库稿
- 简单数字清洗：合并被切开的数字空格，统一常见单位/百分号/时间写法
- Markdown 笔记整理：附带 frontmatter、来源信息、附件链接、时间分段
- 任务队列与进度展示
- 支持 Cookies（会员/限速内容）
- 支持本地音频直转 Markdown：可直接处理现有 `mp3/m4a/wav`
- Docker 一键启动

## 适用场景

- 个人本地离线下载
- 需要轻量级 UI 操作的 yt-dlp 用户

> 提示：该项目不适合公共服务器大规模对外服务，下载任务会占用带宽与服务器资源。

## 快速开始（Docker）

### 1) 拉取镜像

```bash
docker pull zhangjinhong/ytdlp-webui:latest
```

### 2) 启动容器

```bash
docker run --rm -d -p 8080:8080 \
  -v "$HOME/Downloads:/downloads" \
  --name ytdlp-webui \
  zhangjinhong/ytdlp-webui:latest
```

访问：`http://localhost:8080`

### 3) 启用 Cookies（可选）

适用于会员内容或限速内容：

```bash
docker run --rm -d -p 8080:8080 \
  -v "$HOME/Downloads:/downloads" \
  -v "$HOME/Downloads/cookies.txt:/cookies.txt:ro" \
  -e COOKIES_PATH=/cookies.txt \
  --name ytdlp-webui \
  zhangjinhong/ytdlp-webui:latest
```

> Cookies 建议使用浏览器插件导出 `cookies.txt`（如 Get cookies.txt）。

### 4) 停止容器

```bash
docker stop ytdlp-webui
```

## 本地运行（不使用 Docker）

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python webui/app.py
```

访问：`http://localhost:8080`

## Apple Silicon 部署

### 结论

可以做，而且值得做，但推荐方案不是“让当前 Docker 容器直接跑 MLX”，而是：

- 服务 A：保留当前 `ytdlp-webui` Docker 容器，负责下载、任务队列、文件整理、Web UI
- 服务 B：在 macOS 宿主机直接运行 `mlx-whisper` / `lightning-whisper-mlx` 的独立转写服务
- 两者通过 HTTP 通信，并共享同一份下载目录

### 为什么不建议把 MLX 直接放进当前 Docker 容器

- `MLX` 官方定位是 Apple Silicon 机器学习框架：<https://github.com/ml-explore/mlx>
- `lightning-whisper-mlx` 官方 README 也明确写的是 Apple Silicon 优化实现：<https://github.com/mustafaaljadery/lightning-whisper-mlx>
- Docker 官方文档目前写得很直接：Docker Desktop 的通用容器 GPU 支持“only available on Windows with the WSL2 backend”
  - GPU support: <https://docs.docker.com/desktop/features/gpu/>
  - GenAI container guide: <https://docs.docker.com/guides/genai-pdf-bot/containerize/>

也就是说，在 macOS 上，你当前这个 Linux 容器并不能像原生 macOS 进程那样直接吃到 Apple 的 Metal / MLX 加速。

### 为什么 Docker on Mac 看起来“也支持 Apple Silicon”

Docker 的确有一条单独的产品线叫 Docker Model Runner，在 Apple Silicon Mac 上支持 `llama.cpp` 等特定推理引擎：

- Model Runner: <https://docs.docker.com/ai/model-runner/>
- Inference engines: <https://docs.docker.com/ai/model-runner/inference-engines/>

但这不等于“任意自定义 Linux 容器都能直接用 MLX/Metal”。它是 Docker 自己托管的一套模型运行时，不是你当前这个 Flask 容器的通用 GPU 透传方案。

### 推荐架构

```text
+------------------------------+         HTTP          +----------------------------------+
| Docker: ytdlp-webui          |  ------------------>  | macOS Host: mlx-whisper service  |
|                              |                       |                                  |
| - Flask UI                   |                       | - MLX / lightning-whisper-mlx    |
| - yt-dlp download            |                       | - Apple GPU / unified memory     |
| - queue / metadata / md      |                       | - returns srt/txt/json           |
+------------------------------+                       +----------------------------------+
               |                                                          |
               +---------------- shared downloads directory --------------+
```

### 这套双服务的优点

- 下载和 UI 继续保持容器化，部署和回滚简单
- 转写真正跑在 macOS 宿主机，能吃到 Apple Silicon 的速度优势
- 转写服务可以独立重启、独立限流，不会把 Flask 主容器拖死
- 后续可以继续保留 `faster-whisper` 作为 fallback，避免 MLX 服务不可用时整个流程中断

### 这套双服务的落地建议

建议按下面顺序推进：

1. 保留当前容器内 `faster-whisper` 作为默认后备方案
2. 新增一个宿主机常驻的 `mlx-whisper` HTTP 服务
3. 在 WebUI 增加“转写后端”配置：`local-faster-whisper` / `remote-mlx`
4. Docker 容器通过 `host.docker.internal` 访问宿主机服务
5. 共享下载目录，例如都读写 `$HOME/Downloads`
6. 转写失败自动回退到容器内 `faster-whisper`

### 当前实现状态

- 当前仓库：已经支持 `faster-whisper` 转写、平台字幕优先、Raw/Clean 双稿、Markdown 产出
- 当前仓库：已经新增“remote MLX transcription service”接入层
- 当前仓库：容器端可通过 `TRANSCRIPTION_BACKEND=remote_mlx` 调用宿主机 MLX 服务

### 宿主机 MLX 服务启动

先在 Apple Silicon Mac 宿主机安装依赖：

```bash
python3 -m venv .venv-mlx
source .venv-mlx/bin/activate
pip install -r mlx_service/requirements.txt
```

然后启动服务：

```bash
export MLX_SHARED_ROOT="$HOME/Downloads"
export MLX_SERVICE_PORT=9001
export MLX_DEFAULT_MODEL=large-v3
export MLX_DEFAULT_QUANT=4bit
python mlx_service/app.py
```

健康检查：

```bash
curl http://127.0.0.1:9001/health
```

接口说明：

- `GET /health`：查看服务状态、共享目录和已缓存模型
- `POST /api/transcribe`：接收容器侧发来的音频路径和模型参数，返回 `text + segments + language + backend`

### Docker 容器如何接入宿主机 MLX

启动 WebUI 容器时增加这些环境变量：

```bash
docker run --rm -d -p 8080:8080 \
  -v "$HOME/Downloads:/downloads" \
  -e TRANSCRIPTION_BACKEND=remote_mlx \
  -e REMOTE_MLX_URL=http://host.docker.internal:9001 \
  -e TRANSCRIPTION_FALLBACK_LOCAL=1 \
  -e REMOTE_MLX_MODEL=large-v3 \
  -e REMOTE_MLX_BATCH_SIZE=12 \
  -e REMOTE_MLX_QUANT=4bit \
  --name ytdlp-webui \
  zhangjinhong/ytdlp-webui:latest
```

说明：

- `TRANSCRIPTION_BACKEND=remote_mlx`：优先调用宿主机 MLX 服务
- `TRANSCRIPTION_FALLBACK_LOCAL=1`：宿主机服务挂掉时，自动回退到容器内 `faster-whisper`
- `REMOTE_MLX_URL=http://host.docker.internal:9001`：Docker Desktop on macOS 访问宿主机服务的标准地址
- 宿主机与容器必须共享同一份下载目录，默认就是 `$HOME/Downloads <-> /downloads`

### 额外：本地音频直转 Markdown

如果你已经有下载好的音频文件，不想再走 URL 下载流程，可以直接处理本地文件：

```bash
python webui/app.py --audio /path/to/file.mp3
```

也可以把产物统一写入指定目录：

```bash
python webui/app.py --audio /path/to/a.mp3 /path/to/b.m4a --output-dir "$HOME/Downloads/notes"
```

如果你更喜欢 Web UI，现在也可以直接在页面里选择本地音频文件上传转写。上传完成后，它会进入同一个任务队列，并在 `/downloads/YYYY-MM-DD/标题 [哈希]/` 下产出：

- 原始音频
- `.txt` / `.srt`
- `.raw.txt` / `.raw.srt`
- `.md`
- `_meta.json`

说明：

- Web 上传适合临时单文件或少量文件
- 大文件、超长音频、批量历史素材仍更适合 CLI 模式
- 如果后续要接外部 API 优化 Markdown，可以直接消费 `.raw.txt` 或 `.txt`

## 使用说明

1) 如果是在线链接：
   - 在输入框粘贴视频链接（支持多行）
   - 选择下载预设
   - 如需直接入 Markdown 知识库，选择 `转 Markdown 知识库（MP3 + 逐字稿）`
2) 如果是本地已有 MP3 / M4A / WAV：
   - 使用页面里的“本地音频转写”入口直接选文件
   - 或使用 CLI：`python webui/app.py --audio /path/to/file.mp3`
3) 提交后会进入同一个任务队列
4) 完成后同目录生成 `.mp3/.md/.srt/.txt/.raw.srt/.raw.txt/_meta.json`

### 字幕转写模型（Whisper）

- 默认使用 `large-v3`（准确率优先）
- 默认自动语言识别（适合中英文混合场景）
- 可选环境变量：
  - `WHISPER_DEVICE`（默认 `auto`）
  - `WHISPER_COMPUTE_TYPE`（默认 `auto`，会自动尝试 `float16 -> int8_float16 -> int8`）
  - `WHISPER_LANGUAGE`（默认 `auto`，可设 `zh` 或 `en`）
  - `WHISPER_BEAM_SIZE`（默认 `8`）
  - `WHISPER_BEST_OF`（默认 `8`）
  - `ASR_CONCURRENCY`（默认 `1`，建议根据机器性能逐步调大）
  - `MAX_WORKERS`（默认 `6`，控制下载并发）
  - `WHISPER_CACHE_DIR`（模型缓存目录）
  - `TRANSCRIPT_CACHE_DIR`（字幕缓存目录）
  - `TRANSCRIPT_PARAGRAPH_CHARS`（默认 `220`，控制 Markdown 分段长度）
  - `TRANSCRIPT_PARAGRAPH_GAP_SECONDS`（默认 `1.6`，控制段落切分停顿）
  - `PREFER_PLATFORM_SUBTITLES`（默认 `1`，优先使用平台字幕）
  - `SUBTITLE_LANGS`（默认 `zh-Hans,zh-CN,zh,zh-Hant,en,en-US,en-GB`）
  - `ASR_PREPROCESS_ENABLED`（默认 `1`，用 ffmpeg 做转写前预处理）
  - `ASR_AUDIO_FILTER`（默认 `highpass=f=80,lowpass=f=7600,afftdn,loudnorm`）
  - `ASR_SAMPLE_RATE`（默认 `16000`）
  - `TRANSCRIPTION_BACKEND`（默认 `auto`，可选 `auto` / `local` / `remote_mlx`）
  - `TRANSCRIPTION_FALLBACK_LOCAL`（默认 `1`，远程 MLX 失败时回退本地 Whisper）
  - `REMOTE_MLX_URL`（默认空；配置后 `auto` 模式才会优先尝试远程 MLX）
  - `REMOTE_MLX_TIMEOUT`（默认 `1800` 秒）
  - `REMOTE_MLX_MODEL`（默认 `large-v3`）
  - `REMOTE_MLX_BATCH_SIZE`（默认 `12`）
  - `REMOTE_MLX_QUANT`（默认 `4bit`）
  - `LOCAL_AUDIO_MAX_MB`（默认 `1024`，限制 Web 上传本地音频大小）
- 首次转写会自动下载模型文件，耗时取决于网络与模型大小

### 输出目录与命名

- 所有产物按日期自动归类：`/downloads/YYYY-MM-DD/视频标题 [视频ID]/`
- 同一个任务的 `音频 / Markdown / TXT / SRT / raw TXT / raw SRT` 会放在同一目录
- 每个目录会额外生成 `_meta.json` 记录来源链接、模型参数和文件清单，便于快速检索
- Markdown 笔记内会附带 frontmatter、来源链接、附件相对链接和按时间切分后的逐字稿段落

### Markdown 笔记长什么样

默认生成的 `.md` 文件会包含：

- YAML frontmatter：标题、来源链接、平台、语言、模型等
- `## 来源`：便于回看原始链接
- `## 附件`：直接跳转同目录里的音频、字幕、纯文本，以及 raw 原稿
- `## 逐字稿`：按时间戳分段，适合放进 Obsidian 等知识库工具
- 一层轻量清洗：主要处理数字空格、单位与符号，不做激进改写
- 如果平台本身有字幕，会优先直接使用字幕而不是重新跑 Whisper

## HTTP 接口

### WebUI 接口

- `POST /api/start`
  - `Content-Type: application/json`
  - 请求体：`{"url":"...", "preset":"...", "use_cookies":false}`
  - 用途：创建链接下载任务
- `POST /api/local-audio`
  - `Content-Type: multipart/form-data`
  - 表单字段：`audio_files`（可多文件）、`preset`
  - 用途：把本地音频上传到当前服务并直接进入转写队列
- `GET /api/tasks`
  - 用途：获取最近 20 个任务的状态、进度、输出目录和产物清单

### 宿主机 MLX 接口

- `GET /health`
  - 用途：确认宿主机 MLX 服务已启动
- `POST /api/transcribe`
  - `Content-Type: application/json`
  - 请求体示例：

```json
{
  "audio_relative_path": "2026-04-07/demo/demo.mp3",
  "audio_path": "/downloads/2026-04-07/demo/demo.mp3",
  "language": "zh",
  "model": "large-v3",
  "batch_size": 12,
  "quant": "4bit"
}
```

  - 返回：`text`、`segments`、`language`、`backend`、`elapsed_seconds`

## Docker Hub 镜像

- 仓库地址：`zhangjinhong/ytdlp-webui`
- 拉取：`docker pull zhangjinhong/ytdlp-webui:latest`

> 如果你的服务器是 x86_64（amd64）架构且遇到镜像架构不匹配问题，可以在本机或服务器上重新构建镜像后运行。

## 目录结构

```
webui/               Web UI 主程序
mlx_service/         Apple Silicon 宿主机 MLX 转写服务
scripts/             本地快捷脚本（可选）
Dockerfile           Docker 构建文件
requirements.txt     Python 依赖
```

## 免责声明

本项目仅供学习与个人使用，请遵守目标网站的服务条款与版权政策。
