# Docker 部署

这份文档面向“拿到仓库就启动”的场景，目标是把 Docker Compose 变成真正可用的一键部署入口。

## 这次部署方案解决了什么

- 默认用 `docker compose up -d --build` 就能起服务
- 下载产物和网页端保存的配置都会持久化
- Windows / macOS 默认都能直接用仓库内的 `./docker-data` 目录
- 网页端可以改默认下载目录、转写模型、解析模型，以及供 Web 可选知识库稿 / CLI / 后续整理复用的知识库模型和提示词
- 容器里仍然可以直接使用 `video-downloade` CLI

## 默认目录约定

容器内：

- 下载根目录：`/downloads`
- 配置目录：`/config`
- 设置文件：`/config/settings.json`

宿主机默认映射：

- `./docker-data/downloads -> /downloads`
- `./docker-data/config -> /config`

这意味着：

- 你可以在网页里把默认下载目录改成 `/downloads/creator-series`、`/downloads/bilibili`、`/downloads/douyin`
- 也可以在新建任务时单独填写“本次保存到”
- 如果你想把真实文件落到宿主机别的地方，再改 `DOCKER_DOWNLOADS_DIR` 后重启

## 快速开始

### 1. 准备 `.env`

```bash
cp .env.example .env
```

最少建议配置：

- `OPENROUTER_API_KEY`
- `AI_CLEANUP_API_KEY`
- `ARTICLE_DRAFT_API_KEY`
- 如果你准备直接跑 CLI `--knowledge`，再补 `KNOWLEDGE_DRAFT_API_KEY`

如果你还要抓受限内容，再补平台 Cookies：

- `DOCKER_YOUTUBE_COOKIES_PATH`
- `DOCKER_BILIBILI_COOKIES_PATH`
- `DOCKER_DOUYIN_COOKIES_PATH`

### 2. 启动

```bash
docker compose up -d --build
```

### 3. 访问网页

```text
http://localhost:8080
```

### 4. 先做两步初始化

1. 打开网页里的“服务配置”
2. 填好默认下载目录、转写服务、清洗/解析模型与提示词；知识库整理配置可供网页显式生成知识库稿、CLI `--knowledge` 和后续整理链路复用

推荐第一次至少保存这些：

- 默认下载目录：`/downloads/default`
- 转写 Base URL / API Key / 模型
- 清洗稿 Base URL / API Key / 模型
- 解析稿 Base URL / API Key / 模型
- 如果你要直接跑容器内 CLI 的知识库链路，再补知识库 Base URL / API Key / 模型

### 5. 做一次自检

```bash
docker compose exec ytdl-webui video-downloade doctor --json
docker compose exec ytdl-webui video-downloade config --json
```

注意：`doctor` 现在会同时显示 `configured` 和 `verified`。在 Docker 里，如果浏览器登录态只显示 `CONFIGURED_ONLY`，表示它知道你配了这项，但不会把它误判成“容器内已验证可用”。

## Windows / macOS 怎么选真实下载目录

### 默认方式

默认不需要改，直接使用：

- Windows：仓库下的 `.\docker-data\downloads`
- macOS：仓库下的 `./docker-data/downloads`

### 如果要改宿主机真实路径

在 `.env` 里改：

```bash
DOCKER_DOWNLOADS_DIR=./docker-data/downloads
DOCKER_CONFIG_DIR=./docker-data/config
```

Windows 也可以改成绝对路径，例如：

```text
DOCKER_DOWNLOADS_DIR=C:\Users\YourName\Downloads\muku
DOCKER_CONFIG_DIR=C:\Users\YourName\AppData\Local\muku-config
```

macOS 也可以改成绝对路径，例如：

```text
DOCKER_DOWNLOADS_DIR=/Users/yourname/Downloads/muku
DOCKER_CONFIG_DIR=/Users/yourname/.muku-config
```

改完后重启：

```bash
docker compose up -d --build
```

注意：

- 网页里的“默认下载目录”只能设置容器看到的路径，也就是 `/downloads` 下面的目录
- 想改宿主机真实挂载位置，必须改 `DOCKER_DOWNLOADS_DIR`

## Cookies 挂载方式

如果你要在 Docker 里给 YouTube / Bilibili / Douyin 提供登录态，推荐把平台专用 `cookies.txt` 统一放到仓库里的 `./cookies/`，然后在 Compose 里保留这个挂载：

```yaml
volumes:
  - "./cookies:/cookies:ro"
```

然后在 `.env` 中配置容器内路径：

```bash
DOCKER_YOUTUBE_COOKIES_PATH=/cookies/youtube.cookies.txt
DOCKER_BILIBILI_COOKIES_PATH=/cookies/bilibili.cookies.txt
DOCKER_DOUYIN_COOKIES_PATH=/cookies/douyin.cookies.txt
```

这比在容器里直接依赖 `*_COOKIES_FROM_BROWSER` 更稳。后者更适合作为本地 Python 运行时的方案，而不是 Docker 默认路径。

## 容器内 CLI

网页端适合人工使用；如果你要批量跑创作者系列、给 AI agent 用，建议直接调容器里的 CLI。

补一句：当前网页任务默认生成逐字稿和解析稿；如果你要直接出 `知识库.md`，可以在网页里显式勾选知识库稿，或在容器内 CLI 里显式传 `--knowledge`。

### 查看当前配置

```bash
docker compose exec ytdl-webui video-downloade config --json
```

### 用 CLI 写默认配置

```bash
docker compose exec ytdl-webui \
  video-downloade config \
  --download-dir /downloads/default \
  --transcription-model openai/gpt-audio-mini \
  --cleanup-model GLM-4.5 \
  --article-model GLM-4.5 \
  --knowledge-model GLM-4.5 \
  --json
```

### URL -> 逐字稿 + 知识库

```bash
docker compose exec ytdl-webui \
  video-downloade capture "https://www.bilibili.com/video/BVxxxx" \
  --knowledge \
  --json
```

### 批量 URL -> Markdown 知识库

```bash
docker compose exec ytdl-webui \
  video-downloade capture \
  --input-file /downloads/urls.txt \
  --knowledge \
  --jobs 0 \
  --resume \
  --result-file /downloads/runs/capture.json \
  --output paths
```

## 升级方式

```bash
git pull
docker compose up -d --build
```

原有的下载产物和网页端配置都会保留在挂载目录里。
