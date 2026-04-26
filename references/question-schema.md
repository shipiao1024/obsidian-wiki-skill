# Question Ledger Schema

## 页面模板

```markdown
---
title: "<question>"
type: "question"
status: "open"           # open | partial | resolved | dropped
graph_role: "knowledge"
graph_include: "true"
lifecycle: "official"
origin_source: "[[sources/<slug>]]"
origin_query: ""
created: "YYYY-MM-DD"
last_updated: "YYYY-MM-DD"
---

# <question>

## 当前部分答案
- ...

## 已知线索
- ...

## 回答需要什么类型的新材料
- ...

## 相关来源
- [[sources/slug1]]
- [[sources/slug2]]

## 更新记录
- YYYY-MM-DD: 来自 [[sources/slug]] — 新线索/部分答案/推翻
```

## 状态流转

| 当前状态 | 触发条件 | 新状态 |
|---|---|---|
| `open` | 新 ingest 提供了部分答案 | `partial` |
| `open` | 新 ingest 完全回答了问题 | `resolved` |
| `partial` | 新 ingest 完全回答了问题 | `resolved` |
| `partial` | 新 ingest 提供了更多线索 | `partial` (更新线索) |
| `open/partial` | 用户标记为不再关注 | `dropped` |

## 目录结构

```
wiki/questions/<slug>.md
```

slug 生成规则：取问题前 60 字符，去除标点，用 `-` 连接，确保唯一。

## 与 ingest 管道的集成

1. v2 compile 输出中的 `open_questions` 字段自动生成 question 页
2. 每次 ingest 后检查：新文章是否回答了任何 `open` 或 `partial` 状态的 question
3. `rebuild_index()` 在 index.md 中增加 Questions 区段