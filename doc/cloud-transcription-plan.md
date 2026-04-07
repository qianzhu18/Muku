# 云端转写执行方案

更新日期：2026-04-07

## 目标

当前主线已经明确为：

1. `yt-dlp` 下载音频
2. OpenRouter `openai/gpt-audio-mini` 转写 MP3
3. 智谱 OpenAI 兼容接口 `GLM-4.5` 按提示词做文本清洗
4. 输出 Markdown sidecar

本方案不再以本地 `MLX / Whisper` 为主线能力。

## 当前仓库的改造方向

当前 `webui/app.py` 已负责下载任务队列。最小可行改造就是在 `Best Audio (MP3)` 下载完成后，直接接入云端转写，不重写现有 Flask 结构。

推荐第一版继续保持这三点：

- 下载和转写仍在同一个任务里串行完成
- 只在 MP3 预设上自动触发转写
- 先产出 `raw / clean / md / json` 四类 sidecar 文件

## 推荐结论

### 主推方案

- 转写：OpenRouter `openai/gpt-audio-mini`
- 清洗：智谱 OpenAI 兼容接口 `GLM-4.5`
- 提示词：项目根目录 [角色提示词.md](../角色提示词.md)
- Markdown 整理：本地模板输出

这是当前最适合落第一版的路线，原因很直接：

1. OpenRouter 官方已经支持 `input_audio`，可以直接走统一的 `chat/completions` 接口。
2. `openai/gpt-audio-mini` 的官方页面价格很低，适合先跑通大批量 MP3 转写。
3. 转写和后续文本模型都可以放在同一个 OpenRouter 账号体系下，后面扩展最省事。

### 当前清洗配置说明

- Base URL：`https://open.bigmodel.cn/api/coding/paas/v4`
- Model：`GLM-4.5`
- 协议：OpenAI 兼容 `chat/completions`

这一步是“转写后的文本清洗”，不是音频转写。

## 成本概念

### OpenRouter `openai/gpt-audio-mini`

OpenRouter 官方页面当前价格是：

- `$0.60 / 1M input tokens`
- `$2.40 / 1M output tokens`
- `$0.60 / 1M audio tokens`

OpenRouter 页面没有直接给“每分钟成本”。所以这里的分钟数只能做推算，不是官方定价口径。

推算方法：

- OpenAI 官方价格页给 `gpt-4o-mini-transcribe` 的“Estimated cost”是 `$0.003 / minute`
- 同页里它的输入 / 输出价格分别是 `$1.25 / 1M` 和 `$5.00 / 1M`
- `openai/gpt-audio-mini` 在 OpenRouter 上的输入 / 输出价格大约是这组价格的 `48%`

按这个比例粗略推算：

- `gpt-audio-mini` 大约 `~$0.0014 / 分钟`
- 以 `1 美元 ≈ 7.2 元人民币` 粗略换算
- `10 元人民币` 约等于 `~950 分钟`
- 也就是大约 `15 到 16 小时`

这个数字是“成本概念”，不是结算承诺。真实费用会受这些因素影响：

- 音频压缩后大小
- 实际音频 token 消耗
- 输出文本长度
- 提示词长度
- OpenRouter 路由到的提供商

### 智谱 `glm-asr`

智谱官方文档当前给出的价格是 `0.06 元/分钟`。

按这个价格算：

- `10 元人民币` 约等于 `166 分钟`
- 大约 `2.8 小时`

它更适合作为音频转写备选，不是当前默认主线。

## 为什么当前不把智谱放在第一位

不是说智谱不能用，而是当前需求更偏向：

- 优先打通
- 优先便宜
- 中文英文都能稳定转
- 后面还能顺手接别的 OpenRouter 文本模型

在这个约束下，`openai/gpt-audio-mini` 更适合作为默认值。

## 当前实现建议

### 1. 下载后直接转写

`Best Audio (MP3)` 下载完成后：

1. 定位下载好的 MP3
2. 用 `ffmpeg` 压成更适合上传的单声道低码率转写源
3. 调 OpenRouter `chat/completions`
4. 保存逐字稿与 sidecar

### 2. 统一产物规范

建议每个音频默认产出：

- `xxx.mp3`
- `xxx.raw.txt`
- `xxx.clean.txt`
- `xxx.md`
- `xxx.transcript.json`

说明：

- `raw.txt` 保留模型原始转写文本
- `clean.txt` 是规则清洗后的文本
- `md` 是可直接放进 Obsidian 的 Markdown
- `transcript.json` 保留模型名、来源 URL 和 API 返回摘要，方便追错

### 3. 清洗分层

当前链路先做两层：

- 本地轻量规则清洗
- 智谱 `GLM-4.5` 语义清洗

最后再统一渲染 Markdown。

### 4. 第一版不做的事情

先不要同时做这些：

- 精准逐词时间戳
- 说话人分离
- 平台字幕融合
- 多后端智能路由
- 本地上传音频入口

这些不影响当前主链路验证，后面再补。

## 环境变量建议

```env
ENABLE_TRANSCRIPTION=true
TRANSCRIPTION_LANGUAGE=auto
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_TRANSCRIPTION_MODEL=openai/gpt-audio-mini
ENABLE_AI_CLEANUP=true
AI_CLEANUP_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4
AI_CLEANUP_API_KEY=
AI_CLEANUP_MODEL=GLM-4.5
AI_CLEANUP_PROMPT_FILE=/app/角色提示词.md
AI_CLEANUP_FALLBACK_LOCAL=true
TRANSCRIPTION_AUDIO_BITRATE=48k
KEEP_TRANSCRIPTION_INPUT=false
```

默认值建议：

- 转写模型：`openai/gpt-audio-mini`
- 清洗模型：`GLM-4.5`

## 模型优先级

### 转写模型

1. `openai/gpt-audio-mini`
   - 主推
   - 理由：先看成本与联通性，这是当前最合理的默认模型

2. `openai/gpt-audio`
   - 高精度备选
   - 理由：更适合噪声大、口音重或内容更复杂的音频

3. 智谱 `glm-asr`
   - 兼容备选
   - 理由：如果你后面希望部分任务改走智谱，保留适配层即可

### 清洗模型

1. `GLM-4.5`
   - 当前默认
   - 理由：和你给的 ASR 清洗提示词匹配，适合做“转写后修复”

2. 本地规则清洗
   - 回退路径
   - 理由：缺少智谱 key 时也不阻塞网页验证

## 验收标准

第一版完成后，至少满足：

- 选择 `Best Audio (MP3)` 后，下载完成会自动生成逐字稿 sidecar
- 中文和英文音频都能拿到可读文本
- 前端任务状态能显示“下载中 / 转写中 / 完成 / 失败”
- 出错时能在 `transcript.json` 和任务列表中看到错误
- 不启用 AI 整理时，也能直接得到可用的 `.md`
- 没配智谱 key 时，仍能自动回退到本地清洗，不影响转写验证

## 参考资料

- OpenRouter Audio 文档：<https://openrouter.ai/docs/guides/overview/multimodal/audio>
- OpenRouter `openai/gpt-audio-mini`：<https://openrouter.ai/openai/gpt-audio-mini>
- OpenAI Pricing：<https://developers.openai.com/api/docs/pricing>
- 智谱 `GLM-ASR`：<https://docs.bigmodel.cn/cn/guide/models/sound-and-video/glm-asr>
- 智谱 Coding Plan FAQ：<https://docs.bigmodel.cn/cn/coding-plan/faq>
