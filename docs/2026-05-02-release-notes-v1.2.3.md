# 2026-05-02 Release Notes — V1.2.3

版本：`2026.05.02-v2-features-v1.2.3`
基线：`V1.2.2 (Optimization & Hardening)`

这份 release notes 对应 Obsidian Wiki Skill 的 V2 功能升级。核心目标是实现四个能力：对话洞见捕获、深度研究智能触发、维护流程自动化、智能检索，同时保持用户零感知、零负担的设计原则。

## 本版新增功能

### 1. 洞见识别（Insight Detection）

**用户价值**：在日常对话中，LLM 自动识别有价值的问答对，用户只需说"沉淀"即可升级为正式知识页。

**工作方式**：
- LLM 在生成回答时自动判断（无额外调用）
- 10 个信号评分：好问题（概念澄清、框架挑战、跨域连接、决策驱动、缺口暴露）+ 好答案（多源综合、矛盾解决、新连接发现、决策框架、边界明确）
- 总分 ≥ 3 分时触发，自动写入 `wiki/outputs/`
- 回答末尾一行提示：`识别到有价值的洞见，暂存于 [[outputs/{slug}]]。说 "沉淀" 可升级为正式知识页。`

**用户操作**：
- 说"沉淀" → 执行升级流程
- 什么都不说 → 保留在 outputs/，下次维护时统一处理

### 2. 深度研究轻量触发（Lightweight Deep Research Trigger）

**用户价值**：当 vault 内信息不足以回答问题时，自动提示用户升级到深度研究。

**工作方式**：
- 6 个触发信号：外部事实依赖、多源矛盾、高风险决策、低覆盖度、时间敏感、用户追问
- 分级触发：任一 high 命中 / ≥ 2 个 medium / 1 个 medium + 追问 ≥ 3 轮
- 先用 vault 信息完整回答，末尾一行提示

**用户操作**：
- 说"深入研究" → 进入 9 阶段深度研究协议
- 什么都不说 → 当前回答已足够

### 3. 自动维护（Automated Maintenance）

#### 3.1 Review Sweep（自动清理）

**用户价值**：自动识别并清理已过时的待处理 output，减少人工审核负担。

**工作方式**：
- R1 规则：所有引用页面已存在 → 自动标记为已解决
- R2 规则：同标题多个 output，保留最新 → 旧的自动标记为已解决
- R3 规则：对剩余项做 LLM 语义判断（保守策略，不确定时保持 pending）
- 批次控制：每批 20 项，最多 3 批，提前终止

**用户操作**：
- 说"sweep" → 执行自动清理
- 查看结果：`自动清理完成：规则匹配 {N1} 项，语义判断 {N2} 项，保留待审 {N3} 项`

#### 3.2 自动维护建议

**用户价值**：基于 vault 当前状态自动生成维护建议，按严重程度分级展示。

**工作方式**：
- `stale_report.py --auto-suggest` 输出结构化建议 JSON
- 7 种建议类型：健康评分低、stale 页面、pending outputs、重复 output、入库里程碑、维护逾期、stale 综合页
- 3 级严重程度：
  - high → 对话开头主动展示
  - medium → 入库后自然时机展示
  - low → 用户问"状态"时展示

**用户操作**：
- 说"状态" / "维护建议" → 查看所有建议
- 说对应的建议操作（如"lint"、"review"）→ 执行

#### 3.3 入库后自动检查

**用户价值**：入库完成后自动检查知识库健康状态，无需手动触发。

**工作方式**：
- 健康评分检查（评分 < 80 或下降 ≥ 5 分时通知）
- 综合页 Freshness 检查（新来源晚于综合页时建议刷新）
- 审核队列积压检查（≥ 10 个通知，≥ 20 个高优先通知）
- 入库计数里程碑（每 10 篇素材建议 lint）

**用户操作**：
- 查看入库报告末尾的自动检查结果
- 说对应命令（"lint"、"刷新综合"、"review"）→ 执行

### 4. 智能检索（Smart Retrieval）

**用户价值**：知识库规模增大后，查询不再依赖 LLM 逐页 grep 搜索，而是通过语义索引快速定位最相关内容。

**工作方式**：
- 入库后自动构建语义索引（`wiki/semantic-index.json`），包含 domain、concept、entity、claim、relationship 的结构化数据
- 查询时运行 `wiki_retrieve.py`，从索引中评分排序，输出结构化上下文包
- LLM 直接消费预排序的结果，无需自己扫描整个 vault
- 评分综合：标题匹配、声明匹配、域匹配、置信度、页面状态、时效性

**用户操作**：
- 查询流程对用户透明，无需了解内部机制
- 入库后自动重建索引，无需手动触发
- 说"重建索引" → 手动触发 `wiki_index_v2.py --rebuild`

**解决的问题**：
- 入库几百篇后，LLM grep 搜索噪声大、效率低
- 每次查询重复扫描相同页面，浪费上下文窗口
- 无法按置信度、时效性排序搜索结果

## 设计原则

本版所有功能遵循统一设计准则：**用户无感知，零负担**

- LLM 自动判断，用户只做最终确认
- 一行轻量提示，不打断回答流程
- 不弹出确认框，不强制用户了解内部机制
- 保守策略：不确定时不触发、不删除、不修改

## 本版改动文件

| 文件 | 改动类型 |
|------|---------|
| `references/prompts/insight_detection.md` | 新增 |
| `references/prompts/review_sweep.md` | 新增 |
| `references/query-guide.md` | 修改 |
| `references/interaction.md` | 修改 |
| `references/research-guide.md` | 修改 |
| `references/ingest-guide.md` | 修改 |
| `references/maintenance-guide.md` | 修改 |
| `scripts/review_queue.py` | 修改 |
| `scripts/stale_report.py` | 修改 |
| `SKILL.md` | 修改 |
| `scripts/wiki_index_v2.py` | 新增 |
| `scripts/wiki_retrieve.py` | 新增 |
| `docs/SPEC.md` | 修改 |
| `docs/product-overview.html` | 修改 |
| `docs/2026-05-02-v2-design-spec.md` | 修改 |

## 本版已验证内容

- [x] 洞见识别信号评分逻辑（10 信号，加权评分，阈值 ≥ 3）
- [x] 深度研究触发信号（D1-D6，分级触发规则）
- [x] Review sweep R1/R2 规则匹配逻辑
- [x] `--auto-suggest` 输出 JSON schema
- [x] 入库后自动检查 4 项检查逻辑
- [ ] 集成测试（待执行）

## 当前使用约束

- 洞见识别依赖 LLM 在生成回答时自然判断，无额外 LLM 调用
- 深度研究触发信号（D1-D6）与原有三要素触发条件互补，不替代
- Review sweep 的 R3（LLM 语义判断）需要 LLM 执行 `references/prompts/review_sweep.md` 约束
- `--auto-suggest` 输出的建议按严重程度分级展示，不自动执行修复
- 入库后自动检查追加入库报告末尾，不打断主流程
- 同一轮回答最多追加一行提示（洞见识别和深度研究不同时触发）

## 推荐阅读顺序

1. `README.md`
2. `references/setup.md`
3. `SKILL.md`
4. `docs/2026-05-02-version-lock-v1.2.3.md`
5. `docs/2026-05-02-v2-design-spec.md`（详细设计规格）

## 后续版本建议

- 执行集成测试，验证端到端流程
- 收集用户反馈，调整信号权重和触发阈值
- 优化 `--auto-suggest` 的健康评分算法
- 考虑增加用户偏好配置（如关闭某些自动检查）
