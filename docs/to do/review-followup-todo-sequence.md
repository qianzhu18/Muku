# Review 收尾 To Do 序列

这份清单基于本轮 review 的几个核心发现来排优先级，原则是：

1. 先修“对用户的真实承诺”
2. 再修“Web 和 CLI 的能力错位”
3. 最后补“长视频和弱字幕场景的稳定性”

如果只看最推荐的收尾顺序，就是：

1. 文档与 UI 文案对齐真实能力
2. Web 的知识库能力对齐真实行为
3. chunked ASR 作为抓不到字幕时的关键兜底

## P0：先把真相说清楚

这是第一优先级，而且应该先于任何新功能。

原因很简单：

- 现在最容易让新用户误解的不是“做不到”
- 而是“文档和界面都在暗示已经做到”

这一层如果不先收口，后面不管是加预览、加 provider、加 ASR，都会继续放大误解。

## Workstream 1：README / docs / Web 文案对齐

### 目标

把 Web、CLI、Docker、Skill 的能力边界说清楚，特别是：

- Web 当前默认不会产出 `知识库.md`
- CLI 才有 `--knowledge`
- Docker 下浏览器 cookies 不是最稳默认
- `doctor` 现在是 configured 检查，不是 verified 检查

### To Do

- 更新 `README.md`
  - 把“默认产物”改成按入口区分
  - 明确写出：
    - Web 默认产出：`原始逐字稿.txt`、`逐字稿.md`、`解析稿.md`、`转写信息.json`
    - CLI 在 `--knowledge` 时才产出 `知识库.md`
  - 把“入口已对齐”改成更准确的说法，避免让人以为 Web 和 CLI 完全同能力
  - 增加一张能力矩阵：
    - Web
    - CLI
    - Docker
    - Skill
    - 各自支持的输入、知识库生成、cookies 方案、批量能力

- 更新 `docs/windows.md`
  - 把 Docker 用户的认证建议改成：
    - Docker 优先 `cookies.txt`
    - 本地 Python 运行时才优先 `*_COOKIES_FROM_BROWSER`
  - 补一句说明：`*_COOKIES_FROM_BROWSER=chrome` 在容器里不等于一定可读

- 更新 Docker / 新手相关文案
  - 如果 README 里的快速开始仍优先推浏览器 cookies，要调整
  - 明确区分：
    - configured：填了配置
    - verified：当前环境里真的能用

- 新增一节“迁移到另一台电脑”
  - 需要复制什么：
    - `.env`
    - `docker-data/config/settings.json`
    - 可选 `docker-data/downloads`
  - 需要重新检查什么：
    - 下载路径
    - cookies 绝对路径
    - Docker volume 映射
    - 浏览器 cookies 方案是否仍可用

- 调整 Web 首页 / 设置页文案
  - 避免让“知识库整理服务”看起来像 Web 任务默认会执行
  - 避免主页 copy 暗示“贴链接就直接变知识库稿”

### 涉及文件

- [README.md](/Users/mac/qianzhu%20Vault/Archives/Video-Downloade/README.md)
- [docs/windows.md](/Users/mac/qianzhu%20Vault/Archives/Video-Downloade/docs/windows.md)
- [webui/templates/index.html](/Users/mac/qianzhu%20Vault/Archives/Video-Downloade/webui/templates/index.html)

### 完成标准

- 新用户看 README 不会再误以为 Web 默认产 `知识库.md`
- Docker 用户不会被优先引导到高失败率的 browser cookies
- `doctor` 的语义不会再被文案误写成“已验证可用”

### 难度

- 技术难度：`低`
- 产品收益：`高`
- 推荐立即做

## Workstream 2：Web 的知识库能力对齐

这一项要先做决策，再做实现。

核心问题不是“要不要知识库”，而是：

- 是先把 Web 文案降级到真实状态
- 还是直接把 Web 补到真的能生成知识库

### 推荐策略

建议分两步，不要一步到位硬上。

### Phase 2A：先做真相对齐

先把 Web 里的知识库相关设置降级成更准确的表述。

#### To Do

- 把设置中的“知识库整理服务”说明改成：
  - 当前主要用于 CLI / 后续知识库能力复用的配置
  - Web 当前任务默认不会直接生成 `知识库.md`

- 在 Web UI 的任务说明、模式说明、完成状态里避免出现“已生成知识库”的暗示

- 如果当前 Web 不支持知识库任务开关，就不要在主流程里把它写成已支持能力

#### 完成标准

- Web 不再“看起来支持但实际上没跑”

### Phase 2B：再补真正的 Web 知识库开关

等文案收口后，再决定是否把 Web 真补齐。

#### To Do

- 在 Web 提交表单新增一个显式开关：
  - `生成知识库稿`

- 把这个字段传入任务结构
  - Job 里新增 `generate_knowledge`

- 在 transcript 任务完成后继续执行知识库整理
  - 保持和 CLI `--knowledge` 的行为一致

- 任务完成状态要能区分：
  - transcript ready
  - knowledge ready

- Web 详情里展示：
  - `knowledge_path`
  - 是否已生成知识库稿

- Web 失败提示需要能区分：
  - 转写成功但知识库整理失败
  - 整体任务失败

#### 涉及文件

- [webui/app.py](/Users/mac/qianzhu%20Vault/Archives/Video-Downloade/webui/app.py)
- [webui/static/app.js](/Users/mac/qianzhu%20Vault/Archives/Video-Downloade/webui/static/app.js)
- [webui/templates/index.html](/Users/mac/qianzhu%20Vault/Archives/Video-Downloade/webui/templates/index.html)

#### 完成标准

- Web 若勾选知识库开关，任务真正会生成 `知识库.md`
- Web 若未勾选，不再暗示已经生成

#### 难度

- Phase 2A：`低`
- Phase 2B：`中`

## Workstream 3：doctor 从 configured 走向 configured + verified

这是文档对齐之后最值得补的一步。

### 目标

把现在“填了配置就算 OK”的检查，升级成两层：

- configured
- verified

### To Do

- 保留现有 configured 字段
- 新增 verified 字段，至少覆盖：
  - ffmpeg
  - yt-dlp
  - OpenRouter key 能否完成最小请求
  - cookies 文件是否存在
  - browser cookies 在当前环境是否可读取

- 对 Docker 环境下的 browser cookies 给出更明确提示：
  - 已配置但未验证
  - 容器里通常更推荐 `cookies.txt`

- `doctor` 输出中显式显示：
  - configured
  - verified
  - recommendation

### 涉及文件

- [webui/app.py](/Users/mac/qianzhu%20Vault/Archives/Video-Downloade/webui/app.py)
- [webui/cli.py](/Users/mac/qianzhu%20Vault/Archives/Video-Downloade/webui/cli.py)

### 难度

- 技术难度：`中`
- 价值：`高`

## Workstream 4：逐字稿.md 升级成真正的 Markdown 资产

这项很值得做，但优先级略低于“真相对齐”和“知识库开关”。

### 目标

让 `逐字稿.md` 不再只是清洗后的正文，而是可读、可引、可回溯的资产文件。

### To Do

- 重构 `render_markdown()`
- 顶部增加元信息
  - 标题
  - 作者
  - 平台
  - 原链接
  - 转写路线
  - 字幕语言 / ASR 模型
  - 生成时间

- 正文按段组织
  - 至少做轻量分段
  - 允许每段一个轻量时间锚点

- 保持职责边界
  - `原始逐字稿.txt`：不动
  - `逐字稿.md`：资产化
  - `解析稿.md`：二次整理
  - `知识库.md`：再上一层抽象
  - `转写信息.json`：机器可读

- 为 Markdown 渲染补测试

### 涉及文件

- [webui/transcript_pipeline.py](/Users/mac/qianzhu%20Vault/Archives/Video-Downloade/webui/transcript_pipeline.py)
- 相关测试文件

### 难度

- 技术难度：`中`
- 产品收益：`高`

## Workstream 5：chunked ASR

这是“抓不到字幕还能稳定出逐字稿”的关键能力，应该放在前两项之后尽快做。

### 目标

把现在“一整段音频一次性打给远端”的模式，升级为更稳的 fallback 链路。

建议目标链路：

- 平台字幕直提
- 自动字幕
- 音频切片 ASR
- 最后才考虑 OCR 硬字幕

### To Do

- 抽象转写后端
  - `TRANSCRIPTION_BACKEND=openrouter|faster-whisper|mlx-whisper`

- 实现音频切片
  - 先做固定时长切片：5 到 10 分钟
  - 后续可加 VAD 静音切片

- 每段独立转写
  - 每段记录 segment metadata
  - 单段失败可重试

- 合并转写结果
  - 去重
  - 保留段落顺序
  - 写入 metadata

- 在 metadata 中记录：
  - 是否分段
  - 分段数
  - 每段模型 / 后端
  - 是否存在截断重试

- 为长视频回归测试补样例

### 涉及文件

- [webui/openrouter_backends.py](/Users/mac/qianzhu%20Vault/Archives/Video-Downloade/webui/openrouter_backends.py)
- [webui/app.py](/Users/mac/qianzhu%20Vault/Archives/Video-Downloade/webui/app.py)
- 测试文件

### 难度

- 技术难度：`中到高`
- 价值：`极高`

## 推荐执行顺序

如果按最稳的节奏推进，建议是：

1. 修 README / docs / Web 文案
2. 先做 Web 知识库文案降级
3. 再决定是否补真正的 Web 知识库开关
4. 给 `doctor` 增加 configured / verified 分层
5. 升级 `逐字稿.md` 格式
6. 实现 chunked ASR

## 如果只做你说的“第 1 和第 2 件”

最推荐拆成这个顺序：

1. README 改真
2. Windows / Docker 认证建议改真
3. Web 设置文案改真
4. 加能力矩阵
5. 加迁移文档
6. Web 侧决定：
   - 先降级知识库文案
   - 或继续补真正的 Web 知识库开关

## 最后判断

你这轮 review 指出的不是零散 bug，而是一个很清晰的收尾路线：

- 先把“说法”和“现实”对齐
- 再把“Web”和“CLI”的能力对齐
- 最后把“抓不到字幕时的稳态能力”补上

这条路线很对，而且顺序也很重要。
