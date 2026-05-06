# 2026-04-26 Version Lock — cross-domain-patch

版本名：`2026.04.26-cross-domain-patch`
基线版本：`2026.04.25-refactor-v2`

## 本版包含内容

### 跨域关联推理（cross_domain_insights）

- v2 compile schema 新增 `cross_domain_insights` 字段
- 三种同构类型：方法论迁移、因果结构类比、抽象模式共享
- 每条包含 `mapped_concept`、`target_domain`、`bridge_logic`、`potential_question`、`confidence`
- 启发式模式无法产出此字段（`compile_quality: "raw-extract"`），impact 报告提示使用 prepare-only

### 入库影响报告优先使用 LLM 编译数据

- `build_ingest_impact_report()` 优先从 `compiled_payload.result` 取数据：
  - 问题：`open_questions` > `extract_content_questions()`
  - 主题：`knowledge_proposals.concepts`（排除 `action=no_page`）> `extract_content_topics()`

### Spec 同步

- `script-reference.md` v2 schema 字段列表补全（5 → 9 字段）
- `workflow.md` 新增 v2 compile 产出字段表 + `cross_domain_insights` 结构说明 + 入库影响报告完整描述
- `interaction.md` "不推荐的行为"新增入库后必须展示影响报告

## 改动文件清单

| 文件 | 改动类型 |
|------|---------|
| `references/prompts/ingest_compile_prompt_v2.md` | 新增规则 10 + JSON skeleton 加 `cross_domain_insights` |
| `references/examples/compile_mock_response_v2.json` | 加 `cross_domain_insights: []` |
| `scripts/pipeline/validate_compile.py` | 校验 `cross_domain_insights` 结构 |
| `scripts/llm_compile_ingest.py` | `normalize_cross_domain_insights()` + `normalize_result_v2()` 扩展 |
| `scripts/pipeline/ingest_report.py` | LLM 数据优先 + cross_domain_insights 消费 + 领域不匹配重构 |
| `references/script-reference.md` | v2 schema 字段补全 + impact report 描述 |
| `references/workflow.md` | v2 产出字段表 + cross_domain_insights 说明 + 影响报告结构 |
| `references/interaction.md` | 不推荐行为新增 |
| `SKILL.md` | cross_domain_insights 功能描述 + 运行模式区分 |

## 测试结果

- **85 passed, 1 pre-existing failure**（`test_main_allows_empty_collection_rerun` argparse 参数泄漏，与本次改动无关）
- 手动验证：
  - normalize 边界情况（空字段、无效 confidence、非 list 输入）
  - validate 边界情况（缺字段、无效 confidence）
  - ingest_report LLM 数据优先路径
  - ingest_report 启发式回退路径
  - mock JSON 合法性

## 当前使用约束

- 跨域联想仅在 LLM 编译路径（prepare-only / api-compile）可用
- 启发式入库仍可正常运行，但 impact 报告会标注 compile_quality: raw-extract
- `cross_domain_insights` 最多 5 条（`normalize_cross_domain_insights(limit=5)`）

## 后续版本建议

- Concept genealogy（概念谱系追踪）
- 跨域联想驱动自动创建跨域 comparison 页
- `potential_question` 自动写入 `wiki/questions/`
- 测试 argparse 参数泄漏修复
