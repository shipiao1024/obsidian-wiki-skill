# 优化与修复方案

日期：2026-05-02
基线：V1.2.1 (LLM-First Architecture)
依据：`docs/2026-05-02-system-audit.md`

---

## 方案总览

| 阶段 | 目标 | 工作量 | 优先级 | 状态 |
|------|------|--------|--------|------|
| Phase A: 修复断裂 | 测试修复 + 死代码清理 | 小 | 立即 | ✅ 完成 |
| Phase B: 补齐测试 | 三阶段接口单元测试 | 中 | 短期 | ✅ 完成 |
| Phase C: 接口加固 | schema 校验 + guide 补全 | 中 | 短期 | ✅ 完成 |
| Phase D: 架构统一 | utility 去重 + guide 更新 | 中 | 中期 | ✅ 完成 |
| Phase E: 效率优化 | 增量收集 + 自动维护 + 触发改造 | 大 | 长期 | ⏳ 延迟 |

---

## Phase A: 修复断裂（立即）

### A1. 修复 test_wiki_lint_claims.py

**问题**：3 个测试方法引用已删除的 `claim_conflicts`，运行会失败。

**方案**：将测试重写为验证 `--collect-only` 输出的 `all_claims` 字段。

**改动文件**：`tests/test_wiki_lint_claims.py`

**改动内容**：

```python
# 删除以下 3 个测试方法：
# - test_wiki_lint_reports_claim_conflicts (line 106-169)
# - test_wiki_lint_reports_claim_conflicts_between_source_and_synthesis (line 171-221)

# 替换为 2 个新测试方法：

def test_collect_only_returns_all_claims(self) -> None:
    """--collect-only 输出包含 all_claims 字段，含所有页面的主张。"""
    vault = ROOT / ".tmp-tests" / "lint-collect-claims-vault"
    # ... 创建 vault 结构（同现有测试）...
    # 写入含 关键判断 的 source 和 synthesis 页面

    stream = StringIO()
    argv = sys.argv[:]
    try:
        sys.argv = ["wiki_lint.py", "--vault", str(vault), "--collect-only"]
        with redirect_stdout(stream):
            wiki_lint.main()
    finally:
        sys.argv = argv
    report = json.loads(stream.getvalue())

    self.assertIn("all_claims", report)
    self.assertTrue(len(report["all_claims"]) >= 2)
    # 验证 claim 结构
    claim = report["all_claims"][0]
    self.assertIn("path", claim)
    self.assertIn("claim_type", claim)
    self.assertIn("confidence", claim)
    self.assertIn("claim", claim)
    self.assertIn("page_type", claim)


def test_collect_only_returns_low_confidence_claims(self) -> None:
    """--collect-only 输出的 low_confidence_claims 只含 confidence=low 的主张。"""
    vault = ROOT / ".tmp-tests" / "lint-low-conf-vault"
    # ... 创建 vault 结构...
    # 写入含 low 和 high confidence 主张的页面

    stream = StringIO()
    argv = sys.argv[:]
    try:
        sys.argv = ["wiki_lint.py", "--vault", str(vault), "--collect-only"]
        with redirect_stdout(stream):
            wiki_lint.main()
    finally:
        sys.argv = argv
    report = json.loads(stream.getvalue())

    self.assertIn("low_confidence_claims", report)
    for claim in report["low_confidence_claims"]:
        # 从 all_claims 中找到对应主张，确认 confidence=low
        pass
```

**验证**：运行 `python -m pytest tests/test_wiki_lint_claims.py -v`

---

### A2. 清理 format_ingest_dialogue() 死代码

**问题**：`pipeline/ingest_report.py` 中的 `format_ingest_dialogue()` 从未被 orchestrator 调用。

**方案**：保留函数但添加 docstring 标注为"未使用，保留供未来直接调用"。不做删除，因为函数本身逻辑完整，未来可能在交互式场景中使用。

**改动文件**：`scripts/pipeline/ingest_report.py`

**改动内容**：在 `format_ingest_dialogue()` 的 docstring 中增加一行：

```python
"""...
    NOTE: This function is not currently called by ingest_orchestrator.
    It is retained for potential direct-use in interactive dialogue scenarios.
    The orchestrator uses build_ingest_impact_report() + format_ingest_report().
"""
```

---

### A3. 清理 interaction.md 中的 wiki_ingest_wechat.py 引用

**问题**：`references/workflow.md` line 487 仍引用 `wiki_ingest_wechat.py`。

**方案**：检查 workflow.md 中所有 `wiki_ingest_wechat.py` 引用，替换为 `wiki_ingest.py`。

**改动文件**：`references/workflow.md`

**改动内容**：

```
line 487: wiki_ingest_wechat.py → wiki_ingest.py
```

全文搜索 `wiki_ingest_wechat`，确认无其他残留。

---

## Phase B: 补齐测试（短期）

### B1. 为三阶段接口补充单元测试

**问题**：11 个新增的 collect_*/apply_* 函数无测试覆盖。

**方案**：为每个函数创建测试，验证：
1. collect 函数输出结构符合预期 schema
2. apply 函数正确读取 JSON 并写入文件
3. 边界条件（空 vault、缺少字段的 JSON）

**新增文件**：

| 测试文件 | 覆盖函数 |
|---------|---------|
| `tests/test_wiki_lint_three_stage.py` | collect_lint_data(), apply_lint_result() |
| `tests/test_claim_evolution_three_stage.py` | collect_all_claims(), apply_claim_evolution_result() |
| `tests/test_review_queue_three_stage.py` | collect_review_data(), apply_review_result() |
| `tests/test_refresh_synthesis_three_stage.py` | collect_synthesis_data(), apply_synthesis_result() |
| `tests/test_delta_compile_three_stage.py` | collect_delta_data(), apply_delta_result() |
| `tests/test_ingest_report_three_stage.py` | collect_ingest_data() |

**每个测试文件的结构**：

```python
class TestCollectXxx(unittest.TestCase):
    def test_output_has_required_fields(self):
        """collect 输出包含所有必需字段。"""

    def test_output_with_empty_vault(self):
        """空 vault 时不崩溃，返回空列表。"""

    def test_output_respects_filters(self):
        """过滤逻辑正确（如排除当前 slug）。"""

class TestApplyXxx(unittest.TestCase):
    def test_writes_expected_file(self):
        """apply 正确写入文件。"""

    def test_handles_missing_fields_gracefully(self):
        """JSON 缺少可选字段时不崩溃。"""

    def test_appends_to_log(self):
        """apply 后 log.md 有追加记录。"""
```

**预计工作量**：6 个测试文件 × 30-50 行 = 180-300 行代码

---

### B2. 修复现有测试中的 import 路径

**问题**：部分测试文件可能引用了重构后的模块路径变化。

**方案**：运行完整测试套件，修复所有 import 错误。

```powershell
python -m pytest tests/ -v --tb=short 2>&1 | Select-String "ERROR|FAIL"
```

---

## Phase C: 接口加固（短期）

### C1. 为 --apply 函数添加 JSON schema 校验

**问题**：所有 `--apply` 函数直接 `json.loads()` 后访问字段，无 schema 校验。LLM 输出格式错误时抛 KeyError。

**方案**：在每个 `apply_*()` 函数入口添加轻量校验函数。

**新增代码**（放入 `pipeline/shared.py` 或各脚本内）：

```python
def validate_apply_json(data: dict, required_fields: list[str], context: str = "") -> None:
    """Validate LLM result JSON has required fields before apply."""
    missing = [f for f in required_fields if f not in data]
    if missing:
        raise ValueError(
            f"Apply JSON missing required fields: {missing}. "
            f"Context: {context}. "
            f"Ensure LLM output matches the schema in references/prompts/*.md"
        )
```

**各脚本的 required_fields**：

| 脚本 | required_fields |
|------|----------------|
| wiki_lint.py | `[]`（所有字段可选，空 JSON = 无操作） |
| claim_evolution.py | `["relationships"]` |
| review_queue.py | `["prioritized_items"]` |
| refresh_synthesis.py | `["current_conclusion"]` |
| delta_compile.py | `["drafts"]` |
| ingest_report.py | `[]`（所有字段可选） |

**改动文件**：6 个脚本的 apply_*() 函数

**改动内容**：在 `json.loads()` 后、字段访问前，调用 `validate_apply_json()`。

---

### C2. 增加 delta 草稿回写引导模板

**问题**：用户拿到 delta 草稿后不知道下一步该怎么做。

**方案**：在 maintenance-guide.md 的场景 4（审核队列）末尾增加回写引导段。

**改动文件**：`references/maintenance-guide.md`

**新增段落**：

```markdown
### Step 4: 回写已批准的 delta 草稿

当用户确认某个 delta 草稿值得沉淀时：

```powershell
python scripts/apply_approved_delta.py "outputs/<slug>" --vault "D:\Vault"
```

回写后原 output 标记为 `absorbed`，不再出现在审核队列中。

如果自动找不到目标 synthesis，可显式指定：

```powershell
python scripts/apply_approved_delta.py "outputs/<slug>" --vault "D:\Vault" --target "syntheses/主题--综合分析"
```

**引导模板**（向用户展示）：

```
已批准的 delta 草稿：
  → [[outputs/{slug}]]
  回写命令：apply_approved_delta.py "outputs/{slug}"
  目标综合页：{auto-detected or manual}
```
```

---

### C3. 明确跨域联想的前提条件

**问题**：跨域联想只有 LLM 编译模式可产出，但文档未充分说明。

**方案**：在 ingest-guide.md 的 Step 2 编译策略表中增加一列"能力"。

**改动文件**：`references/ingest-guide.md`

**改动内容**：

```markdown
| 模式 | 适用场景 | 命令 | 能力 |
|------|---------|------|------|
| `fetch+heuristic` | 快速入库 | 默认 | basic brief/source |
| `fetch+prepare-only` | 交互式编译（推荐） | `--prepare-only --lean` | full（含跨域联想、主张清单） |
| `fetch+api-compile` | 无人值守 | 配置 API | full |
```

---

## Phase D: 架构统一（中期）

### D1. 统一 utility 函数到 pipeline.shared

**问题**：`parse_frontmatter`、`plain_text`、`split_sentences`、`section_excerpt` 等函数在多个脚本中有独立实现。

**方案**：

1. 确认 `pipeline.shared` 已导出所有需要的函数（检查现有导出）
2. 将 `delta_compile.py` 中重复定义的函数替换为 `from pipeline.shared import ...`
3. 将 `wiki_lint.py` 中的 `parse_frontmatter` 替换为 shared 版本
4. 保留 `*_legacy.py` 文件中的独立实现（它们是冻结的旧逻辑）

**改动文件**：

| 文件 | 改动 |
|------|------|
| `scripts/delta_compile.py` | 移除 parse_frontmatter、plain_text、split_sentences、section_excerpt、sanitize_filename 定义，改为 import |
| `scripts/wiki_lint.py` | 确认使用 pipeline.text_utils 版本（已是） |
| `scripts/claim_evolution.py` | 检查是否有重复 |
| `scripts/review_queue.py` | 检查是否有重复 |

**新增 shared 函数**（如果缺失）：

```python
# pipeline/shared.py 中可能需要新增：
def outbound_links(path: Path) -> set[str]:
    """Extract all [[wikilink]] targets from a file."""
    ...

def load_index_candidates(vault: Path, query: str, top: int = 5) -> list:
    """Load index.md entries ranked by term overlap."""
    ...
```

**验证**：运行完整测试套件确认无回归。

---

### D2. contradict.py 硬编码模式标注

**问题**：`pipeline/output/contradict.py` line 116 仍有硬编码否定模式。

**方案**：不修改脚本逻辑（脚本角色是"生成候选材料"），但在 query-guide.md 中明确标注。

**改动文件**：`references/query-guide.md`

**改动内容**：在 Step 2b 关键词搜索后增加一段：

```markdown
### 2e. 反驳材料收集

`pipeline/output/contradict.py` 提供"潜在对立面"候选页面。脚本使用否定模式
（如"并非"、"不是"、"错误"等）做初步筛选，这是**候选材料生成**，不是语义判断。

你从候选材料中筛选真正有价值的反驳证据，按 `query_synthesis.md` 约束分析。
不要把脚本的否定模式匹配结果直接当作反驳证据。
```

---

### D3. 索引重建统一策略

**问题**：多个脚本独立重建 index.md，维护流程中可能中途过时。

**方案**：在 maintenance-guide.md 末尾增加"维护后统一重建"建议。

**改动文件**：`references/maintenance-guide.md`

**新增段落**：

```markdown
## 维护后统一重建

完成所有维护操作后，建议统一重建索引：

```powershell
python scripts/wiki_query.py --vault "D:\Vault" --rebuild-index
```

这确保 index.md 反映所有维护操作的最终状态。
```

---

## Phase E: 效率优化（长期）

### E1. 增量收集机制

**问题**：所有 --collect-only 函数全量扫描 vault，大 vault 时慢。

**方案**：基于 log.md 的最近变更记录，只扫描自上次维护后变更的文件。

**实现思路**：

1. `collect_lint_data()` 增加 `--since` 参数（ISO 日期）
2. 解析 log.md 获取自该日期后变更的文件列表
3. 只对变更文件做深度扫描，其余使用缓存的上次结果

**预计收益**：100+ 篇来源的 vault，增量扫描比全量快 5-10x。

**实现复杂度**：高。需要设计缓存存储和失效策略。

**建议**：当 vault 来源数超过 200 时再实施。

---

### E2. 自动维护建议

**问题**：所有维护操作需要用户主动触发。

**方案**：在 `stale_report.py` 增加 `--auto-suggest` 模式。

**实现思路**：

1. `stale_report.py --auto-suggest` 输出结构化 JSON
2. JSON 包含：检测到的问题类型、严重程度、建议的维护命令
3. LLM 读取 JSON 后向用户展示维护建议（不自动执行）

**输出 schema**：

```json
{
  "suggestions": [
    {
      "type": "stale_synthesis",
      "target": "syntheses/自动驾驶--综合分析",
      "severity": "medium",
      "reason": "综合页最后更新 30 天前，期间新增 3 篇来源",
      "suggested_command": "refresh_synthesis.py --domain 自动驾驶 --collect-only"
    }
  ],
  "last_maintenance": "2026-04-15",
  "days_since_maintenance": 17
}
```

**建议**：当用户连续 7 天未运行维护时，LLM 在对话中提示。

---

### E3. deep_research_triggers.py 改造

**问题**：5 种触发条件全部脚本实现，与 LLM-First 原则不一致。

**方案**：改为 --collect-only 输出触发信号数据，由 LLM 判断是否触发。

**实现思路**：

1. `deep_research_triggers.py --collect-only` 输出：
   - 跨域碰撞候选（来自 cross_domain_insights）
   - 积累矛盾候选（来自 claim_evolution 中的 contradict 关系）
   - 知识缺口候选（来自 open_questions 的 unresolved 数量）
   - 置信度断崖候选（来自 low_confidence_claims 数量）
2. LLM 按 research-guide.md 判断是否建议 deep-research

**建议**：这是 P5 项目，当前脚本行为可接受（建议性质，LLM 最终决定）。

---

## 实施顺序

```
Phase A (立即)  ──→  Phase B (短期)  ──→  Phase C (短期)
     │                    │                    │
     ▼                    ▼                    ▼
  A1: 修复测试         B1: 补充测试         C1: schema 校验
  A2: 标注死代码       B2: 修复 import      C2: delta 引导模板
  A3: 清理引用                               C3: 跨域联想前提
                                                 │
                                                 ▼
                                          Phase D (中期)
                                               │
                                               ▼
                                          D1: utility 去重
                                          D2: contradict 标注
                                          D3: 索引重建统一
                                                 │
                                                 ▼
                                          Phase E (长期)
                                               │
                                               ▼
                                          E1: 增量收集
                                          E2: 自动维护建议
                                          E3: triggers 改造
```

---

## 验收标准

### Phase A 完成标准
- [ ] `python -m pytest tests/test_wiki_lint_claims.py -v` 全部通过
- [ ] `grep -r "wiki_ingest_wechat" references/ scripts/` 无结果（或仅 legacy shim 文件）
- [ ] format_ingest_dialogue() docstring 已标注

### Phase B 完成标准
- [ ] 6 个新测试文件存在且通过
- [ ] `python -m pytest tests/ -v` 全部通过（无新增失败）

### Phase C 完成标准
- [ ] 所有 --apply 函数有 schema 校验
- [ ] maintenance-guide.md 有 delta 回写引导
- [ ] ingest-guide.md 编译策略表有"能力"列
- [ ] query-guide.md 有反驳材料收集说明

### Phase D 完成标准
- [ ] delta_compile.py 无重复 utility 函数定义
- [ ] 所有脚本统一使用 pipeline.shared 的 parse_frontmatter
- [ ] maintenance-guide.md 有维护后统一重建建议
- [ ] 测试套件全部通过

### Phase E 完成标准
- [ ] collect_lint_data() 支持 --since 参数
- [ ] stale_report.py 支持 --auto-suggest
- [ ] deep_research_triggers.py 改为 --collect-only 模式
