# CLI Usage For AI Agents

优先使用这个仓库提供的原生命令行，而不是直接驱动浏览器或 Web 表单。

## Primary Commands

```bash
# 从 URL 直接生成 MP3 + Markdown 逐字稿
video-downloade capture "https://www.bilibili.com/video/BVxxxx" --json

# 批量输入时，优先使用 stdin 或文件
cat urls.txt | video-downloade capture --stdin --json
video-downloade capture --input-file ./urls.txt --result-file ./capture-result.json --json

# 仅下载，不生成逐字稿
video-downloade download "https://www.bilibili.com/video/BVxxxx" --preset "Best Audio (MP3)" --json

# 把本地音频转成逐字稿
video-downloade audio "/path/to/file.mp3" --source-url "https://example.com" --json

# 反查已有产物
video-downloade artifacts "/path/to/file.mp3" --json
video-downloade artifacts "/path/to/file.mp3" --full-metadata --json

# 检查依赖和 API 配置
video-downloade doctor --json
```

## Output Expectations

- 默认输出可读文本摘要。
- 加 `--json` 时，输出稳定 JSON，适合代理程序读取。
- 也可以用 `--output paths` 只拿关键产物路径，便于 shell 链接下一步。
- 需要批量输入时，优先使用 `--input-file` 或 `--stdin`，避免拼接超长命令。
- 需要可追踪结果时，优先加 `--result-file`.
- `capture` 是 URL 转知识库产物的首选命令。
- `download` 保留纯下载能力。
- `audio` 用于已存在的 MP3、M4A、WAV 等本地音频文件。
- `artifacts` 用于从任意 sidecar 或音频路径反查整组产物。
- `artifacts` 默认只返回摘要 metadata；只有确实需要排障时再加 `--full-metadata`.

## Artifacts

成功后通常会生成这些文件：

- `xxx - 原始逐字稿.txt`
- `xxx - 解析稿.md`
- `xxx - 逐字稿.md`
- `xxx - 转写信息.json`
