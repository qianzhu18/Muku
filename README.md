# ytdlp-webui

一个本地化的网页视频下载工具，基于 `yt-dlp + Flask`，支持多平台链接输入、格式预设、批量队列与进度展示。适合个人本地使用，减少命令行操作成本。

## 功能特性

- Web UI 界面：输入链接即可下载
- 支持批量下载（多行链接）
- 下载格式预设（视频/音频/高分辨率）
- 任务队列与进度展示
- 支持 Cookies（会员/限速内容）
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

## CLI 用法

这个项目现在也可以直接当命令行工具使用，适合让 AI 或脚本直接调用，不必经过网页表单。

安装开发模式命令：

```bash
pip install -e .
```

安装后可用命令：

```bash
# 从 URL 直接生成 MP3 + Markdown 逐字稿
video-downloade capture "https://www.bilibili.com/video/BVxxxx" --json

# 仅下载，不生成逐字稿
video-downloade download "https://www.bilibili.com/video/BVxxxx" \
  --preset "Best Audio (MP3)" \
  --json

# 处理本地音频
video-downloade audio "/path/to/file.mp3" --source-url "https://example.com" --json

# 检查环境与配置
video-downloade doctor --json

# 启动现有 Web UI
video-downloade serve --port 8080
```

如果你暂时不想安装 console script，也可以直接运行：

```bash
python -m webui.cli --help
```

## 使用说明

1) 在输入框粘贴视频链接（支持多行）
2) 选择下载预设（视频 / 音频 / 高分辨率）
3) 点击“开始下载”即可
4) 在任务队列中查看进度

## 云端转写路线

当前推荐路线已经调整为“下载 MP3 -> OpenRouter 转写 -> GLM 清洗 -> Markdown”，不再以本地 `MLX / Whisper` 作为主线。

- 主推转写后端：OpenRouter `openai/gpt-audio-mini`
- 当前清洗后端：智谱 OpenAI 兼容接口 `GLM-4.5`
- 当前提示词文件：`角色提示词.md`
- 当前解析提示词：`解析提示词.md`

说明：
- 清洗稿和解析稿优先走智谱 OpenAI 兼容接口
- 如果本地没有配置智谱 API Key，解析稿会自动回退到 OpenRouter 文本模型

完整执行文档见：[doc/cloud-transcription-plan.md](doc/cloud-transcription-plan.md)

### OpenRouter 配置

最小环境变量：

```bash
-e OPENROUTER_API_KEY=your_key \
-e ENABLE_TRANSCRIPTION=true \
-e OPENROUTER_TRANSCRIPTION_MODEL=openai/gpt-audio-mini
```

可选环境变量：

```bash
-e ENABLE_AI_CLEANUP=true \
-e AI_CLEANUP_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4 \
-e AI_CLEANUP_MODEL=GLM-4.5 \
-e AI_CLEANUP_PROMPT_FILE=/app/角色提示词.md \
-e TRANSCRIPTION_LANGUAGE=auto
```

勾选“下载后提取 MD 逐字稿”后，`Best Audio (MP3)` 任务会额外产出：

- `xxx - 原始逐字稿.txt`
- `xxx - 解析稿.md`
- `xxx - 逐字稿.md`
- `xxx - 转写信息.json`

## Docker Hub 镜像

- 仓库地址：`zhangjinhong/ytdlp-webui`
- 拉取：`docker pull zhangjinhong/ytdlp-webui:latest`

> 如果你的服务器是 x86_64（amd64）架构且遇到镜像架构不匹配问题，可以在本机或服务器上重新构建镜像后运行。

## 目录结构

```
webui/               Web UI 主程序
AGENT.md             给 AI 代理看的命令行使用说明
pyproject.toml       CLI 安装入口与打包配置
scripts/             本地快捷脚本（可选）
Dockerfile           Docker 构建文件
requirements.txt     Python 依赖
```

## 免责声明

本项目仅供学习与个人使用，请遵守目标网站的服务条款与版权政策。
