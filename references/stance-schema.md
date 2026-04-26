# Stance Pages Schema

## 页面模板

```markdown
---
title: "我对 <topic> 的当前立场"
type: "stance"
status: "active"            # active | challenged | abandoned
graph_role: "knowledge"
graph_include: "true"
lifecycle: "official"
confidence: "medium"        # high | medium | low
last_updated: "YYYY-MM-DD"
created: "YYYY-MM-DD"
source_count: 0
---

# 我对 <topic> 的当前立场

## 核心判断
- ... （置信度：high/medium/low）

## 支持证据
- [[sources/slug1]]: ...
- [[sources/slug2]]: ...

## 反对证据（steel-man）
- ...

## 未解决子问题
- [[questions/slug]]

## 触发重新思考的条件
- 如果看到 X，我会重新评估

## 更新记录
- YYYY-MM-DD: [[sources/slug]] reinforce/contradict/extend
```

## Stance Impact Types

每次新 ingest 后，LLM 检查该 source 对现有 stance 的影响：

| Impact | 含义 | 动作 |
|---|---|---|
| `reinforce` | 支持现有核心判断 | 追加到支持证据，source_count++ |
| `contradict` | 与核心判断矛盾 | 追加到反对证据，可能降低 confidence |
| `extend` | 扩展/细化判断但不改变方向 | 更新核心判断措辞，追加更新记录 |
| `neutral` | 与此立场无关 | 不更新 |

## 状态流转

| 当前状态 | 触发条件 | 新状态 |
|---|---|---|
| `active` | 收到 contradict impact + confidence 降至 low | `challenged` |
| `challenged` | 收到 reinforce impact + confidence 升至 medium+ | `active` |
| `active/challenged` | 用户标记为不再关注 | `abandoned` |

## 创建条件

当某个 topic 积累 3+ 个 source 且出现观点分歧时，自动建议创建 stance 页。

## 目录结构

```
wiki/stances/<topic-slug>.md
```