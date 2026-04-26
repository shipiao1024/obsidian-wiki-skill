# 视频合集/频道批量导入设计

## 背景

当前系统已经支持：

- 单个 YouTube 视频 URL
- 单个 Bilibili 视频 URL

视频入口的处理方式是：

1. 先用 `yt-dlp` 获取字幕
2. 无字幕时回退到本地 ASR
3. 把单视频 transcript 编译为统一 `AdapterResult`
4. 再复用现有 `AdapterResult -> Article -> ingest` 主链

但当前还不支持：

- YouTube playlist 的连续导入
- YouTube channel videos 页的连续导入
- Bilibili 合集/系列的连续导入
- 带断点续跑、去重、分批执行的“批量视频导入任务”

因此需要新增一层“集合展开 + import job 状态管理”，而不是重写现有单视频 ingest。

## 目标

本设计只解决：

1. 支持视频合集/频道 URL 作为入口
2. 单次最多处理 20 条
3. 支持断点续跑
4. 不重复下载已完成项
5. 继续复用现有单视频主链

## 非目标

第一版明确不做：

- YouTube channel 全站无限翻页抓全
- Bilibili UP 主空间全部历史作品抓全
- 多任务并发调度
- 自动定时续跑
- “按时间窗口”或“最近 N 条”以外的复杂策略
- 对批量任务本身做 LLM 语义总结

## 来源范围

第一版新增两类来源：

1. `video_playlist_youtube`
- `https://www.youtube.com/playlist?list=...`
- `https://www.youtube.com/@name/videos`
- `https://www.youtube.com/channel/<id>/videos`
- `https://www.youtube.com/c/<name>/videos`

说明：
- playlist 是“明确播放列表”
- channel videos 页在第一版也归到“可展开集合”，但仍然受单次 20 条限制

2. `video_playlist_bilibili`
- `https://space.bilibili.com/<uid>/channel/seriesdetail?sid=...`
- `https://space.bilibili.com/<uid>/channel/collectiondetail?sid=...`
- `https://www.bilibili.com/list/...`

说明：
- 第一版只支持“合集/系列/list”这类已经结构化的集合页
- 不直接支持整个 UP 主空间首页的无限抓全

## 总体方案

核心原则只有一条：

**集合入口只负责展开，不直接生成知识页；知识页仍由现有单视频 ingest 主链负责。**

整体流程如下：

1. 用户输入 playlist / channel / 合集 URL
2. 来源注册表识别为集合类来源
3. 用 `yt-dlp --flat-playlist --dump-single-json` 展开出视频子项
4. 把子项标准化为：
   - `video_id`
   - `video_url`
5. 读取或创建对应的 `wiki/import-jobs/*.md`
6. 过滤：
   - 已在 job 中完成的项
   - 当前列表中的重复项
   - 已存在 `raw/source/brief` 的项
7. 本轮最多取前 20 条
8. 对每个视频 URL 继续调用现有单视频 adapter + ingest 主链
9. 回写 job 状态文件

## 新增目录

新增：

```text
wiki/import-jobs/
```

用途：

- 保存批量视频导入任务状态
- 与 `outputs/`、`sources/`、`briefs/` 隔离
- 提供可审计、可断点续跑的工作层状态

这类页面不属于知识层，应标记：

- `graph_role: "working"`
- `graph_include: "false"`

## Import Job 文件格式

每个集合任务对应一个 job 文件，例如：

- `wiki/import-jobs/youtube-channel-<slug>.md`
- `wiki/import-jobs/bilibili-space-<slug>.md`

建议 frontmatter：

```yaml
---
title: "YouTube 频道批量导入"
type: "import-job"
source_kind: "video_playlist_youtube"
source_url: "https://www.youtube.com/@example/videos"
status: "active"
max_items_per_run: 20
discovered_count: 0
completed_count: 0
remaining_count: 0
last_run_at: ""
graph_role: "working"
graph_include: "false"
lifecycle: "working"
---
```

正文结构：

```md
# YouTube 频道批量导入

## 任务概览

- 来源：...
- 单次上限：100
- 当前状态：active

## 已完成视频

- `abc123` | [[sources/example-video]]
- `def456` | [[sources/another-video]]

## 待处理视频

- `ghi789` | https://www.youtube.com/watch?v=ghi789
- `BV1xx...` | https://www.bilibili.com/video/BV1xx...

## 最近一次结果

- 2026-04-24 16:20 | processed=37 | skipped=12 | failed=1
```

## 唯一 ID 规则

### YouTube

- 直接使用视频 `id`
- 标准单视频 URL：
  - `https://www.youtube.com/watch?v=<id>`

### Bilibili

- 优先使用 `BV...`
- 如果 `entries` 里只有 URL，就从 URL 中提取 `BV`
- 第一版不使用标题作为主键

## 去重规则

每次执行按以下顺序去重：

1. 已在 job `已完成视频` 中的 ID，跳过
2. 当前展开列表中重复的 ID，去重
3. 已存在 `raw/source/brief` 的视频，跳过
4. 剩余项截断到最多 20 条

这样可以保证：

- 单次任务可控
- 可分次跑完
- 不重复下载
- 与现有三页跳过逻辑一致

## 状态模型

job 状态建议使用：

- `active`
  - 还有待处理项
- `completed`
  - 已无剩余项
- `failed`
  - 展开失败，或本轮全部执行失败
- `paused`
  - 第一版保留字段，不强依赖

## 代码边界

### 1. `source_registry.py`

新增来源类型：

- `video_playlist_youtube`
- `video_playlist_bilibili`

这两个类型只代表“集合入口”，不代表最终单视频处理。

### 2. `source_adapters.py`

新增集合展开能力，例如：

- `expand_video_collection_items()`
- `normalize_collection_entry_url()`
- `collection_entry_id()`

这层只做：

- 调 `yt-dlp --flat-playlist --dump-single-json`
- 返回结构化子项

不做：

- vault 写入
- source/brief 生成
- job 状态落盘

### 3. `import_jobs.py`

新增单独模块负责：

- job 文件路径计算
- job frontmatter 读写
- 已完成/待处理项解析
- 最近一次结果回写

### 4. `wiki_ingest_wechat.py`

新增集合处理主控，例如：

- `process_video_collection(...)`

职责：

1. 识别集合 URL
2. 调集合展开器
3. 读取/创建 job
4. 过滤已完成/已存在项
5. 单次最多处理 20 条
6. 逐条复用现有单视频 ingest
7. 回写 job

## 与现有主链的关系

第一版不引入第二套视频 ingest。

复用方式如下：

`collection URL -> expand items -> single video URL list -> existing video adapter -> existing ingest_article()`

这样能最大化复用：

- 单视频字幕/ASR 逻辑
- `quality`
- `review_queue`
- `wiki_lint`
- 三页跳过逻辑

## 失败与保护策略

### 集合展开失败

应返回明确错误，而不是静默跳过：

- `dependency_missing`
- `network_failed`
- `runtime_failed`

### 单个视频失败

第一版建议：

- 记录到 job 的“最近一次结果”
- 不中断整个批次
- 本轮继续处理后续视频

### 单次上限

第一版固定：

- `max_items_per_run = 100`

即使是频道页，也不允许单次无限拉完。

## 测试要求

至少覆盖：

1. 来源识别：
- playlist/channel/list URL 能命中新来源类型

2. 集合展开：
- 能从 `yt-dlp` 返回的 `entries` 生成标准化子项

3. 去重：
- 同一个 `video_id` 不重复处理

4. 主入口行为：
- playlist/channel 输入会展开成多个单视频 URL
- 单次最多处理 20 条

5. 断点续跑：
- 已完成视频不会重复下载

## 风险与权衡

### 风险

- Bilibili 集合页结构波动较大
- YouTube channel videos 页可能带来分页和体量膨胀
- 没有限制时会导致 vault 爆炸式增长

### 当前权衡

因此第一版只接受：

- 结构化集合页
- 单次最多 20 条
- 依赖 job 状态页做分次完成

这个边界是刻意保守的。

## 推荐结论

推荐先实现：

1. playlist / 合集 / channel videos 页入口
2. `wiki/import-jobs/` 状态目录
3. 单次上限 100
4. 已完成项去重

不建议第一版直接实现：

- UP 主全部历史作品无限抓全
- 无上限分页
- 自动任务调度

这样能先把“系列连续下载”做稳，再决定是否继续扩展到真正的“UP 主全量抓取”。
