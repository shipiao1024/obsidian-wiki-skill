# Query Scripts

Query scripts for the Claude-obsidian-wiki-skill pipeline. Read this file when performing a wiki query.

---

## 设计原则

**Claude Code 是主路由层**，负责理解用户意图并选择 `--mode`。脚本的 `--mode auto` 仅用于 CLI 直调兜底。

```
用户口语 → Claude Code（意图理解 + mode 选择）→ wiki_query.py（执行）→ 输出
                ↑ 主路由                              ↑ 执行层
```

组合需求由 Claude Code 拆成多次调用。脚本不做意图理解。

---

## wiki_query.py

### 基本用法

```powershell
# Claude Code 调用（推荐）：由 Claude 选择 mode
python scripts/wiki_query.py "BEV 感知方案" --mode briefing --vault "D:\Vault"

# CLI 直调：不传 --mode，走 auto 兜底（正则匹配）
python scripts/wiki_query.py "什么是 BEV 感知" --vault "D:\Vault"
```

### 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `question` | 必填 | 自然语言问题（positional） |
| `--vault` | 自动发现 | Obsidian vault 路径 |
| `--mode` | `auto` | 输出模式。Claude Code 应显式传入，CLI 直调可省略走 auto |
| `--digest-type` | `deep` | digest 子类型：`deep` / `compare` / `timeline` |
| `--top` | `5` | 候选页面数量 |
| `--no-writeback` | false | 不写入 wiki/outputs/ |

### 10 种输出模式

| mode | 用途 | 典型触发 |
|------|------|---------|
| `brief` | 快速了解 | "是什么"、"定义"、"概述" |
| `briefing` | 会议准备 | "准备开会"、"汇报"、"简报" |
| `contradict` | 反驳质疑 | "反驳"、"反方"、"质疑" |
| `digest` | 深度综合 | "深入分析"（配合 --digest-type） |
| `essay` | 写文章 | "写文章"、"帮我写" |
| `reading-list` | 学习路径 | "学习路径"、"系统学习" |
| `talk-track` | 会议讨论 | "讨论材料"、"开会" |
| `draft-context` | 整理素材 | "素材"、"喂给 LLM" |
| `deep-research` | 深度研究初始材料 | "深入研究"（后续走推理驱动 8 阶段协议） |
| `auto` | 自动路由（兜底） | 不传 --mode 时的默认行为 |

### auto 模式（兜底）

当 Claude Code 未传 `--mode` 时，脚本通过 `intent_router.py` 的正则匹配自动选择模式。优先级：

1. context（素材/上下文/喂给）
2. deep-research（深入研究/系统分析）
3. digest --compare（对比/比较/vs）
4. digest --timeline（时间线/演变）
5. essay（写文章/帮我写）
6. reading-list（学习路径/系统学习）
7. contradict（反驳/反方/质疑）
8. briefing（准备会议/汇报/简报）
9. brief（是什么/定义/概述）
10. brief（默认）

**auto 模式的局限**：无法处理组合需求、模糊意图、非关键词表达。这些情况应由 Claude Code 在上层处理。

### 输出

脚本返回 JSON：

```json
{
  "question": "准备开会讨论端到端自动驾驶",
  "mode": "briefing",
  "auto_routed": "false",
  "entry_layer": "ask",
  "answer": "## 相关来源\n...",
  "used_pages": ["briefs/xxx", "sources/yyy"],
  "output": "wiki/outputs/2026-05-02--143000--准备开会讨论端到端.md"
}
```

- `mode`：实际使用的模式
- `auto_routed`：`"true"` 表示由 auto 模式自动选择，`"false"` 表示由调用方显式指定
- `entry_layer`：`"ask"` / `"digest"` / `"context"`，用于日志和分析

### 行为细节

- 读 `wiki/hot.md` 获取近期上下文
- 读 `wiki/index.md` 按词频 + folder 权重 + 页面状态打分，取 top N
- 优先读 `sources/` 和 `briefs/`，`syntheses/` 和 `comparisons/` 作补充
- `mature`/`evergreen` 页面获得打分加权（+2/+1）
- 问题含数字/日期/引用等高精度信号时，自动关联 `raw/articles/` 原文
- 结果写入 `wiki/outputs/`，更新 `wiki/hot.md` 和 `wiki/log.md`，重建 `wiki/index.md`
