# Docker 部署

这份文档描述的是当前仓库已经稳定下来的 Docker 使用方式，目标是把“本机能跑”整理成“拿到仓库就能起服务”。

## 默认约定

- 默认端口：`8080`
- 默认挂载下载目录：`/downloads`
- 默认入口：Web UI
- 默认镜像入口命令：`video-downloade serve --host 0.0.0.0 --port 8080`
- 默认适配：容器内也可以直接使用 `video-downloade` CLI

## 推荐方式：Docker Compose

这是最适合作为仓库首页默认指令的方式。

### 1. 准备环境变量

```bash
cp .env.example .env
```

最少建议补这几项：

- `OPENROUTER_API_KEY`
- `AI_CLEANUP_API_KEY`
- `ARTICLE_DRAFT_API_KEY`

如果你希望 YouTube / Bilibili 字幕优先链路更稳定，再补：

- `DOCKER_YOUTUBE_COOKIES_PATH`
- `DOCKER_BILIBILI_COOKIES_PATH`

### 2. 启动服务

```bash
docker compose up -d --build
```

### 3. 访问页面

```text
http://localhost:8080
```

### 4. 自检

```bash
docker compose exec ytdl-webui video-downloade doctor --json
```

如果你想看容器日志：

```bash
docker compose logs -f ytdl-webui
```

## 容器内 CLI

容器里安装的是同一套 `video-downloade` CLI，所以部署后可以直接继续跑 AI/脚本链路。

### URL -> 逐字稿 + 知识库

```bash
docker compose exec ytdl-webui \
  video-downloade capture "https://www.bilibili.com/video/BVxxxx" \
  --knowledge \
  --json
```

### 本地侧已有批量 URL 文件

```bash
docker compose exec ytdl-webui \
  video-downloade capture --input-file /downloads/urls.txt --knowledge --json
```

### 查询某条任务的 sidecar

```bash
docker compose exec ytdl-webui \
  video-downloade artifacts "/downloads/Sample [abc]/Sample [abc].mp3" \
  --json
```

## Volume 约定

当前建议至少明确两类挂载：

- 下载产物目录
- Cookies 文件

默认 Compose 文件已经挂载：

```yaml
volumes:
  - ${HOME}/Downloads:/downloads
```

如果你还要挂 Cookies，可追加：

```yaml
volumes:
  - ${HOME}/Downloads:/downloads
  - ./youtube.cookies.txt:/youtube.cookies.txt:ro
  - ./bilibili.cookies.txt:/bilibili.cookies.txt:ro
```

然后在 `.env` 中配置：

```bash
DOCKER_YOUTUBE_COOKIES_PATH=/youtube.cookies.txt
DOCKER_BILIBILI_COOKIES_PATH=/bilibili.cookies.txt
```

## Docker Run

如果你更喜欢直接运行镜像，推荐先在本地构建一个稳定标签：

```bash
docker build -t video-downloade:local .

docker run --rm -d -p 8080:8080 \
  -v "$HOME/Downloads:/downloads" \
  --name ytdlp-webui \
  video-downloade:local
```

容器起来后同样可以执行：

```bash
docker exec -it ytdlp-webui video-downloade doctor --json
```

## 升级方式

### 源码仓库 + Compose

```bash
git pull
docker compose up -d --build
```

### 本地镜像更新

```bash
docker build -t video-downloade:local .
docker rm -f ytdlp-webui
docker run ...
```

## 发布前建议

- 保持 `.env.example` 只放模板，不提交真实密钥
- 不要把真实 `cookies.txt` 提交进仓库
- 推荐同时支持 `amd64` / `arm64`
- README 里优先写 `docker compose up -d --build`，把 `docker run` 放在补充位置
