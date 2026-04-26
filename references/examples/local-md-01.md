---
title: "本地回归样本 Markdown"
author: "Acceptance Fixture"
date: "2026-04-24"
source: "local://acceptance/local-md-01"
---

# 本地回归样本 Markdown

这是一份用于主入口回归测试的本地 Markdown 样本。

## 核心观点

- 本地文件入口不应依赖外部网络。
- 主入口应能把本地 Markdown 写入 `raw/articles`、`wiki/sources`、`wiki/briefs`。
- 这类样本适合优先用于快速健康检查，而不是外部 adapter 验证。

## 使用目的

- 验证 `local_file_md` 能进入统一 adapter 层。
- 验证 `AdapterResult -> Article -> ingest` 仍然连通。
- 验证 `index.md` 与 `log.md` 更新没有被多来源入口改坏。

## 结论

如果这份样本都无法成功入库，问题通常不在来源本身，而在主入口路由、bridge、或 ingest 后半段。
