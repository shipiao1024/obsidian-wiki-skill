# Deep Research Protocol

假说驱动的深度调研协议，结合知识库已有知识与联网检索，产出带证据标注的结构化分析报告。

## 触发条件

三要素同时满足时触发 deep-research：
1. **战略重要性**：答案将影响决策/方向/架构
2. **外部现实依赖**：vault 无法单独回答，需要验证外部事实
3. **框架风险**：用户的第一表述可能不是真实问题

触发词：`"深入研究 X"` / `"深度分析 X"` / `"deep research X"` / `"系统分析 X"` / `"我需要做关于 X 的决策/判断/方案"`

与现有模式区分：
- 简单事实查询 → `brief`
- 结构化概览 → `briefing`
- 多视角聚合（vault 内） → `digest`
- 广泛探索（无具体命题） → `autoresearch`
- 假说驱动+联网验证+证据标注 → **deep-research**

---

## 9 阶段工作流

### Phase 0: 激活与上下文收集

脚本调用：
```
python scripts/wiki_query.py "<topic>" --mode briefing --vault <vault>
python scripts/question_ledger.py list --vault <vault> --json
python scripts/stance_manager.py list --vault <vault> --json
```
读取 `wiki/hot.md` + `wiki/index.md`。

### Phase 1: 意图扩展

宿主 Agent 做推理（无脚本调用）：
- 问用户 1-2 个高价值问题：为什么重要、真正关心什么、好的答案什么样
- 记录用户内在模型到研究上下文页

### Phase 2: 需求审计 + 假说形成

宿主 Agent 做推理 + 脚本持久化：
- 分离表面需求/操作需求/本质需求
- 形成 2-4 个可证伪假说

**假说卡格式**：
```json
{
  "claim": "具体的可证伪断言",
  "type": "causal | structural | comparative | threshold",
  "confidence": 25,
  "confirm_evidence": "什么证据能确认这个假说",
  "contradict_evidence": "什么证据能反驳这个假说",
  "confirm_queries": ["确认查询 1", "确认查询 2"],
  "contradict_queries": ["反驳查询 1"]
}
```

脚本调用：
```
python scripts/deep_research.py init --vault <vault> --topic "<topic>" --hypotheses-json hypotheses.json
python scripts/question_ledger.py create --vault <vault> --question "<hypothesis claim>" --origin-query "<original topic>"
```

### Phase 3: Vault 证据收集

脚本调用：
```
python scripts/deep_research.py collect-vault-evidence --vault <vault> --topic "<topic>" --claims "<claim1>" "<claim2>"
```

对每个假说，宿主 Agent 将 vault 发现分类为：
- **F (Fact)**：来自 source 页的直接事实
- **I (Inference)**：多源推理结论
- **A (Assumption)**：未经验证的假设

来源评级映射：`quality: high` → Tier 1，`quality: acceptable` → Tier 2，`quality: low` → Tier 3

### Phase 4: 假说驱动联网研究（adaptive rounds）

核心循环：
1. 选择最低置信度假说
2. WebSearch 执行确认查询 + 反驳查询
3. 每个结果 URL 走标准 ingest pipeline：
   ```
   python scripts/wiki_ingest.py --url <url> --vault <vault>
   python scripts/llm_compile_ingest.py --prepare-only --lean --vault <vault> --raw <raw_path>
   # 宿主 Agent 在对话中编译
   python scripts/apply_compiled_brief_source.py --vault <vault> --compiled-json <json_path>
   ```
4. 更新假说置信度：
   - Tier 1 确认：+15-25%
   - Tier 1 反驳：-20-35%
   - 多个独立 Tier 1 确认：提升到 Supported (70%+)
5. 更新依赖账本：
   ```
   python scripts/deep_research.py update-ledger --vault <vault> --topic "<topic>" --action add-fact --claim "<claim>" --source "<ref>" --tier <1|2|3>
   python scripts/deep_research.py update-ledger --vault <vault> --topic "<topic>" --action update-confidence --hypothesis-id <H-XX> --confidence <N> --reason "<reason>"
   ```

**证据充分性门控**（必须通过才能退出 Phase 4）：
```
python scripts/deep_research.py check-sufficiency --vault <vault> --topic "<topic>"
```
门控规则：
- 所有假说已更新（不在 Preliminary）
- 每个分支有至少一个 F 节点
- 无结论仅依赖 A 节点
- 争议块非空

不通过 → 继续下一轮搜索。后续阶段（压力测试、预验尸）发现缺口 → 回到 Phase 4 定向补充。

### Phase 5: 外部事实校准

宿主 Agent 产出四块：
- **共识**：多个独立 Tier 1/2 来源一致的部分
- **边界**：文档记录的实际约束
- **争议**：可信来源之间不一致的部分
- **假说结果**：每个假说的校准状态和置信度

### Phase 6: 根本问题挖掘

宿主 Agent 做推理：
- 一阶原理检查（用校准边界，非内部逻辑）
- 压缩到 1-3 根本问题（每个追踪到至少一个 F/I 节点）

### Phase 7: 情景压力测试

对每个主要结论，3-4 情景（基准/压力 A/压力 B/复合），提取边界条件。

脚本调用：
```
python scripts/deep_research.py record-scenarios --vault <vault> --topic "<topic>" --scenarios-json scenarios.json
```

scenarios.json 格式：
```json
[
  {
    "conclusion": "结论文本",
    "base_case": "Holds / Partial / Fails",
    "stress_a": "Holds / Partial / Fails",
    "stress_b": "Holds / Partial / Fails",
    "compound": "Holds / Partial / Fails",
    "boundary_condition": "具体边界条件声明"
  }
]
```

### Phase 8: 预验尸

假设主要建议已失败 → 3 个具体失败情景，映射到依赖账本根节点。

脚本调用：
```
python scripts/deep_research.py record-premortem --vault <vault> --topic "<topic>" --premortem-json premortem.json
```

premortem.json 格式：
```json
[
  {
    "scenario": "失败情景描述",
    "mechanism": "失败机制",
    "ledger_root": "H-01",
    "resolution": "应对措施"
  }
]
```

### Phase 9: 收敛与报告打包

1. 证据密度检查（不通过 → 回 Phase 4）
2. 打包 Why/What/How/Trace 报告
3. 所有强断言带证据标签：`[Fact]` / `[Inference]` / `[Assumption]` / `[Hypothesis X%]` / `[Disputed]` / `[Gap]`
4. 稳定结论 vs 工作假说显式标注

脚本调用：
```
python scripts/deep_research.py finalize-report --vault <vault> --topic "<topic>" --report-file report.md --run-closure
```

---

## 报告结构（Why/What/How/Trace）

### Why — 根本问题
- 根本问题陈述 + 证据锚
- 框架失败注记（如果需求审计改变了初始框架）
- 稳定性评级

### What — 核心结论
- **稳定结论**（≥70% 置信度，有 F/I 节点支撑）
- **工作假说**（40-70%，有部分证据）
- **关键边界**（每个结论的边界条件声明）
- **明确排除**（不属于本研究范围的内容）

### How — 实施路径
- 阶段分解
- 应急分支
- 必须引入 vs 必须避免

### Trace — 证据追踪
- 事实清单
- 情景压力测试表
- 预验尸摘要
- 假说置信度汇总
- 差距与假设清单

---

## 证据标签系统

所有强断言必须携带证据标签：
- `[Fact]` — 来自 Tier 1/2 来源的直接事实
- `[Inference]` — 从多个事实推理得出的结论
- `[Assumption]` — 未经验证的假设
- `[Hypothesis X%]` — 可证伪假说，带当前置信度
- `[Disputed]` — 可信来源之间存在争议
- `[Gap]` — 缺乏证据，需要进一步研究

---

## 置信度标尺

| 范围 | 标签 | 含义 |
|------|------|------|
| 0-20% | Preliminary | 刚形成，无证据支撑 |
| 20-40% | Developing | 有初步线索，但不足以确认或反驳 |
| 40-60% | Working | 有部分证据支持，但有明显差距 |
| 60-80% | Supported | 多个独立来源确认，边界条件清晰 |
| 80-100% | Stable | 证据充分，边界条件经过压力测试 |

---

## 依赖账本节点类型

| 类型 | 标签 | 含义 | 置信度规则 |
|------|------|------|-----------|
| F | 事实 | 来自来源页的直接事实 | 基于 Tier 1/2 来源：90-100%；Tier 3：50-70% |
| I | 推理 | 从多个事实推理得出 | ≤ min(依赖链置信度) |
| A | 假设 | 未经验证的假设 | 0-30% |
| H | 假说 | 可证伪的研究假说 | 按证据动态更新 |
| C | 结论 | 从假说+事实得出的结论 | ≤ min(依赖链置信度) |
| G | 差距 | 缺乏证据的领域 | N/A |
| D | 争议 | 来源之间存在分歧 | N/A |

---

## 来源评级

| Tier | 来源类型 | 置信度影响 |
|------|---------|-----------|
| 1 | 一手研究、分析师报告、标准文档、监管文件 | 确认 +15-25%，反驳 -20-35% |
| 2 | 可靠新闻、从业者博客、会议论文 | 确认 +10-20%，反驳 -15-25% |
| 3 | 论坛、匿名帖、聚合摘要 | 仅用于三角验证，不可锚定 Fact 节点 |

映射 obsidian-wiki source quality：`high` → Tier 1，`acceptable` → Tier 2，`low` → Tier 3

---

## Challenger Mode

当以下信号出现时，宿主 Agent 自动进入 Challenger Mode：
- 用户接受了可能有框架错误的表述
- 假设被当作事实使用
- 置信度在没有新证据的情况下膨胀
- 收敛基于稀薄证据

Challenger Mode 行为：
- 对每个强断言追问证据来源
- 主动寻找反驳论据
- 明确标注哪些是 Assumption 而非 Fact