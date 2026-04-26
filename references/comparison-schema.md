# Comparison Schema

## 页面模板

```markdown
---
title: "<subject_a> vs <subject_b>"
type: "comparison"
status: "seed"
graph_role: "knowledge"
graph_include: "true"
lifecycle: "official"
subject_a: "<subject_a>"
subject_b: "<subject_b>"
created: "YYYY-MM-DD"
last_updated: "YYYY-MM-DD"
---

# <subject_a> vs <subject_b>

## 对比维度
- **维度 1**: <subject_a> 的特点 / <subject_b> 的特点
- **维度 2**: ...

## <subject_a> 的优势
- ...

## <subject_b> 的优势
- ...

## 综合判断
...

## 相关来源
- [[sources/slug1]]
- [[sources/slug2]]
```

## 触发条件

Comparison 页面在以下情况下自动生成：

1. **v2 compile payload 包含 comparisons 字段**：当 LLM 编译结果中检测到来源内容涉及两个可比较的主体时，v2 compile 输出的 `comparisons` 数组会包含 `{subject_a, subject_b, dimensions, verdict}` 条目。`ingest_article()` 在 apply 阶段会调用 `ensure_comparison_page()` 自动创建 comparison 页。

2. **手动创建**：通过 `ensure_comparison_page()` 或直接在 `wiki/comparisons/` 下创建 Markdown 文件。

## 自动创建逻辑

在 `pipeline/ingest_orchestrator.py` 的 `ingest_article()` 函数中（通过 `pipeline/apply.py` shim 也可访问）：
- 检查 v2 compile 结果是否包含 `comparisons` 字段
- 对每个 comparison 条目调用 `ensure_comparison_page()`
- 如果 comparison 页已存在，合并新维度到现有页面
- slug 生成规则：`comparison_slug(subject_a, subject_b)` → 取两主体关键词，用 `-vs-` 连接

## 目录结构

```
wiki/comparisons/<slug>.md
```

## 与 ingest 管道的集成

1. v2 compile 输出中的 `comparisons` 数组自动触发 comparison 页创建
2. `rebuild_index()` 在 index.md 中增加 Comparisons 区段
3. `export_main_graph.py` 将 comparison 页纳入知识图谱节点
4. `wiki_lint.py` 检测孤儿 comparison 页（无 source 同时提及两主体）