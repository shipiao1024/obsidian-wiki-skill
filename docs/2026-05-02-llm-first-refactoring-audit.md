# LLM-First 架构改造审计报告

日期：2026-05-02

## 已完成（本轮）

### Prompt 约束体系（8 个文件）
- `references/prompts/lint_semantic.md` — 健康检查语义分析
- `references/prompts/claim_evolution.md` — 主张关系分析
- `references/prompts/synthesis_refresh.md` — 综合页内容生成
- `references/prompts/review_queue.md` — 审核队列排序
- `references/prompts/ingest_impact.md` — 入库影响分析
- `references/prompts/ingest_compile_prompt_v2.md` — 入库编译
- `references/prompts/query_synthesis.md` — 查询综合与验证
- `references/prompts/research_hypothesis.md` — 研究假说形成与校准

### 行为指南更新（4 个文件）
- `references/maintenance-guide.md` — 4 个维护场景，三阶段模式
- `references/ingest-guide.md` — Step 5 拆分为 5a/5b/5c，引用 ingest_impact.md 和 ingest_compile_prompt_v2.md
- `references/query-guide.md` — 来源可信度表、高精度验证、引用 query_synthesis.md
- `references/research-guide.md` — 假说卡 JSON 格式、引用 research_hypothesis.md

### 脚本改造（P0 — 移除语义判断）
- `scripts/wiki_lint.py` — 移除 CONFLICT_PAIRS、claims_conflict()、claim_conflict_records()；新增 --collect-only / --apply
- `scripts/claim_evolution.py` — 移除关键词匹配和关系分类；新增 --collect-only / --apply
- `scripts/review_queue.py` — 移除 claim_conflict_records 依赖；新增 --collect-only / --apply
- `scripts/refresh_synthesis.py` — 移除域特定 NOISE/PREFERRED_PATTERNS；新增 --collect-only / --apply；旧逻辑移至 refresh_synthesis_legacy.py
- `scripts/pipeline/ingest_orchestrator.py` — 移除自动 claim evolution 重建

### 术语清理
- 所有 references/ 文件：宿主 Agent → 你
- 所有 scripts/ docstring：host-agent → LLM/你
- SKILL.md 索引：8 个 prompt 文件全部列出

## 待办清单（全部 P0 已完成）

### P0 #4: delta_compile.py — 域特定硬编码

位置：lines 26-59
问题：与 refresh_synthesis.py 相同的 NOISE_PATTERNS 和 PREFERRED_PATTERNS。
方案：参照 refresh_synthesis.py 改造模式，新增 --collect-only / --apply。

### P0 #5: ingest_report.py — 标题关键词判断相关来源 ✅

位置：lines 99-122
问题：用标题词项重叠（≥2 个匹配）判断相关来源数量。
方案：已移除关键词逻辑；新增 `collect_ingest_data()` Phase 1 函数，收集所有来源元数据（slug、title、domains、quality、date、core_summary）供 LLM 语义分析。新增 `--collect-only / --apply / --output` CLI。`build_ingest_impact_report()` 不再做相关来源判断，改为输出 `existing_sources_count`（纯计数）。

### P0 #6: query-guide.md 明确 contradict.py 约束 ✅

位置：pipeline/output/contradict.py line 116
问题：硬编码否定模式 ["并非", "不是", "错误", ...] 用于找"潜在对立面"。
方案：已在 query-guide.md Step 3 中明确来源可信度表、高精度验证规则、多来源冲突处理；反驳分析由 LLM 按 query_synthesis.md 约束完成。

### P4: deep_research.py 证据分类预排序 ✅

位置：lines 116-158
问题：collect_vault_evidence() 用关键词判断 confirming/contradicting/neutral。
影响：仅为预排序，LLM 在 Phase 3 按 F/I/A 重新分类。
方案：已在 research-guide.md Phase 3 中明确："你将发现分类为 [Fact]、[Inference]、[Assumption]"，脚本预排序仅为辅助，LLM 按 research_hypothesis.md 证据分类表重新分类。

### P5: deep_research_triggers.py 触发检测

位置：全文
问题：5 种触发条件全部脚本实现。
影响：当前可接受（建议性质，LLM 最终决定）。
方案：长期改为 --collect-only 输出数据，由 LLM 判断。

## 接口模式总结

所有维护脚本统一三阶段接口：

```powershell
# Phase 1: 脚本收集数据
python scripts/<script>.py --vault <vault> --collect-only [--output path.json]

# Phase 2: LLM 分析（在对话中完成）
# LLM 读取 JSON，按 references/prompts/<prompt>.md 约束分析

# Phase 3: 脚本执行写入
python scripts/<script>.py --vault <vault> --apply <result.json>
```

已支持的脚本：wiki_lint.py, claim_evolution.py, review_queue.py, refresh_synthesis.py, delta_compile.py, ingest_report.py
待评估（长期）：deep_research_triggers.py（P5）
