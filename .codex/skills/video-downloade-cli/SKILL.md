---
name: video-downloade-cli
description: >
  Use this skill when the user wants to process video or audio URLs, transcribe local audio,
  generate transcript/article/knowledge assets, inspect sidecars, or drive this repository
  through its CLI instead of the Web UI.
---

# Video Downloade CLI

优先使用这个仓库的 CLI，不要默认去驱动网页。

## Fast path

```bash
video-downloade doctor --json
video-downloade capture "https://www.bilibili.com/video/BVxxxx" --knowledge --json
video-downloade capture "https://www.youtube.com/watch?v=..." --knowledge --json
video-downloade download "https://www.douyin.com/video/1234567890" --json
video-downloade audio "/path/to/file.mp3" --knowledge --json
video-downloade artifacts "/path/to/file.mp3" --json
video-downloade knowledge "/path/to/file.mp3" --json
```

## Command selection

- 用户给的是 URL，且目标是知识库产物：用 `capture --knowledge`
- 用户只想下载文件：用 `download`
- 用户已经有本地音频：用 `audio`；若还要知识库稿，用 `audio --knowledge`
- 用户已经拿到某个 sidecar，想定位整组文件或 metadata：用 `artifacts`
- 用户只想补生成知识库稿：用 `knowledge`
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
video-downloade capture URL --douyin-cookies-from-browser chrome --json
video-downloade capture URL --knowledge-model GLM-4.5 --json
video-downloade capture URL --knowledge-prompt-file ./知识库提示词.md --json
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
- 先跑 `doctor --json`，检查 `youtube_auth_configured`、`bilibili_auth_configured`、`douyin_auth_configured`
- YouTube、B 站、抖音受限内容抓取失败时，优先尝试平台级参数：`--youtube-cookies-*` / `--bilibili-cookies-*` / `--douyin-cookies-*`
- `artifacts` 默认只返回摘要 metadata；排障时再加 `--full-metadata`
- 若仅需下载，不要额外开启逐字稿，以节省成本和时间
- 转写前预处理音频默认写入系统临时目录，不会在下载目录里额外留下第二个可见 MP3
- 知识库整理默认沿用 `ARTICLE_DRAFT_*` 这组配置；只有需要单独后端时再设置 `KNOWLEDGE_DRAFT_*`
