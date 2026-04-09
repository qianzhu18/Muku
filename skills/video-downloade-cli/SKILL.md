---
name: video-downloade-cli
description: >
  Use this skill when an AI agent needs to process video or audio URLs, transcribe local audio,
  generate transcript/article/knowledge assets, inspect sidecars, or operate this repository
  through its CLI instead of the Web UI.
---

# Video Downloade CLI Skill

优先使用这个仓库的 CLI，不要默认去驱动网页。

## Fast path

```bash
video-downloade doctor --json
video-downloade capture "https://www.youtube.com/watch?v=..." --knowledge --json
video-downloade capture "https://www.bilibili.com/video/BVxxxx" --knowledge --json
video-downloade download "https://www.douyin.com/video/1234567890" --json
video-downloade audio "/path/to/file.mp3" --knowledge --json
video-downloade artifacts "/path/to/file.mp3" --json
video-downloade knowledge "/path/to/file.mp3" --json
```

## Routing rules

- 目标是从 URL 直接得到逐字稿和知识库稿：用 `capture --knowledge`
- 只想下载文件：用 `download`
- 已经有本地音频：用 `audio`；如果还要知识库稿，用 `audio --knowledge`
- 已经拿到 sidecar 或音频路径：用 `artifacts`
- 已经有逐字稿资产，只想补生成知识库稿：用 `knowledge`
- 不确定依赖、模型、Cookies、提示词是否就绪：先跑 `doctor`

## Output strategy

- 默认优先 `--json`
- 只需要路径时，用 `--output paths`
- 批量任务建议加 `--result-file`
- 批量输入优先 `--input-file` 或 `--stdin`

## Batch examples

```bash
video-downloade capture --input-file ./urls.txt --knowledge --result-file ./capture.json --json
cat ./urls.txt | video-downloade capture --stdin --output paths
```

## Auth handling

优先使用平台级登录态：

```bash
video-downloade capture URL \
  --youtube-cookies-from-browser chrome \
  --bilibili-cookies-path ./cookies/bilibili.cookies.txt \
  --douyin-cookies-from-browser chrome \
  --json
```

推荐流程：

1. 先执行 `video-downloade doctor --json`
2. 检查 `youtube_auth_configured`、`bilibili_auth_configured`、`douyin_auth_configured`
3. 优先用 `*_COOKIES_FROM_BROWSER`
4. 浏览器方案不稳定时，再回退到 `*_COOKIES_PATH`

## Useful runtime overrides

```bash
video-downloade capture URL --language zh --json
video-downloade capture URL --transcription-model openai/gpt-audio-mini --json
video-downloade capture URL --knowledge-model GLM-4.5 --json
video-downloade capture URL --knowledge-prompt-file ./知识库提示词.md --json
video-downloade audio FILE --no-article --knowledge --json
```

## Expected artifacts

- `xxx - 原始逐字稿.txt`
- `xxx - 解析稿.md`
- `xxx - 知识库.md`
- `xxx - 逐字稿.md`
- `xxx - 转写信息.json`

## Operational notes

- 不要在命令输出中回显真实密钥或 Cookies 内容
- YouTube 下载失败时，优先检查 `doctor --json` 里的 `youtube_auth_configured`
- Bilibili、YouTube、Douyin 建议分开配置 Cookies，避免串用
- 转写前预处理音频默认写入系统临时目录，不会在下载目录里额外留下第二个可见 MP3
- 知识库整理默认沿用 `ARTICLE_DRAFT_*` 这组配置；只有需要单独后端时再设置 `KNOWLEDGE_DRAFT_*`
