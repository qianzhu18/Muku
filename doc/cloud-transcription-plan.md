# 云端转写执行方案

更新日期：2026-04-07

## 目标

这条路线只保留两件事：

- Docker 容器继续负责 `yt-dlp` 下载、队列、Web UI。
- MP3 下载完成后，直接调用云端 API 做转写，再做轻量清洗。

本方案明确放弃本地 `MLX / Whisper` 路线，不再把宿主机模型服务作为主线能力。

## 当前仓库的真实起点

当前 `main` 分支的下载主流程很简单，核心都在 [webui/app.py](../webui/app.py)：

- `FORMAT_PRESETS` 已经有 `Best Audio (MP3)` 预设。
- `worker(job_id)` 负责执行 `yt-dlp` 下载。
- `/api/start` 和 `/api/tasks` 已经够用，可以继续承接“下载后自动转写”的任务状态。

这意味着第一版云端改造不需要重写架构，只需要在下载完成后插一个“转写后处理”钩子。

## 推荐结论

### 主推方案

- 转写：智谱 `glm-asr`
- 清洗：智谱 `glm-4.7-flash` 或 `glm-4.7`

这是当前最适合这个项目的路线，原因有三点：

1. `glm-asr` 是专门的语音转写接口，调用方式直接，适合 `mp3 -> text`。
2. 智谱官方文档明确写了 `0.06 元/分钟`，预算最好估。
3. 官方文档明确支持中文、英语和多种方言，和你的 B 站 / YouTube 混合场景更贴近。

### 兼容方案

- 转写后端兼容 OpenRouter
- 推荐模型：`openai/gpt-audio-mini`

OpenRouter 适合作为“统一后端适配层”，不是第一版的预算锚点。原因是它按 `audio tokens` 计费，不像智谱 `glm-asr` 这样直接按分钟报价，前期预算和回归测试都不如智谱直观。

### 不建议作为主线的方案

- `glm-asr-2512` 不作为长音频主模型

智谱官方文档对 `GLM-ASR-2512` 写明了 `文件大小 ≤ 25 MB、音频时长 ≤ 30 秒`。它更像短音频或实时场景，不适合作为当前“下载完整 MP3 后再批处理”的默认主线。

## 成本概念

### 智谱转写

智谱官方文档给出的 `glm-asr` 价格是 `0.06 元/分钟`。

- `10 元` 约等于 `166 分钟`
- 也就是大约 `2.8 小时`

这还没算清洗阶段，但清洗通常是纯文本 token 成本，远低于音频转写本身。

### 智谱清洗

建议第一版直接分两档：

- 成本优先：`glm-4.7-flash`
- 质量优先：`glm-4.7`

智谱模型概览把 `glm-4.7-flash` 标成了“免费模型”。如果你的整理目标只是“逐字稿去脏、分段、转 Markdown”，优先从 `glm-4.7-flash` 起步更合理。

### OpenRouter 转写

OpenRouter 官方页面当前显示 `openai/gpt-audio-mini` 的价格是：

- `$0.60 / 1M input tokens`
- `$2.40 / 1M output tokens`
- `$0.60 / 1M audio tokens`

这个价格在纸面上很便宜，但它不是“按分钟”报价，而且还会受到音频 token、输出文本 token、提示词长度影响。第一版不建议拿它做预算基准，更适合做兼容后端或备用路由。

## 关于你的智谱会员

智谱官方 FAQ 已经写得很明确：

- `GLM Coding Plan` 额度只适用于它支持的编码工具。
- 自建应用、网站、机器人、SaaS 场景要走“标准 API 服务”，独立计费。

所以你的结论应该很明确：

- 你可以继续使用智谱生态。
- 但这个项目里的“下载器 + 转写 + 清洗”不会直接吃掉 Coding 套餐额度。
- 真正结算的是标准 API 余额、赠金或资源包。

## 第一版产品边界

第一版先只做这条闭环：

1. 下载 MP3
2. 云端转写成原始文本
3. 本地做轻量规则清洗
4. 可选调用文本模型整理为 Markdown

先不要在第一版同时追求：

- 精准逐词时间戳
- 说话人分离
- 平台字幕融合
- 多后端自动路由

这些都可以作为后续增强项，但不该阻塞当前主链路上线。

## 仓库里的建议改造方式

### 1. 新增提供商适配层

建议新增：

- `webui/transcription_backends.py`
- `webui/cleanup_backends.py`

职责很简单：

- `transcribe_with_zhipu(audio_path, meta)`
- `transcribe_with_openrouter(audio_path, meta)`
- `cleanup_with_zhipu(text, meta)`
- `cleanup_with_openrouter(text, meta)`

所有后端都统一返回同一份结构，例如：

```json
{
  "provider": "zhipu",
  "model": "glm-asr",
  "text": "逐字稿内容",
  "raw_response": {}
}
```

这样后面你想切换提供商，不需要碰主流程。

### 2. 在下载完成后插转写钩子

当前集成点就是 `webui/app.py` 里的 `worker(job_id)`。

建议逻辑：

1. 先完成 `yt-dlp` 下载
2. 如果预设是 `Best Audio (MP3)`，则进入转写后处理
3. 找到本次任务对应的音频文件
4. 调用云端转写
5. 落盘产物

这一步不要把“下载”和“转写”写死在一个 try 里，应该拆成两个阶段，这样失败重试更清楚。

### 3. 先固化产物规范

建议每个音频默认输出这些 sidecar 文件：

- `xxx.mp3`
- `xxx.raw.txt`
- `xxx.clean.txt`
- `xxx.md`
- `xxx.transcript.json`

说明：

- `raw.txt` 永远保留原始转写结果
- `clean.txt` 只做轻量规则清洗
- `md` 才是最终知识库版本
- `transcript.json` 留 API 原始响应和模型信息，方便追错

### 4. 清洗分两层

不要一上来就把“清洗”和“Markdown 结构化”混成一步。

建议拆成：

- 轻量规则清洗：本地执行
- 结构化整理：LLM 执行

本地规则清洗只做低风险动作：

- 多空格合并
- 中英文标点基础修正
- 常见数字与单位之间的空格修正
- 段落切分

LLM 清洗再做高层整理：

- 小标题
- 列表
- 摘要
- Obsidian 风格 Markdown

### 5. 加最小可用配置

建议先加这些环境变量：

```env
ENABLE_TRANSCRIPTION=true
TRANSCRIPTION_PROVIDER=zhipu
TRANSCRIPTION_MODEL=glm-asr
ENABLE_CLEANUP=true
CLEANUP_PROVIDER=zhipu
CLEANUP_MODEL=glm-4.7-flash
ZHIPU_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_TRANSCRIPTION_MODEL=openai/gpt-audio-mini
OPENROUTER_CLEANUP_MODEL=openai/gpt-4o-mini
```

默认值建议：

- 转写默认 `zhipu / glm-asr`
- 清洗默认 `zhipu / glm-4.7-flash`

### 6. 失败与重试策略

第一版只做最稳的断点机制：

- 如果 `xxx.raw.txt` 已存在，则跳过转写
- 如果 `xxx.clean.txt` 已存在，则跳过轻量清洗
- 如果 `xxx.md` 已存在，则跳过 Markdown 整理

网络失败时：

- 单任务重试 3 次
- 采用指数退避
- 每次失败都把错误写进 `transcript.json`

## 模型推荐

### 转写模型优先级

1. `glm-asr`
   - 主推
   - 理由：专用转写接口、中文和中英混合场景友好、预算最清楚

2. `openai/gpt-audio-mini` on OpenRouter
   - 兼容方案
   - 理由：统一 API、后续切模型方便、适合你以后做多后端兼容

3. `openai/gpt-audio` on OpenRouter
   - 高精度备选
   - 理由：适合特别难的口音、噪声、混合内容，但成本高很多

### 清洗模型优先级

1. `glm-4.7-flash`
   - 第一版默认
   - 理由：够便宜，适合“转 Markdown 知识库”这种轻整理任务

2. `glm-4.7`
   - 质量优先
   - 理由：更适合长文整理、结构重写、知识库条理化

3. OpenRouter 文本模型
   - 兼容后端
   - 推荐思路：选便宜、稳定、中文表现好的纯文本模型即可

## 执行顺序

建议严格按下面顺序做，不要并行发散：

1. 先接 `glm-asr`，只产出 `raw.txt + transcript.json`
2. 再加本地轻量清洗，产出 `clean.txt`
3. 再接 `glm-4.7-flash`，产出 `md`
4. 最后才加 OpenRouter 兼容后端

## 验收标准

完成第一版后，至少满足这几个条件：

- 选 `Best Audio (MP3)` 下载后，能自动得到 `raw.txt`
- 中文视频和英文视频都能稳定产出可读文本
- 转写失败时，任务状态和错误信息能回显到 UI
- 重启服务后，不会重复浪费已经转写成功的文件
- `10 元` 预算下，至少能稳定跑完 `2 小时以上` 音频

## 参考资料

- OpenRouter Audio 文档：<https://openrouter.ai/docs/guides/overview/multimodal/audio>
- OpenRouter API 概览：<https://openrouter.ai/docs/api/reference/overview>
- OpenRouter `openai/gpt-audio-mini`：<https://openrouter.ai/openai/gpt-audio-mini>
- 智谱 `GLM-ASR`：<https://docs.bigmodel.cn/cn/guide/models/sound-and-video/glm-asr>
- 智谱 `GLM-ASR-2512`：<https://docs.bigmodel.cn/cn/guide/models/sound-and-video/glm-asr-2512>
- 智谱 `GLM-4.7`：<https://docs.bigmodel.cn/cn/guide/models/text/glm-4.7>
- 智谱 `GLM-4.7-Flash`：<https://docs.bigmodel.cn/cn/guide/models/free/glm-4.7-flash>
- 智谱模型概览：<https://docs.bigmodel.cn/cn/guide/start/model-overview>
- 智谱 Coding Plan FAQ：<https://docs.bigmodel.cn/cn/coding-plan/faq>
