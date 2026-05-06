---
name: obsidian-wiki
description: Obsidian 个人知识操作系统。入库（微信/网页/视频/文件）、查询（口语化）、深度研究、维护。两层架构：raw/ 不可变原始证据，wiki/ AI 编译知识层�?---

# Obsidian Wiki Skill

两层知识工作流：`raw/` 存不可变原始证据，`wiki/` �?AI 编译知识层。你（Claude Code）是主入口和决策者，Python 脚本处理机械操作（fetch / 写文�?/ PDF / 图谱）�?
## 触发条件

**硬触�?*（始终激活）�?- 用户消息含入�?URL：`mp.weixin.qq.com`、`bilibili.com/video`、`youtube.com/watch`、`youtu.be/`、`douyin.com/video`
- 用户消息含意图关键词：`落盘`、`入库`、`ingest`、`归档`、`save to wiki`、`存到知识库`

**软触�?*（vault 上下文存在时激活）�?- 用户消息含：`知识库`、`wiki`、`维护知识库`、`日常维护`、`lint`、`review`、`sweep`、`状态`、`维护建议`
- 用户�?`autoresearch`、`自动研究`、`深入研究`、`deep research`、`深度分析`、`系统分析`
- 用户�?`沉淀`、`结晶`（洞见沉淀流程�?
**不触�?*�?- 用户只要求总结/翻译/解释文章，无入库意图
- 用户问与知识库无关的通用问题

## 任务识别 �?加载对应 Guide

收到请求后，先识别任务类型，再加载对应的 guide 文件�?*不要一次性加载所有文件�?*

| 任务 | 识别信号 | 加载 |
|------|---------|------|
| **入库** | URL / 文件路径 / "入库" / "ingest" | `references/ingest-quickstart.md`（快速参考）+ `references/ingest-guide.md`（详细流程） |
| **查询** | 关于知识库内容的问题 | `references/query-guide.md` |
| **深度研究** | "深入研究" / "系统分析" / "deep research" | `references/research-guide.md` |
| **维护** | "lint" / "体检" / "日常维护" / "review" / "sweep" / "状�? | `references/maintenance-guide.md` |
| **沉淀** | "沉淀" / "结晶" | `references/interaction.md` § 洞见沉淀 |
| **保存对话** | "save" / "保存对话" / "记录讨论" | `references/interaction.md` § 保存对话 |
| **首次配置** | 首次调用或依赖缺�?| `references/setup.md` |

## 通用约定

### Vault 路径
- �?`vault.conf` 或用户指定的 `--vault` 获取
- �?vault 时按 `purpose.md` 域匹配自动选择

### 写入边界
- **你直接写�?*：`wiki/outputs/`（查询结果、delta 草稿）�?临时工作产物，不污染主知识层
- **脚本写的**：`raw/`、`wiki/briefs/`、`wiki/sources/`、`wiki/concepts/` 等正式页�?�?通过入库流水�?- **不主动修�?*：正�?wiki 页面（除非用户明确要求）

### 引用规范
- �?`[[页面名]]` 格式引用 wiki 页面
- 区分 vault 知识（标注来源）和模型补充知识（标注"模型知识，vault 中暂�?�?- 精确数字/日期/原文引用必须回看 `raw/` 验证

### 不要加载
- `docs/` 目录 �?用户文档，非运行时上下文
- `README.md`、`README.en.md` �?项目概述

## 脚本入口（仅名称�?
入库相关：`init_vault.py`、`wiki_ingest.py`、`llm_compile_ingest.py`（`--two-step`）、`apply_compiled_brief_source.py`、`source_adapters.py`、`adapter_result_to_article.py`

查询相关：`wiki_query.py`（索引重�?+ 结果写入，查询逻辑由你执行）、`wiki_index_v2.py`（语义索引构�?+ 查询）、`wiki_retrieve.py`（智能检索，替代 grep 搜索�?
维护相关：`wiki_lint.py`、`wiki_size_report.py`、`stale_report.py`（`--auto-suggest`）、`refresh_synthesis.py`、`review_queue.py`（`--sweep`、`--apply-sweep`）、`archive_outputs.py`、`graph_cleanup.py`、`graph_trim.py`、`export_main_graph.py`、`apply_approved_delta.py`、`delta_compile.py`

深度研究：`deep_research.py`

视频相关：`import_jobs.py`、`install_video_cookies.py`

其他：`question_ledger.py`、`stance_manager.py`、`check_deps.py`、`env_compat.py`

脚本详情�?PowerShell 示例：加载对�?guide 文件�?
## 参考文件索�?
### 行为指南（按需加载�?
| 文件 | 内容 | 加载时机 |
|------|------|---------|
| `references/ingest-quickstart.md` | 入库快速指南（精简版，核心流程�?| 首次入库 / 快速参�?|
| `references/ingest-guide.md` | 入库工作流完整版（fetch �?ingest �?compile �?apply �?report�?| 入库任务详细参�?|
| `references/query-guide.md` | 查询工作流（智能检�?�?理解 �?合成 �?写入�?| 查询任务 |
| `references/research-guide.md` | 深度研究工作流（推理驱动 8 阶段 + 横纵双轴分析）�?| 深度研究 |
| `references/maintenance-guide.md` | 维护工作流（脚本收集 �?LLM 判断 �?脚本执行�?| 维护任务 |
| `references/interaction.md` | 用户对话路由 + 入库后引�?+ 保存对话 | 保存对话 / 入库引导 |

### LLM 约束 Prompt（guide 引用�?
| 文件 | 内容 | 引用�?|
|------|------|--------|
| `references/prompts/lint_semantic.md` | 健康检查语义分析约�?| maintenance-guide |
| `references/prompts/claim_evolution.md` | 主张关系分析约束 | maintenance-guide |
| `references/prompts/synthesis_refresh.md` | 综合页内容生成约�?| maintenance-guide |
| `references/prompts/review_queue.md` | 审核队列排序约束 | maintenance-guide |
| `references/prompts/review_sweep.md` | Review sweep 自动清理约束（R1/R2 规则 + LLM 语义判断�?| maintenance-guide |
| `references/prompts/insight_detection.md` | 洞见识别约束�?0 信号加权评分，阈�?�?3�?| query-guide |
| `references/prompts/ingest_impact.md` | 入库影响分析约束 | ingest-guide |
| `references/prompts/ingest_compile_prompt_v2.md` | 入库编译约束 | ingest-guide |
| `references/prompts/query_synthesis.md` | 查询综合与验证约�?| query-guide |
| `references/prompts/research_hypothesis.md` | 研究假说形成与校准约�?| research-guide |

### 参考文档（不加载到运行时）

| 文件 | 内容 |
|------|------|
| `references/workflow.md` | 操作模式 + vault 结构 + 页面约定 |
| `references/setup.md` | 环境配置 + 依赖安装 |
| `references/video-rules.md` | 视频处理 + 合集保护 + cookie |
| `references/deep-research-protocol.md` | 推理驱动 8 阶段协议 + 横纵双轴分析 |
| `references/pipeline-scripts.md` | 脚本参数详情 |
