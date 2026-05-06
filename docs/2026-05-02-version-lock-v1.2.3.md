# 2026-05-02 Version Lock — V1.2.3 (V2 Features: Insight Detection + Deep Research Triggers + Auto Maintenance + Smart Retrieval)

版本名：`2026.05.02-v2-features-v1.2.3`
基线版本：`V1.2.2 (Optimization & Hardening)`

## 本版新增内容（相对于 V1.2.2）

### 1. 洞见识别（Insight Detection）

**设计准则**：用户无感知，零负担 — LLM 自动判断，用户只需说"沉淀"确认。

- 新增 `references/prompts/insight_detection.md`：10 个信号评分系统
  - 好问题信号（5 个）：概念澄清(2)、框架挑战(2)、跨域连接(1)、决策驱动(1)、缺口暴露(0.5)
  - 好答案信号（5 个）：多源综合(2)、矛盾解决(2)、新连接发现(1)、决策框架(1)、边界明确(0.5)
  - 触发阈值：总分 ≥ 3 分
- 修改 `references/query-guide.md`：
  - Step 3 新增"洞见识别"段（判断时机、依据、触发后操作）
  - Step 5 新增"洞见识别触发时的写入"逻辑
  - Step 5 更新"沉淀提议"（区分洞见触发 vs 普通写入）
- 修改 `references/interaction.md`：新增"对话中的轻量引导"段
  - 洞见识别引导模板
  - 深度研究引导模板
  - 设计原则（用户无感知、一行提示、自然语言交互、不重复）

**输出格式**：
- 写入路径：`wiki/outputs/{date}--insight--{short-title}.md`
- Frontmatter：`mode: insight`, `lifecycle: temporary`, `origin: conversation`
- 末尾提示：`识别到有价值的洞见，暂存于 [[outputs/{slug}]]。说 "沉淀" 可升级为正式知识页。`

### 2. 深度研究轻量触发（Lightweight Deep Research Trigger）

- 修改 `references/query-guide.md`：新增 Step 6 深度研究引导
  - 6 个触发信号（D1-D6）：外部事实依赖(high)、多源矛盾(high)、高风险决策(high)、低覆盖度(medium)、时间敏感(medium)、用户追问(low)
  - 触发规则：任一 high 命中 / ≥ 2 个 medium / 1 个 medium + 追问 ≥ 3 轮
  - 末尾提示模板：`这个问题涉及 [外部最新信息 / 来源矛盾 / vault 覆盖不足]，当前回答可能不完整。说 "深入研究" 可启动系统调研。`
- 修改 `references/research-guide.md`：新增"对话中自动触发"段
  - 与原有三要素触发条件（战略重要性 + 外部现实依赖 + 框架风险）互补
  - 对话触发信号表（D1-D6）

### 3. 自动维护（Automated Maintenance）

#### 3.1 Review Sweep（自动清理）

- 新增 `references/prompts/review_sweep.md`：Review sweep LLM 约束
  - R1 规则（missing-page）：所有引用页面已存在 → auto-resolved
  - R2 规则（superseded）：同标题多个 output，保留最新 → 旧的 auto-resolved
  - R3 规则（LLM 语义判断）：对 R1/R2 剩余项做保守判断
  - 批次控制：batch=20, max_batches=3, 提前终止
- 修改 `scripts/review_queue.py`：新增 `--sweep`、`--apply-sweep` 模式
  - `--sweep`：收集数据 + 规则匹配（R1/R2）+ 分批输出
  - `--apply-sweep`：执行 LLM sweep 决策（resolved → archived）
  - 新增函数：`_existing_wiki_pages()`、`_extract_wikilinks()`、`_rule_match_sweep()`、`collect_sweep_data()`、`apply_sweep_result()`
- 修改 `references/maintenance-guide.md`：新增场景 5 Review Sweep

#### 3.2 自动维护建议

- 修改 `scripts/stale_report.py`：新增 `--auto-suggest` 模式
  - 输出结构化 JSON：suggestions 数组 + health_score + pending_outputs + ingest_count
  - 7 种建议类型：low_health_score、stale_pages、pending_outputs、duplicate_outputs、ingest_milestone、maintenance_overdue、stale_synthesis
  - 3 级严重程度：high（对话开头主动展示）、medium（入库后自然时机）、low（用户问"状态"时展示）
  - 新增函数：`_compute_health_score()`、`_count_pending_outputs()`、`_last_maintenance_date()`、`_count_ingest_records()`、`build_auto_suggestions()`
- 修改 `references/maintenance-guide.md`：新增场景 6 自动维护建议

#### 3.3 入库后自动检查

- 修改 `references/ingest-guide.md`：新增"入库后自动检查"段
  - 健康评分检查（评分 < 80 或下降 ≥ 5 分时通知）
  - 综合页 Freshness 检查（新来源晚于综合页时建议刷新）
  - 审核队列积压检查（≥ 10 个通知，≥ 20 个高优先通知）
  - 入库计数里程碑（每 10 篇素材建议 lint）
  - 执行约定：追加入库报告末尾，不打断主流程

### 4. 智能检索（Smart Retrieval）

**设计准则**：脚本做机械检索，LLM 做语义判断 — 解决大规模知识库中 LLM 认知负担过重的问题。

- 新增 `scripts/wiki_index_v2.py`：语义索引构建 + 查询
  - `--rebuild`：扫描 wiki/ 全部页面，构建 `semantic-index.json`
  - `--query`：按概念/域名称查询索引
  - 索引结构：domains、concepts、entities、claims、relationships、sources、stats
  - 提取逻辑：frontmatter 元数据、关键判断段声明、主题域链接、stance 支持/反对关系
- 新增 `scripts/wiki_retrieve.py`：智能检索脚本
  - 解析查询 → 提取核心概念
  - 查语义索引 → 匹配 domain、concept、entity、claim
  - 评分排序 → 综合标题匹配、声明匹配、域匹配、置信度、时效性
  - 读 top-k 页面 → 提取关键段落（核心摘要、关键判断、支持/反对证据）
  - 输出结构化上下文包（JSON），LLM 直接消费
  - 参数：`--top-k`（返回页数）、`--read`（深度阅读页数）、`--types`（限定类型）
- 修改 `references/query-guide.md`：Step 2 重设计
  - 首选 `wiki_retrieve.py` 智能检索
  - 补充 `wiki_index_v2.py --query` 语义索引查询
  - Grep 仅作兜底（索引不可用时）
  - 更新上下文效率策略

**解决的核心问题**：
- 入库几百篇后，LLM 无法高效搜索整个 vault
- grep 搜索噪声大，无法按置信度、时效性排序
- 每次查询重复扫描相同页面，浪费上下文窗口
- 语义索引提供结构化入口，检索脚本提供预排序结果

**设计约束**：
- 语义索引入库后自动重建，确保检索结果反映最新内容
- 检索结果包含 page_contents（关键段落），通常不需要再读全文
- Grep 兜底确保索引不可用时系统仍可工作

## 全量改动文件清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `references/prompts/insight_detection.md` | **新增** | 洞见识别 prompt 约束（10 信号 + 评分 + 触发规则） |
| `references/prompts/review_sweep.md` | **新增** | Review sweep LLM 约束（R1/R2 规则 + 语义判断） |
| `references/query-guide.md` | 修改 | Step 3 洞见识别 + Step 5 洞见写入 + Step 6 深度研究引导 |
| `references/interaction.md` | 修改 | 新增"对话中的轻量引导"段（洞见 + 深度研究模板） |
| `references/research-guide.md` | 修改 | 新增"对话中自动触发"段（D1-D6 信号表） |
| `references/ingest-guide.md` | 修改 | 新增"入库后自动检查"段（4 项检查 + 执行约定） |
| `references/maintenance-guide.md` | 修改 | 新增场景 5 Review Sweep + 场景 6 自动维护建议 + 更新总览表 |
| `scripts/review_queue.py` | 修改 | 新增 `--sweep`、`--apply-sweep`、`--batch-size`、`--max-batches` 参数 |
| `scripts/stale_report.py` | 修改 | 新增 `--auto-suggest` 模式 + 5 个辅助函数 |
| `SKILL.md` | 修改 | 更新触发条件 + 任务识别 + 脚本入口 + 参考文件索引 |
| `scripts/wiki_index_v2.py` | **新增** | 语义索引构建 + 查询（`--rebuild` / `--query`） |
| `scripts/wiki_retrieve.py` | **新增** | 智能检索（语义索引评分排序 + 结构化上下文包输出） |
| `docs/SPEC.md` | 修改 | 更新查询架构（§4.3）+ 新增脚本条目 |
| `docs/product-overview.html` | 修改 | 新增智能检索 feature card + hero badge |
| `docs/2026-05-02-v2-design-spec.md` | 修改 | 新增 Phase 4 智能检索设计规格 |

## 设计原则

本版所有功能遵循统一设计准则：**用户无感知，零负担**

- LLM 自动判断（洞见识别、深度研究触发、维护建议）
- 用户只做最终确认（说"沉淀"/"深入研究"/"lint"等）
- 一行轻量提示，不打断回答流程
- 不弹出确认框，不强制用户了解内部机制
- 保守策略：不确定时不触发、不删除、不修改

## 当前使用约束

- 洞见识别依赖 LLM 在生成回答时自然判断，无额外 LLM 调用
- 深度研究触发信号（D1-D6）与原有三要素触发条件互补，不替代
- Review sweep 的 R3（LLM 语义判断）需要 LLM 执行 `references/prompts/review_sweep.md` 约束
- `--auto-suggest` 输出的建议按严重程度分级展示，不自动执行修复
- 入库后自动检查追加入库报告末尾，不打断主流程
- 同一轮回答最多追加一行提示（洞见识别和深度研究不同时触发）

## 验收标准

- [x] 洞见识别：对话中引用 ≥ 3 来源的综合回答自动写入 outputs/，末尾有提示
- [x] 深度研究触发：vault 覆盖不足时末尾有升级提示
- [x] 健康检查：入库后自动评分，评分下降时有提示
- [x] 审核队列：outputs/ 积压 ≥ 10 时有提示，sweep 自动清理已失效项
- [x] 维护建议：`--auto-suggest` 输出结构化 JSON
- [x] 智能检索：`wiki_retrieve.py` 输出结构化上下文包，query-guide.md Step 2 使用新流程
- [ ] 所有测试通过（待集成测试）

## 与上一版本的兼容性

- 所有新增功能为增量添加，不破坏现有工作流
- 现有 `--collect-only`、`--apply` 模式不受影响
- 现有维护场景（健康检查、主张演化、综合刷新、审核队列）行为不变
- 新增的自动检查和建议为 L1/L2 层级，不自动执行修改操作
