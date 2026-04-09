# Skills

这个目录用于存放面向开源社区公开的 agent / AI skill 说明，目标是让不同的 AI 工具都能直接复用本仓库的 CLI 契约，而不是重复摸索“该调哪个命令、哪些参数最稳”。

## 当前提供

- [video-downloade-cli](video-downloade-cli/SKILL.md)

这个 skill 现在包含：

- `SKILL.md`：工作流与命令约定
- `agents/openai.yaml`：面向 Codex/OpenAI 风格 skill 列表的界面元数据

## 快速安装到 Codex

推荐直接运行仓库脚本：

```bash
./scripts/install-video-downloade-skill
```

如果你想手动安装：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R ./skills/video-downloade-cli "${CODEX_HOME:-$HOME/.codex}/skills/video-downloade-cli"
```

## 目录约定

- `.codex/skills/`：仓库内当前直接使用的本地 skill
- `skills/`：适合开源发布、给其他 agent 工具复用的版本

后续如果要兼容更多 agent 平台，可以继续在这里补不同格式的 skill 模板，但核心原则不变：优先复用 CLI，而不是驱动网页。
