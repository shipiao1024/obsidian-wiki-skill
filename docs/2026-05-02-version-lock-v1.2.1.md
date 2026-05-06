# 2026-05-02 Version Lock — v1.2.1 (LLM-First Architecture)

版本名：`1.2.1-llm-first`
基线版本：`Obsidian-wiki-skill-V1.2`
锁定日期：2026-05-02

## 本版核心变更：LLM-First 架构改造

**设计原则**：脚本是手和脚，LLM 是大脑。脚本处理 I/O 和确定性任务，LLM 负责理解、判断、决策、综合。

**统一三阶段模式**：
```
Phase 1: 脚本收集数据  (--collect-only → JSON)
Phase 2: LLM 语义分析  (读 JSON + Prompt 约束 → 结构化结果)
Phase 3: 脚本执行写入  (--apply result.json → wiki 页面)
```

---

## 一、Prompt 约束体系（8 个文件）

| 文件 | 内容 | 引用者 |
|------|------|--------|
| `references/prompts/lint_semantic.md` | 健康检查语义分析 | maintenance-guide |
| `references/prompts/claim_evolution.md` | 主张关系分析 | maintenance-guide |
| `references/prompts/synthesis_refresh.md` | 综合页内容生成 | maintenance-guide |
| `references/prompts/review_queue.md` | 审核队列排序 | maintenance-guide |
| `references/prompts/ingest_impact.md` | 入库影响分析 | ingest-guide |
| `references/prompts/ingest_compile_prompt_v2.md` | 入库编译 | ingest-guide |
| `references/prompts/query_synthesis.md` | 查询综合与验证 | query-guide |
| `references/prompts/research_hypothesis.md` | 研究假说形成与校准 | research-guide |

## 二、脚本改造（6 个核心脚本）

### 已完成三阶段改造

| 脚本 | 移除的语义逻辑 | 新增 Phase 1 | 新增 Phase 3 |
|------|--------------|-------------|-------------|
| `wiki_lint.py` | CONFLICT_PAIRS、claims_conflict()、claim_conflict_records() | collect_lint_data() | apply_lint_result() |
| `claim_evolution.py` | match_claims_by_keywords()、classify_relationship() | collect_all_claims()、collect_claims_json() | apply_claim_evolution_result() |
| `review_queue.py` | claim_conflict_records 依赖 | collect_review_data() | apply_review_result() |
| `refresh_synthesis.py` | NOISE_PATTERNS、PREFERRED_PATTERNS、RAW_SECTION_HEADINGS | collect_synthesis_data() | apply_synthesis_result() |
| `delta_compile.py` | NOISE_PATTERNS、PREFERRED_PATTERNS、RAW_SECTION_HEADINGS | collect_delta_data() | apply_delta_result() |
| `ingest_report.py` | 标题关键词重叠判断相关来源 | collect_ingest_data() | apply + LLM result merge |

### Legacy 兼容文件

| 文件 | 内容 |
|------|------|
| `scripts/refresh_synthesis_legacy.py` | 旧域特定启发式逻辑（综合刷新） |
| `scripts/delta_compile_legacy.py` | 旧域特定启发式逻辑（增量编译） |

### 其他脚本改动

| 脚本 | 改动 |
|------|------|
| `pipeline/ingest_orchestrator.py` | 移除自动 claim evolution 重建，改为 LLM 驱动 |

## 三、行为指南更新（4 个文件）

| 文件 | 改动 |
|------|------|
| `references/maintenance-guide.md` | 4 个维护场景全部更新为三阶段模式 |
| `references/ingest-guide.md` | Step 5 拆分为 5a/5b/5c（脚本收集 → LLM 分析 → 展示报告）；Step 2 引用 ingest_compile_prompt_v2.md |
| `references/query-guide.md` | 来源可信度表、高精度验证规则、多来源冲突处理；引用 query_synthesis.md |
| `references/research-guide.md` | 假说卡 JSON 格式、证据分类表、压力测试约束；引用 research_hypothesis.md |

## 四、术语清理

| 范围 | 改动 |
|------|------|
| 所有 references/ 文件 | "宿主 Agent" → "你" |
| 所有 scripts/ docstring | "host-agent" → "LLM/你" |
| SKILL.md | "Host-Agent" → "你（Claude Code）" |

## 五、产品文档同步

| 文件 | 改动 |
|------|------|
| `docs/product-overview.html` | V2.0 → V2.1：新增三阶段模式 Slide、8 Prompt 约束卡片、术语同步 |
| `docs/2026-05-02-llm-first-refactoring-audit.md` | 完整改造审计报告 |

## 六、全量改动文件清单

### scripts/ 目录

| 文件 | 改动类型 |
|------|---------|
| `scripts/wiki_lint.py` | 重构：移除语义判断，新增 --collect-only/--apply |
| `scripts/claim_evolution.py` | 重构：移除关键词匹配，新增 --collect-only/--apply |
| `scripts/review_queue.py` | 重构：移除 claim_conflict_records 依赖，新增 --collect-only/--apply |
| `scripts/refresh_synthesis.py` | 重构：移除域特定模式，新增 --collect-only/--apply |
| `scripts/refresh_synthesis_legacy.py` | **新增**：旧启发式逻辑 |
| `scripts/delta_compile.py` | 重构：移除域特定模式，新增 --collect-only/--apply |
| `scripts/delta_compile_legacy.py` | **新增**：旧启发式逻辑 |
| `scripts/pipeline/ingest_orchestrator.py` | 移除自动 claim evolution 重建 |
| `scripts/pipeline/ingest_report.py` | 重构：移除关键词相关来源判断，新增 collect_ingest_data() + CLI |
| `scripts/pipeline/deep_research.py` | 术语更新 |
| `scripts/pipeline/output/deep_research.py` | 术语更新 |

### references/ 目录

| 文件 | 改动类型 |
|------|---------|
| `references/prompts/lint_semantic.md` | 已有（上一版本） |
| `references/prompts/claim_evolution.md` | 已有（上一版本） |
| `references/prompts/synthesis_refresh.md` | 已有（上一版本） |
| `references/prompts/review_queue.md` | 已有（上一版本） |
| `references/prompts/ingest_impact.md` | 已有（上一版本） |
| `references/prompts/ingest_compile_prompt_v2.md` | 已有（上一版本） |
| `references/prompts/query_synthesis.md` | **新增** |
| `references/prompts/research_hypothesis.md` | **新增** |
| `references/maintenance-guide.md` | 更新为三阶段模式 |
| `references/ingest-guide.md` | Step 5 拆分 + ingest_compile_prompt_v2 引用 |
| `references/query-guide.md` | 来源可信度 + 高精度验证 + query_synthesis 引用 |
| `references/research-guide.md` | 假说卡 + 证据分类 + research_hypothesis 引用 |
| `references/interaction.md` | 术语清理 + query_synthesis 引用 |
| `references/workflow.md` | 术语清理 |
| `references/deep-research-protocol.md` | 术语清理 |
| `references/autoresearch-protocol.md` | 术语清理 |
| `references/setup.md` | 术语清理 |
| `references/review-scripts.md` | 术语清理 |
| `references/pipeline-scripts.md` | 术语清理 |

### docs/ 目录

| 文件 | 改动类型 |
|------|---------|
| `docs/product-overview.html` | V2.0 → V2.1 同步 |
| `docs/2026-05-02-llm-first-refactoring-audit.md` | **新增**：完整审计报告 |

### SKILL.md

| 文件 | 改动类型 |
|------|---------|
| `SKILL.md` | LLM 约束 Prompt 表新增 query_synthesis.md + research_hypothesis.md |

## 七、待办事项（后续版本）

| 优先级 | 项目 | 状态 |
|--------|------|------|
| P5 | deep_research_triggers.py 触发检测改为 --collect-only 输出 | 长期，当前可接受 |

## 八、接口模式总结

所有维护脚本统一三阶段接口：

```powershell
# Phase 1: 脚本收集数据
python scripts/<script>.py --vault <vault> --collect-only [--output path.json]

# Phase 2: LLM 分析（在对话中完成）
# LLM 读取 JSON，按 references/prompts/<prompt>.md 约束分析

# Phase 3: 脚本执行写入
python scripts/<script>.py --vault <vault> --apply <result.json>
```

已支持脚本：wiki_lint.py, claim_evolution.py, review_queue.py, refresh_synthesis.py, delta_compile.py, ingest_report.py

---

## 复制基线命令

```powershell
# 在 D:\AI\obsidian-wiki\ 目录下执行
xcopy "Obsidian-wiki-skill-V1.2" "Obsidian-wiki-skill-V1.2.1" /E /I /H /Y
```
