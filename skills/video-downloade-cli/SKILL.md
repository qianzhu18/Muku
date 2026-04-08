---
name: video-downloade-cli
description: >
  Use this skill when an AI agent needs to download videos or audio from URLs,
  generate Markdown transcripts, inspect transcript sidecars, or operate this
  repository through its CLI instead of the Web UI.
---

# Video Downloade CLI Skill

优先使用这个仓库的 CLI，不要默认去驱动网页。

## Best commands

```bash
# URL -> Markdown transcript
video-downloade capture "https://www.youtube.com/watch?v=..." --json

# URL -> file download only
video-downloade download "https://www.bilibili.com/video/BVxxxx" --preset "Best Audio (MP3)" --json

# Share text -> transcript
video-downloade capture "【标题】 https://www.bilibili.com/video/BVxxxx" --json

# Local audio -> transcript
video-downloade audio "/path/to/file.mp3" --json

# Inspect sidecars
video-downloade artifacts "/path/to/file.mp3" --json

# Build knowledge-base note from transcript assets
video-downloade knowledge "/path/to/file.mp3" --json

# Environment / auth check
video-downloade doctor --json
```

## Routing rules

- 目标是逐字稿或解析稿：用 `capture`
- 只想下载视频或 MP3：用 `download`
- 已经有本地音频：用 `audio`
- 已经拿到 sidecar 路径：用 `artifacts`
- 想把逐字稿整理成结构化知识库：先 `capture`，再 `knowledge`
- 不确定依赖、模型、Cookies 是否已配置：先跑 `doctor`

## Input handling

- 支持纯 URL
- 支持 Bilibili / YouTube 分享文案
- 支持多行输入、文件输入和 stdin

## Auth handling

优先使用平台级登录态：

```bash
video-downloade capture URL \
  --youtube-cookies-from-browser chrome \
  --bilibili-cookies-path ./cookies/bilibili.cookies.txt \
  --json
```

也可走环境变量：

```bash
YOUTUBE_COOKIES_FROM_BROWSER=chrome
YOUTUBE_COOKIES_PATH=/absolute/path/to/youtube.cookies.txt
BILIBILI_COOKIES_PATH=/absolute/path/to/bilibili.cookies.txt
```

## Output conventions

- 默认优先 `--json`
- 只需要路径时用 `--output paths`
- 批量任务建议加 `--result-file`

## Expected artifacts

- `xxx - 原始逐字稿.txt`
- `xxx - 解析稿.md`
- `xxx - 知识库.md`
- `xxx - 逐字稿.md`
- `xxx - 转写信息.json`

## Operational notes

- 不要在命令输出中回显真实密钥或 Cookies 内容
- YouTube 下载失败时，优先检查 `doctor --json` 里的 `youtube_auth_configured`
- Bilibili 和 YouTube 建议分开配置 Cookies，避免串用
- 逐字稿模式是“字幕优先，音频转写兜底”
