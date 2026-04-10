# CLI Usage For AI Agents

优先使用这个仓库提供的原生命令行，而不是直接驱动浏览器或 Web 表单。

## Primary Commands

```bash
# URL -> 逐字稿 + 解析稿 + 知识库稿
video-downloade capture "https://www.bilibili.com/video/BVxxxx" --knowledge --json

# 批量 URL
cat urls.txt | video-downloade capture --stdin --knowledge --json
video-downloade capture --input-file ./urls.txt --result-file ./capture-result.json --json

# 仅下载，不生成逐字稿
video-downloade download "https://www.bilibili.com/video/BVxxxx" --preset "Best Audio (MP3)" --json

# 本地音频 -> 逐字稿 + 知识库稿
video-downloade audio "/path/to/file.mp3" --knowledge --json

# 反查已有产物
video-downloade artifacts "/path/to/file.mp3" --json
video-downloade artifacts "/path/to/file.mp3" --full-metadata --json

# 仅补知识库稿
video-downloade knowledge "/path/to/file.mp3" --json

# 检查依赖和 API 配置
video-downloade doctor --json
video-downloade config --json
```

## Output Expectations

- 默认输出可读文本摘要。
- 加 `--json` 时，输出稳定 JSON，适合代理程序读取。
- 也可以用 `--output paths` 只拿关键产物路径，便于 shell 链接下一步。
- 需要批量输入时，优先使用 `--input-file` 或 `--stdin`。
- 需要可追踪结果时，优先加 `--result-file`。
- `capture --knowledge` 是 URL 转知识库产物的首选命令。
- `audio --knowledge` 用于已存在的 MP3、M4A、WAV 等本地音频文件。
- `artifacts` 用于从任意 sidecar 或音频路径反查整组产物。
- `artifacts` 默认只返回摘要 metadata；只有确实需要排障时再加 `--full-metadata`。

## Auth Notes

- 如果平台字幕接口需要登录态，优先用 `--youtube-cookies-from-browser chrome` 或平台专用 `cookies.txt`。
- YouTube 和 Bilibili 建议分开配置 Cookies，不要串用。

## Runtime Config

- 如果要先把默认下载目录、转写模型、解析模型或知识库模型配好，优先调用 `video-downloade config --json` 查看现状。
- 需要写入默认配置时，用 `video-downloade config --download-dir ... --transcription-model ... --cleanup-model ... --article-model ... --knowledge-model ... --json`。
- Docker 场景下，下载目录应写容器内路径，例如 `/downloads/default`；宿主机真实路径由 Compose 的卷映射决定。

## Skill

如果代理支持读取仓库内 skill，优先加载：

- [skills/muku-video-to-md/SKILL.md](skills/muku-video-to-md/SKILL.md)
- [.codex/skills/muku-video-to-md/SKILL.md](.codex/skills/muku-video-to-md/SKILL.md)
