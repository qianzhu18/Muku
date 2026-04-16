# 幕库迭代 To Do 序列与验证规范

这份文档的目标不是再列一份“大想法清单”，而是把幕库后续的开发节奏固定下来：

- 每一轮只解决一组清晰问题
- 每一轮都要有测试验证
- 每一轮结束都要把状态沉淀回文档

这样项目才能持续迭代，而不是每次都重新梳理上下文。

## 当前迭代快照

截至 `2026-04-16`，已经完成的迭代：

### Iteration 01

- 范围：`P0-1 + P0-2A`
- 结果：文档 / Web 文案和真实能力对齐

### Iteration 02

- 范围：`P0-2B`
- 结果：Web 支持显式勾选生成 `知识库.md`

### Iteration 03

- 范围：`P0-3`
- 结果：`doctor` 与认证语义区分 `configured / verified`

### Iteration 04

- 范围：`P1-1`
- 结果：Web 任务详情支持产物预览

### Iteration 05

- 范围：`P1-2`
- 结果：音频 ASR fallback 支持固定时长切片和分段转写

### Iteration 06

- 范围：`Web 任务入口交互优化`
- 结果：首屏主入口改成“先粘贴链接”，高级选项默认折叠，提交反馈会直接引导下一步动作

### Iteration 07

- 范围：`Web 首屏层级重构`
- 结果：左侧主区域改成大尺寸粘贴框和直接开始动作，准备状态改为折叠摘要，不再占据主交互空间

### Iteration 08

- 范围：`模式选择强化 + 观察台压缩`
- 结果：首屏直接强调 `逐字稿 MD / MP3 / 视频` 三种处理模式，右侧观察台改成预览优先、路径折叠，减少纵向滚动负担

### Iteration 09

- 范围：`首屏下载动作回归`
- 结果：把主按钮移回输入框下方，恢复“粘贴链接后立刻开始”的首屏逻辑，同时压缩输入区和模式卡高度，避免 CTA 被挤出可视区域

### Iteration 10

- 范围：`Web UI 回退到稳定表单`
- 结果：撤回大粘贴框和模式卡重构，恢复旧版“新建任务 + 下载格式下拉框 + 底部主下载按钮”的稳定界面，默认模式回到 `Highest Video (MP4)`

## 下一轮 To Do 序列

建议严格按这个顺序推进，不要同时拉开太多战线。

### Next 01

- 编号：`P1-3`
- 主题：源内容解析预览
- 目标：用户在开始任务前就能判断内容值不值得处理
- 关闭标准：
  - 有 `/api/parse` 或等价接口
  - 返回标题、作者、平台、时长、字幕线索、推荐处理链路
  - Web 端支持“先解析，再开始”

### Next 02

- 编号：`P1-4`
- 主题：`逐字稿.md` 资产化
- 目标：让逐字稿不只是清洗正文，而是真正的 Markdown 资产
- 关闭标准：
  - 顶部元信息
  - 更稳定的分段
  - 与 `原始逐字稿 / 解析稿 / 知识库稿` 的职责边界清晰

### Next 03

- 编号：`P1-5`
- 主题：迁移到另一台电脑的说明
- 目标：把配置迁移、目录迁移、cookies 检查写成可执行文档

### Next 04

- 编号：`P2-1`
- 主题：provider 抽象
- 目标：为更多平台、解析预览、API 化打底

## 每轮开发固定动作

后面每轮都建议按下面 5 步执行。

### 1. 只选一个主 workstream

不要一轮里同时推进：

- chunked ASR
- provider 抽象
- 解析预览

这种跨层改动会让测试边界变糊。

### 2. 先做最小闭环

每轮只交付“能单独成立的一段价值”，例如：

- 先支持固定 10 分钟切片，再讨论 VAD
- 先支持任务详情预览，再讨论独立内容页
- 先支持返回基础 metadata，再讨论缩略图和格式卡片

### 3. 必做自测

每轮开发后至少跑这组基础验证：

```bash
node --check webui/static/app.js
python3 -m py_compile webui/app.py webui/cli.py webui/transcript_pipeline.py webui/openrouter_backends.py
./.venv/bin/python -m unittest tests.test_subtitle_route
```

如果某一轮改动了特定模块，还要补针对性的测试：

- ASR 链路：补长音频 / 分片 / 重试测试
- 解析预览：补 `/api/parse` 接口测试
- Markdown 资产化：补产物内容断言测试

### 4. 必做文档回写

每轮结束后至少回写这 3 类文档：

- `docs/to do/priority-roadmap.md`
- 对应专题文档
- 如果用户可见能力发生变化，再同步 `README.md`

### 5. 必做阶段报告

每轮收尾都要写清楚：

- 这轮做了什么
- 哪些文件改了
- 跑了哪些测试
- 测试结果是什么
- 下一轮建议做什么

## 统一测试基线

这是当前建议长期保留的最小回归基线。

### 基础回归

```bash
node --check webui/static/app.js
python3 -m py_compile webui/app.py webui/cli.py webui/transcript_pipeline.py webui/openrouter_backends.py
./.venv/bin/python -m unittest tests.test_subtitle_route
```

### 当前最新一次基线结果

`2026-04-16`

- `node --check webui/static/app.js`：通过
- `python3 -m py_compile webui/app.py webui/cli.py webui/transcript_pipeline.py webui/openrouter_backends.py`：通过
- `./.venv/bin/python -m unittest tests.test_subtitle_route`：通过，`67` 个测试全部成功

## 每轮 DoD

一轮迭代只有同时满足下面几项，才算真正完成：

- 有明确关闭的需求点
- 功能已经落进代码，不只是停在方案
- 至少跑过一轮基础回归
- 文档里的优先级和状态已经同步
- 最终报告能说明“下一轮应该接什么”

## 文档维护规则

后面每完成一轮，建议同步做这两个动作：

1. 在这份文档里补一条新的 iteration 记录
2. 在 [priority-roadmap.md](/Users/mac/qianzhu%20Vault/Archives/Video-Downloade/docs/to%20do/priority-roadmap.md) 里更新状态

这样这套 To Do 序列就能长期保持可执行，而不是只在某个阶段有用。
