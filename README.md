# 幕库 Muku

> Video-to-Markdown for Bilibili, YouTube, Douyin, and other yt-dlp-supported platforms
>
> 把知识视频沉淀为可检索、可连接、可被 AI 持续使用的 Markdown 知识库

把平台上的知识视频，从“刷过就忘”，变成你本地可检索、可连接、可被 AI 持续使用的 Markdown 知识库。

幕库主打 Bilibili、YouTube、Douyin 等知识密度高的平台，同时兼容其他 yt-dlp 支持的站点。它的重点不是做一个“什么都下”的通用下载器，而是把链接、片单、创作者列表和本地音频沉淀为可以长期复用的知识资产。当前项目同时提供 `Web UI + CLI + Docker + Skill` 四套入口。

## 我该怎么开始

- 新手第一次使用：优先走 `Docker Desktop + Web UI`
- 想批量处理、接入脚本或 agent：优先走 `CLI`
- 想把能力装进 Codex：用仓库自带的 `Skill`

如果你是 Windows 新手用户，建议先看 [docs/windows.md](docs/windows.md)。

## 官方验证矩阵

| 系统 / 环境 | 推荐入口 | 当前状态 | 说明 |
| --- | --- | --- | --- |
| Windows 11 + Docker Desktop | Web UI | 已验证 | 适合第一次使用 |
| macOS + Docker Desktop | Web UI | 已验证 | 推荐默认部署方式 |
| macOS + Python 3.12 | CLI / 本地 Web | 已验证 | 适合开发与调试 |
| Ubuntu / Linux | CLI | CI 持续验证 | 更适合开发者与服务器 |

## 3 分钟快速开始

对新手来说，最稳的入口是 Docker。

### macOS / Linux

```bash
cp .env.example .env
docker compose up -d --build
```

### Windows PowerShell

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

默认访问地址：

```text
http://localhost:5657
```

第一次启动后，建议立刻做这三步：

1. 打开右上角“设置”
2. 设置默认下载目录和模型 / Key
3. 跑一次 `doctor`

```bash
docker compose exec ytdl-webui video-downloade doctor
docker compose exec ytdl-webui video-downloade doctor --json
```

## 幕库是什么

幕库，英文名 `Muku`，是一个主打 Bilibili、YouTube、Douyin，并兼容其他 yt-dlp 平台的 `Video-to-Markdown` 工具。

`幕` 代表字幕、画面和内容现场，`库` 代表本地知识库。幕库想做的不是把视频“存下来”，而是把其中的知识“收入库”。

对外我们会直接用 `Video-to-Markdown` 来描述幕库，因为这比抽象口号更容易理解，也更准确地点出了项目的最终产物：`Markdown`。

## 为什么最后是 MD

- `MD` 不是输出格式细节，而是项目的真正目标：把视频变成可以长期沉淀的知识资产
- Markdown 天然适合 Git、Obsidian、全文检索、RAG 和 agent 工作流
- 相比只留下 `mp4` 或 `mp3`，`md` 更容易被引用、连接、改写和再加工
- 所以幕库的重点不是“下载完成”，而是“入库完成”

## 幕库要解决的问题

- 收藏夹、稍后再看、创作者主页里有很多高质量视频，但看过之后很难复用
- 平台内容天然碎片化，不适合沉淀到 Obsidian、RAG 或个人知识库
- 传统下载器关注的是文件拿到没有，幕库关注的是知识有没有被整理成可读、可索引、可连接的 Markdown
- 当你想让 AI 帮你持续跟踪一组博主、频道或系列时，需要稳定的 CLI 和 skill，而不是每次重新点网页

## 幕库适合什么场景

- 单条视频链接在 Web 默认整理为 `逐字稿.md`、`解析稿.md`；需要时可在 Web 显式勾选知识库稿，任务详情里也能直接预览这些产物
- 批量把 B 站合集、YouTube 系列、抖音分享列表沉淀到本地知识库
- 把研究型、课程型、访谈型、播客型内容转为 Markdown 资产
- 让 AI agent 根据 skill 自动执行 `采集链接 -> 批量入库 -> 返回产物路径`
- 接入 Obsidian、本地文件夹、全文检索、RAG 或其他 AI 工作流

## 幕库不是什么

- 不是以娱乐内容下载为核心的通用下载器
- 不是适合大规模公网公开部署的下载站
- 不以“下载成功率最大化”作为唯一目标，而是优先服务“知识沉淀质量”

## 平台支持

| 平台 | 输入形态 | 推荐认证方式 | 当前说明 |
| --- | --- | --- | --- |
| YouTube | 网页链接、分享链接 | Docker 优先 `YOUTUBE_COOKIES_PATH`；本地运行可用 `YOUTUBE_COOKIES_FROM_BROWSER=chrome` | 字幕优先，部分视频依赖 `YTDLP_REMOTE_COMPONENTS=ejs:github` |
| Bilibili | 网页链接、分享文案 | Docker 优先 `BILIBILI_COOKIES_PATH`；本地运行可用 `BILIBILI_COOKIES_FROM_BROWSER=chrome` | 高知识密度视频场景表现更好 |
| Douyin | 网页链接、分享短链、分享文案 | Docker 优先 `DOUYIN_COOKIES_PATH`；本地运行可用 `DOUYIN_COOKIES_FROM_BROWSER=chrome` | 适合用来沉淀短视频里的观点和素材 |
| 其他 yt-dlp 支持的平台 | 建议直接粘贴完整链接 | 优先 `COOKIES_PATH`；本地运行可用 `COOKIES_FROM_BROWSER=chrome` | Web UI 会直接放行直链，适合 Vimeo、X、TikTok 等 yt-dlp 已支持站点；快手、视频号当前仍需额外 provider / bridge |

建议第一次使用前先跑：

```bash
video-downloade doctor --json
```

注意：`doctor` 现在会把认证状态拆成 `configured` 和 `verified` 两层。浏览器登录态通常只能算“已配置”，真正的 `verified` 更偏向容器内可见的 `cookies.txt` 或一次真实任务验证；Docker 环境更稳的默认方案仍是挂载平台专用 `cookies.txt`。

## 核心工作流

1. 输入单条链接、分享文案、批量 URL 列表，或直接输入本地音频
2. 优先直提平台字幕，失败后回退到 MP3 转写
3. 生成逐字稿、解析稿，以及按入口 / 开关决定是否继续生成知识库稿和转写 metadata
4. 产物落到本地文件系统，继续喂给 Obsidian、RAG、AI agent 或你自己的知识库流程

按入口区分的默认产物：

- Web UI 默认产出：`xxx - 原始逐字稿.txt`、`xxx - 逐字稿.md`、`xxx - 解析稿.md`、`xxx - 转写信息.json`
- Web UI 勾选“生成知识库稿”后：会继续产出 `xxx - 知识库.md`
- CLI 在传入 `--knowledge` 时，或后续单独运行 `video-downloade knowledge` 时，会额外生成 `xxx - 知识库.md`

文件说明：

- `xxx - 原始逐字稿.txt`：原始逐字稿，仅保留原始文本
- `xxx - 逐字稿.md`：清洗后的逐字稿正文，不重复附带原始稿或解析稿
- `xxx - 解析稿.md`：最终解析成稿正文，默认遵循 `解析提示词.md`
- `xxx - 知识库.md`：在 Web 显式勾选知识库稿、CLI `--knowledge`，或后续单独整理时生成
- `xxx - 转写信息.json`

## 快速开始

### Docker Compose

推荐给第一次使用项目的用户：

macOS / Linux：

```bash
cp .env.example .env
docker compose up -d --build
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

默认会在仓库里生成两个持久化目录：

- `./docker-data/downloads`：下载产物
- `./docker-data/config`：网页端与 CLI 保存的运行配置

Windows 和 macOS 默认都可以直接使用这套映射，不需要先手改绝对路径。

默认访问地址：

```text
http://localhost:5657
```

启动后推荐先做三步：

1. 打开网页右上角的“设置”
2. 在设置抽屉里先补平台 Cookies，再配置默认下载目录、转写服务、清洗/解析模型与提示词；知识库整理配置主要供 CLI `--knowledge` 和后续整理链路复用
3. 回到双栏工作台左侧发起任务，右侧观察队列与详情，再做一次容器内自检

```bash
docker compose exec ytdl-webui video-downloade doctor --json
docker compose exec ytdl-webui video-downloade config --json
```

如果你想直接跑完整的知识库链路：

```bash
docker compose exec ytdl-webui \
  video-downloade capture "https://www.bilibili.com/video/BVxxxx" \
  --knowledge \
  --json
```

### 本地运行

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env
video-downloade serve --port 5657
```

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
Copy-Item .env.example .env
video-downloade serve --port 5657
```

如果你只想用 CLI：

```bash
python -m webui.cli --help
```

## 能力矩阵

| 入口 | 适合场景 | 默认产物 | 知识库稿 | 推荐认证方式 |
| --- | --- | --- | --- | --- |
| Web UI | 单条链接、人工观察任务状态、在线预览产物 | 原始逐字稿、逐字稿、解析稿、metadata | 默认不直接生成；可显式勾选知识库稿 | Docker 优先平台专用 `cookies.txt`；本地运行可用浏览器登录态或 `cookies.txt` |
| CLI | 批量任务、脚本、agent、断点续跑 | 按命令生成逐字稿链路产物 | `--knowledge` 或 `video-downloade knowledge` | 平台专用 `cookies.txt` 最稳；本地运行时可用 `*_COOKIES_FROM_BROWSER` |
| Docker Compose | Web UI + 容器内 CLI | 网页默认产物同 Web；容器内 CLI 可跑完整链路 | 通过容器内 CLI 完整支持 | 优先挂载 `./cookies:/cookies:ro` 并配置 `DOCKER_*_COOKIES_PATH` |
| Skill | AI 自动入库、批量采集后处理 | 取决于 skill 调用的 CLI 参数 | 通常走 CLI `--knowledge` | 跟随底层 CLI / Docker 配置 |

## 关键环境变量

- `DOWNLOAD_DIR`：默认下载目录；本地运行建议填 macOS / Windows 的绝对路径
- `DOWNLOAD_ROOT_DIR`：可选的下载根目录限制；Docker 默认锁定为 `/downloads`
- `VIDEO_DOWNLOADE_CONFIG_DIR`：网页端和 CLI 保存运行配置的目录
- `DOCKER_DOWNLOADS_DIR`：Docker 映射到宿主机的真实下载目录，默认是 `./docker-data/downloads`
- `DOCKER_CONFIG_DIR`：Docker 映射到宿主机的真实配置目录，默认是 `./docker-data/config`
- `MUKU_WEB_PORT`：Docker 映射到宿主机的网页端口，默认 `5657`
- `OPENROUTER_API_KEY`：音频转写必需
- `OPENROUTER_BASE_URL`：转写服务 Base URL，支持兼容 OpenRouter 的网关
- `AI_CLEANUP_API_KEY`：清洗稿必需
- `ARTICLE_DRAFT_API_KEY`：解析稿必需
- `AI_CLEANUP_TIMEOUT_SECONDS` / `AI_CLEANUP_MAX_RETRIES`：清洗阶段超时与重试次数
- `ARTICLE_DRAFT_TIMEOUT_SECONDS` / `ARTICLE_DRAFT_MAX_RETRIES`：成稿阶段超时与重试次数
- `KNOWLEDGE_DRAFT_TIMEOUT_SECONDS` / `KNOWLEDGE_DRAFT_MAX_RETRIES`：知识库阶段超时与重试次数
- `COOKIES_PATH`：其他 yt-dlp 支持平台的通用 `cookies.txt` 路径
- `COOKIES_FROM_BROWSER`：其他 yt-dlp 支持平台可复用的通用浏览器登录态
- `YOUTUBE_COOKIES_PATH`：Docker 和本地运行都适用，是更稳的 YouTube 登录态方案
- `BILIBILI_COOKIES_PATH`：Docker 和本地运行都适用，是更稳的 B 站登录态方案
- `DOUYIN_COOKIES_PATH`：Docker 和本地运行都适用，是更稳的抖音登录态方案
- `YOUTUBE_COOKIES_FROM_BROWSER` / `BILIBILI_COOKIES_FROM_BROWSER` / `DOUYIN_COOKIES_FROM_BROWSER`：更适合本地 Python 运行时直接复用浏览器登录态
- Web 设置抽屉现在也可以直接保存通用 Cookies 和平台 Cookies；如果仓库里已经有 `cookies/youtube.cookies.txt`、`cookies/bilibili.cookies.txt`、`cookies/douyin.cookies.txt`，或 Docker 内挂载了 `/cookies/*.cookies.txt`，网页会直接识别并优先使用这些平台专用文件
- `YTDLP_REMOTE_COMPONENTS=ejs:github`：为部分受 JS challenge 保护的 YouTube 视频启用格式解析

推荐的认证检查顺序：

本地 Python 运行：

1. 先在浏览器登录目标平台
2. 优先准备平台专用 `cookies.txt`，并放到设置抽屉里填写，或直接放到仓库 `cookies/*.cookies.txt`
3. 本地调试时，再补 `*_COOKIES_FROM_BROWSER=chrome`
4. 再跑 `video-downloade doctor --json`，确认对应平台至少进入 `configured`；如果你用的是 `cookies.txt`，则还能进一步看到 `verified`

Docker 运行：

1. 先导出平台专用 `cookies.txt`
2. 通过 `./cookies:/cookies:ro` 挂进容器，并配置 `DOCKER_*_COOKIES_PATH=/cookies/*.cookies.txt`
3. 再跑 `video-downloade doctor --json`
4. 只有在你确认容器能读取宿主机浏览器配置时，再把 `*_COOKIES_FROM_BROWSER` 当调试手段，而不是默认方案

导出 `cookies.txt` 的最短路径：

1. 在浏览器里先登录目标平台
2. 用任意支持导出 Netscape `cookies.txt` 的浏览器扩展或导出工具，按平台分别导出
3. 文件命名为 `youtube.cookies.txt`、`bilibili.cookies.txt`、`douyin.cookies.txt`
4. 放到仓库 `./cookies/` 目录
5. Docker 用户在 `.env` 里配置 `DOCKER_*_COOKIES_PATH=/cookies/*.cookies.txt`

现在容器内会在运行任务前先把这些只读挂载的 Cookies 复制到临时可写文件，再交给 `yt-dlp`，所以保留 `./cookies:/cookies:ro` 这个更稳的挂载方式就可以。

如果你是 Docker 部署用户，需要区分两层路径：

- 网页和 CLI 里配置的下载目录，是容器内路径，例如 `/downloads/default`
- 真正落到 Windows / macOS 哪个文件夹，由 `DOCKER_DOWNLOADS_DIR` 决定

## 高频 CLI 命令

```bash
# URL -> 逐字稿 + 解析稿 + 知识库稿
video-downloade capture "https://www.bilibili.com/video/BVxxxx" \
  --knowledge \
  --json

# YouTube：建议带平台专用登录态
video-downloade capture "https://www.youtube.com/watch?v=..." \
  --youtube-cookies-from-browser chrome \
  --knowledge \
  --json

# 批量 URL -> Markdown 知识库
video-downloade capture \
  --input-file ./urls.txt \
  --knowledge \
  --jobs 0 \
  --resume \
  --result-file ./runs/capture.json \
  --output paths

# 批量任务实时进度（NDJSON，每个任务完成一行，结尾汇总）
video-downloade capture --input-file ./urls.txt --stream | tee progress.jsonl
# progress.jsonl 每行一个事件：task_done / task_failed / batch_complete，
# 方便 Monitor 类工具或 tail -f 消费。

# 本地音频 -> 知识库
video-downloade audio "/path/to/file.mp3" --knowledge --json

# 反查整组 sidecar 与 metadata
video-downloade artifacts "/path/to/file.mp3" --json

# 已有 sidecar 时单独补知识库稿
video-downloade knowledge "/path/to/file.mp3" --json

# 检查依赖和配置
video-downloade doctor --json

# 查看或保存默认配置
video-downloade config --json
video-downloade config \
  --download-dir "/Users/you/Downloads/muku" \
  --transcription-model openai/gpt-audio-mini \
  --cleanup-base-url https://openrouter.ai/api/v1 \
  --cleanup-model stepfun/step-3.7-flash \
  --article-base-url https://openrouter.ai/api/v1 \
  --article-model stepfun/step-3.7-flash \
  --knowledge-base-url https://openrouter.ai/api/v1 \
  --knowledge-model stepfun/step-3.7-flash \
  --json

# 启动现有 Web UI
video-downloade serve --port 5657
```

更多命令和参数见 [docs/cli.md](docs/cli.md)。

## 第一次排障建议

如果你是第一次部署，优先按这个顺序检查：

1. 运行 `video-downloade doctor`
2. 确认 `ffmpeg` 和 `yt-dlp` 是 `OK`
3. 确认 `transcript capture` 是 `OK`
4. 如果 YouTube / Douyin 失败率高，再补平台专用 Cookies；Docker 优先 `cookies.txt`

补一句：`doctor` 现在会直接展示 `configured` 和 `verified`。如果你在 Docker 里看到浏览器登录态停留在 `CONFIGURED_ONLY`，这不是 bug，而是它故意提醒你“容器里这类来源无法预检”，这时更稳的方案仍是平台专用 `cookies.txt`。

如果你看到“response was truncated before completion”这类报错，说明远端转写响应被截断了。优先尝试：

- 确认当前版本已经启用默认的 chunked ASR；长音频会优先按固定时长切片再转写
- 改用平台直提字幕
- 把 `TRANSCRIPTION_CHUNK_SECONDS` 调小，例如从 `600` 改到 `300`
- 后续再补知识库整理，不要第一次就把链路拉满

### 批量任务卡住 / openrouter.ai 连接失败

批量下载或转写中途卡死、报 TLS 握手超时或 DNS 解析失败，通常是 openrouter.ai 在国内网络下被间歇性干扰。按顺序排查：

1. **Cookies 预检拦截**：批量启动前会自动预检 B 站登录态（请求 `api.bilibili.com/x/web-interface/nav`）。若 cookies 过期或返回 412，会立即中止并提示。确认 cookies 有效但想跳过预检，加 `--skip-cookie-check`。
2. **显式代理**：在 `.env` 配置 `OPENROUTER_PROXY=http://127.0.0.1:7897`（你的本地代理端口）。配置后转写、清洗、知识库调用都会走代理，告别系统环境变量透传的 SSL 错乱。
3. **代理 SSL 证书问题**：若代理导致证书校验失败，临时设 `OPENROUTER_INSECURE_SKIP_VERIFY=true`（仅在受控环境使用）。
4. **重试已强化**：默认 6 次重试 + 退避封顶 60 秒 + 20% 抖动，连接/读取超时分开（30s/600s）。仍失败可调 `OPENROUTER_MAX_RETRIES`、`OPENROUTER_RETRY_BACKOFF_MAX`。
5. **看不到进度**：加 `--stream`，每个任务完成立即输出一行 NDJSON，配合 `tee progress.jsonl` 或 Monitor 工具实时消费。

## Web 工作台

当前 Web UI 已经改成更适合日常使用的双栏工作台：

- 桌面端默认是单屏双栏：左侧发任务，右侧盯队列和详情
- 左侧：发起新任务、选择模式、临时覆盖本次保存目录
- 右侧：观察任务队列、切换到单条任务详情、看输出路径、报错和产物预览
- 右上角“设置”：打开折叠式配置抽屉，集中维护平台 Cookies、默认下载目录、模型、服务地址和提示词
- 当前网页任务默认产出逐字稿和解析稿；如果你已经补齐知识库配置，也可以在提交任务时显式勾选继续生成 `知识库.md`

这样页面不会再因为配置项太多而无限变长，部署后也更适合直接给自己或小团队使用。

## 迁移到另一台电脑

如果你要把幕库迁到另一台电脑，最少需要关注这几类内容：

- 建议复制：
  - `.env`
  - `docker-data/config/settings.json`
  - 可选的 `docker-data/downloads`
- 需要重新检查：
  - 绝对下载路径是否仍存在
  - `*_COOKIES_PATH` 或 `DOCKER_*_COOKIES_PATH` 是否仍指向正确文件
  - Docker volume 映射是否仍然成立
  - 本地 Python 运行时的 `*_COOKIES_FROM_BROWSER` 在新机器上是否真的可用

一个实用原则是：配置可以迁，路径和登录态要重新验证。

## Skill 与 AI 自动入库

幕库的核心不是“把一个链接下下来”，而是把一组高价值内容持续收入库。所以项目默认提供了可供 agent 直接复用的 skill。

- 公开 skill：[skills/muku-video-to-md/SKILL.md](skills/muku-video-to-md/SKILL.md)
- 仓库内本地 skill：[.codex/skills/muku-video-to-md/SKILL.md](.codex/skills/muku-video-to-md/SKILL.md)

安装到 Codex：

```bash
./scripts/install-muku-skill
```

如果你要做“博主主页 / 系列页 / 片单 -> 批量知识库”的自动化，推荐把幕库和 [`web-access`](https://github.com/eze-is/web-access) 组合起来：

1. 用浏览器型 agent 把目标页面提取为 `./urls.txt`
2. 再让 `muku-video-to-md` 调用：

```bash
video-downloade capture \
  --input-file ./urls.txt \
  --knowledge \
  --jobs 0 \
  --resume \
  --result-file ./runs/creator-series/capture.json \
  --output paths
```

这样一来，AI 处理的就不再是一堆零散视频，而是一套持续生长的本地 Markdown 知识库。

## 开源状态

- 协议：MIT，见 [LICENSE](LICENSE)
- 适合个人、本地、自托管、小团队内部使用
- 当前 Docker、CLI、Web UI、Skill 共享同一套底层链路，但 Web 默认仍更聚焦单条任务与逐字稿 / 解析稿
- 目前网页端保存的是本地或私有部署配置，不建议直接暴露为公网多人共用面板

## 文档入口

- [docs/cli.md](docs/cli.md)：CLI、AI 集成、批量与知识库工作流
- [docs/docker-deployment.md](docs/docker-deployment.md)：Docker 一键部署与容器内 CLI 用法
- [docs/creator-batch-workflow.md](docs/creator-batch-workflow.md)：搭配 `web-access` 批量采链接并自动入库
- [docs/input-expansion-roadmap.md](docs/input-expansion-roadmap.md)：分享链接识别、多端入口和 APK 路线
- [skills/README.md](skills/README.md)：公开 skill 目录与安装方式

## 当前边界

- 当前更适合个人、本地或小范围自用
- 当前主要面向本地知识库、研究整理和 AI 工作流
