# Skills

这个目录用于存放面向开源社区公开的 agent / AI skill 说明。

目标：

- 让 Codex、Claude Code、Cursor Agent 等工具可以直接复用本仓库的 CLI 契约
- 避免每个 agent 都重复摸索“该调哪个命令、哪些参数最稳”
- 把下载、逐字稿、sidecar 反查这些常见操作收成稳定提示词

当前提供：

- [video-downloade-cli](video-downloade-cli/SKILL.md)

说明：

- `.codex/skills/` 里保留的是当前仓库内部直接使用的 skill
- `skills/` 里放的是适合开源发布、给其他 agent 工具复用的版本
- 若后续要兼容更多 agent 平台，可以继续在这里补不同格式的 skill 模板
