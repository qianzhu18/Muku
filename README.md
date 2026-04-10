# 幕库 Muku

> Video-to-Markdown for Bilibili, YouTube, and Douyin
>
> 把知识视频沉淀为可检索、可连接、可被 AI 持续使用的 Markdown 知识库

把平台上的知识视频，从“刷过就忘”，变成你本地可检索、可连接、可被 AI 持续使用的 Markdown 知识库。

幕库面向 Bilibili、YouTube、Douyin 等知识密度高的平台。它的重点不是做一个“什么都下”的通用下载器，而是把链接、片单、创作者列表和本地音频沉淀为可以长期复用的知识资产。当前项目同时提供 `Web UI + CLI + Docker + Skill` 四套入口。

## 幕库是什么

幕库，英文名 `Muku`，是一个面向 Bilibili、YouTube、Douyin 等平台的 `Video-to-Markdown` 工具。

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

- 单条视频链接直接整理为 `逐字稿.md`、`解析稿.md`、`知识库.md`
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
| YouTube | 网页链接、分享链接 | `YOUTUBE_COOKIES_FROM_BROWSER=chrome` | 字幕优先，部分视频依赖 `YTDLP_REMOTE_COMPONENTS=ejs:github` |
| Bilibili | 网页链接、分享文案 | `BILIBILI_COOKIES_FROM_BROWSER=chrome` 或 `BILIBILI_COOKIES_PATH` | 高知识密度视频场景表现更好 |
| Douyin | 网页链接、分享短链、分享文案 | `DOUYIN_COOKIES_FROM_BROWSER=chrome` 或 `DOUYIN_COOKIES_PATH` | 适合用来沉淀短视频里的观点和素材 |

建议第一次使用前先跑：

```bash
video-downloade doctor --json
```

## 核心工作流

1. 输入单条链接、分享文案、批量 URL 列表，或直接输入本地音频
2. 优先直提平台字幕，失败后回退到 MP3 转写
3. 生成逐字稿、解析稿、知识库稿和转写 metadata
4. 产物落到本地文件系统，继续喂给 Obsidian、RAG、AI agent 或你自己的知识库流程

默认产物包括：

- `xxx - 原始逐字稿.txt`
- `xxx - 逐字稿.md`
- `xxx - 解析稿.md`
- `xxx - 知识库.md`
- `xxx - 转写信息.json`

## 快速开始

### Docker Compose

推荐的默认部署方式：

```bash
cp .env.example .env
docker compose up -d --build
```

默认会在仓库里生成两个持久化目录：

- `./docker-data/downloads`：下载产物
- `./docker-data/config`：网页端与 CLI 保存的运行配置

Windows 和 macOS 默认都可以直接使用这套映射，不需要先手改绝对路径。

默认访问地址：

```text
http://localhost:8080
```

启动后推荐先做三步：

1. 打开网页右上角的“设置”
2. 在设置抽屉里配置默认下载目录、转写服务、清洗/解析/知识库模型与提示词
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

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env
python webui/app.py
```

如果你只想用 CLI：

```bash
python -m webui.cli --help
```

## 关键环境变量

- `DOWNLOAD_DIR`：默认下载目录；本地运行建议填 macOS / Windows 的绝对路径
- `DOWNLOAD_ROOT_DIR`：可选的下载根目录限制；Docker 默认锁定为 `/downloads`
- `VIDEO_DOWNLOADE_CONFIG_DIR`：网页端和 CLI 保存运行配置的目录
- `DOCKER_DOWNLOADS_DIR`：Docker 映射到宿主机的真实下载目录，默认是 `./docker-data/downloads`
- `DOCKER_CONFIG_DIR`：Docker 映射到宿主机的真实配置目录，默认是 `./docker-data/config`
- `OPENROUTER_API_KEY`：音频转写必需
- `OPENROUTER_BASE_URL`：转写服务 Base URL，支持兼容 OpenRouter 的网关
- `AI_CLEANUP_API_KEY`：清洗稿必需
- `ARTICLE_DRAFT_API_KEY`：解析稿必需
- `YOUTUBE_COOKIES_FROM_BROWSER` / `YOUTUBE_COOKIES_PATH`：提升 YouTube 字幕直提和下载成功率
- `BILIBILI_COOKIES_FROM_BROWSER` / `BILIBILI_COOKIES_PATH`：提升 B 站字幕直提成功率
- `DOUYIN_COOKIES_FROM_BROWSER` / `DOUYIN_COOKIES_PATH`：为受限抖音内容预留登录态
- `YTDLP_REMOTE_COMPONENTS=ejs:github`：为部分受 JS challenge 保护的 YouTube 视频启用格式解析

推荐的认证检查顺序：

1. 先在浏览器登录目标平台
2. 优先用 `*_COOKIES_FROM_BROWSER=chrome`
3. 再跑 `video-downloade doctor --json` 确认 `*_auth_configured` 已变成 `true`
4. 浏览器方案不可用时，再回退到 `*_COOKIES_PATH=/absolute/path/to/cookies.txt`

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
  --cleanup-model GLM-4.5 \
  --article-model GLM-4.5 \
  --knowledge-model GLM-4.5 \
  --json

# 启动现有 Web UI
video-downloade serve --port 8080
```

更多命令和参数见 [docs/cli.md](docs/cli.md)。

## Web 工作台

当前 Web UI 已经改成更适合日常使用的双栏工作台：

- 桌面端默认是单屏双栏：左侧发任务，右侧盯队列和详情
- 左侧：发起新任务、选择模式、临时覆盖本次保存目录
- 右侧：观察任务队列、切换到单条任务详情、看输出路径和报错
- 右上角“设置”：打开折叠式配置抽屉，集中维护默认下载目录、模型、服务地址和提示词

这样页面不会再因为配置项太多而无限变长，部署后也更适合直接给自己或小团队使用。

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
- 当前 Docker、CLI、Web UI、Skill 四条入口已经对齐
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
