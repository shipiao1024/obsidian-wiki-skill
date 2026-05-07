# Obsidian Wiki Skill — 产品与技术规格

> **文档位置**：本文件位于 `docs/SPEC.md`，是面向用户的完整规格文档，不参与 skill 运行时加载。

## 1. 设计哲学

### 1.1 核心信念

**知识的价值在于可积累、可关联、可演化。** 个人知识库的普遍失败模式是"导入几百篇文章后三个月停止维护"——因为写入成本是可见的，读出价值却不是。Obsidian Wiki Skill 的设计目标是扭转这个方向：每次入库不只是"多了一篇"，而是让整个知识库产生新的连接、新的问题、新的视角。

设计思想参考 [Karpathy 的 llm-wiki 方法论](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)：ingest 是**编译**而不是归档，LLM 把原始资料编译为持久 Wiki，prefer 链接而非重复。

### 1.2 三条设计原则

**两层证据原则**：`raw/` 是不可变原始层（最终事实来源），`wiki/` 是 AI 编译层（可演化、可迭代）。精确数字、日期、原文引用必须回看 `raw/`；理解与分析看 `wiki/`。这条分界线保证了知识的可验证性——AI 编译的结果永远可以溯源到原始证据。

**host-agent 优先**：Claude Code 是主入口，Python 脚本是支撑。AI 做语义理解和知识编译，脚本做文件操作和流程编排。用户体验是对话，不是命令行序列。这意味着知识库的维护成本接近于"和 AI 聊天"，而不是"运行一堆脚本"。

**概念成熟度门槛**：concept/entity 不会因"提到一次就建页"，必须 ≥2 来源稳定引用才升级为正式图谱节点。这避免了知识图谱被一次性名词污染——只有反复出现的概念才值得成为持久节点。

### 1.3 设计取舍

| 选择 | 取舍 | 理由 |
|------|------|------|
| 本地文件系统 + Obsidian | 放弃 Web UI 和数据库 | 知识应属于用户，不依赖任何在线服务 |
| LLM 编译优先 | 启发式仅作 `--no-llm-compile` opt-in | LLM 编译质量远高于启发式，但保留启发式用于快速批量场景 |
| 5 级序数置信度 | 放弃百分比/概率表达 | 人类对"Supported"的理解比"73%"更准确 |
| 风险分级审批 | 放弃全量双提案 | 低风险操作自动执行避免摩擦，高风险操作必须确认 |
| 两步 CoT 入库 | 放弃单步全量编译 | 分离事实提取和结构编译，减少幻觉和信息丢失 |

## 2. 系统架构

### 2.1 知识层结构

```
raw/              ← 不可变原始层（最终证据）
  inbox/          ← 待处理输入暂存
  articles/       ← 完整原文
  transcripts/    ← 视频文稿
  assets/         ← 图片、附件

wiki/             ← AI 编译知识层（可演化）
  briefs/         ← 一句话结论 + 核心要点（快速浏览层）
  sources/        ← 核心摘要 + 关联 + 声明（蒸馏层）
  concepts/       ← 概念页（跨来源聚合，≥2 来源引用才升级为正式节点）
  entities/       ← 实体页（人/公司/产品/方法）
  domains/        ← 域页（主题领域边界与导航）
  syntheses/      ← 综合分析页（跨来源综合）
  questions/      ← 问题追踪页（open → partial → resolved → dropped）
  stances/        ← 立场页（我对 X 的当前判断 + 证据）
  comparisons/    ← 结构化对比页（A vs B：维度 + 优劣 + 综合判断）
  research/       ← 深度研究报告 + PDF（Why/What/How/Trace 结构）
  outputs/        ← 查询结果 + delta 提案 + 子图页面
  semantic-index.json  ← 语义索引（V2.0：域/概念/实体/声明/关系的结构化索引，供智能检索使用）
```

**保真度排序**：`raw/articles/` > `wiki/sources/` > `wiki/briefs/`

**PDF 输出**：每次入库自动生成 `wiki/briefs/{slug}.pdf`；深度研究报告自动生成 `wiki/research/{slug}--report.pdf`。均使用 Playwright + Chrome 渲染，academic 主题。

**页面状态生命周期**：`seed` → `developing`（≥1 引用）→ `mature`（≥3 引用）→ `evergreen`（≥6 引用）。状态在每次 ingest 时自动升级。

### 2.2 五阶段流水线（V2.0 增强）

```
URL/文件/文本 → [1. Fetch + 格式归一化] → [2. Ingest(raw) + 结构修复] → [3. Two-Step CoT Compile] → [4. Risk-Graded Apply(wiki) + 结构修复] → [5. Review + 触发检测]
```

| 阶段 | 输入 | 输出 | 核心模块 |
|------|------|------|---------|
| Fetch | URL/文件/文本 | Markdown 文本 + metadata + assets | `adapters/`（含格式归一化层） |
| Ingest | AdapterResult | `raw/articles/` + `raw/transcripts/` + `raw/assets/` | `pipeline/ingest.py` + `pipeline/structure_fix.py`（Obsidian 渲染空行修复） |
| Compile | raw 页面 | fact_inventory → 结构化 JSON | `llm_compile_ingest.py`（三模式：prepare-only / api-compile / heuristic） |
| Apply | 编译结果 | wiki 全层 + 原子卡片 + 深度研究触发 | `pipeline/apply.py` + `pipeline/risk_approval.py` + `pipeline/structure_fix.py`（页面输出空行兜底） |
| Review | vault 状态 | lint + review queue + 深度研究建议 + Brief PDF | `wiki_lint.py`（含 structure_violations 检查） + `deep_research_triggers.py` + `pdf_utils.py` |

### 2.3 两步 CoT 入库流程

V2.0 的核心改进：将编译分为两步，减少幻觉和信息丢失。

**Step 1 — 事实提取**（`fact_extraction_prompt.md`）：
- 输入：原始文章文本
- 输出：`fact_inventory`，包含：
  - `atomic_facts`：原子事实列表，每条含 `evidence_type`（fact/inference/assumption/hypothesis/disputed/gap）、`confidence`（5 级序数）、`grounding_quote`（原文锚定）
  - `argument_structure`：论证结构（generators / logic_chain / assumptions）
  - `key_entities`：关键实体
  - `cross_domain_hooks`：跨域联想钩子
  - `open_questions`：开放问题
  - `quantitative_markers`：定量标记

**Step 2 — 结构编译**（`compile_prompt.md`，受 Step 1 约束）：
- 输入：原始文章 + Step 1 的 fact_inventory
- 输出：v2 结构化 JSON（knowledge_proposals / claim_inventory / cross_domain_insights / open_questions / stance_impacts）

约束机制：Step 2 的 claim_inventory 必须与 Step 1 的 atomic_facts 对齐，不允许凭空生成 Step 1 未提取的事实。这大幅减少了 LLM 编译中的幻觉。

### 2.4 风险分级审批模型

入库操作按风险等级分类，避免全量双提案的摩擦：

| 风险等级 | 操作类型 | 处理方式 |
|---------|---------|---------|
| **Low** | create_candidate / link_existing / add_to_graph / create_question | AI 自动执行 |
| **Medium** | promote_to_official / update_synthesis / modify_stance | 展示 diff，不阻塞 |
| **High** | delete_page / merge_pages / modify_stable_page | 必须用户确认后执行 |

`risk_approval.py` 在 Apply 阶段自动分类所有操作，过滤出需要用户关注的中/高风险项。

### 2.5 格式归一化层

V2.0 新增格式归一化层，在 Fetch 阶段将各种文档格式统一转换为 Markdown：

| 格式 | 工具 | 输出 |
|------|------|------|
| DOCX | markitdown（Microsoft） | Markdown |
| PPTX | markitdown | Markdown |
| XLSX / XLS | pandas + openpyxl | Markdown 表格 |
| EPUB | ebooklib + beautifulsoup4 | Markdown |
| PDF | pypdf（首选）→ markitdown（fallback） | Markdown |
| HTML | beautifulsoup4（本地）/ baoyu（网页） | Markdown |

归一化后的 Markdown 进入统一的编译流水线，下游无需感知原始格式。

### 2.6 渲染兼容性修复层

V1.4 新增结构修复层，确保所有页面在 Obsidian 中正确渲染。数学块、列表、表格前后缺空行是 Obsidian 渲染异常的常见原因（公式不渲染、列表粘连、表格被吞）。

**两层防护**：

1. **预防**：compile prompt 内含 6 条 Obsidian 渲染规范（数学/列表/表格空行、callout 语法、代码围栏、连续空行），LLM 编译时即产出规范 markdown
2. **修复**：`pipeline/structure_fix.py` 在 page builder 和 raw page 输出前执行三阶段空行修复

**三阶段修复**：

| 阶段 | 功能 | 触发条件 |
|------|------|---------|
| 阶段1 | 数学块/列表块/表格块前后补空行 | 块级元素前后无空行 |
| 阶段2 | 多行数学块内部首尾空行清理 | `$$` 开行后或闭行前有空行 |
| 阶段3 | 单行数学块前后补空行 | `$$E=mc^2$$` 独占一行且前后无空行 |

**安全机制**：代码围栏内不误处理、frontmatter 不破坏、已有空行不重复、纯 stdlib 无额外依赖。

### 2.7 编译模式

三种显式编译模式，**默认 prepare-only**（不依赖外部 API key）：

| 模式 | 标志 | 编译者 | 需要 API key | 适用场景 |
|------|------|-------|:----------:|---------|
| **prepare-only** | 默认（无需参数） | LLM agent 在对话中编译 | 否 | 日常入库、单篇精读（**推荐**） |
| **api-compile** | `--api-compile` | 脚本直接调 OpenAI 兼容 API | 是 | 无人值守批量处理 |
| **heuristic** | `--no-llm-compile` | 启发式规则提取 | 否 | 快速入库、不需要 LLM 分析 |

**设计原则**：默认路径不依赖外部 API。`prepare-only` 模式下脚本生成结构化 payload，LLM agent 在对话中基于 payload 完成编译，是最常用的交互场景。`api-compile` 是 opt-in，仅在需要无人值守时启用。

**`llm_compile_ingest.py` 独立模式**：该脚本支持 `--prepare-only --lean` 精简模式，可在 `wiki_ingest.py` 之后单独运行以获取更精细的 payload 控制（移除 system_prompt/user_prompt，上下文减少 ~80%）。

## 3. 置信度与证据体系

### 3.1 五级序数置信度

| 级别 | 含义 | 典型场景 |
|------|------|---------|
| `Seeded` | 初始种子，未经验证 | 自动生成的候选 |
| `Preliminary` | 初步判断，证据有限 | 单来源推断 |
| `Working` | 工作假设，有多方支持 | 多来源交叉验证 |
| `Supported` | 有明确证据支持 | 原文直接陈述 + 数据佐证 |
| `Stable` | 稳定可靠，长期验证 | 多来源 + 时间检验 |

置信度是**可升降的**——新入库内容可能提升或降低已有判断的置信度。

### 3.2 六类证据类型

| 类型 | 含义 | 标记 |
|------|------|------|
| `fact` | 原文明确陈述的事实 | `[Fact]` |
| `inference` | 基于事实的合理推断 | `[Inference]` |
| `assumption` | 未经验证的假设 | `[Assumption]` |
| `hypothesis` | 可证伪的假说（附概率） | `[Hypothesis X%]` |
| `disputed` | 存在争议的判断 | `[Disputed]` |
| `gap` | 已知的信息缺口 | `[Gap]` |

## 4. 模块清单

### 4.1 入口脚本

| 脚本 | 功能 |
|------|------|
| `wiki_ingest.py` | 主入口 orchestrator（域优先路由 + 多源适配，默认 prepare-only；`--api-compile` 启用 API 直连） |
| `wiki_query.py` | 查询入口（索引重建 + 结果写入，查询逻辑由 LLM 执行） |
| `wiki_index_v2.py` | **V2.0** 语义索引构建 + 查询（`--rebuild` / `--query`） |
| `wiki_retrieve.py` | **V2.0** 智能检索（语义索引评分排序 + 结构化上下文包输出） |
| `wiki_lint.py` | 健康检查 |
| `llm_compile_ingest.py` | LLM 编译器（`--prepare-only --lean` 精简 payload、`--two-step` 两步 CoT、`--extract-facts-only` 事实提取） |
| `apply_compiled_brief_source.py` | 回写宿主 Agent 产出的结构化 JSON（含 `--validate-only` 预校验：结构 + grounding + 证据密度） |
| `delta_compile.py` | 重编译草案生成 |
| `refresh_synthesis.py` | 刷新综合分析页 |
| `review_queue.py` | 审核队列（含 `--sweep` 自动清理模式） |
| `archive_outputs.py` | 归档重复 outputs |
| `stale_report.py` | 过期报告 + 盲区检测 + `--auto-suggest` 维护建议 |
| `wiki_size_report.py` | vault 规模告警 |
| `apply_approved_delta.py` | 应用已审核 delta |
| `graph_cleanup.py` | 回填 graph metadata |
| `graph_trim.py` | 低信号页降级 |
| `export_main_graph.py` | 导出主知识图谱（Mermaid + 主图谱视角） |
| `question_ledger.py` | Question Ledger CLI |
| `stance_manager.py` | Stance Pages CLI |
| `import_jobs.py` | 批量视频 job 管理 |
| `install_video_cookies.py` | Cookie 安装辅助 |
| `deep_research.py` | 深度调研 CLI |
| `source_registry.py` | URL/文件 pattern 匹配注册表 |
| `source_adapters.py` | 源适配器 CLI 入口 |
| `adapter_result_to_article.py` | AdapterResult → Article 转换 |
| `env_compat.py` | KWIKI_* → WECHAT_WIKI_* 兼容映射 |
| `check_deps.py` | 依赖检查与自动安装 |
| `init_vault.py` | Vault 初始化 |
| `douyin_browser_capture.js` | Playwright 网络响应捕获脚本 |

### 4.2 流水线核心（`pipeline/`）

| 模块 | 功能 |
|------|------|
| `types.py` | Article dataclass + WIKI_DIRS + 常量 |
| `text_utils.py` | regex helpers + plain_text + parse_frontmatter |
| `extractors.py` | detect_domains + extract_concepts/entities + taxonomy helpers |
| `vault_config.py` | resolve_vault + multi-vault registry |
| `fetch.py` | 输入收集 + 适配器调度 |
| `ingest.py` | vault 初始化 + raw 写入 + hot.md 初始化 |
| `compile.py` | LLM compile wrapper + 验证门控（三模式显式分支：prepare-only / api-compile / heuristic，含 `try_llm_compile_two_step()`） |
| `page_builders.py` | wiki 页面内容生成 + merge/replace + write/upsert + `auto_graph_include()` |
| `taxonomy.py` | ensure_taxonomy/synthesis/comparison_pages + status 升级 |
| `ingest_orchestrator.py` | ingest_article 主编排器 |
| `index_log.py` | rebuild_index + append_log + update_hot_cache |
| `apply.py` | re-export shim（向后兼容） |
| `validate_compile.py` | v2 编译结果验证门控 |
| `risk_approval.py` | **V2.0** 风险分级审批模型（LOW/MEDIUM/HIGH 三级） |
| `atomic_cards.py` | 原子知识卡片系统（独立工具，未接入流水线） |
| `deep_research_triggers.py` | **V2.0** 隐式深度研究触发检测（5 种触发条件，已接入入库流程） |
| `spaced_repetition.py` | **V2.0** FSRS-6 间隔复习调度器（独立模块） |
| `graph_layers.py` | **V2.0** 域子图页面生成（Mermaid 可视化，已接入图谱重建流程） |
| `question.py` | Question Ledger CRUD |
| `stance.py` | Stance Pages CRUD + impact 检测 |
| `typed_edges.py` | 知识图谱边分类 |
| `digest.py` | 多源 Digest（深度报告/对比表/时间线） |
| `graph_mermaid.py` | Mermaid 静态图谱（Louvain 社区分组 + 度数剪枝） |
| `graph_analysis.py` | 页面扫描 + Louvain 社区检测（共享工具） |
| `evolution.py` | 知识演化追踪 |
| `blindspots.py` | 知识盲区检测 |
| `deep_research.py` | 深度调研编排（假说初始化、依赖账本、证据收集、报告打包） |
| `dependency_ledger.py` | F/H/I/A/C/G/D 节点 CRUD + 置信度传播 + 充分性门控 |
| `ingest_report.py` | 入库报告 + 对话式引导（`format_ingest_dialogue()`） |
| `claim_evolution.py` | 主张演化追踪（reinforce / contradict / extend 关系，依赖 wiki_lint） |
| `pdf_utils.py` | **V2.0** PDF 生成工具（frontmatter 剥离 + wikilink 清理 + md-to-pdf 调用，brief 带封面页） |
| `encoding_fix.py` | Windows 控制台 UTF-8 编码修复（5 个主入口脚本已集成） |
| `validation_protocol.py` | **V2.0** 深度报告质量门控（7 项红线检验 + 依赖链审查，已接入 Phase 9.5） |

### 4.3 查询架构（V2.0 智能检索）

**LLM 是查询主控层**。用户说自然语言，LLM 理解意图、调用检索脚本、综合答案、选择输出格式。脚本做机械操作（语义索引构建、智能检索、结果写入）。

**V2.0 核心改进**：用 `wiki_retrieve.py` 智能检索替代 LLM 驱动的 grep 搜索。脚本从语义索引中评分排序，输出结构化上下文包，LLM 直接消费结果。

**检索流水线**：

```
用户问题 → wiki_retrieve.py → 语义索引(semantic-index.json) → 评分排序 → 结构化上下文包 → LLM 综合回答
```

| 阶段 | 执行者 | 说明 |
|------|--------|------|
| 意图理解 | LLM | 提取核心概念 + 判断查询类型 |
| 智能检索 | `wiki_retrieve.py` | 查语义索引、评分排序、读 top-k 页面、输出上下文包 |
| 综合回答 | LLM | 基于上下文包生成回答，选择输出格式 |
| 结果写入 | `wiki_query.py` | 写入 `wiki/outputs/`、更新 log/hot |

**语义索引**（`wiki_index_v2.py`）：

索引存储为 `wiki/semantic-index.json`，包含：
- `domains`：域索引（sources、concepts、entities 列表）
- `concepts`：概念索引（title、status、confidence、domains、sources、related_concepts）
- `entities`：实体索引（同上结构）
- `claims`：所有页面的声明提取（text、confidence、source）
- `relationships`：stance 支持/反对关系 + synthesis 综合关系
- `sources`：来源元数据（title、domains、confidence、date、quality）
- `stats`：统计信息

每次入库后自动重建（`--rebuild`），查询前自动检查是否存在。

**行为指南**：`references/query-guide.md` 定义完整的查询行为，包含检索策略、综合原则、9 种输出格式模板、持久化规则、上下文效率约束。

**9 种输出格式**（LLM 根据用户意图自动选择）：

| 用户意图 | 输出格式 | 输出内容 |
|---------|---------|---------|
| "什么是 X"、"总结" | 快速了解 | 3-5 句要点 + 来源引用 |
| "深入分析"、"综述" | 深度综合 | 多来源交叉的结构化报告 |
| "对比 X 和 Y"、"vs" | 对比分析 | 对比表 + 关键差异 |
| "演变"、"时间线" | 时间线 | Mermaid gantt + 事件说明 |
| "准备开会"、"汇报" | 认知简报 | 要点 + 反面信号 + 待讨论问题 |
| "反驳"、"质疑" | 反驳材料 | 最强反面证据 + 冲突信号 |
| "写文章"、"帮我写" | 文章草稿 | 论点 + 证据 + 叙述结构 |
| "学习路径"、"系统学习" | 学习路径 | 按依赖排序的推荐阅读 |
| "素材"、"给 LLM" | 素材包 | 带编号来源摘要 + 原文片段 |

**CLI 兜底**：脚本的 `--mode auto` 通过 `intent_router.py` 正则匹配做自动路由，仅用于 CLI 直调场景。

### 4.4 源适配器注册表（`adapters/`）

| source_id | 匹配规则 | 适配器 |
|-----------|---------|--------|
| `wechat_url` | `mp.weixin.qq.com/s/` | wechat-article-for-ai |
| `web_url` | 通用 HTTP URL | baoyu-url-to-markdown |
| `video_url_youtube` | `youtube.com/watch`, `youtu.be/` | yt-dlp + ASR fallback |
| `video_url_bilibili` | `bilibili.com/video/`, `b23.tv/` | yt-dlp + ASR fallback |
| `video_url_douyin` | `douyin.com/video/` 等 | yt-dlp + Playwright 浏览器捕获 + ASR |
| `video_playlist_*` | YouTube/B站/抖音合集/频道 | yt-dlp playlist expansion |
| `local_file_md` | `.md`, `.markdown` | 本地读取 |
| `local_file_html` | `.html`, `.htm` | 本地读取 |
| `local_file_pdf` | `.pdf` | pypdf → markitdown fallback |
| `local_file_txt` | `.txt` | 纯文本读取 |
| `local_file_docx` | `.docx` | **V2.0** markitdown |
| `local_file_pptx` | `.pptx` | **V2.0** markitdown |
| `local_file_xlsx` | `.xlsx`, `.xls` | **V2.0** pandas + openpyxl |
| `local_file_epub` | `.epub` | **V2.0** ebooklib + beautifulsoup4 |
| `plain_text` | 直接文本粘贴 | 直接入库 |

## 5. 知识图谱

### 5.1 图谱形态

| 图谱 | 生成方式 | 使用方式 |
|------|---------|---------|
| `wiki/knowledge-graph.md` | Mermaid 静态图（Louvain 社区分组 + 度数剪枝，≤40 节点） | Obsidian 内直接渲染 |
| `wiki/graph-view.md` | 主图谱视角（仅 concepts/entities/domains/syntheses） | Obsidian 内渲染 + 过滤建议 |
| 域子图页面 | 按领域筛选的局部 Mermaid 图（`graph_layers.py`） | 每个域一个子图页面 |

图谱使用类型化边（supports/contradicts/answers/evolves/belongs_to/mentions），边权重当前统一为 1.0。社区检测使用简化 Louvain 算法。

### 5.2 图谱降噪

- `raw/articles/`、`sources/`、`briefs/`、`outputs/` 不进主图谱
- `concepts/entities` 需 ≥2 来源引用才进主图谱
- `auto_graph_include()` 自动根据页面类型、置信度、生命周期决定是否纳入图谱
- 域子图页面（`graph_layers.py`）提供按领域筛选的局部视图

## 6. 深度研究系统

### 6.1 九阶段深度调研

**触发词**：`深入研究 X` / `deep research X` / `系统分析 X`

```
Phase 0: 上下文收集（hot.md + 已有立场/问题）
Phase 1: 意图扩展（挖掘真实问题）
Phase 2: 假说形成（2-4 个可证伪假说）
Phase 3: Vault 证据分类（F/I/A 节点）
Phase 4: 联网研究（adaptive rounds，证据充分性门控）
Phase 5: 外部事实校准
Phase 6: 根本问题挖掘
Phase 7: 情景压力测试
Phase 8: 预验尸（failure mode analysis）
Phase 9: 收敛 + Why/What/How/Trace 报告
Phase 9.5: 质量门控（7 项红线检验 + 依赖链审查 + PDF 生成）
```

**Phase 9.5 质量门控**：报告写入后自动执行 7 项红线检验（决策者、边界条件、证据标签、反面证据、空洞、骑墙、诚实）和依赖链审查（结论置信度 ≤ 依赖链最低节点，Stable 结论须 3 跳内追溯到 Fact）。检验结果作为附录 A 写入报告末尾。随后自动生成 PDF。

**报告存储**：
- Markdown: `wiki/research/{slug}--report.md`
- PDF: `wiki/research/{slug}--report.pdf`

### 6.2 隐式触发检测

V2.0 新增：入库后自动分析编译结果和知识库状态，检测是否值得启动深度研究。

| 触发条件 | 说明 | 优先级 |
|---------|------|--------|
| 跨域碰撞 | insight 置信度 ≥ Working 且有 bridge_logic | 高/中 |
| 积累矛盾 | 3+ 条 disputed 声明在同一主题 | 高 |
| 高影响问题 | 开放问题与 3+ 现有页面有关键词重叠 | 中 |
| 知识缺口集群 | 3+ 条 gap 声明在同一领域 | 中 |
| 置信度断崖 | Supported/Stable 级别声明出现争议 | 高 |

## 7. Brief 认知压缩增强

Brief 页是知识库的核心浏览层。V2.0 通过增强编译提示词和 brief 渲染，让 brief 承担更完整的分析功能。

### 7.1 文章类型分类

每篇文章在编译时自动标注 `article_type`（七种类型），brief 的分析维度根据类型自适应：

| 类型 | 值 | 核心分析问题 |
|------|---|------------|
| 技术分析 | `tech_analysis` | 什么结构约束驱动了设计选择？ |
| 专家访谈 | `interview` | 什么前提驱动了结论？ |
| 方法论 | `methodology` | 哪些步骤是必要的？ |
| 理论建构 | `theory` | 概念创新是什么？ |
| 综述 | `review` | 分类框架和覆盖范围？ |
| 观点评论 | `opinion` | 推理链条严密吗？ |
| 产品评测 | `product` | 评估维度是否全面？ |

### 7.2 Brief 页面结构（增强后）

```
骨架（Generators + diagram）     ← 类型自适应：不同类型的"生成力"含义不同
数据（data_points）               ← 类型自适应：不同类型的"可锚定证据"不同
推演（正/负反馈环）                ← 类型自适应：不同类型的反馈环模式不同
失效信号（falsification）          ← 类型自适应：不同类型的失效条件不同
方法论评估（条件渲染）             ← 新增：仅当文章有明确方法论时显示
关键判断（claim_inventory）        ← 增强：含逻辑风险标记
隐性假设（单独分组）               ← 新增：从 assumption 类型 + hidden_assumptions 提取
跨域联想（cross_domain_insights）  ← 新增：持久化入库后影响报告中的高信号
适合谁读（who_should_read）        ← 新增：具体读者画像
为什么值得重访（why_revisit）      ← 新增：重访触发条件
原文入口
```

### 7.3 内容质量维度

参考 knowledge-mgmt-main 的 `/read` 分析框架，在编译阶段增加内容质量审查：

- **隐性假设识别**：提取作者未明说但论证依赖的前提
- **方法论评估**：评估研究/分析方法的优势、局限、替代方案
- **逻辑风险标注**：标记 claim 中的循环论证、过度推广、相关≠因果等逻辑风险

## 8. 间隔复习

V2.0 实现了 FSRS-6（Free Spaced Repetition Scheduler）间隔复习调度器，用于知识保持：

- **评分**：Again(1) / Hard(2) / Good(3) / Easy(4)
- **状态**：New → Learning → Review → Relearning
- **参数**：19 个 FSRS-6 默认参数，基于记忆稳定性（stability）和难度（difficulty）计算下次复习间隔

当前为**独立模块**，尚未与原子卡片系统集成。集成后原子卡片可自动成为复习卡片。

## 9. 入库后引导

V2.0 的入库后引导不再是"写入完成"，而是**对话式引导**：

```
入库完成：{标题} → {vault}

核心判断：{一句话结论}

关键要点（锚定原文）：
  - {claim_1} [证据类型]「原文引用」
  - {claim_2} [证据类型]「原文引用」

Brief PDF：[wiki/briefs/{slug}.pdf](file:///...)

跨域联想：
  - {概念} → {领域}：{bridge_logic}

知识提案：
  - 新建页面：{concepts} / {entities}
  - 建议链接：{existing_pages}

深度研究建议：（如触发条件满足）
  [高优先级] {trigger_type}: {topic}
    原因：{reason}
    建议假设：{hypothesis}

可以继续：追问 / 查看影响报告 / 启动深度研究 / 运行日常维护
```

## 10. 对话洞见捕获（V1.2.3）

V1.2.3 新增：LLM 在回答用户问题时自动判断问答价值，有价值的洞见自动写入 `wiki/outputs/`。

### 10.1 信号评分系统

**好问题信号**：

| 信号 | 判断规则 | 权重 |
|------|---------|------|
| Q1 概念澄清 | 问题暴露了知识库中概念的模糊定义或边界不清 | 2 分 |
| Q2 框架挑战 | 问题质疑了知识库中已有结论或假设 | 2 分 |
| Q3 跨域连接 | 问题将两个原本不相关的领域联系起来 | 1 分 |
| Q4 决策驱动 | 问题的答案将直接影响用户的决策或方向 | 1 分 |
| Q5 缺口暴露 | 问题指向了知识库中完全没有覆盖的领域 | 0.5 分 |

**好答案信号**：

| 信号 | 判断规则 | 权重 |
|------|---------|------|
| A1 多源综合 | 答案引用了 ≥ 3 个不同来源页面，且做了交叉分析 | 2 分 |
| A2 矛盾解决 | 答案澄清了知识库中两个或多个来源之间的矛盾 | 2 分 |
| A3 新连接发现 | 答案发现了知识库中未被记录的实体/概念之间的关系 | 1 分 |
| A4 决策框架 | 答案提供了可操作的决策框架或评估维度 | 1 分 |
| A5 边界明确 | 答案明确了某个概念的适用范围和不适用范围 | 0.5 分 |

**触发阈值**：总分 ≥ 3 分

### 10.2 输出格式

- 写入路径：`wiki/outputs/{date}--insight--{short-title}.md`
- Frontmatter：`mode: insight`, `lifecycle: temporary`, `origin: conversation`
- 末尾提示：`识别到有价值的洞见，暂存于 [[outputs/{slug}]]。说 "沉淀" 可升级为正式知识页。`

### 10.3 设计原则

- **用户无感知**：用户不需要了解"洞见识别"概念
- **LLM 自动判断**：在生成回答时自然判断，无额外 LLM 调用
- **一行轻量提示**：不打断回答流程
- **自然语言交互**：用户只需说"沉淀"即可确认

## 11. 深度研究智能触发（V1.2.3）

V1.2.3 新增：查询过程中，LLM 自动判断 vault 信息是否足够，不足时提示用户升级到深度研究。

### 11.1 触发信号

| 信号 | 判断规则 | 优先级 |
|------|---------|--------|
| D1 外部事实依赖 | 答案需要验证外部事实（最新数据、事件、政策），vault 中没有 | high |
| D2 多源矛盾 | 搜索 vault 后发现 ≥ 2 个来源对同一问题有矛盾回答 | high |
| D3 高风险决策 | 问题涉及重大决策（方向选择、架构决策、投资判断），且 vault 信息不充分 | high |
| D4 低覆盖度 | 搜索 vault 后发现 < 2 个相关页面，需要外部补充 | medium |
| D5 时间敏感 | 问题涉及"最新的"、"最近的"、"当前的"，vault 内容可能已过时 | medium |
| D6 用户追问 | 用户在同一个话题上追问 ≥ 3 轮，说明查询结果不满足需求 | low |

### 11.2 触发规则

满足以下任一条件时，建议升级到深度研究：
- 任一 high 优先级信号命中
- ≥ 2 个 medium 优先级信号命中
- 1 个 medium + 用户追问 ≥ 3 轮

### 11.3 与现有触发机制的关系

| 机制 | 时机 | 触发来源 | 输出 |
|------|------|---------|------|
| `deep_research_triggers.py` | 入库后 | compile payload 中的 claim/inference | 格式化的建议文本 |
| 对话中触发（V1.2.3） | 回答时 | vault 搜索结果 + 问题特征 | 一行轻量提示 |

两者互补：
- 入库触发：检测"已有知识中的结构性问题"（矛盾、缺口、置信度断崖）
- 对话触发：检测"用户当前问题超出 vault 能力"（外部依赖、低覆盖、时间敏感）

## 12. 自动维护（V1.2.3）

V1.2.3 新增：将维护流程分层自动化，减少用户手动触发的频率。

### 12.1 维护分层模型

| 层级 | 定义 | 用户感知 | 操作 |
|------|------|---------|------|
| L0 全自动 | 脚本执行，无需 LLM，无需用户确认 | 无 | 索引重建、log 追加 |
| L1 自动检查 + 通知 | 脚本收集 + LLM 判断，结果通知用户 | 一行提示 | 健康评分、stale 检测 |
| L2 自动检查 + 确认 | 脚本收集 + LLM 判断 + 展示建议，用户确认后执行 | 展示建议 + 等待确认 | 综合刷新、claim 演化 |
| L3 手动触发 | 用户主动发起 | 用户主动 | 深度研究、crystallize |

### 12.2 Review Sweep（自动清理）

对标桌面应用的 `sweepResolvedReviews()`，自动识别并清理已过时的待处理 output。

**规则 R1 — missing-page 类型**：
- 条件：output 的 frontmatter 含 `mode: insight` 或 `type: query`
- 逻辑：从 output 内容中提取引用的 `[[页面名]]`，如果所有引用页面都已存在 → 标记为 resolved

**规则 R2 — 被覆盖的 output**：
- 条件：多个 output 标题相同或高度相似
- 逻辑：按 created 日期排序，保留最新的，旧的标记为 resolved

**规则 R3 — LLM 语义判断**（对规则 R1/R2 剩余项）：
- 批次参数：batch = 20, max_batches = 3
- 提前终止：某批次 resolved = 0 则停止
- 保守策略：contradiction/suggestion 类型默认保持 pending

### 12.3 自动维护建议

`stale_report.py --auto-suggest` 输出结构化建议 JSON：

```json
{
  "suggestions": [
    {
      "type": "low_health_score|stale_pages|pending_outputs|...",
      "severity": "high|medium|low",
      "reason": "具体原因",
      "suggested_action": "建议操作",
      "suggested_command": "对应脚本命令"
    }
  ],
  "health_score": 72,
  "pending_outputs": 12,
  "ingest_count": 30
}
```

**展示规则**：
- high severity → 对话开头主动展示
- medium severity → 入库完成后自然时机展示
- low severity → 不主动提示，用户问"状态"时展示

### 12.4 入库后自动检查

入库完成后自动执行以下检查（L1 层级）：
- 健康评分检查（评分 < 80 或下降 ≥ 5 分时通知）
- 综合页 Freshness 检查（新来源晚于综合页时建议刷新）
- 审核队列积压检查（≥ 10 个通知，≥ 20 个高优先通知）
- 入库计数里程碑（每 10 篇素材建议 lint）

## 10. 环境变量

以下变量仅在 `--api-compile` 模式下需要。默认 prepare-only 模式不依赖任何外部 API。

| 变量 | 用途 | 仅 api-compile 需要 |
|------|------|:-------------:|
| `KWIKI_API_KEY` | LLM API Key | 是 |
| `KWIKI_COMPILE_MODEL` | LLM 模型名 | 是 |
| `KWIKI_API_BASE` | LLM API 基地址 | 是 |
| `KWIKI_COMPILE_TEMPERATURE` | 编译温度（默认 0.2） | 是 |
| `KWIKI_COMPILE_MAX_TOKENS` | 最大 token（默认 2200） | 是 |
| `KWIKI_COMPILE_MOCK_FILE` | Mock 编译 JSON 路径（测试用） | 是 |
| `KWIKI_WEB_ADAPTER_BIN` | Web 适配器命令 | 是 |
| `KWIKI_VIDEO_ADAPTER_BIN` | 视频适配器命令 | 是 |
| `KWIKI_VIDEO_COOKIES_FROM_BROWSER` | 浏览器 cookie 来源 | 是 |
| `KWIKI_VIDEO_COOKIES_FILE` | Cookie 文件路径 | 是 |
| `KWIKI_ASR_MODEL` | ASR 模型（默认 small） | 是 |
| `KWIKI_NODE_BIN` | Node.js 路径（抖音浏览器兜底） | 是 |
| `KWIKI_DOUYIN_HEADLESS` | 抖音浏览器无头模式（默认 1） | 是 |
| `KWIKI_WECHAT_TOOL_DIR` | wechat-article-for-ai 路径 | 是 |
| `KWIKI_DEPS_DIR` | Python 依赖目录 | 是 |

所有变量有 `WECHAT_WIKI_*` / `WECHAT_ARTICLE_*` 旧名兼容映射（通过 `env_compat.py`）。

## 11. 依赖

### 11.1 依赖分组

| 分组 | 包 | 用途 |
|------|---|------|
| **core** | 无（全部 stdlib） | Python 运行时 |
| **test** | pytest, pytest-mock | 测试套件 |
| **wechat** | chardet（+ wechat-article-for-ai 外部依赖） | 微信公众号 |
| **video** | yt-dlp | 视频字幕提取 |
| **video_asr** | faster-whisper | 无字幕视频 ASR |
| **pdf** | pypdf | 本地 PDF |
| **format_normalization** | markitdown, pandas, openpyxl, ebooklib, beautifulsoup4 | DOCX/PPTX/XLSX/EPUB 格式归一化 |
| **web** | baoyu-url-to-markdown（npm） | 通用网页 |

### 11.2 依赖检查工具

```powershell
python scripts/check_deps.py                      # 仅检查
python scripts/check_deps.py --install             # 检查 + 自动安装
python scripts/check_deps.py --install --china     # 中国镜像安装
python scripts/check_deps.py --install --group=format_normalization  # 格式归一化组
```

镜像地址：

| 镜像 | 用途 | 地址 |
|------|------|------|
| 清华 PyPI | pip 包 | `https://pypi.tuna.tsinghua.edu.cn/simple` |
| npmmirror | npm 包 | `https://registry.npmmirror.com` |
| ghfast.top | GitHub Release | `https://ghfast.top/` |
| hf-mirror | Hugging Face 模型 | `https://hf-mirror.com` |

## 12. 测试

```powershell
python -m pytest tests/ -q
```

274 tests passing。覆盖：源适配器、流水线核心、页面构建器、验证门控、风险审批、原子卡片、深度研究触发、间隔复习、图层层、格式归一化路由。
