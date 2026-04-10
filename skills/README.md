# Muku Skills

这个目录存放幕库对外公开的 agent / AI skill。目标不是让 agent 去点网页，而是直接复用稳定的 CLI 契约，把 Bilibili、YouTube、Douyin 等平台上的知识视频沉淀为 Markdown 知识库。

## 当前提供

- [muku-video-kb](muku-video-kb/SKILL.md)

这个 skill 适合：

- 单条 URL 直接生成逐字稿、解析稿和知识库稿
- 本地音频补做转写和知识库整理
- 从 `urls.txt` 批量把一组视频收入本地知识库
- 让 AI agent 复用稳定 JSON 输出，不必驱动 Web UI

推荐使用顺序：

1. 先跑 `video-downloade doctor --json`
2. 再按平台补 `--youtube-cookies-*` / `--bilibili-cookies-*` / `--douyin-cookies-*`
3. 最后让 agent 调 `capture --knowledge`、`audio --knowledge`、`artifacts` 等命令

推荐的批量入库命令：

```bash
video-downloade capture \
  --input-file ./urls.txt \
  --knowledge \
  --jobs 0 \
  --resume \
  --result-file ./runs/creator-series/capture.json \
  --output paths
```

如果你要先从创作者主页、系列页、合集页采链接，再批量生成 Markdown 知识库，推荐和 [`web-access`](https://github.com/eze-is/web-access) 组合使用：前者负责浏览器采集 URL，后者负责把 URL 批量入库。

## 快速安装到 Codex

推荐直接运行：

```bash
./scripts/install-muku-skill
```

如果你还在沿用旧脚本名，`./scripts/install-video-downloade-skill` 也可以继续使用。

如果你想手动安装：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R ./skills/muku-video-kb "${CODEX_HOME:-$HOME/.codex}/skills/muku-video-kb"
```

## 目录约定

- `.codex/skills/`：仓库内当前直接使用的本地 skill
- `skills/`：适合开源发布、给其他 agent 工具复用的版本

后续如果要兼容更多 agent 平台，可以继续在这里补不同格式的 skill 模板，但核心原则不变：优先复用 CLI，而不是驱动网页。
