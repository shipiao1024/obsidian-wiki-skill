# Obsidian Wiki Skill — 产品与技术规格

> **文档位置**：本文件位于 `docs/SPEC.md`，是面向用户的完整规格文档，不参与 skill 运行时加载。

## 1. 产品定位

Obsidian Wiki Skill 是一个本地知识库管理工具，把外部资料（文章、视频、网页）编译进 Obsidian vault，形成可检索、可关联、可演化的结构化知识层。

核心价值：不是替代 Obsidian，而是在 Obsidian 上叠加一层 AI 编译结果——降低阅读长文成本、显式化跨文档关联、让后续查询和维护只需先看 `wiki/index.md`。

## 2. 系统架构

### 2.1 三层知识模型

```
raw/              ← 不可变原始层（最终证据）
  inbox/          ← 待处理输入暂存
  articles/       ← 完整原文
  transcripts/    ← 视频文稿
  assets/         ← 图片、附件

wiki/             ← AI 编译知识层（可演化）
  briefs/         ← 一句话结论 + 核心要点（有损摘要）
  sources/        ← 核心摘要 + 关联 + 声明（蒸馏版）
  concepts/       ← 概念页（跨来源聚合）
  entities/       ← 实体页
  domains/        ← 域页（主题领域）
  syntheses/      ← 综合分析页（跨来源综合）
  questions/      ← 问题追踪页（open→partial→resolved→dropped）
  stances/        ← 立场页（reinforce/contradict/extend）
  comparisons/    ← 结构化对比页（A vs B）
  outputs/        ← 查询结果 + delta 提案
```

**保真度排序**：`raw/articles/` > `wiki/sources/` > `wiki/briefs/`

查询规则：数字/定义/原文引用/作者立场 → 必须回看 `raw/`；一般理解 → 可看 `sources/`；快速判断 → 看 `briefs/`。

### 2.2 五阶段流水线

```
URL/文件/文本 → [1. Fetch] → [2. Ingest(raw)] → [3. Compile] → [4. Apply(wiki)] → [5. Review]
```

| 阶段 | 输入 | 输出 | 核心模块 |
|------|------|------|---------|
| Fetch | URL/文件/文本 | AdapterResult（markdown_body + metadata + assets） | `adapters/` |
| Ingest | AdapterResult | `raw/articles/` + `raw/transcripts/` + `raw/assets/` | `pipeline/ingest.py` |
| Compile | raw 页面 | 结构化 JSON（brief/source/proposals/claims/questions/stances） | `llm_compile_ingest.py` 或启发式 |
| Apply | 编译结果 | `wiki/briefs/` + `wiki/sources/` + taxonomy + synthesis + questions + stances | `pipeline/ingest_orchestrator.py` + `pipeline/page_builders.py` + `pipeline/taxonomy.py` |
| Review | vault 状态 | lint 报告、review queue、blind spots、evolution | `wiki_lint.py` + review 脚本 |

### 2.3 两类执行入口

| 入口 | 执行者 | 编译来源 | 适用场景 | 需要的配置 |
|------|--------|---------|---------|-----------|
| **Claude Code 交互式** | Claude Code（本身是 LLM） | Claude Code 生成结构化 JSON → `apply_compiled_brief_source.py` 回写 | 日常使用、人可审核干预 | 仅需 vault 路径 |
| **脚本直连 API** | Python 脚本调 OpenAI 兼容接口 | `llm_compile_ingest.py` 自动调 API | 批量无人值守、定时任务、CI | `KWIKI_API_KEY` + `KWIKI_COMPILE_MODEL` + `KWIKI_API_BASE` |

**推荐**：Claude Code 交互式。无需额外 API Key，编译质量更高，出错可人工干预。

脚本直连路径的三个 API 环境变量（`KWIKI_API_KEY` / `KWIKI_COMPILE_MODEL` / `KWIKI_API_BASE`）**只对脚本直连有意义**，Claude Code 交互式不需要配置。

## 3. 软件架构

### 3.1 模块组织

```
scripts/
  wiki_ingest.py          ← 主入口（orchestrator）
  wiki_ingest_wechat.py   ← 兼容 shim，转发到 wiki_ingest.py
  wiki_query.py           ← 查询入口
  wiki_lint.py            ← 健康检查入口
  llm_compile_ingest.py   ← LLM 编译器（支持 prepare-only 交互模式）
  apply_compiled_brief_source.py ← 人工审核后的回写入口
  delta_compile.py        ← 重编译草案生成
  refresh_synthesis.py    ← 刷新综合分析页
  review_queue.py         ← 审核队列
  archive_outputs.py      ← 归档重复 outputs
  stale_report.py         ← 过期报告
  wiki_size_report.py     ← vault 规模告警
  apply_approved_delta.py ← 应用已审核 delta
  graph_cleanup.py        ← 回填 graph metadata
  graph_trim.py           ← 低信号页降级
  export_main_graph.py    ← 导出主知识图谱
  question_ledger.py      ← Question Ledger CLI
  stance_manager.py       ← Stance Pages CLI
  import_jobs.py          ← 批量视频 job 管理
  install_video_cookies.py ← Cookie 安装辅助
  deep_research.py        ← 深度调研 CLI（init/update-ledger/record-scenarios/record-premortem/finalize-report/list/status/check-sufficiency/rollback/collect-vault-evidence）
  source_registry.py      ← URL/文件 pattern 匹配注册表
  source_adapters.py      ← 源适配器 CLI 入口
  adapter_result_to_article.py ← AdapterResult → Article 转换
  env_compat.py           ← KWIKI_* → WECHAT_WIKI_* 兼容映射
  douyin_browser_capture.js ← Playwright 网络响应捕获脚本（抖音浏览器兜底）

  adapters/               ← 源适配器包
    __init__.py            ← 路由 dispatcher (run_adapter_for_source)
    types.py               ← 类型定义（AdapterResult, AdapterStatus, QualityLevel 等）
    utils.py               ← 文本/HTML 解析工具
    quality.py             ← 内容质量评估（assess_web/video/pdf_quality）
    video.py               ← YouTube/Bilibili/抖音（3段 cookie 尝试 + 抖音 Playwright 浏览器捕获兜底）
    web.py                 ← 通用网页（baoyu-url-to-markdown）
    wechat.py              ← 微信公众号
    local.py               ← 本地 Markdown/HTML/PDF/TXT
    text.py                ← 纯文本
    collection.py          ← 视频合集/频道扩展

  kwiki/                  ← CLI 入口包（DEPRECATED — 薄桩，用 wiki_ingest.py 等替代）
    __init__.py
    __main__.py            ← 顶层调度（fetch/ingest/apply/review）
    fetch.py               ← kwiki fetch 阶段（DEPRECATED stub）
    ingest.py              ← kwiki ingest 阶段（DEPRECATED stub）
    apply.py               ← kwiki apply 阶段（DEPRECATED stub）
    review.py              ← kwiki review 阶段（evolution/blind-spots 可运行，其余 stub）

  pipeline/               ← 流水线核心包
    types.py               ← Article dataclass + WIKI_DIRS + 常量
    text_utils.py          ← regex helpers + plain_text + parse_frontmatter + section_excerpt
    extractors.py          ← detect_domains + extract_concepts/entities + taxonomy helpers
    vault_config.py        ← resolve_vault + multi-vault registry + video/transcript helpers
    shared.py              ← re-export shim（向后兼容）
    fetch.py               ← 输入收集 + 适配器调度
    ingest.py              ← vault 初始化 + raw 写入 + hot.md 初始化
    compile.py             ← LLM compile wrapper + 验证门控
    page_builders.py       ← wiki 页面内容生成 + merge/replace + write/upsert
    taxonomy.py            ← ensure_taxonomy/synthesis/comparison_pages + status 升级
    ingest_orchestrator.py ← ingest_article 主编排器
    index_log.py           ← rebuild_index + append_log + update_hot_cache
    apply.py               ← re-export shim（向后兼容）
    output/                ← 9 种查询输出模式子包
      __init__.py          ← dispatcher + shared helpers + re-exports
      brief.py             ← brief 模式
      briefing.py          ← briefing 模式
      draft_context.py     ← draft-context 模式
      contradict.py        ← contradict 模式
      digest.py            ← digest 模式（→ pipeline/digest.py）
      essay.py             ← essay 模式
      reading_list.py      ← reading-list 模式 + --seed 冷启动
      talk_track.py        ← talk-track 模式
      deep_research.py     ← deep-research 模式
    question.py            ← Question Ledger CRUD
    stance.py              ← Stance Pages CRUD + impact 检测
    typed_edges.py         ← 知识图谱边分类
    validate_compile.py    ← v2 编译结果验证门控
    digest.py              ← 多源 Digest（深度报告/对比表/时间线）
    graph_mermaid.py       ← Mermaid 静态图谱
    graph_analysis.py      ← 三信号边权重 + Louvain 社区 + 洞察引擎
    graph_html.py          ← 交互式水彩风格 HTML 图谱
    evolution.py           ← 知识演化追踪
    blindspots.py          ← 知识盲区检测
    deep_research.py       ← 深度调研编排（假说初始化、依赖账本、证据收集、报告打包）
    dependency_ledger.py   ← F/H/I/A/C/G/D 节点 CRUD + 置信度传播 + 充分性门控

templates/
  purpose-template.md     ← purpose.md 模板（研究方向声明）
  graph-styles/wash/      ← 交互式图谱前端模板

deps/                     ← 前端 vendor（d3, rough, marked, purify）
```

### 3.1b Skill 文档架构

Skill 运行时文档按阶段拆分，宿主 Agent 按任务类型条件加载，不一次性读取全部：

| 文件 | 内容 | 加载时机 |
|------|------|---------|
| `SKILL.md` | 触发条件 + 路由表 + 脚本名称列表 | 必加载（56行） |
| `references/workflow.md` | 操作模式、pipeline、vault 结构、页面约定 | ingest / compile / apply / autoresearch |
| `references/interaction.md` | 路由规则、状态词汇、用户提示模板、入库后引导 | save / autoresearch / deep-research |
| `references/pipeline-scripts.md` | ingest / compile / apply 脚本详情 | ingest / compile / apply |
| `references/review-scripts.md` | lint / review / 维护脚本详情 | review |
| `references/query-scripts.md` | wiki_query.py 详情 | query |
| `references/helper-scripts.md` | cookie、question ledger、stance manager | helper 操作 |
| `references/video-rules.md` | 视频处理、合集保护、cookie 规则 | 视频入库 |
| `references/output-modes.md` | wiki_query.py 8种输出模式 | query |
| `references/setup.md` | 环境配置、依赖安装 | 首次配置或依赖缺失 |
| `references/cross-project-access.md` | 跨项目只读 vault 访问 | 其他项目引用 |
| `references/question-schema.md` | Question 页模板 | question 操作 |
| `references/stance-schema.md` | Stance 页模板 | stance 操作 |
| `references/deep-research-protocol.md` | 9 阶段深度调研协议、假说驱动、证据标签、依赖账本 | deep-research |

**不参与运行时加载**：`docs/` 目录（SPEC.md、skill-analysis.md）、`README.md`、`README.en.md`。

典型 ingest 调用只加载 SKILL.md + workflow.md + pipeline-scripts.md（~30KB），而非旧架构的全量 ~82KB。

### 3.2 源适配器注册表

| source_id | URL Pattern | 适配器 | 优先级 |
|-----------|-------------|--------|--------|
| `wechat_url` | `mp.weixin.qq.com/s/` | wechat-article-to-markdown | 100 |
| `web_url` | 通用 HTTP URL | baoyu-url-to-markdown | 10 |
| `video_url_youtube` | `youtube.com/watch`, `youtu.be/` | yt-dlp + (ASR fallback) | 90 |
| `video_url_bilibili` | `bilibili.com/video/`, `b23.tv/` | yt-dlp + ASR fallback | 90 |
| `video_url_douyin` | `douyin.com/video/`, `douyin.com/...?modal_id=...`, `v.douyin.com/` | yt-dlp + browser capture fallback (ASR) | 90 |
| `video_playlist_youtube` | `youtube.com/playlist`, `/@<handle>/videos`, `/channel/<id>/videos`, `/c/<name>/videos` | yt-dlp playlist expansion | 95 |
| `video_playlist_bilibili` | `space.bilibili.com/*/channel/*`, `bilibili.com/list/` | yt-dlp playlist expansion | 95 |
| `video_playlist_douyin` | `douyin.com/user/` | yt-dlp playlist expansion | 95 |
| `local_file_md` | `.md`, `.markdown` extension | 本地 Markdown 读取 | 100 |
| `local_file_html` | `.html`, `.htm` extension | 本地 HTML 读取 | 100 |
| `local_file_pdf` | `.pdf` extension | pypdf 文本提取 | 100 |
| `local_file_txt` | `.txt` extension | 纯文本读取 | 100 |
| `plain_text` | 直接文本粘贴 | 直接入库 | 100 |

### 3.3 编译模式

| 模式 | 入口 | LLM 来源 | 输出 |
|------|------|---------|------|
| **启发式** | `wiki_ingest.py --no-llm-compile` | 无（规则提取） | brief + source（规则生成） |
| **脚本直连 API** | `wiki_ingest.py`（配置 KWIKI_API_KEY） | OpenAI 兼容接口 | v2 JSON → brief + source + taxonomy + delta + questions + stances |
| **Claude Code 交互** | `llm_compile_ingest.py --prepare-only` → Claude Code → `apply_compiled_brief_source.py` | Claude Code 本身 | 同上，人可审核 |
| **Claude Code 交互（lean）** | `llm_compile_ingest.py --prepare-only --lean` → Claude Code → `apply_compiled_brief_source.py` | Claude Code 本身 | 同上，上下文占用减少 ~80% |

### 3.4 v2 编译输出结构

LLM 编译（或 Claude Code 交互生成）的标准 JSON 结构：

```json
{
  "schema_version": "2.0",
  "result": {
    "version": "2.0",
    "compile_target": { "vault", "raw_path", "slug", "title", "author", "date", "source_url" },
    "document_outputs": {
      "brief": { "one_sentence", "key_points", "who_should_read", "why_revisit" },
      "source": { "core_summary", "knowledge_base_relation", "contradictions", "reinforcements" }
    },
    "knowledge_proposals": { "domains", "concepts", "entities" },
    "update_proposals": [],
    "claim_inventory": [{ "claim", "claim_type", "confidence", "evidence" }],
    "open_questions": [],
    "stance_impacts": [{ "stance_topic", "impact", "evidence", "confidence" }],
    "comparisons": [{ "subject_a", "subject_b", "dimensions", "verdict" }],
    "review_hints": { "priority", "needs_human_review", "suggested_review_targets" }
  }
}
```

**验证门控**：`validate_compile.py` 在 Apply 前检查结构完整性（brief.one_sentence 非空、key_points 非空、core_summary 非空、confidence 合法枚举值等）。验证失败 → 自动降级为启发式，不报错退出。

### 3.5 置信度标注体系

| 级别 | 含义 | 来源 |
|------|------|------|
| `high` | 原文明确陈述的事实 | claim_inventory 中 confidence=high 的声明占多数 |
| `medium` | 原文有支持但需要推断 | claim_inventory 中 confidence=medium 占多数 |
| `low` | 原文证据不足或间接 | claim_inventory 中 confidence=low 占多数 |

入库时自动从 `claim_inventory` 提取主导置信度，写入 brief/source 页的 frontmatter `confidence` 字段。

## 4. 完整功能清单

### 4.1 入库（Ingest）

**交互入口**：给 Claude Code 一个 URL、文件路径或文本片段，说"入库"

**脚本入口**：`python scripts/wiki_ingest.py --vault <path> <url/text/file>`

- 自动识别源类型（微信/网页/YouTube/B站/抖音/本地文件）
- 视频：提取字幕 → ASR fallback（faster-whisper）→ 质量评估
- 合集/频道：自动扩展 + import job 状态跟踪 + 冷却/退避
- 编译 → 写入 raw + wiki 全层
- **自动创建** Question 页（从 open_questions）
- **自动检测** Stance impact（reinforce/contradict/extend）
- **purpose.md 过滤**：排除范围内的内容降级为仅 brief

### 4.2 查询（Query）

**交互入口**：向 Claude Code 提问

**脚本入口**：`python scripts/wiki_query.py --vault <path> --mode <mode> "问题"`

| 模式 | 输出 | 适用场景 |
|------|------|---------|
| `brief` | 经典摘要回答 | 快速了解 |
| `briefing` | 结构化简报：来源 + 主张 + 争议 + 问题 + 立场 | 会议前准备 |
| `draft-context` | 带 [[ref]] 回链的素材包 | 喂给 LLM 做二次分析 |
| `contradict` | 最强反驳 + 类型化关系图谱反对边 | 找反方论据 |
| `digest --digest-type deep` | 多源深度报告：背景 + 观点 + 跨视角对比 + 未解问题 | 深度研究 |
| `digest --digest-type compare` | 对比表：核心观点/优势/劣势 | 技术路线选择 |
| `digest --digest-type timeline` | Mermaid 时间线 + 事件列表 | 追踪发展脉络 |
| `essay` | 文章草稿：立场 + 综合 + 来源依据 + 展望 | 写文章 |
| `reading-list` | 阅读路径：基础→进阶排序 + 前置阅读 | 系统学习 |
| `talk-track` | 会议素材包：核心论点 + 反驳 + 待讨论问题 | 开会 |

### 4.3 知识图谱

| 输出 | 生成方式 | 使用方式 |
|------|---------|---------|
| `wiki/knowledge-graph.md` | Mermaid 静态图谱（≤30节点度数剪枝） | Obsidian 内直接渲染 |
| `wiki/typed-graph.md` | 类型化边图谱（supports/contradicts/answers/evolves） | `export_main_graph.py --typed-edges` |
| `wiki/graph-data.json` | 三信号边权重 + Louvain 社区 + 洞察引擎 | 数据层，供 HTML 图谱消费 |
| `wiki/knowledge-graph.html` | 交互式水彩风格 HTML（D3.js + Rough.js） | 双击打开 → 浏览器交互 |

**三信号边权重**：共引频率 × 0.5 + 来源重叠 × 0.3 + 类型亲和度（supports=2.0, contradicts=2.5, evolves=1.5, answers=1.2, belongs_to=0.8, mentions=0.3）

**Louvain 社区发现**：自动将节点聚类，生成社区色块

**洞察引擎**：跨社区强连接（惊人连接）、桥梁节点、孤立节点、稀疏社区

**learning 模式**：path（推荐起点 + 邻居）→ community（主社区）→ global（全景）

### 4.4 维护（Maintenance）

| 脚本 | 功能 |
|------|------|
| `wiki_lint.py` | 健康检查：缺页、孤儿页、空分类、断链、低质量来源、声明冲突、状态不一致 |
| `review_queue.py --write` | 审核队列：delta 提案 + 低质量候选 + 冲突声明 |
| `delta_compile.py` | 生成重编译草案 |
| `apply_approved_delta.py` | 应用已审核的 delta |
| `stale_report.py` | 过期报告 + 盲区检测 |
| `refresh_synthesis.py` | 刷新综合分析页 |
| `graph_cleanup.py` | 回填 graph metadata |
| `graph_trim.py --apply-policy` | 低信号页降级 |
| `export_main_graph.py` | 导出 Mermaid 主图谱 + typed-graph + HTML 交互图谱 |
| `wiki_size_report.py` | vault 规模告警 |

### 4.5 Question Ledger

**自动**：入库时从 `open_questions` 自动创建 question 页

**手动**：`python scripts/question_ledger.py <list|create|check|resolve|drop> --vault <path>`

状态流：`open` → `partial`（新来源提供线索）→ `resolved` → `dropped`

入库时自动检测新来源是否回答了已有 open/partial 问题。

### 4.6 Stance Pages

**自动**：入库时从 `stance_impacts` 自动检测对已有立场的影响

**手动**：`python scripts/stance_manager.py <list|create|impact> --vault <path>`

impact 类型：`reinforce`（巩固）、`contradict`（反驳）、`extend`（延伸）、`neutral`（无关）

### 4.7 purpose.md 目的性过滤

在 vault 根目录放置 `purpose.md`（使用 `templates/purpose-template.md` 模板），声明：
- **核心问题**：最想搞清楚什么
- **关注领域**：持续跟踪的主题
- **排除范围**：明确不关注什么

效果：
- 编译时，与关注领域相关的实体/话题优先创建页面
- 排除范围内的内容仅标注，不创建独立 concept/entity/domain 页
- 核心问题相关内容在 open_questions 中体现

### 4.8 深度调研（Deep Research）

**触发条件**：三要素同时满足时触发——战略重要性 + 依赖外部事验证 + 框架风险

**触发词**：`深入研究 X` / `深度分析 X` / `deep research X` / `系统分析 X`

**与现有模式区分**：
- 简单事实查询 → brief
- 结构化概览 → briefing
- 多视角聚合（vault 内） → digest
- 广泛探索（无具体命题） → autoresearch
- 假说驱动 + 联网验证 + 证据标注 → **deep-research**

9 阶段工作流：Phase 0 激活 → Phase 1 意图扩展 → Phase 2 假说形成 → Phase 3 Vault 证据 → Phase 4 联网研究（adaptive rounds） → Phase 5 外部校准 → Phase 6 根本问题 → Phase 7 压力测试 → Phase 8 预验尸 → Phase 9 收敛报告

详见 `references/deep-research-protocol.md`

### 4.9 入库后标准引导

每次入库完成后，宿主 Agent 必须按标准模板展示结果（不只返回"写入完成"）：

**普通入库**（无跨域联想/战略级开放问题）：
```
入库完成：{标题} → {vault}
编译质量：{structured | raw-extract}
新增：{N 个概念候选, N 个实体候选, N 个开放问题}

可以继续：追问 / 查看影响报告 / 运行日常维护
```

**高信号入库**（有跨域联想或战略级开放问题）：
```
入库完成：{标题} → {vault}
编译质量：structured
跨域联想：{概念 → 领域映射}
开放问题：{问题列表}

可以继续：围绕开放问题追问 / 运行日常维护
```

Deep-research 不在入库后主动推荐——它的触发时机是追问场景（问题同时具备战略重要性 + 外部验证需求 + 框架风险时，宿主 Agent 才建议升级）。

详见 `references/interaction.md` "入库后标准引导模板"

## 5. 技术细节

### 5.1 Claude Code 交互式 vs 脚本直连差异

| 维度 | Claude Code 交互 | 脚本直连 |
|------|-----------------|---------|
| 编译者 | Claude Code 本身 | 外部 OpenAI 兼容 API |
| 需要额外 API Key | 否 | 是（KWIKI_API_KEY 等） |
| 编译质量 | Claude Code 能力上限 | 取决于配置的模型 |
| 出错干预 | 人可实时审核调整 | 无人值守，验证门控自动降级 |
| 工作流 | `--prepare-only` → Claude → `apply` | 一条命令全流程 |
| 适用场景 | 日常入库、单篇精读 | 批量处理、定时任务 |

**Claude Code 交互流程**：
```
1. llm_compile_ingest.py --prepare-only --lean → 生成精简编译上下文 JSON（推荐）
   或 llm_compile_ingest.py --prepare-only → 生成完整 payload（用于管道到外部 API）
2. Claude Code 基于上下文生成 v2 结构化 JSON
3. apply_compiled_brief_source.py --compiled-json <json> → 回写 wiki
```

`--lean` 模式从输出中移除 `system_prompt`、`user_prompt`、`existing_source`、`existing_brief`，并过滤匹配 ASR 转写噪声模式的 synthesis excerpt。宿主 Agent 本身是 LLM，不需要这些字段（它们是为外部 API 调用设计的）。保留的关键字段：`metadata`、`context`（含 `purpose`、`related_domains`、`related_sources`、`related_syntheses`、`detected_domains`、`pending_deltas`）、`expected_output_schema_version`。

### 5.2 视频源处理链路

```
URL → yt-dlp 提取字幕 → subtitle_to_text()
                         ↓ (无字幕) → 下载音频 → faster-whisper ASR → 质量评估(最高 acceptable)
                         ↓ (有弹幕但非字幕) → 忽略弹幕，走 ASR fallback
                         ↓ (嵌入式元数据字幕) → 提取 → 标记 confidence=medium
                         ↓ (抖音 cookie/平台阻断) → Playwright 浏览器捕获 → ASR → 质量评估(最高 acceptable)
```

视频来源质量评估规则：ASR 文稿最长只评 `acceptable`；平台字幕评 `high` 或 `acceptable`。

**抖音浏览器兜底**：当 `yt-dlp` 对抖音 URL 返回 cookie/登录/fresh cookies/JSON 解析类错误时，自动切换到 Playwright 浏览器捕获模式：

1. `normalize_video_fetch_url()` 将抖音精选/搜索页 `modal_id` 归一化为 `https://www.douyin.com/video/<id>`
2. `resolve_video_cookie_arg_variants()` 按 3 段顺序尝试 cookie：浏览器 cookie → cookies.txt 文件 → 无 cookie
3. `should_fallback_to_douyin_browser_capture()` 检测失败信号（fresh cookies / failed to parse JSON / cookie / authenticated / login）
4. `run_douyin_browser_capture()` 启动 Playwright Chromium → 拦截 `douyinvod.com` 视频响应 → curl 下载 mp4
5. `build_douyin_browser_capture_result()` 对下载的视频执行 ASR → 构建成功/失败 AdapterResult

### 5.3 合集/频道保护机制

批量视频导入使用 import job 状态跟踪：

- `--collection-limit`：单次上限（clamp 到 20）
- `--collection-delay-seconds`：成功项间等待
- `--collection-failure-threshold`：连续失败阈值 → 暂停 job
- `--collection-backoff-seconds` + `--collection-jitter-seconds`：退避 + 抖动
- `--collection-platform-cooldown-seconds`：冷却期，期间跳过整个 collection

### 5.4 环境变量

| 变量 | 用途 | 仅脚本直连需要 |
|------|------|:-------------:|
| `KWIKI_API_KEY` | LLM API Key | ✅ |
| `KWIKI_COMPILE_MODEL` | LLM 模型名 | ✅ |
| `KWIKI_API_BASE` | LLM API 基地址 | ✅ |
| `KWIKI_COMPILE_TEMPERATURE` | 编译温度（默认 0.2） | ✅ |
| `KWIKI_COMPILE_MAX_TOKENS` | 最大 token（默认 2200） | ✅ |
| `KWIKI_COMPILE_MOCK_FILE` | Mock 编译 JSON 路径（测试用） | ✅ |
| `KWIKI_WEB_ADAPTER_BIN` | Web 适配器命令 | ✅ |
| `KWIKI_VIDEO_ADAPTER_BIN` | 视频适配器命令 | ✅ |
| `KWIKI_VIDEO_COOKIES_FROM_BROWSER` | 浏览器 cookie 来源 | ✅ |
| `KWIKI_VIDEO_COOKIES_FILE` | Cookie 文件路径 | ✅ |
| `KWIKI_VIDEO_COOKIES_FROM_BROWSER` | 浏览器 cookie 来源 | ✅ |
| `KWIKI_ASR_MODEL` | ASR 模型（默认 small） | ✅ |
| `KWIKI_ASR_COMPUTE_TYPE` | ASR 计算类型（默认 int8） | ✅ |
| `KWIKI_NODE_BIN` | Node.js 可执行文件路径（抖音浏览器兜底） | ✅ |
| `KWIKI_DOUYIN_USER_AGENT` | 抖音浏览器捕获 User-Agent | ✅ |
| `KWIKI_DOUYIN_HEADLESS` | 抖音浏览器是否无头模式（默认 1，设 0 为有头） | ✅ |
| `KWIKI_WECHAT_TOOL_DIR` | wechat-article-for-ai 路径 | ✅ |
| `KWIKI_DEPS_DIR` | Python 依赖目录 | ✅ |

所有变量有 `WECHAT_WIKI_*` / `WECHAT_ARTICLE_*` 旧名兼容映射（通过 `env_compat.py`）。

### 5.5 Obsidian Vault 自动发现

Windows 下读取 `%APPDATA%\obsidian\obsidian.json`：
1. 优先唯一 `open: true` 且路径存在的 vault
2. 没有打开中的 vault 时，唯一已登记且存在的 vault
3. 多候选 → 必须传 `--vault`

## 6. 依赖

### 6.0 依赖检查工具

```powershell
python scripts/check_deps.py                      # 仅检查
python scripts/check_deps.py --install             # 检查 + 自动安装
python scripts/check_deps.py --install --china     # 中国镜像安装
python scripts/check_deps.py --install --group=wechat  # 仅安装微信组
python scripts/check_deps.py --install-camoufox    # 单独安装 Camoufox
python scripts/check_deps.py --install-camoufox --china  # Camoufox 中国镜像
```

依赖分组：`core` | `wechat` | `video` | `video_asr` | `pdf` | `web` | `test`

镜像地址汇总：

| 镜像 | 用途 | 地址 | 用法 |
|------|------|------|------|
| 清华 PyPI | pip 包 | `https://pypi.tuna.tsinghua.edu.cn/simple` | `pip install -i <地址>` |
| npmmirror | npm 包 | `https://registry.npmmirror.com` | `npm install --registry=<地址>` |
| ghfast.top | GitHub Release / 仓库 | `https://ghfast.top/` | 在 GitHub URL 前加此前缀 |
| hf-mirror | Hugging Face 模型 | `https://hf-mirror.com` | `set HF_ENDPOINT=<地址>` |

### 6.1 Python pip 依赖

见 `requirements.txt`。核心依赖为零（全部 stdlib），可选依赖按来源类型分组：

| 包 | 用途 | 分组 | 未安装时行为 |
|----|------|------|-------------|
| `camoufox[geoip]` | 微信文章反检测浏览器 | wechat | 微信文章不可用 |
| `markdownify` | HTML → Markdown | wechat | 微信文章不可用 |
| `beautifulsoup4` | HTML 解析 | wechat | 微信文章不可用 |
| `httpx` | HTTP 客户端 | wechat | 微信文章不可用 |
| `chardet` | 避免字符集告警 | wechat | Windows 下 requests 告警 |
| `yt-dlp` | 视频源字幕提取 | video | 视频源不可用 |
| `faster-whisper` | 无字幕视频 ASR fallback | video_asr | 无字幕视频降级为不可用 |
| `pypdf` | 本地 PDF 入库 | pdf | PDF 源不可用 |

### 6.1b Node.js 可选依赖

| 包 | 用途 | 安装方式 | 未安装时行为 |
|----|------|---------|-------------|
| `playwright` | 抖音浏览器捕获兜底 | `npm install`（在 skill 根目录运行，读取 `package.json`） | 抖音视频 yt-dlp 失败时无法自动浏览器兜底 |

`package.json` 在 skill 根目录登记了 `playwright` 依赖。安装方式：

```powershell
cd <skill-root>
npm install
npx playwright install chromium
```

中国镜像：
```powershell
npm install --registry=https://registry.npmmirror.com
npx playwright install chromium
```

### 6.1c 抖音浏览器捕获脚本

### 6.2 外部可执行依赖

| 工具 | 用途 | 分组 | 标准安装 | 中国镜像安装 |
|------|------|------|---------|------------|
| `wechat-article-for-ai` | 微信公众号抓取 | wechat | `git clone https://github.com/bzd6661/wechat-article-for-ai.git` | `git clone https://ghfast.top/https://github.com/bzd6661/wechat-article-for-ai.git` |
| `yt-dlp` | 视频源 + 合集扩展 | video | `pip install yt-dlp` | `pip install yt-dlp -i https://pypi.tuna.tsinghua.edu.cn/simple` |
| `baoyu-url-to-markdown` | 通用网页抓取 | web | `npm install -g baoyu-url-to-markdown` 或 bun 运行 skill 本地脚本 | `npm install -g baoyu-url-to-markdown --registry=https://registry.npmmirror.com` 或 bun 运行 skill 本地脚本 |

### 6.3 运行时下载依赖

| 资源 | 触发条件 | 大小 | 标准路径 | 中国镜像路径 |
|------|---------|------|---------|------------|
| Camoufox 浏览器二进制 | 首次使用微信适配器 | ~530MB | `python -m camoufox fetch` (自动下载) | `python scripts/check_deps.py --install-camoufox --china` (通过 ghfast.top) |
| uBlock Origin addon | Camoufox 启动前检查 | ~4MB | Camoufox fetch 时自动安装 | check_deps.py 中国模式下自动从 GitHub 镜像下载 |
| faster-whisper 模型权重 | 首次使用 ASR | tiny~75MB, small~460MB | 从 Hugging Face 自动下载 | `set HF_ENDPOINT=https://hf-mirror.com` |

**Camoufox 中国安装注意事项**：

1. Camoufox 启动时检查 UBO addon，缺失则清空 Cache 重新下载——因此中国环境必须先安装 UBO addon
2. addons.mozilla.org 在中国返回 HTTP 451（屏蔽），UBO 需通过 ghfast.top + GitHub 下载
3. 手动安装步骤：下载 zip → 解压到 `%LOCALAPPDATA%\camoufox\camoufox\Cache\` → 写入 version.json → 下载 UBO XPI → 解压到 `Cache\addons\UBO\`
4. 推荐：直接用 `check_deps.py --install-camoufox --china`，已内置上述全流程

### 6.4 前端依赖（交互式图谱）

`deps/` 下 bundled：d3.min.js。由 `graph_html.py` 自动复制到 vault 输出目录，无需单独安装。（rough.min.js/marked.min.js/purify.min.js 已移除，图谱使用标准 SVG 渲染和结构化内容模板。）

## 7. 典型使用场景

### 7.1 日常单篇入库（推荐方式）

```
用户 → Claude Code："把这篇文章入库 https://example.com/article"
Claude Code → wiki_ingest.py --no-llm-compile → raw + brief + source + taxonomy
或
Claude Code → llm_compile_ingest.py --prepare-only → 生成上下文
Claude Code → 自己生成 v2 JSON → apply_compiled_brief_source.py → 完整编译结果
```

### 7.2 批量视频导入

```
python scripts/wiki_ingest.py --vault <path> --no-llm-compile \
  --collection-limit 5 --collection-delay-seconds 1 \
  "https://www.youtube.com/playlist?list=..."
```

### 7.3 深度研究一个主题

```
python scripts/wiki_query.py --vault <path> --mode digest --digest-type deep "AIDV技术路线"
→ wiki/syntheses/AIDV技术路线--deep.md
```

### 7.4 会前准备

```
python scripts/wiki_query.py --vault <path> --mode talk-track "BEV vs 纯视觉"
→ 立场论点 + 反驳 + 待讨论问题
```

### 7.5 写文章

```
python scripts/wiki_query.py --vault <path> --mode essay "端到端架构对EEA的影响"
→ 引言 + 论点 + 综合 + 依据 + 展望（带 [[ref]] 回链）
```

### 7.6 知识图谱可视化

```
python -c "from pipeline.graph_mermaid import write_knowledge_graph; ..."
python -c "from pipeline.graph_html import write_graph_html; ..."
→ Obsidian 内看 knowledge-graph.md
→ 双击 knowledge-graph.html → 浏览器交互图谱
```

### 7.7 周期维护

```
python scripts/wiki_lint.py --vault <path>          → 健康检查
python scripts/stale_report.py --vault <path>       → 过期报告
python scripts/refresh_synthesis.py --vault <path>  → 刷新综合分析
```