# CLI Usage For AI Agents

优先使用这个仓库提供的原生命令行，而不是直接驱动浏览器或 Web 表单。

## Primary Commands

```bash
# 从 URL 直接生成 MP3 + Markdown 逐字稿
video-downloade capture "https://www.bilibili.com/video/BVxxxx" --json

# 仅下载，不生成逐字稿
video-downloade download "https://www.bilibili.com/video/BVxxxx" --preset "Best Audio (MP3)" --json

# 把本地音频转成逐字稿
video-downloade audio "/path/to/file.mp3" --source-url "https://example.com" --json

# 检查依赖和 API 配置
video-downloade doctor --json
```

## Output Expectations

- 默认输出可读文本摘要。
- 加 `--json` 时，输出稳定 JSON，适合代理程序读取。
- `capture` 是 URL 转知识库产物的首选命令。
- `download` 保留纯下载能力。
- `audio` 用于已存在的 MP3、M4A、WAV 等本地音频文件。

## Artifacts

成功后通常会生成这些文件：

- `xxx - 原始逐字稿.txt`
- `xxx - 解析稿.md`
- `xxx - 逐字稿.md`
- `xxx - 转写信息.json`
