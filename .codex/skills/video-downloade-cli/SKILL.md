---
name: video-downloade-cli
description: >
  Use this skill when the user wants to download media from URLs, transcribe MP3 or local audio,
  generate Markdown transcript assets, inspect sidecar artifacts, or drive this repository through
  its CLI instead of the Web UI. Triggers include requests like "下载并转逐字稿", "转成 md",
  "处理本地 mp3", "批量转写", "用命令行跑", "用 AI 调用这个项目", "inspect artifacts",
  and "doctor this downloader".
---

# Video Downloade CLI

优先使用这个仓库的 CLI，不要默认去驱动网页。

## Primary commands

```bash
# URL -> MP3 + 逐字稿 + 解析稿
video-downloade capture "https://www.bilibili.com/video/BVxxxx" --json

# YouTube with platform-specific auth
video-downloade capture "https://www.youtube.com/watch?v=..." \
  --youtube-cookies-from-browser chrome \
  --json

# 批量 URL
video-downloade capture --input-file ./urls.txt --result-file ./capture.json --json
cat ./urls.txt | video-downloade capture --stdin --output paths

# 纯下载
video-downloade download "https://www.bilibili.com/video/BVxxxx" --preset "Best Audio (MP3)" --json

# 本地音频 -> 逐字稿
video-downloade audio "/path/to/file.mp3" --json

# 反查 sidecar
video-downloade artifacts "/path/to/file.mp3" --json

# 逐字稿 -> 知识库整理稿
video-downloade knowledge "/path/to/file.mp3" --json

# 环境检查
video-downloade doctor --json
```

## Command selection

- 用户给的是 URL，且目标是知识库产物：用 `capture`
- 用户只想下载文件：用 `download`
- 用户已经有本地音频：用 `audio`
- 用户已经拿到某个 sidecar，想定位整组文件或 metadata：用 `artifacts`
- 用户想把逐字稿整理成知识库条目：先 `capture`，再 `knowledge`
- 先确认配置、依赖、密钥状态：用 `doctor`

## Output strategy

- 默认优先 `--json`，给 AI 最稳定
- 只需要路径时，用 `--output paths`
- 需要保存机器可读结果时，加 `--result-file`
- 批量输入优先 `--input-file` 或 `--stdin`

## Useful runtime overrides

```bash
video-downloade capture URL --language zh --json
video-downloade capture URL --transcription-model openai/gpt-audio-mini --json
video-downloade capture URL --youtube-cookies-path ./cookies/youtube.cookies.txt --json
video-downloade capture URL --bilibili-cookies-path ./cookies/bilibili.cookies.txt --json
video-downloade capture URL --cleanup-model GLM-4.5 --article-model GLM-4.5 --json
video-downloade capture URL --no-article --json
video-downloade audio FILE --cleanup-prompt-file ./角色提示词.md --article-prompt-file ./解析提示词.md --json
```

## Expected artifacts

- `xxx - 原始逐字稿.txt`
- `xxx - 解析稿.md`
- `xxx - 知识库.md`
- `xxx - 逐字稿.md`
- `xxx - 转写信息.json`

## Operational notes

- 默认配置从仓库根目录 `.env` 读取，不要在命令里回显密钥
- YouTube 或 B 站受限内容抓取失败时，优先尝试平台级参数：`--youtube-cookies-*` / `--bilibili-cookies-*`
- `artifacts` 默认只返回摘要 metadata；排障时再加 `--full-metadata`
- 若仅需下载，不要额外开启逐字稿，以节省成本和时间
