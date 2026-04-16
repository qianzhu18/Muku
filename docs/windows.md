# Windows 快速开始

这份文档面向第一次在 Windows 上使用幕库的用户。目标不是解释全部细节，而是让你先把项目跑起来，再做第一次转写验证。

## 推荐入口

如果你是新手，优先用 `Docker Desktop + Web UI`。

- 优点：不需要自己装 Python 环境
- 优点：下载目录和设置目录更容易持久化
- 优点：更适合第一次验证 YouTube / Bilibili / Douyin 链路

如果你已经熟悉 Python，再看 [README.md](../README.md) 里的本地 CLI 路径。

## 官方建议环境

- Windows 11
- Docker Desktop
- PowerShell 7 或 Windows PowerShell
- Chrome 或 Edge

## 3 分钟启动

在仓库根目录打开 PowerShell：

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

启动后打开：

```text
http://localhost:8080
```

## 第一次建议这样配

打开网页右上角的“设置”，至少先填这些：

1. 默认下载目录：`/downloads/default`
2. `OPENROUTER_API_KEY` 对应的转写服务配置
3. 清洗稿 / 解析稿模型与 Key；知识库整理配置可以后面再补

如果你现在只想验证“项目能不能跑通”，也可以先只保留转写能力，把解析稿和知识库整理先暂时关掉。当前 Web 默认不会直接生成 `知识库.md`；如果后面你补齐知识库配置，也可以在网页里显式勾选继续生成，或者用 CLI `--knowledge` 再补。

## Windows 上真实文件会落到哪里

默认情况下：

- 下载产物：`.\docker-data\downloads`
- 运行配置：`.\docker-data\config`

如果你想改成本机其他目录，在 `.env` 中修改：

```text
DOCKER_DOWNLOADS_DIR=C:\Users\YourName\Downloads\muku
DOCKER_CONFIG_DIR=C:\Users\YourName\AppData\Local\muku-config
```

改完后重新执行：

```powershell
docker compose up -d --build
```

注意两层路径：

- 网页里填写的是容器内路径，比如 `/downloads/default`
- Windows 真实路径由 `DOCKER_DOWNLOADS_DIR` 决定

## 第一次自检

建议启动后立刻跑：

```powershell
docker compose exec ytdl-webui video-downloade doctor
docker compose exec ytdl-webui video-downloade doctor --json
```

如果 `doctor` 里这几项都正常，基本就可以发起第一次任务：

- `ffmpeg: OK`
- `yt-dlp: OK`
- `transcript capture: OK`

注意：`doctor` 现在会同时给出 `configured` 和 `verified`。如果你在 Docker 里看到浏览器登录态停在 `CONFIGURED_ONLY`，意思是“配置写进去了，但容器里没法提前证明它真的能读到浏览器 profile”。

## Cookies 怎么配更稳

对于 YouTube、Bilibili、Douyin，在 Docker 模式下更稳的默认方案是单独导出的 `cookies.txt`。

推荐顺序：

1. 先在 Chrome 或 Edge 登录目标平台
2. 优先导出对应平台的 `cookies.txt`
3. 挂载到容器里的 `/cookies/*.cookies.txt`
4. 再运行 `video-downloade doctor --json`

如果你不是 Docker，而是本地 Python 运行，再优先尝试 `*_COOKIES_FROM_BROWSER=chrome` 会更自然。

Docker 模式下如果要挂载本地 cookies 文件，可以把文件放到仓库里的 `.\cookies\`，然后在 `docker-compose.yml` 中启用：

```yaml
volumes:
  - "./cookies:/cookies:ro"
```

然后在 `.env` 中配置：

```text
DOCKER_YOUTUBE_COOKIES_PATH=/cookies/youtube.cookies.txt
DOCKER_BILIBILI_COOKIES_PATH=/cookies/bilibili.cookies.txt
DOCKER_DOUYIN_COOKIES_PATH=/cookies/douyin.cookies.txt
```

## PowerShell 常用命令

```powershell
docker compose exec ytdl-webui video-downloade doctor
docker compose exec ytdl-webui video-downloade config --json
docker compose exec ytdl-webui video-downloade capture "https://www.bilibili.com/video/BVxxxx" --json
docker compose logs -f ytdl-webui
```

## 最常见的 5 个问题

### 1. 网页打不开

- 先确认 Docker Desktop 已启动
- 再执行 `docker compose ps`
- 默认地址是 `http://localhost:8080`

### 2. 能打开网页，但任务报错

- 先运行 `docker compose exec ytdl-webui video-downloade doctor`
- 看 `ffmpeg`、`yt-dlp`、`transcript capture` 是否正常

### 3. 下载目录改了，但找不到文件

- 网页里填的是容器路径，不是 Windows 路径
- 宿主机真实位置取决于 `DOCKER_DOWNLOADS_DIR`

### 4. YouTube / Douyin 失败率高

- 通常是登录态没配
- Docker 下优先给对应平台单独配置 `cookies.txt`，不要只靠全局 Cookies 或浏览器登录态

### 5. 逐字稿失败，并提示响应被截断

- 这通常是音频太长，远端模型没一次性返回完整内容
- 优先尝试平台字幕直提
- 或者缩短单次输入，再重试
