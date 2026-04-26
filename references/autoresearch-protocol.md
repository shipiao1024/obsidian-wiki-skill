# Autoresearch Protocol

广域探索补盲协议，自动识别知识库缺口并定向搜索填充，3 轮递进聚焦。

## 触发条件

触发词：`"autoresearch"` / `"自动研究"` / `"深入调查"` / `"知识库补盲"`

适用场景：用户想围绕一个主题做多轮自主搜索和入库，但无具体命题/假说。

与现有模式区分：
- 简单事实查询 → `brief`
- 结构化概览 → `briefing`
- 多视角聚合（vault 内） → `digest`
- 广泛探索+自动补盲 → **autoresearch**
- 假说驱动+联网验证+证据标注 → `deep-research`

---

## 3 阶段工作流

### Phase 1: Vault Gap Scan

识别知识库当前覆盖缺口。

脚本调用：
```
python scripts/wiki_lint.py --vault <vault>
python -m kwiki review --vault <vault> --action blind-spots
python -m kwiki review --vault <vault> --action evolution
python scripts/question_ledger.py list --vault <vault> --json
python scripts/stance_manager.py list --vault <vault> --json
```

宿主 Agent 分析结果，产出：
- 欠覆盖域列表（orphan taxonomy、domain gaps）
- 高价值开放问题（open/partial questions）
- 活跃立场（active/challenged stances 需要新证据）
- 知识盲区（blind-spots.md 中的 research gaps）

### Phase 2: Targeted Web Search

宿主 Agent 按缺口优先级执行 3 轮递进搜索：

**Round 1: 广域搜索**
- 针对最大缺口域，WebSearch 3-5 个宽泛查询
- 选择 top 3 URL 走标准 ingest pipeline：
  ```
  python scripts/wiki_ingest.py --url <url> --vault <vault>
  ```
- 检查已覆盖，避免重复入库

**Round 2: 聚焦搜索**
- 针对高价值开放问题，WebSearch 2-3 个针对性查询
- 选择 top 2 URL 入库

**Round 3: 证据补充**
- 针对 active/challenged stances，WebSearch 1-2 个证据查询
- 选择 top 1 URL 入库

每轮搜索后：
- 重新检查已有覆盖，避免重复入库
- 如果该轮未发现新内容，提前终止

### Phase 3: Gap-fill Verification

验证补盲效果。

脚本调用：
```
python scripts/wiki_lint.py --vault <vault>
python -m kwiki review --vault <vault> --action blind-spots
```

宿主 Agent 产出：
- 覆盖改善报告：新增了哪些域/问题的来源
- 遗留缺口：仍然欠覆盖的域
- 建议下一步：是否有值得 deep-research 的战略级问题

更新 hot.md：
```
python -m kwiki review --vault <vault> --action evolution
```

---

## 区别矩阵

| 维度 | autoresearch | mini-research | deep-research |
|------|-------------|--------------|---------------|
| 阶段数 | 3 | 3 | 9 |
| 驱动力 | 缺口驱动（盲区→搜索） | 问题驱动（快速假说→验证） | 假说驱动（可证伪假说→验证） |
| 依赖账本 | 无 | 无 | 有（F/I/A/H/C/G/D 节点） |
| 搜索轮数 | 3 轮递进 | 2 轮定向 | adaptive rounds |
| 产出 | 覆盖改善报告 | 搜索指南+简要结论 | 结构化 Why/What/How/Trace 报告 |
| 证据标注 | 无 | 无 | 有（Fact/Inference/Gap 等） |
| 适用 | 知识库刚建、域覆盖不全 | 想快速了解某个话题 | 战略级决策需要系统验证 |

---

## 宿主 Agent 行为约束

1. 不要在单轮搜索中入库超过 5 篇——autoresearch 目的是拓宽，不是批量灌入
2. 每轮搜索后检查已有覆盖，重复来源直接跳过
3. 如果某轮搜索未发现新内容，提前终止而非强行凑满 3 轮
4. autoresearch 的入库走标准 ingest pipeline（fetch → ingest → compile → apply → review）
5. autoresearch 不产出独立报告——改善效果通过 Phase 3 的 lint + blindspots 验证