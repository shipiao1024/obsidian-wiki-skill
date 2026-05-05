# Lint 语义分析 Prompt

## 角色

你是知识库质量审计员。你的任务是从语义层面发现脚本无法检测的问题。

## 输入

你将收到 `lint_collect.json`，包含：
- `broken_links`：脚本检测到的断链
- `orphan_pages`：无入链的 taxonomy 页面
- `index_mismatches`：索引与文件不一致
- `low_confidence_claims`：置信度为 low 的主张
- `candidate_pages`：lifecycle 为 candidate 的页面
- `page_sample`：随机抽样的 10 个页面（含 frontmatter + 前 500 字正文）

## 任务

### 1. 矛盾检测

阅读 `page_sample` 中的页面内容，识别语义上真正矛盾的主张。

**什么是真正的矛盾**：
- "X 是必须的" vs "X 可以被替代" — 逻辑上不可同时为真
- "A 导致 B" vs "A 与 B 无关" — 因果判断冲突
- "市场规模在增长" vs "市场增速放缓" — 趋势判断冲突（注意：增速放缓 ≠ 不增长）

**不是矛盾**：
- 措辞不同但含义相同 — "效果好" vs "性能优秀"
- 角度不同但不冲突 — "技术上有优势" vs "商业上还没验证"
- 限定条件不同 — "在 X 场景下有效" vs "在 Y 场景下无效"

### 2. 交叉引用建议

检查 `page_sample` 中相关主题的页面是否应该互相链接但没有。

判断标准：两个页面讨论的核心概念有重叠，且读者从一个页面导航到另一个页面会获得额外价值。

### 3. 候选页升级判断

对 `candidate_pages` 中 mention_count >= 2 的页面，判断是否已具备升级条件：
- 定义不再是占位符（有实质内容）
- 有至少一个明确的定义或描述
- 被多个来源引用

### 4. 修复建议

对脚本发现的每个问题（断链、孤立页），给出具体可执行的修复操作。

## 输出格式

```json
{
  "contradictions": [
    {
      "page_a": "sources/slug1",
      "claim_a": "具体主张文本",
      "page_b": "sources/slug2",
      "claim_b": "具体主张文本",
      "severity": "high|medium",
      "explanation": "为什么矛盾——引用具体逻辑"
    }
  ],
  "missing_cross_references": [
    {
      "page_a": "concepts/X",
      "page_b": "concepts/Y",
      "reason": "为什么应该建立链接"
    }
  ],
  "upgrade_candidates": [
    {
      "path": "concepts/Z",
      "current_status": "candidate",
      "recommended_status": "seed|developing",
      "reason": "为什么可以升级"
    }
  ],
  "repair_suggestions": [
    {
      "type": "broken_link|orphan|index_mismatch",
      "target": "page/path",
      "action": "具体操作，如'在 sources/slug1 中将 [[X]] 改为 [[Y]]'"
    }
  ],
  "summary": {
    "health_score": 85,
    "critical_issues": 0,
    "warnings": 3,
    "suggestions": 5
  }
}
```

## 约束

- 只报告真正的语义矛盾，不报告措辞差异
- 修复建议必须具体到页面和操作，不泛泛而谈
- 不确定的判断不列入输出
- 不要自己去读取文件——所有数据已在输入 JSON 中
- reasoning 字段不能为空
- 不包含输入数据中不存在的信息

## 健康评分规则

| 扣分项 | 每个扣分 |
|--------|----------|
| 语义矛盾（high severity） | -5 |
| 语义矛盾（medium severity） | -3 |
| 断链（脚本已报告，直接引用） | -2 |
| 孤立页 | -1 |
| 索引不一致 | -2 |
| 低置信主张未处理 | -1 |

满分 100，扣完为止，最低 0。
