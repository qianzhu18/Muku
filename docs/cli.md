# CLI 与 AI 集成

这个仓库的命令行已经是第一公民，不只是 Web UI 的附属工具。

如果你的目标是：

- 让 AI 代理稳定调用这个项目
- 批量处理 URL 或本地音频
- 从视频直接整理出知识库笔记
- 在 Docker 容器里复用同一套能力

优先走 CLI，而不是驱动浏览器。

## 安装

```bash
pip install -e .
```

或者直接运行模块：

```bash
python -m webui.cli --help
```

## 最推荐的工作流

### URL -> 逐字稿 + 解析稿 + 知识库稿

```bash
video-downloade capture "https://www.bilibili.com/video/BVxxxx" \
  --knowledge \
  --json
```

### 本地音频 -> 逐字稿 + 知识库稿

```bash
video-downloade audio "/path/to/file.mp3" \
  --knowledge \
  --json
```

### 已有 sidecar -> 单独补知识库稿

```bash
video-downloade knowledge "/path/to/file.mp3" --json
```

### 批量 URL

```bash
video-downloade capture \
  --input-file ./urls.txt \
  --knowledge \
  --jobs 0 \
  --resume \
  --result-file ./capture.json \
  --json
cat ./urls.txt | video-downloade capture --stdin --output paths
```

## 命令选择

- URL 输入，目标是逐字稿或知识库产物：`capture`
- 只想下载视频或 MP3：`download`
- 已经有本地音频：`audio`
- 已经有 sidecar 路径，想定位整组产物：`artifacts`
- 已经有逐字稿资产，只想补生成知识库稿：`knowledge`
- 想先检查依赖、模型、Cookies、提示词：`doctor`

## AI 友好的输出约定

- 默认推荐 `--json`
- 只需要路径时用 `--output paths`
- 需要把结果落盘时用 `--result-file`
- 长批量任务建议始终带上 `--resume`
- `artifacts` 默认只返回 metadata 摘要；排障时再加 `--full-metadata`

如果你在写 agent workflow，推荐顺序是：

1. `video-downloade doctor --json`
2. `capture --knowledge --json` 或 `audio --knowledge --json`
3. 必要时再用 `artifacts --json` 反查 sidecar

## 常用覆盖项

```bash
video-downloade capture URL --language zh --json
video-downloade capture URL --transcription-model openai/gpt-audio-mini --json
video-downloade capture URL --cleanup-model GLM-4.5 --article-model GLM-4.5 --json
video-downloade capture URL --knowledge-model GLM-4.5 --json
video-downloade capture URL --knowledge-prompt-file ./知识库提示词.md --json
video-downloade audio FILE --no-article --knowledge --json
```

## 断点恢复与高并发

`capture`、`download`、`audio`、`knowledge` 现在都支持：

```bash
--jobs 0
--resume
--result-file ./capture.json
```

推荐理解方式：

- `--jobs 0`：自动并发；URL 批量会走更积极的自动并发档位，本地音频和知识库整理维持更稳的并发上限
- `--result-file`：每个条目完成就会增量写入 JSON checkpoint，不需要等整批跑完
- `--resume`：先复用 checkpoint；对于 `capture` / `download --transcript` / `audio`，还会额外复用下载目录里已经存在的逐字稿 sidecar

这意味着如果一批任务在第 7 条时中断，再跑同一条命令时：

- 已经完成知识库的条目会直接跳过
- 已经生成逐字稿、但知识库还没完成的条目会直接从知识库阶段继续
- 本地已经存在 sidecar 的 URL / 音频，也不会重复下载或重复转写

一个更稳的批量模板：

```bash
video-downloade capture \
  --input-file ./urls.txt \
  --knowledge \
  --jobs 0 \
  --resume \
  --result-file ./runs/creator-series/capture.json \
  --output paths
```

## Cookies 与平台登录态

YouTube 或 Bilibili 字幕优先链路更稳定的做法，是按平台分开配置登录态：

```bash
video-downloade capture URL \
  --youtube-cookies-from-browser chrome \
  --bilibili-cookies-path ./cookies/bilibili.cookies.txt \
  --json
```

也可以写进 `.env`：

```bash
YOUTUBE_COOKIES_FROM_BROWSER=chrome
YOUTUBE_COOKIES_PATH=/absolute/path/to/youtube.cookies.txt
BILIBILI_COOKIES_PATH=/absolute/path/to/bilibili.cookies.txt
DOUYIN_COOKIES_PATH=/absolute/path/to/douyin.cookies.txt
```

## 容器里调用 CLI

如果你已经用 Docker 启动服务，也不需要额外装第二套工具：

```bash
docker compose exec ytdl-webui video-downloade doctor --json
docker compose exec ytdl-webui video-downloade capture URL --knowledge --json
```

## Skill 封装

公开 skill 已经整理在：

- [../skills/video-downloade-cli/SKILL.md](../skills/video-downloade-cli/SKILL.md)

安装到 Codex：

```bash
./scripts/install-video-downloade-skill
```

如果你想手动复制：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R ./skills/video-downloade-cli "${CODEX_HOME:-$HOME/.codex}/skills/video-downloade-cli"
```

## 搭配 web-access

如果你的需求不是“已经有视频链接”，而是“先去某个博主主页、合集页、系列页把链接采下来”，推荐搭配 [`web-access`](https://github.com/eze-is/web-access)：

- 它适合打开创作者主页、动态页面和需要浏览器登录态的站点，再把链接整理成 `urls.txt`
- 本仓库 CLI 负责把 `urls.txt` 批量变成逐字稿、解析稿和知识库 Markdown

推荐 prompt：

```text
请打开这个创作者主页，只提取「XXX 系列」的视频链接。
要求：
1. 每行一个 URL
2. 不要输出解释
3. 保存为 ./urls.txt
```

然后直接执行：

```bash
video-downloade capture \
  --input-file ./urls.txt \
  --knowledge \
  --jobs 0 \
  --resume \
  --result-file ./runs/creator-series/capture.json \
  --output paths
```

仓库里还附了一个可直接试跑的 demo 链接文件，见 [creator-batch-workflow.md](./creator-batch-workflow.md)。
