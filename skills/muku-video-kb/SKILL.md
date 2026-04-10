---
name: muku-video-kb
description: >
  Use this skill when an AI agent needs to turn knowledge-heavy video URLs or local audio
  from Bilibili, YouTube, Douyin, and similar sources into Markdown transcript and
  knowledge-base assets through the Muku CLI.
---

# Muku Video KB

幕库的目标是把知识视频收入本地 Markdown 知识库，而不是做一个通用下载器。

优先使用这个仓库的 CLI，不要默认去驱动网页。

## Best use cases

- 用户给的是知识型视频 URL，希望直接得到逐字稿、解析稿和知识库稿
- 用户给的是一组视频列表，希望批量沉淀为 Markdown 知识库
- 用户已经有本地音频，希望补做转写和知识库整理
- 用户想让 agent 返回 JSON 或路径，继续衔接后续 AI 工作流

## Fast path

```bash
video-downloade doctor --json
video-downloade capture "https://www.youtube.com/watch?v=..." --knowledge --json
video-downloade capture "https://www.bilibili.com/video/BVxxxx" --knowledge --json
video-downloade audio "/path/to/file.mp3" --knowledge --json
video-downloade artifacts "/path/to/file.mp3" --json
video-downloade knowledge "/path/to/file.mp3" --json
```

## Routing rules

- 目标是从 URL 直接得到 Markdown 资产：优先用 `capture --knowledge`
- 只在用户明确要求“下载文件本身”时才用 `download`
- 已经有本地音频：用 `audio`；若还要知识库稿，用 `audio --knowledge`
- 已经拿到 sidecar 或音频路径：用 `artifacts`
- 已经有逐字稿资产，只想补生成知识库稿：用 `knowledge`
- 不确定依赖、模型、Cookies、提示词是否就绪：先跑 `doctor`

## Output strategy

- 默认优先 `--json`
- 只需要路径时，用 `--output paths`
- 批量任务建议加 `--result-file`
- 长批量任务默认搭配 `--resume`
- 批量输入优先 `--input-file` 或 `--stdin`

## Batch ingestion

```bash
video-downloade capture \
  --input-file ./urls.txt \
  --knowledge \
  --jobs 0 \
  --resume \
  --result-file ./runs/creator-series/capture.json \
  --output paths
```

批量场景约定：

- `--jobs 0`：自动并发
- `--result-file`：每个条目完成即写 checkpoint
- `--resume`：优先复用 checkpoint 和已有 sidecar，避免重复下载、重复转写

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

## Pairing with browsing agents

如果任务是“先从博主主页、频道页、系列页、合集页采链接，再批量收入知识库”，推荐与 [`web-access`](https://github.com/eze-is/web-access) 搭配：

1. 让浏览器型 agent 把目标视频 URL 提取成 `./urls.txt`
2. 再调用上面的批量 `capture --knowledge` 命令

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
