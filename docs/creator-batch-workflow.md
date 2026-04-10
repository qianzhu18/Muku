# Creator Batch Workflow

这个工作流适合两种场景：

- 先去某个博主主页、系列页、合集页采一批视频链接
- 再把这一批视频直接整理成 Markdown 逐字稿和知识库

推荐组合：

- 本仓库的 `muku-video-kb` skill：负责下载、逐字稿、知识库整理
- [`web-access`](https://github.com/eze-is/web-access)：负责打开动态页面、浏览器登录态页面和创作者主页，把 URL 提成 `urls.txt`

## 1. 安装

安装本仓库 skill：

```bash
./scripts/install-muku-skill
```

安装 [`web-access`](https://github.com/eze-is/web-access)：

```bash
claude plugin marketplace add https://github.com/eze-is/web-access
claude plugin install web-access@web-access --scope user
```

`web-access` 的 README 当前建议准备 `Node.js 22+`，并在 Chrome 里开启远程调试，以便走 CDP 浏览器模式。

## 2. 让 web-access 采链接

推荐 prompt：

```text
请打开这个创作者主页，只提取「XXX 系列」的视频链接。
要求：
1. 每行一个 URL
2. 不要输出解释
3. 保存为 ./urls.txt
```

如果不是系列页，而是整页创作者视频，也可以改成：

```text
请打开这个博主主页，提取最近 10 条视频链接。
要求：
1. 每行一个 URL
2. 不要输出解释
3. 保存为 ./urls.txt
```

## 3. 用 CLI 批量转知识库

最推荐的命令模板：

```bash
video-downloade capture \
  --input-file ./urls.txt \
  --knowledge \
  --jobs 0 \
  --resume \
  --result-file ./runs/creator-series/capture.json \
  --output paths
```

关键点：

- `--jobs 0`：自动并发，适合批量 URL
- `--result-file`：每个条目完成就会写一次 checkpoint
- `--resume`：中断后直接重跑同一条命令，会跳过已完成条目，并优先复用已有 sidecar

如果平台需要登录态，建议加平台专用 Cookies：

```bash
video-downloade capture \
  --input-file ./urls.txt \
  --youtube-cookies-from-browser chrome \
  --bilibili-cookies-path ./cookies/bilibili.cookies.txt \
  --douyin-cookies-from-browser chrome \
  --knowledge \
  --jobs 0 \
  --resume \
  --result-file ./runs/creator-series/capture.json \
  --output paths
```

## 4. 仓库内 Demo

仓库里附了一份公开演示链接文件：

```text
./examples/creator-batch/bilibili-demo.urls.txt
```

你可以直接试跑：

```bash
video-downloade capture \
  --input-file ./examples/creator-batch/bilibili-demo.urls.txt \
  --bilibili-cookies-path ./cookies/bilibili.cookies.txt \
  --output-dir ./runs/bilibili-creator-demo \
  --knowledge \
  --jobs 0 \
  --resume \
  --result-file ./runs/bilibili-creator-demo/capture.json \
  --output paths
```

如果命令中途停掉，不要改参数，直接重新执行同一条命令即可。
