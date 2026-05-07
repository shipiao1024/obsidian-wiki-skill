# Obsidian Wiki 工作流参考

## 设计原则

知识库随意图生长。三层架构：

```
意图层   Value Point    — 表达"为什么关注"，不是"关注什么"
涌现层   Domain + Proposal — 领域从内容涌现，≥3 篇触发提案
物理层   Vault          — raw/ 不可变证据 + wiki/ AI 编译知识层
```

- **Value Point ≠ 领域标签**。标签说关注什么，Value Point 说为什么关注
- **领域从内容涌现**，不需要预先声明。compile 产出 domain，不匹配已有锚点时累积提案
- **入库是编译**，不是归档。每次入库产出立场影响、开放问题推进、跨域联想——不是"多了一篇"
- **脚本导航，LLM 判断**。预计算结构是导航线索，语义判断由 LLM 执行

### purpose.md 格式

每个 vault 根目录的 `purpose.md` 支持价值锚点声明：

```markdown
## 价值锚点

### 理解学习的底层机制
> 想搞清楚学习的真正约束是什么
关联领域: 认知科学, 学习方法论
- 刻意练习为什么有效？
```

旧格式（无 `## 价值锚点`）完全兼容，`parse_purpose_md()` 返回 `value_points: []`。

### Domain Proposal 流程

1. 入库时 compile 产出 domain
2. 不匹配已有 Value Point 或关注领域 → 累积到 `wiki/domain-proposals.json`
3. 同一 domain 累积 ≥3 个来源 → 入库影响报告显示"新领域提案"
4. 用户确认后 → 更新 purpose.md（添加 VP / 归入已有 VP / 归入排除范围）

### 跨 Vault 检索

查询时 `wiki_retrieve.py` 默认执行跨 Vault 补充检索：
1. 主 vault 正常检索
2. 检查 `cognitive_context.cross_domain_insights` 中的 target_domain
3. 如匹配其他 vault 的关注领域 → 从目标 vault 补充检索 top-3
4. 补充结果标记为 `cross_vault_supplementary`，权威性低于主 vault 结果

### Vault 拆分与迁移

当 vault 内容量 ≥50 sources 且领域内聚度高时，系统建议拆分。拆分是可选优化。拆分时 source 页物理复制，concept 页逻辑唯一。入库后如果 domain 更匹配其他 vault，影响报告显示路由建议，用户可运行 `reroute_vault.py` 迁移 source。

---

## 正式运行模式

当前系统对外只讲 4 种正式运行模式：

1. `fetch+heuristic`
- 适合快速入库、未配置 LLM、或批量初抓。
- 结果是：抓取后直接生成启发式 `brief/source`。

2. `fetch+prepare-only`
- 适合在当前 Codex / Claude 对话里完成语义编译。
- 结果是：先抓取并写入 `raw`，再生成 compile payload，由你产出 JSON，再回写正式页。
- 推荐使用 `--lean` 模式生成 payload，减少上下文占用 ~80%（移除你不需要的 `system_prompt`/`user_prompt`，过滤乱码 synthesis excerpt）。完整 payload 适合管道到外部 API。
- **当文档超过 800 行时自动切换为 chunked-prepare 模式**（见下方分块编译段落）。

3. `fetch+chunked-prepare`
- 适合长文档（书籍、PDF、ASR 转录）的分块深度精读。
- 流程：自动分块 → 逐块提取 → 跨块综合 → V2.0 compile JSON
- 手动指定：`--chunked --chunk-size 500`
- 精读版 claim 数量是粗读版的 9 倍，揭示先验知识无法覆盖的关键论点

4. `fetch+api-compile`
- 适合无人值守或批处理。
- 结果是：抓取后直接调用 OpenAI-compatible 接口生成结构化编译结果，再回写正式页。

推荐默认模式是 `fetch+prepare-only`。如果没有 LLM 配置或用户只要求快速入库，则退回 `fetch+heuristic`。

## 来源覆盖

当前系统已经不只是"微信公众号入口"，而是统一来源入口：

- 已接入默认 URL 主入口：
  - 微信公众号 URL
  - 通用网页 URL
  - YouTube URL
  - Bilibili URL
- 已接入同一默认脚本主入口：
  - 本地 Markdown
  - 本地文本
  - 本地 HTML
  - 本地 PDF
  - 纯文本粘贴

视频入口策略：

1. 先取平台字幕
2. 无字幕时回退到本地 ASR
3. 当前 ASR 使用 `faster-whisper`
4. 批量视频入口默认按小窗口串行执行，并带基础保护：
   - collection limit
   - 请求间隔
   - 失败退避
   - 随机抖动
   - 连续失败后暂停与冷却

## 来源质量标准

来源质量分两层：

1. **最低可接受验收** — 决定来源能否进入 `raw/articles` 和后续 ingest 主链，主要由 `status` 表达
2. **知识质量分级** — 只在 `status == ok` 时使用：`low` / `acceptable` / `high`

当前实现约定：

- `quality = low` 不会阻止来源进入 `raw/` 和基础 `source/brief` 流程
- 但它会把该来源同时暴露给 `review_queue.py` 的 `低质量来源候选` 和 `wiki_lint.py` 的 `low_quality_sources`
- 因此 `low` 更接近"允许入库，但默认需要复核"，而不是"静默接受为高信号来源"

### `web_url`

最低可接受验收：

- 成功产出 Markdown
- 能提取非空正文
- 能得到可用标题
- 正文不是明显的登录页、导航页、报错页或空壳页

建议失败状态：

- `dependency_missing`
- `browser_not_ready`
- `network_failed`
- `empty_result`
- `runtime_failed`

质量分级：

- `low`：只有标题和极短正文，或正文主要由导航、版权、广告、登录提示组成
- `acceptable`：标题正确，正文基本可读，但仍带少量模板噪声
- `high`：标题正确，正文主体清晰，噪声低，可直接进入 `brief/source` 编译

建议最低阈值：纯正文字符数至少 `>= 200`，标题不能是明显占位值

### `video_url`

最低可接受验收：

- 成功得到字幕或 ASR 文稿
- 文稿非空
- 能得到视频标题或稳定文件标题
- 文稿不是只有时间戳、序号或零散噪声

建议失败状态：`dependency_missing` / `network_failed` / `runtime_failed` / `empty_result`

质量分级：

- `low`：文稿极短，或大量残留时间戳、重复句、错字，标题仍是占位值
- `acceptable`：标题正确，文稿连续可读，允许保留少量口语噪声
- `high`：标题、作者、日期较完整，文稿连续、噪声低，可直接作为稳定知识来源

建议最低阈值：清洗后文本字符数至少 `>= 300`，时间戳行不能主导全文

视频文稿来源优先级固定为：`platform_subtitle` → `embedded_subtitle` → `asr`。Bilibili `danmaku.xml` 不再直接进入正文，只保留为弱参考资产。当前实现对 `transcript_source = asr` 额外施加保守策略：即使文本很长，默认最高只评到 `acceptable`。

## 批量视频保护机制

→ 详细保护参数和语义见 `references/video-rules.md`

### `local_file_pdf`

最低可接受验收：

- PDF 可成功提取文本
- 文本非空
- 文本不是仅页眉页脚、页码或目录残片
- 文件不是扫描件空壳

建议失败状态：`dependency_missing` / `invalid_input` / `runtime_failed` / `unsupported` / `empty_result`

质量分级：

- `low`：提取文本严重断裂，页眉页脚重复很多，主体结构难以阅读
- `acceptable`：主体文本连续可读，虽有格式损失，但可用于编译
- `high`：主体结构清楚，标题或章节基本可恢复，可直接作为稳定知识输入

建议最低阈值：提取文本字符数至少 `>= 300`，若正文几乎全是碎片、页码或重复页眉页脚，不应算 `ok`

## 五阶段流水线

无论走哪种模式，都应理解为同一条五阶段流水线：

1. `抓取 fetch` — 从匹配到的来源 adapter 拉取 markdown、字幕、音频或图片
2. `入库 ingest` — 写入 `raw/articles`、`raw/assets`，建立 slug，执行跳过或覆盖策略
3. `编译 compile` — 产出 heuristic 结果、prepare-only payload，或 API 编译结果
4. `应用 apply` — 写入 `brief/source`，刷新 taxonomy/synthesis，必要时发出 `delta-compile`
5. `审核 review` — 运行 lint、review queue、批准回写、图谱降噪和 working output 归档

这意味着现有脚本应该被看作同一条流水线的不同阶段，而不是多个平行的小工具。

### Layer 1: Raw

```text
raw/articles/<slug>.md
raw/assets/<slug>/*
raw/transcripts/<slug>--*.md
```

- 只保存原文和本地附件
- 不做人工主题分类
- 不在这里写总结、观点和推断
- 这是最终证据层
- 对于视频来源：
  - `raw/articles/<slug>.md` 是来源总页
  - `raw/transcripts/<slug>--subtitle|asr|calibrated.md` 是完整文稿页

### Layer 2: Wiki

```text
wiki/sources/<slug>.md
wiki/briefs/<slug>.md
wiki/concepts/*.md
wiki/entities/*.md
wiki/domains/*.md
wiki/syntheses/*.md
wiki/questions/*.md
wiki/stances/*.md
wiki/comparisons/*.md
wiki/outputs/*.md
wiki/claim-evolution.md
wiki/evolution.md
```

- `sources/`：保真来源页。记录来源信息、关键论点、已成熟概念/实体、候选概念/实体、与知识库的关系
- `briefs/`：快读页。有损压缩，服务快速了解，不追求覆盖所有细节
- `concepts/`：概念页（认知节点）。跨来源沉淀定义、当前判断、证据链、跨域联想、未解问题——每次入库演化
- `entities/`：实体页（认知节点）。与概念页同结构：类型 + 当前判断 + 证据链
- `domains/`：主题域页，用于控制多主题知识库的边界和导航
- `syntheses/`：跨来源综合分析页
- `questions/`：问题追踪页（open→partial→resolved→dropped）
- `stances/`：立场页（reinforce/contradict/extend/neutral）
- `comparisons/`：结构化对比页（A vs B），包含对比维度、双方优势、综合判断、相关来源
- `outputs/`：查询或专题任务生成的临时工作产物与待复核草稿，不是正式知识层
- 当前 ingest 会自动维护最小 `syntheses/` 页，但 `outputs/` 仍然留给 query 流程回写
- 对于安装到 Codex / Claude Code 的主工作流，推荐由你负责"阅读上下文并生成结构化编译结果"，脚本只负责准备上下文与回写文件

## 每篇文章的最低产物

每次 ingest 至少生成：

1. `raw/articles/<slug>.md`
2. `wiki/sources/<slug>.md`
3. `wiki/briefs/<slug>.md`
4. `wiki/index.md` 更新
5. `wiki/log.md` 追加记录

在当前实现里，还会自动生成第一版：

6. `wiki/concepts/*.md`
7. `wiki/entities/*.md`
8. `wiki/domains/*.md`
9. `wiki/syntheses/*.md`

---

## 分块编译模式

### 适用场景

当文档超过 800 行时，系统自动切换为 `chunked-prepare` 模式。适用于：
- PDF 书籍（通常 5000+ 行）
- 长知乎文章
- ASR 转录（1000-1500 行）

### 流程

```
Long Document → chunk_raw_document() → Per-chunk extraction (LLM) → Cross-chunk synthesis → V2.0 compile JSON
```

### 架构隔离

分块逻辑在后端（raw 文件层面）操作，与前端来源类型完全解耦。所有 7 种来源类型的长文档都已覆盖：
- 7 种前端 adapter 统一输出 `Article(text, title, ...)` → `raw/{slug}.md`
- `chunk_raw_document()` 操作 raw 文件，不受来源类型影响
- 唯一需要补充的是自动分块阈值判断（已实现：>800 行自动切换）

### 参数

- `--chunked`：手动指定分块模式
- `--chunk-size N`：每 chunk 最大行数（默认 500）

### 精读 vs 粗读效果

精读版 claim 数量是粗读版的 9 倍，且揭示 8+ 个先验知识无法覆盖的关键论点/案例。

---

## V2.0 Compile JSON 自动修正

apply 脚本在加载 V2.0 compile JSON 时自动修正常见 LLM 生成偏差：

| 常见错误 | 自动修正 |
|---------|---------|
| `schema_version` 在 `metadata` 内 | 移到 JSON 顶层 |
| `key_points` 在 `skeleton` 内 | 移到 `brief` 内 |
| `source` 在 `brief` 内 | 移到 `document_outputs` 内 |
| `claim_inventory` 在 `document_outputs` 内 | 提升到 `result` 顶层 |
| `evidence_type` 自定义值 | 映射到 6 个合法枚举 |
| `stance_impacts.impact` 描述文字 | 映射到 4 个合法枚举 |
| `open_questions` 对象 | 提取 `.question`/`.text` 转为字符串 |
| `skeleton` 为纯字符串 | 包装为 `{generators, diagram}` 结构 |

每次修正写入 stderr，格式 `[auto-correct] Moved schema_version to top level` 等。

当 v2 compile 返回 `comparisons` 时，还会自动创建：

10. `wiki/comparisons/*.md` — 结构化对比页（A vs B），由 `ensure_comparison_page()` 自动生成。

### v2 compile 产出字段

v2 compile 完整产出包含以下字段：

| 字段 | 说明 |
|------|------|
| `compile_target` | 编译目标元信息（vault、raw_path、slug、title、author、date） |
| `document_outputs` | brief（one_sentence、key_points）+ source（core_summary、contradictions、reinforcements） |
| `knowledge_proposals` | domains / concepts / entities 各带 action（link_existing、create_candidate、no_page 等）和 confidence（内部字段，不在入库输出中展示） |
| `update_proposals` | 对已有页面的更新建议 |
| `claim_inventory` | 核心论断清单，含 claim_type、confidence、verification_needed |
| `open_questions` | 内容衍生的可追踪问题（LLM 编译优先使用，启发式回退到 `extract_content_questions`） |
| `cross_domain_insights` | 跨域类比推理（仅 LLM 编译路径可产出） |
| `stance_impacts` | 对已有立场页的影响（reinforce、contradict、extend） |
| `review_hints` | 复核优先级和建议 |

`cross_domain_insights` 每条包含：

- `mapped_concept`：新内容中的概念名
- `target_domain`：知识库中最可能产生联想的现有领域名
- `bridge_logic`：一句话类比/同构逻辑——为什么这个跨域联想有价值
- `migration_conclusion`：从源域推断目标域的可行动判断（必填，无此字段则跨域联想不展示）
- `potential_question`：从跨域关联生成的可追踪问题
- `confidence`：high / medium / low（内部字段，不在入库输出中展示）

同构类型：
- **方法论迁移**：A 领域的方法可适用于 B 领域
- **因果结构类比**：A 和 B 有相似的因果链
- **抽象模式共享**：A 和 B 有相同的表示/组织结构

启发式模式无法产出 `cross_domain_insights`（`compile_quality: "raw-extract"`），impact 报告会提示"使用 prepare-only 可获得跨域联想分析"。

### 入库影响报告

每次入库完成后，系统通过 `pipeline/ingest_report.py` 生成影响报告，包含：

1. **快速了解入口**：brief 页链接
2. **内容要点**：优先使用 LLM `knowledge_proposals.concepts`（排除 `action=no_page`），启发式回退到 `extract_content_topics`
3. **深度探索问题**：优先使用 LLM `open_questions`，启发式回退到 `extract_content_questions`
4. **跨域联想**：当 `cross_domain_insights` 非空时，展示概念→领域映射和 bridge_logic；领域不匹配时建议创建新领域或作为跨域参考保留
5. **编译质量状态**：启发式 = raw-extract（非结构化），LLM = structured
6. **自动创建的开放问题**：wiki/questions/ 中由本来源触发的问题
7. **立场影响**：wiki/stances/ 中受本来源影响的立场
8. **已有相关来源数量**
9. **知识图谱更新**
10. **新领域提案**（V2.1）：proposable_domains 非空时展示
11. **路由建议**（V2.1）：domain 更匹配其他 vault 时展示

影响报告的目的不是"写入完成"，而是让用户看到知识库变化和可探索方向。

注意：`concepts/` 和 `entities/` 不再按"提到一次就建页"的方式生成。当前实现要求同一概念/实体在多个 `source` 中稳定出现，才升级为正式节点；否则只保留在 `source` 页的候选区，避免污染图谱。

## 图谱分层约定

- 主知识图谱只应关注 `domains/`、`syntheses/`、已成熟 `concepts/`、已成熟 `entities/`
- `raw/articles/`、`sources/`、`briefs/` 属于文档层，不应作为主图谱核心
- `index.md`、`log.md` 属于系统层
- `outputs/` 属于工作层，只用于对话沉淀、待复核草稿和临时问答
- 当前脚本会在 frontmatter 中写入 `graph_role` 与 `graph_include`，用于把系统页、文档页、工作页从主图谱里降噪

Obsidian 使用提示：

- Obsidian 原生全局图不会自动隐藏这些页面；`graph_role` / `graph_include` 的作用是给你稳定的筛选依据
- 平时不要直接看"无筛选的全局图"，而是从 `domains/` 或 `syntheses/` 页面打开局部图谱
- 如果想在 Obsidian 里获得一个"写死知识层范围"的主图谱页面：

```powershell
python Claude-obsidian-wiki-skill\scripts\export_main_graph.py `
  --vault "D:\Obsidian\MyVault"
```

运行后打开 `wiki/graph-view.md`：
  - 页面内的 Mermaid 图只包含 `concepts/entities/domains/syntheses`
  - 页面顶部还会写出一份适合复制到 Obsidian 图谱搜索框的过滤规则

如果要看全局图，优先按路径筛选，只保留：
  - `path:"wiki/domains"` / `path:"wiki/syntheses"` / `path:"wiki/concepts"` / `path:"wiki/entities"`
同时排除：
  - `path:"wiki/outputs"` / `path:"wiki/briefs"` / `path:"wiki/sources"` / `path:"raw/articles"`

如果某些 `concept/domain/synthesis` 已经存在，但信息密度仍然太低，可以用 `graph_trim.py` 先把它们降出主图谱，而不是立刻删除文件。

推荐固化默认图谱策略：

- `raw/articles`、`sources`、`briefs`、`outputs`、`index`、`log` 永远不进主图谱
- `concepts/entities` 只有在"至少两篇来源稳定引用 + 页面已不再是占位定义"时，才进入主图谱
- `domains/syntheses` 只有在至少两篇来源支撑时，才进入主图谱
- 对于结构上成立、但视觉上仍然太吵的页面，再用 `graph_trim.py --demote-*` 做人工收缩

## 快读页建议结构

快读页（brief）的内部结构由 compile schema 定义（skeleton.generators、key_points、data_points 等）。入库完成后向用户展示的格式见 `ingest-quickstart.md` 的"入库完成必选输出"模板——直接引用骨架和关键判断原文，不拆子维度，不展示置信度分布。

## Source 页建议结构

```markdown
# 标题

## 来源信息
## 核心摘要
## 候选概念
## 候选实体
## 与现有知识库的关系
```

## 页面状态生命周期

所有 wiki 页面携带 `status` frontmatter 字段，表示知识成熟度：

| Status | 含义 | 自动升级触发条件 |
|--------|------|-----------------|
| `candidate` | 低置信判断，需人工审核或多来源确认 | `needs_human_review=True` 或 `confidence=low` 且无 high 主张 |
| `seed` | 初始草稿，单来源占位 | 默认值（official 页），或 candidate 被 2+ 来源确认后升级 |
| `developing` | 多来源开始引用，正在形成稳定认知 | `page_mention_count >= 1` |
| `mature` | 稳定、定义清晰、多来源支撑 | `page_mention_count >= 3` |
| `evergreen` | 持续维护、始终相关 | `page_mention_count >= 6` |

- 状态升级在每次 ingest 时自动触发（`check_and_upgrade_status()`）
- 状态不会自动降级
- 过渡期兼容：`"draft"` 等同 `"seed"`
- 查询时 `mature`/`evergreen` 页面排名权重更高（score +2/+1）
- `wiki_lint.py` 检查 `status_mismatch`：状态与引用数不一致时报告

### 页面生命周期（lifecycle）

所有 wiki 页面携带 `lifecycle` frontmatter 字段，控制页面可见度和审核状态：

| Lifecycle | 含义 | 适用页面类型 |
|-----------|------|-------------|
| `official` | 正式知识页面，进入主导航 | 所有通过置信度门控的 brief/source/concept/entity |
| `candidate` | 待审核页面，不进入主导航 | 低置信来源页及其关联 concept/entity |
| `temporary` | 临时工作产物 | query output |
| `review-needed` | 待复核草稿 | delta-compile output |
| `absorbed` | 已吸收为正式知识 | 被 apply_approved_delta 处理后的 output |
| `archived` | 已归档，不再活跃 | 被 archive_outputs 处理后的 output |

- `candidate` → `official` 的升级条件：2+ 来源含 high 置信主张提及该概念/实体时，`check_and_upgrade_status()` 自动升级
- candidate 页面顶部显示 `[!warning] 候选页待审` callout，提醒引用时标注置信度
- candidate 页面的主张分为 `## 关键判断`（high/medium）和 `## 待验证判断`（low），隔离低置信内容
- `review_queue.py` 专门列出候选页待审、可升级候选页和低置信判断

### 置信度传播机制

v2 compile 产出 `claim_inventory`，每条主张含 `claim_type`、`confidence`（high/medium/low）、`verification_needed`。置信度数据在管线中传播（内部机制，不在入库完成输出中展示）：

1. **apply 层穿透**：`claim_inventory` 从 compiled JSON 传递到 page builder，不再在 `to_legacy_compile_shape()` 中丢弃
2. **brief/source 渲染**：`## 关键判断` 段以 `[type|confidence] claim` 格式渲染，frontmatter 增加 `claim_confidence_high/medium/low` 计数
3. **lifecycle 门控**：`review_hints.needs_human_review=True` 或 `confidence=low` 且无 high 主张 → `lifecycle: "candidate"`；否则 `lifecycle: "official"`
4. **synthesis 投影**：`refresh_synthesis.py` 从 source 页的 `## 关键判断` 段提取主张，按置信度加权评分（high=6, medium=3, low=1），生成综合页的"当前结论"和"核心判断"。无主张时 fallback 到 raw 句子评分
5. **演化追踪**：`claim_evolution.py` 用关键词重叠匹配跨来源主张，分类为 reinforce/contradict/extend。矛盾主张进入 `review_queue.py` 的 `## 矛盾主张` 段
6. **路径分层**：candidate 页低置信主张隔离到 `## 待验证判断`；official 页所有主张在同一段。concept/entity 页从来源页继承 candidate lifecycle

### autoresearch 模式

- 适合围绕一个主题做多轮自主搜索和入库
- 流程：
  1. 读 wiki/hot.md 和 wiki/index.md 确定已有覆盖
  2. Round 1: WebSearch(broad) -> top 3 URLs -> WebFetch -> wiki_ingest.py
  3. Round 2: WebSearch(deeper angles) -> top 2 URLs -> WebFetch -> wiki_ingest.py
  4. Round 3: WebSearch(specific evidence) -> top 1 URL -> WebFetch -> wiki_ingest.py
- 每轮搜索后检查已有覆盖，避免重复入库
- 所有入库走标准 ingest pipeline（fetch -> ingest -> compile -> apply -> review）

### save 模式

适合把对话中的有价值讨论保存为正式 wiki 页面。5 种保存类型：

| 类型 | 写入路径 | 适用场景 |
|------|---------|---------|
| synthesis | wiki/syntheses/ | 跨来源综合讨论 |
| concept | wiki/concepts/ | 新概念定义 |
| source | wiki/sources/ (via apply_compiled_brief_source.py) | 来源讨论 |
| decision | wiki/stances/ | 决策或判断 |
| session | wiki/outputs/ | 会话摘要 |

所有写入走标准 apply 路径，使用 apply_compiled_brief_source.py 回写。

## 什么时候更新 Concepts / Entities / Domains

- 当一个概念在两篇以上文章里反复出现，给它独立页面；单次提及只保留为候选概念
- 当一个人物、公司、产品在后续文章会持续出现，给它独立页面；单次提及只保留为候选实体
- 当知识库出现明显的主题团簇，为它们建立 `domains/` 页面
- 当多个来源之间存在明显对比、冲突或综合价值，建立 `syntheses/` 页面

当前脚本会先用启发式规则自动建第一页，后续由 query/lint/人工复核把草稿推高质量。

## Codex / Claude 主入口

推荐交互式主流程：

1. `wiki_ingest.py` 抓取并写入 `raw`
2. `llm_compile_ingest.py --prepare-only --lean` 输出精简编译上下文（推荐；不加 `--lean` 则输出完整 payload，适合管道到外部 API）
3. 当前 Codex / Claude 会话基于该上下文生成 JSON
4. `apply_compiled_brief_source.py` 把 JSON 回写为正式 `brief/source`

第 3 步生成的 JSON，建议直接遵循 `system_prompt`、`user_prompt`、`expected_output_schema` 三个字段。使用 `--lean` 时这三个字段被移除，你只需读取 `context` 部分。首次调试时，可以先参照 `references/examples/agent_interactive_compiled_result.json`。

在 Windows PowerShell 下，如果要把 `--prepare-only` 输出落成文件，建议使用 `Out-File -Encoding utf8`，避免后续读取 payload 时出现编码问题。

- skill 的入口仍然是 Codex / Claude 交互界面
- Python 脚本只做辅助，不抢走你的 LLM 角色
- 外部 API 只作为后备路径
- `wiki_ingest.py` 是默认脚本入口，但不是默认用户入口

## Query 与 Lint 约定

- Query 时先读 `wiki/index.md`，再读命中的 brief/source/concept 页面
- 如果问题涉及原文措辞、精确数字、时间线、作者真实立场，必须回到 `raw/articles/`
- 高质量回答应写回 `wiki/outputs/` 或 `wiki/syntheses/`
- 运行 `wiki_lint.py` 做最基本的健康检查
- 如果要做多来源端到端回归，不要临时拼样本，直接按 `references/acceptance-samples.md` 维护固定样本集
- 正式样本名单建议单独维护在 `references/acceptance-baseline.md`
- 当前实现里，`wiki_query.py` 会默认把查询结果写回 `wiki/outputs/`，并追加到 `wiki/log.md`
- `wiki_query.py` 会排除已有 `outputs/` 页面作为检索候选，避免知识库自我回声
- `wiki/outputs/` 不要求逐篇人工复核。只有高频重复问题、`delta_compile.py` 生成的 `review-needed` 草稿、或你明确指定要沉淀的回答，才值得进入人工确认队列
- 正式回归时，运行 `apply_approved_delta.py`，把已批准的 `outputs/*.md` 吸收到 `source/brief/synthesis`，并把该 output 标记为 `absorbed`
- `absorbed` output 仍保留作审计记录，但会从 `index.md` 的日常输出区隐藏
- `wiki_size_report.py` 用来判断当前库是否还适合只靠 `index.md` + 定向读页
- `stale_report.py` 用来判断哪些页已经进入"应该重新编译或合并"的状态
- `delta_compile.py` 用来把这些待维护信号转换成可复核的重编译草稿
- `refresh_synthesis.py` 用来把现有 `syntheses/` 从"最小汇总页"刷新成更像真正综合页的结构
- Lint 时优先检查：
  - source 页存在但 brief 页缺失
  - concepts/entities 未被链接
  - orphan pages
  - 新来源推翻旧结论但未更新 domain/synthesis

## 什么时候升级检索层

- 当 `wiki_size_report.py` 仍是 `GREEN`，继续坚持 `index-first`
- 当它进入 `YELLOW`，开始准备本地搜索兜底
- 当它进入 `RED`，说明单靠 `index.md` 已经不够，应该引入更强的候选筛选

## 什么时候触发重新编译

- 当 `stale_report.py` 报出高频重复 query → 适合沉淀成更正式的 `syntheses/` 或重写 `source/brief`
- 当它报出高频重复 ingest → 该来源或相关 taxonomy 页正在被频繁调试，适合做一次集中清理
- 当它报出"placeholder + 多来源" → 这页已经不适合继续停留在草稿状态
- 此时可以直接运行 `delta_compile.py` 生成待复核草稿，而不是手动从头重写
- 如果想先把主题域的综合层抬高，再让 query 依赖它，应先运行 `refresh_synthesis.py`

## 批准回写流程

- 普通 `wiki_query.py` 结果默认是 `lifecycle: temporary`
- `delta_compile.py` 生成的草稿默认是 `lifecycle: review-needed`
- 你确认某个 output 值得沉淀后，执行：

```powershell
python Claude-obsidian-wiki-skill\scripts\apply_approved_delta.py "outputs/<slug>"
```

- `delta-source` 会自动回写到对应的 `sources/<slug>` 和 `briefs/<slug>`
- `delta-query` 或普通 `output` 会优先吸收到证据里已经引用的 `syntheses/*`；如果自动找不到目标，可显式指定：

```powershell
python Claude-obsidian-wiki-skill\scripts\apply_approved_delta.py "outputs/<slug>" --target "syntheses/自动驾驶--综合分析"
```

- 回写后，原 output 会被标记为 `status: accepted` + `lifecycle: absorbed`
- 同时会在 `wiki/log.md` 追加 `apply_delta` 记录

## 审核队列

运行 `review_queue.py --write` 会生成 `wiki/review_queue.md`，页面结构包含以下段：

- `冲突候选`：`wiki_lint.py` 检测到的矛盾主张对应的 output
- `低质量来源候选`：`quality: low` 的 source 页
- `待处理`：`lifecycle: review-needed` 或 `temporary` 的 output
- `重复候选`：同标题的重复 output
- `已吸收统计`：absorbed/archived/pending 数量
- `候选页待审`：`lifecycle: candidate` 的 brief/source 页
- `低置信判断`：confidence=low 的主张（从 sources/briefs 的 `## 关键判断` 段提取）
- `可升级候选页`：满足 2+ 来源确认阈值的 candidate concept/entity 页
- `矛盾主张`：`claim_evolution.py` 检测到的跨来源矛盾主张对

`absorbed` 历史草稿不再混进待处理清单，只保留数量统计和审计痕迹。对于同标题的重复测试草稿，可运行 `archive_outputs.py --apply`，只保留最新未吸收的一份，其余标记为 `archived`。
