# Video-Downloade

一个本地优先的视频下载与逐字稿转换工具，当前提供 `Web UI + CLI` 两种入口。项目主线是：输入 Bilibili / YouTube 等链接，下载视频或音频，并在需要时生成 Markdown 逐字稿与 sidecar 文件。

## 当前能力

- Web UI：直接粘贴链接，支持多任务队列与进度展示
- CLI：适合脚本、AI 代理和批处理调用
- 下载预设：最高画质视频、MP3 音频、Markdown 逐字稿
- 逐字稿路由：优先直提平台字幕，失败后回退到 MP3 转写
- sidecar 产物：原始稿、解析稿、逐字稿、转写信息 JSON
- Docker 部署：支持本地一键启动

## 项目状态

- 已可使用：本地 Web 下载、CLI 调用、Docker 运行、字幕优先逐字稿流程
- 正在完善：公开文档整理、Docker 一键部署规范、分享链接识别、安卓 APK 封装
- 路线文档：
  - [公开文档入口](docs/README.md)
  - [Docker 部署规划](docs/docker-deployment.md)
  - [输入链接与多端拓展路线](docs/input-expansion-roadmap.md)

> 提示：当前更适合个人、本地或小范围自用，不建议直接作为公共下载站点大规模对外开放。

## 文档结构

- `README.md`：GitHub 首页，只保留项目概览、安装与快速上手
- `docs/`：对社区公开的说明文档、路线图与部署文档
- `doc/`：内部设计草稿与开发备忘，不作为公开文档源

这个分层的目标是把“给使用者看的说明”和“开发中的想法草稿”彻底分开，后面开源时会更清晰。

## 快速开始

### Docker Compose

直接从源码目录启动：

```bash
cp .env.example .env
docker compose up -d --build
```

默认访问：`http://localhost:8080`

默认下载目录挂载为：

```bash
${HOME}/Downloads:/downloads
```

如果要启用 Cookies，可在本地 `.env` 中配置：

```bash
DOCKER_COOKIES_PATH=/cookies.txt
```

然后再把你的 Cookies 文件挂进容器，例如：

```yaml
volumes:
  - ${HOME}/Downloads:/downloads
  - ./cookies.txt:/cookies.txt:ro
```

### Docker Run

如果你更希望直接运行镜像：

```bash
docker pull zhangjinhong/ytdlp-webui:latest

docker run --rm -d -p 8080:8080 \
  -v "$HOME/Downloads:/downloads" \
  --name ytdlp-webui \
  zhangjinhong/ytdlp-webui:latest
```

镜像内也会安装 `video-downloade`，所以除了 Web UI，你也可以在容器里直接调用同一套 CLI 契约。

### 本地运行

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python webui/app.py
```

首次启动前建议先补好 `.env`：

- `OPENROUTER_API_KEY`：音频转写必需
- `AI_CLEANUP_API_KEY` / `ARTICLE_DRAFT_API_KEY`：清洗稿和解析稿必需
- `YOUTUBE_COOKIES_FROM_BROWSER` / `YOUTUBE_COOKIES_PATH`：提升 YouTube 下载和字幕直提成功率
- `BILIBILI_COOKIES_PATH` / `BILIBILI_COOKIES_FROM_BROWSER`：提升 B 站字幕直提成功率

开源协作约定：

- `.env` 不提交
- `cookies.txt` / `*.cookies.txt` 不提交
- 仓库只保留 `.env.example` 作为模板

## Web 使用方式

1. 在输入框粘贴一个或多个链接，或直接粘贴 Bilibili / YouTube 分享文案。
2. 选择下载预设：`Highest Video (MP4)`、`Best Audio (MP3)` 或 `Markdown 逐字稿（字幕优先）`。
3. 点击开始任务。
4. 在任务列表中查看状态、输出路径和逐字稿产物。

当前 Web API 入口很简单：

- `POST /api/start`：提交任务
- `GET /api/tasks`：查询最近任务

输入层会自动从分享文案中提取 URL，例如：

```text
【SpaceX冲击史上最大IPO，马斯克想要的真的只是一家“公司”吗？】 https://www.bilibili.com/video/BV14PXKBbEhy/?share_source=copy_web&vd_source=...
```

这也为后续安卓端和分享入口复用同一套后端打下了基础。

## CLI 用法

安装开发模式命令：

```bash
pip install -e .
```

安装后可用命令：

```bash
# 从 URL 直接生成 Markdown 逐字稿
# 路由：先尝试直提平台字幕，失败再回退到 MP3 转写
video-downloade capture "https://www.bilibili.com/video/BVxxxx" --json

# 批量 URL：从文件或 stdin 输入
video-downloade capture --input-file ./urls.txt --output paths
cat ./urls.txt | video-downloade capture --stdin --json

# 仅下载音频或视频，不生成逐字稿
video-downloade download "https://www.bilibili.com/video/BVxxxx" \
  --preset "Best Audio (MP3)" \
  --json

# 处理本地音频
video-downloade audio "/path/to/file.mp3" --source-url "https://example.com" --json

# 反查某个音频或 sidecar 对应的整组产物
video-downloade artifacts "/path/to/file.mp3" --json
video-downloade artifacts "/path/to/file.mp3" --full-metadata --json

# 检查环境与配置
video-downloade doctor --json

# 启动现有 Web UI
video-downloade serve --port 8080
```

如果你暂时不想安装 console script，也可以直接运行：

```bash
python -m webui.cli --help
```

几个高频 CLI 选项：

- `--input-file` / `--stdin`：批量输入 URL 或音频路径
- `--output text|json|paths`：切换输出格式，方便人类或 AI 消费
- `--result-file`：把结果 JSON 落盘，便于后续自动化
- `--cookies-from-browser`：直接读取浏览器登录态，适合 YouTube / Bilibili 需要登录才能拿字幕的场景
- `--language`：覆盖本次转写语言提示
- `--transcription-model` / `--cleanup-model` / `--article-model`：单次任务覆盖模型
- `--cleanup/--no-cleanup`、`--article/--no-article`：控制成本和处理深度
- `artifacts` 默认返回 metadata 摘要；加 `--full-metadata` 才返回完整 `转写信息.json`

## 逐字稿链路

当前推荐路线已经调整为：

1. 平台字幕直提
2. 无字幕时回退到 MP3 转写
3. 逐字稿清洗
4. 可选解析稿生成
5. 输出 Markdown 与 JSON sidecar

当前默认方向：

- 转写后端：OpenRouter `openai/gpt-audio-mini`
- 清洗后端：智谱 OpenAI 兼容接口 `GLM-4.5`
- 清洗提示词：`角色提示词.md`
- 解析提示词：`解析提示词.md`

如果你选择 `Markdown 逐字稿（字幕优先）`，成功后通常会额外产出：

- `xxx - 原始逐字稿.txt`
- `xxx - 解析稿.md`
- `xxx - 逐字稿.md`
- `xxx - 转写信息.json`

如果你发现 `YouTube` 或部分 `Bilibili` 视频在“字幕优先”模式下总是直接回退到 MP3，通常不是路由逻辑失效，而是平台要求登录态才能访问字幕接口。这时建议：

- 配置 `COOKIES_PATH`
- 或在 CLI 里加 `--cookies-from-browser chrome`

### Cookies 怎么配

推荐顺序：

1. 最省事：直接用浏览器登录态

```bash
video-downloade capture "https://www.youtube.com/watch?v=..." \
  --cookies-from-browser chrome \
  --json
```

也可以写进 `.env`：

```bash
YOUTUBE_COOKIES_FROM_BROWSER=chrome
```

常见写法：

- `chrome`
- `edge`
- `chrome:Profile 1`
- `firefox::default`

2. 兼容方案：导出 `cookies.txt`

常见流程：

- 在浏览器里登录 YouTube 或 Bilibili
- 安装浏览器扩展，例如 `Get cookies.txt LOCALLY`
- 打开对应视频页面
- 导出站点 cookies 为 `cookies.txt`
- 在 `.env` 里配置：

```bash
YOUTUBE_COOKIES_PATH=/absolute/path/to/youtube.cookies.txt
BILIBILI_COOKIES_PATH=/absolute/path/to/bilibili.cookies.txt
```

说明：

- Web UI 里“启用 Cookies”只是表示“这次任务允许使用 Cookies”
- 真正要想生效，还需要你提前配置好平台对应的登录态
- 推荐把 YouTube 和 Bilibili 分开配置，避免一份 B 站 cookies 误用到 YouTube
- 如果两者都没配，第三种模式仍然能工作，只是更容易直接回退到 MP3 转写
- 开源仓库不要提交真实 Cookies；只在本地 `.env` 和本地 Cookies 文件里保存
- Docker Compose 场景下，建议用 `DOCKER_COOKIES_PATH=/cookies.txt`，不要直接把宿主机的 `COOKIES_PATH` 复用进容器

### 为什么 YouTube 现在更容易失败

这不是你这套仓库单独的问题。`yt-dlp` 官方 FAQ 和 YouTube 相关说明里已经明确提到，YouTube 会对一部分请求触发额外校验，常见报错就是：

- `Sign in to confirm you're not a bot`

这类场景通常需要：

- 浏览器登录态
- 或重新导出的 YouTube cookies
- 某些情况下还需要额外的 YouTube extractor 参数或 PO Token 流程

官方参考：

- [yt-dlp FAQ: Passing cookies to yt-dlp](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#passing-cookies-to-yt-dlp)
- [yt-dlp FAQ: Extractors / Exporting YouTube cookies](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies)
- [yt-dlp Wiki: PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide)

最小环境变量示例：

```bash
OPENROUTER_API_KEY=your_key
ENABLE_TRANSCRIPTION=true
OPENROUTER_TRANSCRIPTION_MODEL=openai/gpt-audio-mini
```

可选环境变量示例：

```bash
ENABLE_AI_CLEANUP=true
AI_CLEANUP_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4
AI_CLEANUP_MODEL=GLM-4.5
AI_CLEANUP_PROMPT_FILE=/app/角色提示词.md
TRANSCRIPTION_LANGUAGE=auto
```

## 后续拓展方向

- Docker 一键部署规范化：面向 GitHub 用户整理 `compose + env + volume + cookies` 的稳定模板
- 分享链接识别：支持 Bilibili / YouTube 的网页链接、短链、App 分享文案和移动端分享文本
- 统一输入层：把“原始输入 -> 链接规范化 -> 平台识别 -> 任务提交”做成独立模块
- 安卓 APK：优先做“分享到 App 后直接发起解析任务”的轻量壳层

这些规划已经拆成独立文档，后面可以边做边迭代，不需要等全部功能完成后再整理。

## 目录结构

```text
webui/               Web UI、Flask API 与转写主流程
docs/                对社区公开的说明文档
doc/                 内部设计草稿（默认不作为公开文档）
AGENT.md             给 AI 代理看的命令行使用说明
pyproject.toml       CLI 安装入口与打包配置
scripts/             本地辅助脚本
Dockerfile           Docker 构建文件
docker-compose.yml   Docker Compose 启动文件
requirements.txt     Python 依赖
```

## 免责声明

本项目仅供学习与个人使用，请遵守目标网站的服务条款、版权政策与当地法律法规。
