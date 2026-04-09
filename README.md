# Video-Downloade

一个本地优先的视频下载、逐字稿生成与知识库整理工具，当前同时提供 `Web UI + CLI + Docker + Skill` 四套入口。

项目主线已经比较明确：

- 网页服务：适合直接粘贴链接并查看任务进度
- Docker 容器：适合一键部署和复用现成 Web 服务
- CLI：适合脚本、AI 代理、批量任务和容器内调用
- Skill：适合让 Codex、Claude Code、Cursor Agent 等工具直接复用这套 CLI 契约

## 当前能力

- Web UI：支持多任务队列、任务状态和产物路径展示
- CLI：支持 `capture / download / audio / artifacts / knowledge / doctor / serve`
- 字幕优先：优先直提平台字幕，失败后回退到 MP3 转写
- sidecar 产物：原始稿、解析稿、逐字稿、知识库稿、转写信息 JSON
- Docker 部署：可直接 `docker compose up -d --build`
- AI 集成：稳定 `--json / --output paths / --result-file` 输出，适合代理程序消费

## 平台支持

| 平台 | 输入形态 | 推荐认证方式 | 当前说明 |
| --- | --- | --- | --- |
| YouTube | 网页链接、分享链接 | `YOUTUBE_COOKIES_FROM_BROWSER=chrome` | 字幕优先，部分视频依赖 `YTDLP_REMOTE_COMPONENTS=ejs:github` |
| Bilibili | 网页链接、分享文案 | `BILIBILI_COOKIES_FROM_BROWSER=chrome` 或 `BILIBILI_COOKIES_PATH` | 字幕直提成功率更高 |
| Douyin | 网页链接、分享短链、分享文案 | `DOUYIN_COOKIES_FROM_BROWSER=chrome` 或 `DOUYIN_COOKIES_PATH` | 内部已带专用 fallback provider，适合分享链接下载 |

建议第一次使用前先跑：

```bash
video-downloade doctor --json
```

## 文档入口

- [README.md](README.md)：项目概览、安装、快速上手
- [docs/cli.md](docs/cli.md)：CLI、AI 集成、批量与知识库工作流
- [docs/docker-deployment.md](docs/docker-deployment.md)：Docker 一键部署与容器内 CLI 用法
- [docs/input-expansion-roadmap.md](docs/input-expansion-roadmap.md)：分享链接识别、多端入口和 APK 路线
- [docs/creator-batch-workflow.md](docs/creator-batch-workflow.md)：搭配 `web-access` 批量抓取创作者视频并整理成知识库
- [docs/open-source-launch.md](docs/open-source-launch.md)：开源发布文案与推文草稿
- [skills/README.md](skills/README.md)：公开 skill 目录与安装方式

> 当前更适合个人、本地或小范围自用，不建议直接作为公共下载站点大规模对外开放。

## 快速开始

### Docker Compose

推荐对外展示的默认部署方式：

```bash
cp .env.example .env
docker compose up -d --build
```

默认访问地址：

```text
http://localhost:8080
```

默认下载目录挂载：

```text
${HOME}/Downloads:/downloads
```

启动后可以先做一次容器内自检：

```bash
docker compose exec ytdl-webui video-downloade doctor --json
```

如果你想直接在容器里走完整的视频知识库链路：

```bash
docker compose exec ytdl-webui \
  video-downloade capture "https://www.bilibili.com/video/BVxxxx" \
  --knowledge \
  --json
```

Cookies 场景可在本地 `.env` 中配置：

```bash
DOCKER_COOKIES_PATH=/cookies.txt
DOCKER_YOUTUBE_COOKIES_PATH=/youtube.cookies.txt
DOCKER_BILIBILI_COOKIES_PATH=/bilibili.cookies.txt
DOCKER_DOUYIN_COOKIES_PATH=/douyin.cookies.txt
```

然后把文件挂进容器：

```yaml
volumes:
  - ${HOME}/Downloads:/downloads
  - ./youtube.cookies.txt:/youtube.cookies.txt:ro
  - ./bilibili.cookies.txt:/bilibili.cookies.txt:ro
```

### Docker Run

如果你更希望直接运行镜像，推荐先在本地构建一个稳定标签：

```bash
docker build -t video-downloade:local .

docker run --rm -d -p 8080:8080 \
  -v "$HOME/Downloads:/downloads" \
  --name ytdlp-webui \
  video-downloade:local
```

镜像内同样安装了 `video-downloade`，所以除了 Web UI，也可以直接调用 CLI：

```bash
docker exec -it ytdlp-webui video-downloade doctor --json
```

### 本地运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env
python webui/app.py
```

如果你只想用 CLI，不必先启动 Web：

```bash
python -m webui.cli --help
```

### 关键环境变量

首次启动前建议先补好 `.env`：

- `OPENROUTER_API_KEY`：音频转写必需
- `AI_CLEANUP_API_KEY`：清洗稿必需
- `ARTICLE_DRAFT_API_KEY`：解析稿必需
- `YOUTUBE_COOKIES_FROM_BROWSER` / `YOUTUBE_COOKIES_PATH`：提升 YouTube 下载和字幕直提成功率
- `BILIBILI_COOKIES_PATH` / `BILIBILI_COOKIES_FROM_BROWSER`：提升 B 站字幕直提成功率
- `DOUYIN_COOKIES_PATH` / `DOUYIN_COOKIES_FROM_BROWSER`：为受限抖音内容预留平台级登录态
- `YTDLP_REMOTE_COMPONENTS=ejs:github`：为部分受 JS challenge 保护的 YouTube 视频启用格式解析
- `KEEP_TRANSCRIPTION_INPUT=false`：默认不保留转写前预处理音频，避免下载目录里出现第二个 MP3

知识库整理默认会沿用 `ARTICLE_DRAFT_*` 这一组配置；如果你想给知识库链路单独指定模型或后端，可以在 `.env` 里额外设置 `KNOWLEDGE_DRAFT_*`。

推荐的认证检查顺序：

1. 先在浏览器登录目标平台。
2. 优先用 `*_COOKIES_FROM_BROWSER=chrome`。
3. 再跑 `video-downloade doctor --json` 确认 `*_auth_configured` 已变成 `true`。
4. 如果浏览器方案不可用，再回退到 `*_COOKIES_PATH=/absolute/path/to/cookies.txt`。

## Web 使用方式

1. 在输入框粘贴一个或多个链接，或直接粘贴 Bilibili / YouTube / Douyin 分享文案。
2. 选择下载预设：`Highest Video (MP4)`、`Best Audio (MP3)` 或 `Markdown 逐字稿（字幕优先）`。
3. 点击开始任务。
4. 在任务列表中查看状态、输出路径和逐字稿产物。

当前 Web API 入口：

- `POST /api/start`：提交任务
- `GET /api/tasks`：查询最近任务

输入层会自动从分享文案中提取 URL，例如：

```text
【SpaceX冲击史上最大IPO，马斯克想要的真的只是一家“公司”吗？】 https://www.bilibili.com/video/BV14PXKBbEhy/?share_source=copy_web&vd_source=...
```

这也为后续安卓端和分享入口复用同一套后端打下了基础。

逐字稿链路的预处理音频默认写入系统临时目录，不会在下载目录里额外留下第二个可见 MP3；只有你显式开启 `KEEP_TRANSCRIPTION_INPUT=true` 时，才会保留这类调试文件。

## CLI 用法

安装开发模式命令：

```bash
pip install -e .
```

高频命令：

```bash
# URL -> 逐字稿 + 解析稿 + 知识库稿
video-downloade capture "https://www.bilibili.com/video/BVxxxx" \
  --knowledge \
  --json

# YouTube：建议传平台专用登录态
video-downloade capture "https://www.youtube.com/watch?v=..." \
  --youtube-cookies-from-browser chrome \
  --knowledge \
  --json

# 批量 URL：从文件或 stdin 输入
video-downloade capture \
  --input-file ./urls.txt \
  --knowledge \
  --jobs 0 \
  --resume \
  --result-file ./capture.json \
  --json
cat ./urls.txt | video-downloade capture --stdin --output paths

# 仅下载音频或视频，不生成逐字稿
video-downloade download "https://www.bilibili.com/video/BVxxxx" \
  --preset "Best Audio (MP3)" \
  --json

# 兼容旧链路：先下载音频，再顺带补逐字稿和知识库稿
video-downloade download "https://www.bilibili.com/video/BVxxxx" \
  --preset "Best Audio (MP3)" \
  --transcript \
  --knowledge \
  --json

# 本地音频 -> 逐字稿 + 知识库稿
video-downloade audio "/path/to/file.mp3" --knowledge --json

# 反查某个音频或 sidecar 对应的整组产物
video-downloade artifacts "/path/to/file.mp3" --json
video-downloade artifacts "/path/to/file.mp3" --full-metadata --json

# 已经有 sidecar 时，单独补生成知识库稿
video-downloade knowledge "/path/to/file.mp3" --json

# 检查依赖和配置
video-downloade doctor --json

# 启动现有 Web UI
video-downloade serve --port 8080
```

几个高频 CLI 选项：

- `--input-file` / `--stdin`：批量输入 URL 或音频路径
- `--output text|json|paths`：切换输出格式，方便人类或 AI 消费
- `--result-file`：把结果 JSON 增量落盘，长批量任务中途打断后可直接续跑
- `--jobs`：批量并发任务数，`0` 表示自动；URL 批量默认会自动拉高到更积极的并发档位
- `--resume`：优先复用 checkpoint 和已有逐字稿 / 知识库产物，避免重复下载、重复转写
- `--cookies-from-browser`：直接读取浏览器登录态
- `--youtube-cookies-path` / `--youtube-cookies-from-browser`：只覆盖 YouTube 登录态
- `--bilibili-cookies-path` / `--bilibili-cookies-from-browser`：只覆盖 Bilibili 登录态
- `--douyin-cookies-path` / `--douyin-cookies-from-browser`：只覆盖 Douyin 登录态
- `--cleanup/--no-cleanup`、`--article/--no-article`：控制成本和处理深度
- `--knowledge/--no-knowledge`：在 `capture / download --transcript / audio` 后继续生成知识库稿
- `--knowledge-model` / `--knowledge-prompt-file`：单次任务覆盖知识库整理配置
- `--overwrite-knowledge`：覆盖已有 `xxx - 知识库.md`
- `artifacts` 默认返回 metadata 摘要；加 `--full-metadata` 才返回完整 `转写信息.json`

## Creator Batch Workflow

如果你想把“某个博主的一组视频”直接整理成 Markdown 知识库，推荐把本仓库 skill 和 [`web-access`](https://github.com/eze-is/web-access) 组合起来用。

推荐流程：

1. 安装本仓库 skill：`./scripts/install-video-downloade-skill`
2. 安装 [`web-access`](https://github.com/eze-is/web-access)：
   `claude plugin marketplace add https://github.com/eze-is/web-access`
   `claude plugin install web-access@web-access --scope user`
3. 用 `web-access` 打开创作者主页、系列页或合集页，把目标视频链接提取到 `./urls.txt`
4. 直接执行批量知识库命令：

```bash
video-downloade capture \
  --input-file ./urls.txt \
  --knowledge \
  --jobs 0 \
  --resume \
  --result-file ./runs/creator-series/capture.json \
  --output paths
```

`--result-file + --resume` 现在会按条目持续写 checkpoint；如果中途停掉，再跑同一条命令就会跳过已经完成的 URL，并优先复用下载目录里已有的逐字稿 sidecar。对长批量任务来说，重跑时通常能省掉绝大部分重复时间。

更完整的 prompt 模板、demo 链接文件和实操说明见 [docs/creator-batch-workflow.md](docs/creator-batch-workflow.md)。
## Open Source

本项目当前采用 [MIT License](LICENSE)。

如果你准备对外发布自己的实例，建议：

- 把服务定位为个人或团队内部工具，而不是公开大规模下载站
- 不要把真实 API Key、cookies.txt 或浏览器 profile 路径提交到仓库
- 把 `.env`、容器挂载目录和 Cookies 管理写成你的部署规范
更完整的 CLI 说明见 [docs/cli.md](docs/cli.md)。

## 视频知识库链路

当前推荐流程已经整理成：

1. 平台字幕直提
2. 无字幕时回退到 MP3 转写
3. 逐字稿清洗
4. 可选解析稿生成
5. 可选知识库整理

当前默认方向：

- 转写后端：OpenRouter `openai/gpt-audio-mini`
- 清洗后端：智谱 OpenAI 兼容接口 `GLM-4.5`
- 清洗提示词：`角色提示词.md`
- 解析提示词：`解析提示词.md`
- 知识库提示词：`知识库提示词.md`

如果你使用 `capture --knowledge` 或 `audio --knowledge`，成功后通常会额外产出：

- `xxx - 原始逐字稿.txt`
- `xxx - 解析稿.md`
- `xxx - 知识库.md`
- `xxx - 逐字稿.md`
- `xxx - 转写信息.json`

## Cookies 与平台登录态

如果你发现 `YouTube` 或部分 `Bilibili` 视频在“字幕优先”模式下总是直接回退到 MP3，通常不是路由逻辑失效，而是平台要求登录态才能访问字幕接口。

推荐顺序：

1. 最省事：直接用浏览器登录态

```bash
video-downloade capture "https://www.youtube.com/watch?v=..." \
  --youtube-cookies-from-browser chrome \
  --json
```

也可以写进 `.env`：

```bash
YOUTUBE_COOKIES_FROM_BROWSER=chrome
YTDLP_REMOTE_COMPONENTS=ejs:github
```

常见浏览器参数：

- `chrome`
- `edge`
- `chrome:Profile 1`
- `firefox::default`

2. 兼容方案：导出 `cookies.txt`

```bash
YOUTUBE_COOKIES_PATH=/absolute/path/to/youtube.cookies.txt
BILIBILI_COOKIES_PATH=/absolute/path/to/bilibili.cookies.txt
DOUYIN_COOKIES_PATH=/absolute/path/to/douyin.cookies.txt
```

说明：

- Web UI 里“启用 Cookies”只表示这次任务允许使用 Cookies
- 真正要想生效，还需要你提前配置好平台对应的登录态
- 推荐把 YouTube、Bilibili 和 Douyin 分开配置，避免串用
- 开源仓库不要提交真实 Cookies；只在本地 `.env` 和本地 Cookies 文件里保存
- Docker Compose 场景下，建议用 `DOCKER_COOKIES_PATH=/cookies.txt` 一类容器内路径

如果遇到 YouTube 的 bot 校验或格式受保护问题，可参考：

- [yt-dlp FAQ: Passing cookies to yt-dlp](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#passing-cookies-to-yt-dlp)
- [yt-dlp FAQ: Extractors / Exporting YouTube cookies](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies)
- [yt-dlp Wiki: PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide)

## AI / Skill 集成

仓库里现在提供两套 skill 目录：

- [skills/README.md](skills/README.md)：面向开源发布的公开 skill
- [.codex/skills/video-downloade-cli/SKILL.md](.codex/skills/video-downloade-cli/SKILL.md)：当前仓库内直接使用的本地 skill

推荐的 AI 调用流程：

1. 先跑 `video-downloade doctor --json`
2. URL 输入优先用 `capture --knowledge --json`
3. 本地音频优先用 `audio --knowledge --json`
4. 已有 sidecar 时用 `artifacts` / `knowledge`
5. 优先消费 `--json` 或 `--output paths`，不要默认驱动浏览器

如果你要把公开 skill 安装到 Codex：

```bash
./scripts/install-video-downloade-skill
```

这会把 `skills/video-downloade-cli` 复制到 `${CODEX_HOME:-$HOME/.codex}/skills/video-downloade-cli`。

## 目录结构

```text
webui/               Web UI、Flask API 与转写主流程
docs/                对社区公开的说明文档
doc/                 内部设计草稿（默认不作为公开文档）
skills/              对外发布的 skill 目录
.codex/skills/       仓库内直接使用的本地 skill
AGENT.md             给 AI 代理看的命令行使用说明
pyproject.toml       CLI 安装入口与打包配置
scripts/             本地辅助脚本与 skill 安装脚本
Dockerfile           Docker 构建文件
docker-compose.yml   Docker Compose 启动文件
requirements.txt     Python 依赖
```

## 免责声明

本项目仅供学习与个人使用，请遵守目标网站的服务条款、版权政策与当地法律法规。
