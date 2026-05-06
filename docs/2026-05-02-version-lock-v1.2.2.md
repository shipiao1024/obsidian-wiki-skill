# 2026-05-02 Version Lock — v1.2.2 (Optimization & Hardening)

版本名：`1.2.2-optimization`
基线版本：`Obsidian-wiki-skill-V1.2`
锁定日期：2026-05-02
前置版本：`1.2.1-llm-first`

## 本版核心变更：系统优化与接口加固

基于 `docs/2026-05-02-system-audit.md` 审计结果，执行 `docs/2026-05-02-optimization-plan.md` Phase A-D。

**变更类别**：测试补全、接口加固、utility 去重、遗留测试修复。

---

## 一、新增 validate_apply_json() 校验机制

| 文件 | 改动 |
|------|------|
| `scripts/pipeline/text_utils.py` | 新增 `validate_apply_json()` 函数 |
| `scripts/pipeline/shared.py` | re-export `validate_apply_json` |

接入的 apply 函数：

| 脚本 | 函数 | required_fields |
|------|------|----------------|
| `claim_evolution.py` | `apply_claim_evolution_result()` | `["relationships"]` |
| `review_queue.py` | `apply_review_result()` | `["prioritized_items"]` |
| `refresh_synthesis.py` | `apply_synthesis_result()` | `["current_conclusion"]` |
| `delta_compile.py` | `apply_delta_result()` | `["drafts"]` |

LLM 输出 JSON 缺少必需字段时抛出 `ValueError`，附带可操作的错误信息。

## 二、Utility 去重（delta_compile.py）

`scripts/delta_compile.py` 移除 5 个重复函数定义 + 4 个重复 regex 常量，改为从 `pipeline.shared` 统一 import：

| 移除的本地定义 | 替换为 |
|--------------|--------|
| `parse_frontmatter()` | `from pipeline.shared import parse_frontmatter` |
| `plain_text()` | `from pipeline.shared import plain_text` |
| `section_excerpt()` | `from pipeline.shared import section_excerpt` |
| `split_sentences()` | `from pipeline.shared import split_sentences` |
| `sanitize_filename()` | `from pipeline.shared import sanitize_filename` |
| `INVALID_CHARS` | `from pipeline.shared import INVALID_CHARS` |
| `FRONTMATTER` | `from pipeline.shared import FRONTMATTER` |
| `CODE_BLOCK` | `from pipeline.shared import CODE_BLOCK` |
| `HEADING` | `from pipeline.shared import HEADING` |

## 三、死代码标注

| 文件 | 函数 | 标注 |
|------|------|------|
| `scripts/pipeline/ingest_report.py` | `format_ingest_dialogue()` | docstring 标注为"未使用，保留供未来交互式场景" |

## 四、行为指南更新

| 文件 | 改动 |
|------|------|
| `references/maintenance-guide.md` | 新增"Step 4: 回写已批准的 delta 草稿"；新增"维护后统一重建"段 |
| `references/ingest-guide.md` | Step 2 编译策略表新增"能力"列；标注 cross_domain_insights/claim_inventory 仅 LLM 编译可用 |
| `references/query-guide.md` | 新增"2e. 反驳材料收集"段，明确 contradict.py 是候选材料生成而非语义判断 |
| `references/workflow.md` | 修复 2 处 `wiki_ingest_wechat.py` → `wiki_ingest.py` |

## 五、测试补全（+49 个新测试）

### 新增测试文件

| 文件 | 覆盖函数 | 测试数 |
|------|---------|--------|
| `tests/test_ingest_report_three_stage.py` | `collect_ingest_data()` | 8 |
| `tests/test_wiki_lint_three_stage.py` | `collect_lint_data()` | 8 |
| `tests/test_claim_evolution_three_stage.py` | `collect_all_claims()`, `collect_claims_json()`, `apply_claim_evolution_result()` | 9 |
| `tests/test_review_queue_three_stage.py` | `collect_review_data()`, `apply_review_result()` | 9 |
| `tests/test_refresh_synthesis_three_stage.py` | `collect_synthesis_data()`, `apply_synthesis_result()` | 7 |
| `tests/test_delta_compile_three_stage.py` | `collect_delta_data()`, `apply_delta_result()` | 8 |

每个测试覆盖三个维度：输出 schema 验证、空 vault 边界条件、核心过滤/提取逻辑。

### 修复的遗留测试

| 文件 | 问题 | 修复 |
|------|------|------|
| `tests/test_wiki_lint_claims.py` | 2 个测试引用已删除的 `claim_conflicts` | 重写为 `--collect-only` 输出测试 |
| `tests/test_wiki_lint_claims.py` | 1 个断言引用不存在的 `confidence` 字段 | 修正为检查 claim 文本 |
| `tests/test_review_queue_claims.py` | 3 个测试引用已重命名的 `build_review_queue` | 重写为测试 `build_review_queue_page` |

## 六、全量改动文件清单

### scripts/ 目录

| 文件 | 改动类型 |
|------|---------|
| `scripts/pipeline/text_utils.py` | 新增 `validate_apply_json()` |
| `scripts/pipeline/shared.py` | re-export `validate_apply_json` |
| `scripts/pipeline/ingest_report.py` | `format_ingest_dialogue()` docstring 标注 |
| `scripts/claim_evolution.py` | import `validate_apply_json` + apply 入口校验 |
| `scripts/review_queue.py` | import `validate_apply_json` + apply 入口校验 |
| `scripts/refresh_synthesis.py` | import `validate_apply_json` + apply 入口校验 |
| `scripts/delta_compile.py` | 移除 5 个重复函数 + 4 个重复 regex；import `validate_apply_json` + apply 入口校验 |

### references/ 目录

| 文件 | 改动类型 |
|------|---------|
| `references/maintenance-guide.md` | 新增 delta 回写引导 + 维护后重建建议 |
| `references/ingest-guide.md` | 编译策略表补充能力列 |
| `references/query-guide.md` | 新增反驳材料收集段 |
| `references/workflow.md` | 修复 wiki_ingest_wechat 引用 |

### tests/ 目录

| 文件 | 改动类型 |
|------|---------|
| `tests/test_ingest_report_three_stage.py` | **新增** |
| `tests/test_wiki_lint_three_stage.py` | **新增** |
| `tests/test_claim_evolution_three_stage.py` | **新增** |
| `tests/test_review_queue_three_stage.py` | **新增** |
| `tests/test_refresh_synthesis_three_stage.py` | **新增** |
| `tests/test_delta_compile_three_stage.py` | **新增** |
| `tests/test_wiki_lint_claims.py` | 修复 3 个断裂测试 |
| `tests/test_review_queue_claims.py` | 重写 3 个测试适配新 API |

### docs/ 目录

| 文件 | 改动类型 |
|------|---------|
| `docs/2026-05-02-optimization-plan.md` | 状态更新为 Phase A-D 完成 |
| `docs/2026-05-02-version-lock-v1.2.2.md` | **新增**：本文件 |

## 七、测试结果

```
325 passed in 7.61s
```

## 八、待办事项（后续版本 — Phase E）

| 项目 | 优先级 | 说明 |
|------|--------|------|
| E1. 增量收集机制 | 低 | vault > 200 篇时实施 |
| E2. 自动维护建议 | 低 | 连续 7 天未维护时提示 |
| E3. deep_research_triggers.py 改造 | P5 | 当前行为可接受 |

---

## 复制基线命令

```powershell
# 在 D:\AI\obsidian-wiki\ 目录下执行
xcopy "Obsidian-wiki-skill-V1.2" "Obsidian-wiki-skill-V1.2.2" /E /I /H /Y
```
