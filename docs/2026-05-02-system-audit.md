# 系统性产品审核报告

日期：2026-05-02
版本基线：V1.2.1 (LLM-First Architecture)
审核范围：全产品——用户场景、用户价值、系统稳健性、架构一致性、系统效率

---

## 一、总体评价

产品在本轮 LLM-First 改造后，架构方向正确：三阶段模式（脚本收集 → LLM 判断 → 脚本执行）统一了 6 个核心维护脚本的接口，8 份 Prompt 约束文件建立了 LLM 行为边界。但在落地层面存在**测试断裂、遗留代码未清理、接口模式覆盖不完整**三类系统性问题。

**核心矛盾**：改造完成了"脚本不再做语义判断"的目标，但"LLM 按约束执行"的保障仅靠文档约定，无代码强制。这在单人使用场景可接受，在多人协作或 agent 自动执行场景会成为隐患。

---

## 二、用户场景审核

### 2.1 场景覆盖度

| 场景 | 覆盖状态 | 质量评估 |
|------|---------|---------|
| 单篇入库（URL） | ✅ 完整 | 流程清晰，5 阶段流水线成熟 |
| 单篇入库（本地文件） | ✅ 完整 | 支持 .md/.txt/.html/.pdf |
| 批量入库 | ✅ 完整 | 合集保护机制健全 |
| 口语化查询 | ✅ 完整 | 9 种输出格式，路由逻辑清晰 |
| 深度研究 | ✅ 完整 | 9 阶段协议 + 质量门控 |
| 日常维护 | ✅ 三阶段改造完成 | 4 场景统一接口 |
| autoresearch | ✅ 完整 | 3 轮递进搜索 |
| save 模式 | ✅ 完整 | 5 种保存类型 |

**问题 S1：维护场景的三阶段模式对用户认知负担高**

旧模式：用户说"运行 lint"→ 脚本直接输出报告。
新模式：用户说"运行 lint"→ 脚本输出 JSON → LLM 分析 → 脚本写入 → 展示报告。

对普通用户而言，三阶段是透明的（LLM 自动串联），但要求 LLM 正确理解 `--collect-only` → 分析 → `--apply` 的完整链路。如果 LLM 漏掉某一步，用户会看到不完整的输出。

**建议**：在 maintenance-guide.md 中增加"快速模式"说明——当用户只说"lint"时，LLM 自动完成三阶段全流程，不需要用户感知中间步骤。

### 2.2 场景间衔接

| 衔接点 | 状态 | 问题 |
|--------|------|------|
| 入库 → 查询 | ✅ | brief/source 自动进入索引 |
| 入库 → 深度研究 | ✅ | 触发条件清晰（三要素判断） |
| 查询 → 沉淀 | ✅ | outputs/ → apply_approved_delta 流程 |
| 维护 → 入库 | ⚠️ | delta_compile 草稿的回写路径不够直观 |
| 深度研究 → 入库 | ✅ | 研究中发现的 URL 自动走 ingest |

**问题 S2：delta_compile 草稿的生命周期不够清晰**

delta_compile 生成的 `review-needed` 草稿需要用户手动运行 `apply_approved_delta.py` 回写。但这个操作在 interaction.md 和 maintenance-guide.md 中都没有明确的用户引导模板。用户拿到 delta 草稿后，不知道下一步该怎么做。

**建议**：在 maintenance-guide.md 的场景 4（审核队列）中增加 delta 草稿的回写引导模板。

---

## 三、用户价值审核

### 3.1 价值交付链

```
用户输入 → 系统处理 → 用户获得
```

| 价值主张 | 交付路径 | 真实触达 |
|---------|---------|---------|
| 快速了解一篇文章 | brief 页 + PDF | ✅ 直接可用 |
| 跨来源综合分析 | syntheses/ 页 | ⚠️ 依赖 LLM 编译质量 |
| 跨域联想 | cross_domain_insights | ⚠️ 仅 LLM 编译可产出 |
| 知识图谱可视化 | Mermaid + Obsidian 图 | ✅ 直接可用 |
| 主张演化追踪 | claim-evolution.md | ⚠️ 改造后依赖 LLM，旧数据不兼容 |
| 深度研究报告 | research/ + PDF | ✅ 完整 |
| 日常维护建议 | review_queue.md | ⚠️ 改造后首次运行需 LLM 分析 |

**问题 V1：跨域联想的可得性低**

`cross_domain_insights` 只有在使用 `fetch+prepare-only` + LLM 编译时才能产出。`fetch+heuristic` 模式完全无法产出。但产品 HTML 和文档中把"跨域联想"作为核心卖点，容易让用户产生预期落差。

**建议**：在用户引导中明确——跨域联想需要 LLM 编译模式，启发式模式不支持。

### 3.2 价值衰减点

| 衰减点 | 表现 | 原因 |
|--------|------|------|
| 入库后无跟进 | 用户入库 10 篇后不再维护 | 维护流程需要用户主动触发 |
| 综合页过时 | syntheses/ 内容滞后于 sources/ | 需要手动运行 refresh_synthesis |
| 候选页堆积 | candidate 页面越来越多 | 升级条件（2+ 来源确认）门槛高 |
| outputs/ 堆积 | 临时输出越来越多 | 归档需要用户主动运行 |

**问题 V2：缺乏自动维护触发机制**

当前所有维护操作都需要用户主动触发。没有定时任务或阈值触发机制。`stale_report.py` 可以检测问题，但不会自动触发修复。

**建议**：增加 `--auto-suggest` 模式——当 `stale_report.py` 检测到问题时，自动输出维护建议（不自动执行）。

---

## 四、系统稳健性审核

### 4.1 测试覆盖

**问题 R1（严重）：测试文件引用已删除函数**

`tests/test_wiki_lint_claims.py` 中有 3 个测试方法引用了 `claim_conflicts`，该功能已在 LLM-First 改造中从 `wiki_lint.py` 移除：

- `test_wiki_lint_reports_claim_conflicts`（line 106）
- `test_wiki_lint_reports_claim_conflicts_between_source_and_synthesis`（line 171）
- line 168/169/221 的断言引用 `report["claim_conflicts"]`

这些测试运行时会失败。需要更新为测试 `--collect-only` 输出的 `all_claims` 字段。

**问题 R2：无测试覆盖新增的三阶段接口**

以下新增函数没有对应的单元测试：

| 函数 | 文件 | 测试状态 |
|------|------|---------|
| `collect_lint_data()` | wiki_lint.py | ❌ 无测试 |
| `apply_lint_result()` | wiki_lint.py | ❌ 无测试 |
| `collect_all_claims()` | claim_evolution.py | ❌ 无测试 |
| `apply_claim_evolution_result()` | claim_evolution.py | ❌ 无测试 |
| `collect_review_data()` | review_queue.py | ❌ 无测试 |
| `apply_review_result()` | review_queue.py | ❌ 无测试 |
| `collect_synthesis_data()` | refresh_synthesis.py | ❌ 无测试 |
| `apply_synthesis_result()` | refresh_synthesis.py | ❌ 无测试 |
| `collect_delta_data()` | delta_compile.py | ❌ 无测试 |
| `apply_delta_result()` | delta_compile.py | ❌ 无测试 |
| `collect_ingest_data()` | ingest_report.py | ❌ 无测试 |

### 4.2 错误处理

| 场景 | 当前行为 | 评估 |
|------|---------|------|
| vault 路径不存在 | 报错退出 | ✅ |
| index.md 不存在 | 提示初始化 | ✅ |
| --apply 传入格式错误的 JSON | 可能抛未处理异常 | ⚠️ |
| --collect-only 时磁盘满 | 无特殊处理 | ⚠️ |
| LLM 输出不符合 schema | 无校验 | ❌ |

**问题 R3：`--apply` 无输入 JSON schema 校验**

所有 `--apply` 函数直接 `json.loads()` 后访问字段，没有校验 JSON 结构是否符合预期 schema。如果 LLM 输出格式错误（如缺少 `drafts` 字段），脚本会抛 KeyError 而非友好错误信息。

**建议**：为每个 `--apply` 函数添加 JSON schema 校验（使用 jsonschema 库或手写校验）。

### 4.3 数据一致性

**问题 R4：索引重建时机不一致**

多个脚本独立调用 `_rebuild_index()`：

| 脚本 | 重建索引 |
|------|---------|
| apply_compiled_brief_source.py | ✅ |
| delta_compile.py | ✅ |
| wiki_lint.py | ❌（legacy 模式不重建） |
| claim_evolution.py | ❌ |
| refresh_synthesis.py | ❌ |

如果用户按"lint → claim → refresh → delta"顺序运行维护，索引可能在中途过时。只有最后一步（delta）会重建索引。

**建议**：在 maintenance-guide.md 中建议：维护全流程结束后手动运行一次索引重建，或在最后一步统一重建。

---

## 五、接口/架构一致性审核

### 5.1 三阶段接口覆盖

| 脚本 | --collect-only | --apply | --output | legacy 回退 | 状态 |
|------|---------------|---------|----------|------------|------|
| wiki_lint.py | ✅ | ✅ | ✅ | ✅ main_legacy() | 完成 |
| claim_evolution.py | ✅ | ✅ | ✅ | ❌ | 完成 |
| review_queue.py | ✅ | ✅ | ✅ | ❌ | 完成 |
| refresh_synthesis.py | ✅ | ✅ | ✅ | ✅ legacy import | 完成 |
| delta_compile.py | ✅ | ✅ | ✅ | ✅ legacy import | 完成 |
| ingest_report.py | ✅ | ✅ | ✅ | ❌ | 完成 |
| wiki_query.py | ❌ | ❌ | ❌ | — | 未改造 |
| export_main_graph.py | ❌ | ❌ | ❌ | — | 不需要（纯机械） |
| archive_outputs.py | ❌ | ❌ | ❌ | — | 不需要（纯机械） |
| stale_report.py | ❌ | ❌ | ❌ | — | 可考虑（检测逻辑可扩展） |
| deep_research.py | ❌ | ❌ | ❌ | — | 协议驱动，不需要 |
| graph_trim.py | ❌ | ❌ | ❌ | — | 不需要（纯机械） |

**评估**：6/6 核心维护脚本已完成改造。不涉及语义判断的脚本（graph_trim、archive_outputs、export_main_graph）不需要改造。`stale_report.py` 当前是纯机械检测，但未来可考虑输出结构化数据供 LLM 判断。

### 5.2 Prompt 约束文件完整性

| Prompt 文件 | 引用者 | JSON schema 定义 | 约束规则 | 评估 |
|-------------|--------|-----------------|---------|------|
| lint_semantic.md | maintenance-guide | ✅ | ✅ | 完整 |
| claim_evolution.md | maintenance-guide | ✅ | ✅ | 完整 |
| synthesis_refresh.md | maintenance-guide | ✅ | ✅ | 完整 |
| review_queue.md | maintenance-guide | ✅ | ✅ | 完整 |
| ingest_impact.md | ingest-guide | ✅ | ✅ | 完整 |
| ingest_compile_prompt_v2.md | ingest-guide | ✅ | ✅ | 完整 |
| query_synthesis.md | query-guide | ✅ | ✅ | 完整 |
| research_hypothesis.md | research-guide | ✅ | ✅ | 完整 |

**评估**：8/8 prompt 文件结构完整。每个文件都定义了角色、输入 schema、输出 schema、判断标准和约束规则。

### 5.3 代码重复

**问题 A1：utility 函数重复定义**

以下函数在多个文件中有独立实现：

| 函数 | 出现位置 | 共享模块可用 |
|------|---------|-------------|
| `parse_frontmatter()` | delta_compile.py, wiki_lint.py, claim_evolution.py, review_queue.py | ✅ pipeline.shared |
| `plain_text()` | delta_compile.py, wiki_lint.py | ✅ pipeline.shared |
| `split_sentences()` | delta_compile.py | ✅ pipeline.shared |
| `section_excerpt()` | delta_compile.py, wiki_lint.py | ✅ pipeline.shared |
| `sanitize_filename()` | delta_compile.py | ✅ pipeline.shared |
| `outbound_links()` | delta_compile.py | ❌ 无共享版本 |
| `load_index_candidates()` | delta_compile.py | ❌ 无共享版本 |

`delta_compile.py` 定义了 10+ 个函数，其中大部分可以在 `pipeline.shared` 中找到。这些重复是因为改造时保留了原有代码结构。

**建议**：长期重构时将 delta_compile.py 和 wiki_lint.py 的 utility 函数统一到 pipeline.shared。

### 5.4 术语一致性

| 位置 | 检查项 | 状态 |
|------|--------|------|
| references/ 目录 | "宿主 Agent" → "你" | ✅ 已清理 |
| scripts/ docstring | "host-agent" → "LLM/你" | ✅ 已清理 |
| SKILL.md | "Host-Agent" → "你" | ✅ 已清理 |
| product-overview.html | "Host-Agent 优先" → "LLM 优先" | ✅ 已更新 |
| scripts/pipeline/output/contradict.py | 无术语问题 | ✅ |
| scripts/pipeline/deep_research.py | docstring 已更新 | ✅ |

**评估**：术语清理彻底，无残留。

---

## 六、系统效率审核

### 6.1 上下文效率

| 环节 | 上下文占用 | 优化状态 |
|------|-----------|---------|
| compile payload | --lean 模式减少 ~80% | ✅ |
| query 搜索 | 控制 10 页以内 | ✅ |
| --collect-only 输出 | JSON 格式，结构化 | ✅ |
| maintenance LLM 分析 | 每次读取 prompt 约束文件 | ⚠️ prompt 文件较大 |

**问题 E1：维护场景的 prompt 约束文件加载开销**

每次维护操作都需要加载对应的 prompt 约束文件（如 lint_semantic.md、claim_evolution.md）。这些文件平均 200-400 行。如果用户连续运行多个维护场景，prompt 文件会重复加载。

**评估**：当前可接受。prompt 文件是按需加载（不是一次性全部加载），且 LLM 的上下文窗口足够大。但未来可以考虑将 prompt 压缩为更精简的版本。

### 6.2 磁盘 I/O

| 操作 | I/O 模式 | 评估 |
|------|---------|------|
| collect_ingest_data() | 读所有 sources/*.md | ⚠️ 大 vault 时慢 |
| collect_lint_data() | 遍历所有 wiki/ 页面 | ⚠️ 大 vault 时慢 |
| _rebuild_index() | 读所有页面 + 写 index.md | ⚠️ 重复执行 |
| collect_all_claims() | 读所有 sources + briefs | ⚠️ 大 vault 时慢 |

**问题 E2：无增量收集机制**

所有 `--collect-only` 函数都是全量扫描。对于 100+ 篇来源的 vault，每次维护都需要遍历所有文件。

**评估**：当前规模（<200 篇来源）可接受。长期可考虑增量收集（基于 log.md 的最近变更记录）。

### 6.3 脚本执行效率

| 脚本 | 执行时间估算 | 瓶颈 |
|------|------------|------|
| wiki_ingest.py | 10-30s | 网络抓取 |
| llm_compile_ingest.py | 1-5s | 纯数据准备 |
| apply_compiled_brief_source.py | 2-5s | 文件写入 + 索引重建 |
| wiki_lint.py --collect-only | 1-3s | 全量扫描 |
| claim_evolution.py --collect-only | 1-3s | 全量扫描 |
| delta_compile.py --collect-only | 1-3s | 索引解析 |

**评估**：所有脚本执行时间在合理范围内。主要瓶颈是 LLM 分析阶段（取决于模型响应速度），而非脚本本身。

---

## 七、遗留问题清单

### 严重（必须修复）

| ID | 问题 | 影响 | 建议 |
|----|------|------|------|
| R1 | test_wiki_lint_claims.py 引用已删除的 claim_conflicts | 测试失败 | 更新测试为 --collect-only 模式 |
| R2 | 11 个新增函数无单元测试 | 回归风险 | 为 collect_*/apply_* 函数补充测试 |

### 高优先

| ID | 问题 | 影响 | 建议 |
|----|------|------|------|
| H1 | contradict.py 仍有硬编码否定模式 | 与 LLM-First 原则不一致 | 在 query-guide.md 中标注为"候选材料生成"，或重构为 --collect-only |
| H2 | deep_research.py 仍有关键词证据分类 | 与 LLM-First 原则不一致 | 已在 research-guide.md 中标注为预排序，可接受 |
| H3 | deep_research_triggers.py 5 种触发条件全部脚本实现 | 长期不一致 | P5 待办，当前可接受 |
| S2 | delta 草稿回写无用户引导模板 | 用户不知道下一步 | 在 maintenance-guide.md 增加引导模板 |

### 中优先

| ID | 问题 | 影响 | 建议 |
|----|------|------|------|
| A1 | utility 函数重复定义 | 维护成本高 | 长期统一到 pipeline.shared |
| R4 | 索引重建时机不一致 | 中途索引过时 | 在 guide 中建议维护后统一重建 |
| V1 | 跨域联想可得性低 | 用户预期落差 | 在引导中明确 LLM 编译前提 |
| M2 | format_ingest_dialogue() 从未被调用 | 死代码 | 清理或明确使用场景 |

### 低优先

| ID | 问题 | 影响 | 建议 |
|----|------|------|------|
| L1 | kwiki/ 模块大部分死代码 | 代码体积 | 长期清理 |
| L2 | legacy 文件保留域特定模式 | 仅影响旧域 | 文档标注即可 |
| L3 | HTML 未展示 9 种查询格式 | 产品展示不完整 | 下次更新 HTML |
| E1 | prompt 文件加载开销 | 可接受 | 长期优化 |
| E2 | 无增量收集机制 | 可接受 | 长期优化 |

---

## 八、优先行动建议

### 立即行动（本轮）

1. **修复断裂测试**：更新 test_wiki_lint_claims.py 中引用 claim_conflicts 的 3 个测试
2. **增加 delta 草稿回写引导**：在 maintenance-guide.md 场景 4 增加回写操作模板
3. **清理死代码**：移除 format_ingest_dialogue() 或标注使用场景

### 短期行动（下一版本）

4. **补充三阶段接口测试**：为 6 个脚本的 collect_*/apply_* 函数编写单元测试
5. **统一 utility 函数**：将重复的 parse_frontmatter、plain_text 等统一到 pipeline.shared
6. **增加 JSON schema 校验**：为 --apply 函数添加输入校验

### 长期优化

7. **增量收集机制**：基于 log.md 变更记录实现增量扫描
8. **自动维护建议**：stale_report.py 增加 --auto-suggest 模式
9. **deep_research_triggers.py 改造**：P5 项目
10. **kwiki/ 模块清理**：移除或归档
