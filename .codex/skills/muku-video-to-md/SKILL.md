---
name: muku-video-to-md
description: >
  Use this skill when the user wants to turn knowledge-heavy video URLs or local audio
  into Markdown transcript and knowledge-base assets through the Muku CLI instead of
  driving the Web UI.
---

# Muku Video to MD

幕库的目标是把知识视频收入本地 Markdown 知识库，而不是做一个通用下载器。

优先使用这个仓库的 CLI，不要默认去驱动网页。

## Fast path

```bash
video-downloade doctor --json
video-downloade config --json
video-downloade capture "https://www.bilibili.com/video/BVxxxx" --knowledge --json
video-downloade capture "https://www.youtube.com/watch?v=..." --knowledge --json
video-downloade audio "/path/to/file.mp3" --knowledge --json
video-downloade artifacts "/path/to/file.mp3" --json
video-downloade knowledge "/path/to/file.mp3" --json
```

## Command selection

- 用户给的是 URL，且目标是知识库产物：优先用 `capture --knowledge`
- 用户只想下载文件本身：用 `download`
- 用户已经有本地音频：用 `audio`；若还要知识库稿，用 `audio --knowledge`
- 用户已经拿到某个 sidecar，想定位整组文件或 metadata：用 `artifacts`
- 用户只想补生成知识库稿：用 `knowledge`
- 先确认配置、依赖、密钥状态：用 `doctor`

## Output strategy

- 默认优先 `--json`，给 AI 最稳定
- 只需要路径时，用 `--output paths`
- 需要保存机器可读结果时，加 `--result-file`
- 长批量任务默认搭配 `--resume`
- 批量输入优先 `--input-file` 或 `--stdin`

## Batch workflow

```bash
video-downloade capture \
  --input-file ./urls.txt \
  --knowledge \
  --jobs 0 \
  --resume \
  --result-file ./capture.json \
  --output paths
```

- `--jobs 0`：自动并发
- `--result-file`：每个条目完成就会写 checkpoint
- `--resume`：优先复用 checkpoint 和已有逐字稿 sidecar

## Useful runtime overrides

```bash
video-downloade config --download-dir "/Users/you/Downloads/muku" --json
video-downloade capture URL --language zh --json
video-downloade capture URL --transcription-model openai/gpt-audio-mini --json
video-downloade capture URL --youtube-cookies-path ./cookies/youtube.cookies.txt --json
video-downloade capture URL --bilibili-cookies-path ./cookies/bilibili.cookies.txt --json
video-downloade capture URL --douyin-cookies-from-browser chrome --json
video-downloade capture URL --knowledge-model stepfun/step-3.7-flash --json
video-downloade capture URL --knowledge-prompt-file ./知识库提示词.md --json
video-downloade audio FILE --cleanup-prompt-file ./角色提示词.md --article-prompt-file ./解析提示词.md --json
```

## Local text backend

本机清洗稿、解析稿、知识库稿默认都走 OpenRouter：

```bash
AI_CLEANUP_BASE_URL=https://openrouter.ai/api/v1
AI_CLEANUP_MODEL=stepfun/step-3.7-flash
ARTICLE_DRAFT_BASE_URL=https://openrouter.ai/api/v1
ARTICLE_DRAFT_MODEL=stepfun/step-3.7-flash
KNOWLEDGE_DRAFT_BASE_URL=https://openrouter.ai/api/v1
KNOWLEDGE_DRAFT_MODEL=stepfun/step-3.7-flash
```

转写仍使用 `OPENROUTER_API_KEY` 和 `openai/gpt-audio-mini`。不要回显真实 key。

## Expected artifacts

- `xxx - 原始逐字稿.txt`
  原始逐字稿，仅保留原始文本
- `xxx - 逐字稿.md`
  清洗后的逐字稿正文，不重复附带原始稿、解析稿或额外说明
- `xxx - 解析稿.md`
  仅保留解析成稿正文，严格遵循 `解析提示词.md`
- `xxx - 知识库.md`
- `xxx - 转写信息.json`

## Operational notes

- 默认配置从仓库根目录 `.env` 读取，不要在命令里回显密钥
- 如果用户说“网页里已经配过默认目录和模型”，先跑 `video-downloade config --json`，确认 CLI 侧也已经读到同一份配置
- 先跑 `doctor --json`，检查 `youtube_auth_configured`、`bilibili_auth_configured`、`douyin_auth_configured`
- YouTube、B 站、抖音受限内容抓取失败时，优先尝试平台级参数：`--youtube-cookies-*` / `--bilibili-cookies-*` / `--douyin-cookies-*`
- `artifacts` 默认只返回摘要 metadata；排障时再加 `--full-metadata`
- 若仅需下载，不要额外开启逐字稿，以节省成本和时间
- 转写前预处理音频默认写入系统临时目录，不会在下载目录里额外留下第二个可见 MP3
- `逐字稿.md` 默认只写清洗后的正文；原始内容单独放在 `原始逐字稿.txt`
- `解析稿.md` 默认只写最终成稿，不添加“解析稿”“成稿如下”等外层包装
- 默认解析规则来自仓库根目录的 `解析提示词.md`；批量回写或重生成时也要遵守同一规范
- 知识库整理默认显式使用 `KNOWLEDGE_DRAFT_*`，本机与 `ARTICLE_DRAFT_*` 同样走 OpenRouter StepFun
- 如果要先从创作者主页 / 系列页提取链接，推荐和 [`web-access`](https://github.com/eze-is/web-access) 搭配：先让它生成 `urls.txt`，再调上面的批量命令
