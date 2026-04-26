# 多来源回归样本集

## 目的

这份样本集不是功能说明，而是每次修改入口、adapter、ingest、review、lint 后都可以重跑的一组固定验收样本。

目标只有 3 个：

- 验证主入口是否还能处理当前正式支持的来源
- 验证 `status / quality / review / lint` 这条链是否还通
- 验证真实环境依赖问题不会被误判成代码回归

## 样本集原则

样本集分成两层：

1. `golden samples`
- 长期固定
- 用于回归
- 尽量选择公开、稳定、低版权风险、低登录依赖的来源

2. `diagnostic samples`
- 临时补充
- 用于排查某个特定 bug 或来源异常
- 不纳入正式回归基线

建议优先维护 `golden samples`，数量不要太多。当前阶段推荐总量控制在 10 到 12 个。

## 建议覆盖矩阵

### 1. 微信 URL

至少保留 2 篇：

- 1 篇图片较少、结构稳定的公众号文章
- 1 篇图片较多、标题较长的公众号文章

最低验证点：

- `raw/articles/*.md` 生成成功
- `wiki/sources/*.md` 与 `wiki/briefs/*.md` 生成成功
- `index.md` 与 `log.md` 更新成功
- `compile_mode` 与 `compile_reason` 可解释

### 2. 通用网页 URL

至少保留 2 个：

- 1 个静态公开页面
- 1 个正文较长的技术文章或博客页

推荐基线样本：

- `https://example.com`
- 另选一个长期可公开访问的技术文档页

最低验证点：

- `run_web_adapter()` 成功或明确失败分类
- 标题不是占位值
- `quality` 正常出现
- 如果环境有浏览器/CDP 问题，应明确落到：
  - `browser_not_ready`
  - `network_failed`
  - `runtime_failed`

### 3. 视频 URL

至少保留 2 个：

- 1 个字幕稳定的 YouTube 视频
- 1 个 Bilibili 视频

最低验证点：

- 能得到 transcript
- 标题来自真实 metadata，而不是 `video`
- `quality` 正常出现
- 无字幕样本应能验证：
  - ASR fallback
  - 或明确的依赖缺失状态

### 4. 本地文件

至少保留 3 个：

- `sample.md`
- `sample.txt`
- `sample.pdf`

建议额外准备：

- 1 个低质量 PDF 样本
  - 文本很短
  - 或结构明显破碎
  - 用来验证 `quality = low`

最低验证点：

- 主入口可直接 ingest
- `AdapterResult -> Article -> ingest` 整条链可用
- PDF 可区分：
  - `ok`
  - `unsupported`
  - `dependency_missing`

### 5. 纯文本

至少保留 1 个：

- 1 段 300 到 800 字的纯文本

最低验证点：

- `--text` 能进入同一主入口
- 能生成 `raw/source/brief`
- 不依赖 URL 路由和外部 adapter

## 推荐最小基线

当前阶段建议先固定这 8 个：

1. 微信文章 A
2. 微信文章 B
3. 网页 A：`https://example.com`
4. 网页 B：一篇公开技术文章
5. YouTube 视频 A
6. Bilibili 视频 A
7. 本地 Markdown A
8. 本地 PDF A

如果想把 `quality=low` 也纳入正式验收，再加这 2 个：

9. 低质量 PDF
10. 低质量网页或低质量纯文本样本

## 每轮回归建议顺序

建议分三段跑，不要一口气混在一起。

### 第一段：快速健康检查

目标：先看入口有没有明显断。

推荐顺序：

1. 本地 Markdown
2. `--text`
3. `https://example.com`

如果这三项都失败，不必继续跑视频和微信。

### 第二段：真实来源检查

目标：验证外部 adapter 与主入口联动。

推荐顺序：

1. 微信 URL
2. 网页 URL
3. YouTube URL
4. Bilibili URL

### 第三段：质量链检查

目标：验证 `quality -> review/lint`。

推荐顺序：

1. 导入 1 个高质量来源
2. 导入 1 个低质量来源
3. 运行：

```powershell
python Claude-obsidian-wiki-skill\scripts\review_queue.py --write
python Claude-obsidian-wiki-skill\scripts\wiki_lint.py --vault "D:\Obsidian\MyVault"
```

验收点：

- `review_queue.md` 出现 `低质量来源候选`
- `wiki_lint.py` 输出 `low_quality_sources`

## 每类来源的最低验收口径

### 成功

至少满足：

- 主入口没有异常退出
- `status == ok` 或进入既定 fallback
- `raw/source/brief` 产物齐
- `index/log` 正常更新

### 部分成功

允许存在：

- `compile_mode = heuristic`
- `quality = low`
- 视频走了字幕或 ASR fallback

但必须满足：

- 错误或降级是可解释的
- 不得静默失败

### 失败

以下情况算失败：

- 主入口吞错
- `status` 不可解释
- 产物缺失但日志不提示
- 标题退化成明显占位值且没有被发现

## 建议记录格式

每次回归建议至少记录：

- 日期
- Git 提交或工作区版本
- 样本名称
- 来源类型
- 最终 `status`
- 最终 `quality`
- `compile_mode`
- 备注

建议用一个简单表格维护，例如：

```text
2026-04-24 | web-A | web_url | ok | acceptable | heuristic | Example Domain 正常
2026-04-24 | pdf-low | local_file_pdf | ok | low | heuristic | 已进入 review/lint
2026-04-24 | video-A | video_url_youtube | ok | acceptable | heuristic | 字幕成功
```

## 当前最值得优先固定的正式回归样本

先固定下面这组，足够支撑日常回归：

- 2 个微信 URL
- 1 个静态网页 URL
- 1 个技术文章 URL
- 1 个 YouTube 视频
- 1 个 Bilibili 视频
- 1 个本地 Markdown
- 1 个本地 PDF
- 1 个低质量 PDF
- 1 个纯文本

等这组稳定后，再考虑继续扩样本，而不是先扩来源类型。

