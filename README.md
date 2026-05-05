# Obsidian Wiki Skill

[English](README.en.md) | [简体中文](README.md)

**把外部知识编译进 Obsidian，构建个人知识操作系统。**

不是做一次性摘要——每次入库，整个知识库产生新的连接、新的问题、新的视角。写入成本可见，读出价值更可见。

```
raw/    ← 不可变原始证据（最终事实来源）
wiki/   ← AI 编译知识层（可演化、可检索、可输出）
```

设计思想参考 [Karpathy 的 llm-wiki 方法论](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)：ingest 是编译而不是归档，知识的价值在于可积累、可关联、可演化。

> **产品概述**：[docs/product-overview.html](docs/product-overview.html)（浏览器打开，含架构图、三阶段模式、核心能力、价值分析）

---

## 这个工具解决什么问题

个人知识库的普遍失败模式：导入几百篇文章后三个月就停止维护——因为**写入的成本是可见的，读出的价值却不是**。

Obsidian Wiki Skill 扭转了这个方向。每次入库，知识库不只是"多了一篇"，而是：

- **自动检测这篇文章对你现有立场的影响**（reinforce / contradict / extend）
- **自动将内容与已有开放问题关联**（open question 推进 → partial → resolved）
- **自动检测是否值得启动深度研究**（积累矛盾、跨域碰撞、知识缺口）
- **自动触发跨域联想**（bridge_logic → migration_conclusion，不只是"相似"而是"可迁移策略"）

每次入库，知识库整体升级。

---

## 架构设计

### LLM 优先，脚本做 I/O

LLM 做语义判断（相关来源识别、主张关系分析、综合内容生成），脚本做机械操作（文件读写、索引构建、PDF 生成）。核心 Python 依赖为零，全部 stdlib。

### 三阶段统一模式

所有维护流程遵循同一模式：

```
脚本收集数据 → LLM 语义判断 → 脚本执行写入
```

10 份结构化 Prompt 约束文件控制 LLM 行为：`ingest_compile_v2`（入库编译）、`ingest_impact`（影响分析）、`claim_evolution`（主张关系）、`lint_semantic`（健康检查）、`synthesis_refresh`（综合刷新）、`review_queue`（审核排序）、`review_sweep`（自动清理）、`insight_detection`（洞见识别）、`query_synthesis`（查询验证）、`research_hypothesis`（研究假说）。

### 质量控制

- **成熟度门槛**：≥2 来源引用才建正式页面，避免孤证污染知识层
- **风险分级**：Low（自动执行）/ Medium（展示结果，用户确认）/ High（需用户明确批准）
- **Two-Step CoT Compile**：先提取事实，再结构化编译，两次 LLM 调用保证入库质量
- **Schema 自动修正**：V2.0 compile JSON 嵌套错误、枚举偏差自动修正，不需手动修复

---

## 核心差异化

### 多源统一接入

微信公众号、通用网页、YouTube / Bilibili / 抖音（字幕优先，ASR fallback）、视频合集 / 频道（断点续跑 + 冷却保护）、本地 Markdown / PDF / HTML / TXT / DOCX / PPTX / XLSX / EPUB、直接粘贴纯文本——统一归一化为 Article 结构，域优先路由自动匹配 vault。

### 长文本分块精读（Map-Reduce）

长文档自动分块 → 逐块 LLM 提取 → 跨块综合。精读版 claim 数量是粗读版的 9 倍。自动阈值 >800 行，`--chunk-size` 可调，7 种来源类型全覆盖。后端 raw 文件层面操作，与前端来源类型完全解耦。

### Obsidian 原生知识图谱

拒绝花哨炫技。Mermaid 静态图直接在 Obsidian 内渲染，Louvain 社区分组 + 度数剪枝自动化关系净化。主图谱仅含 concepts / entities / domains / syntheses，域子图页面按领域筛选解决大图谱噪音问题。

### Brief 认知压缩报告

7 种文章类型自适应分析，产出 6 维骨架：生成力叙事、数据、推演、失效信号、方法论评估、隐性假设。附 40 条主张清单 + 置信度标注 + 来源溯源。自动生成 PDF。

### Deep Research 深度研究报告

推理驱动的 8 阶段协议，横纵双轴分析：纵向追时间深度（起源→演进→决策逻辑→阶段划分），横向追同期广度（竞品对比→生态位→趋势判断）。产出叙事驱动的结构化报告 + PDF，所有断言携带证据标签。

### 5 项质量门控

深度研究报告自动执行 5 项检验：叙事完整性、决策逻辑、反面证据、证据标签、边界条件。结果作为附录写入报告末尾。

### 置信度与证据体系

每条断言标注 `[Fact]` / `[Inference]` / `[Assumption]` / `[Hypothesis]` / `[Disputed]` / `[Gap]`。假说可被证伪，置信度随新证据升降。`grounding_quote` 回溯原文验证，ASR/PDF 容差匹配。

### 对话洞见捕获

LLM 在回答用户问题时自动判断问答价值（10 信号加权评分，阈值 >= 3 分），有价值的洞见自动写入 `wiki/outputs/`。用户只需说"沉淀"即可入库。

### 口语化查询 + 10 种输出格式

用户说自然语言，LLM 理解意图、调用检索、综合答案、选择格式。零认知成本：

```
用户："什么是 BEV 感知？"              → 快速了解：3-5 句要点 + 来源
用户："准备开会讨论端到端自动驾驶"       → 认知简报：要点 + 反面 + 待讨论问题
用户："对比 BEV 和纯视觉方案"           → 对比分析：对比表 + 关键差异
用户："深入研究端到端自动驾驶量产可行性"  → 推理驱动 8 阶段 + 横纵双轴分析
```

10 种输出模式：快速了解、会议准备、对比分析、深度综合、写文章、学习路径、会议讨论、整理素材、深度研究、自动路由。

### 自动维护

- **健康评分**：入库后自动检查，评分下降时通知
- **Review Sweep**：自动清理已过时的待处理 output（规则匹配 + LLM 语义判断）
- **综合刷新**：新来源晚于综合页时自动建议刷新
- **维护建议**：`stale_report.py --auto-suggest` 输出结构化建议，按严重程度分级

---

## 快速上手

```powershell
# 1. 安装依赖（中国用户加 --china）
python scripts/check_deps.py --install

# 2. 初始化 Vault
python scripts/init_vault.py --vault "D:\Obsidian\MyVault"

# 3. 入库（Claude Code 交互式推荐）
# 在 Claude Code 对话里直接给一个 URL，说"入库"即可

# 4. 查询（口语化沟通即可）
# 用户只需说自然语言："端到端自动驾驶的技术路线是什么？"

# 5. 日常维护
python scripts/wiki_lint.py --vault "D:\Vault"
python scripts/stale_report.py --vault "D:\Vault" --blind-spots
python scripts/stale_report.py --vault "D:\Vault" --auto-suggest
python scripts/review_queue.py --vault "D:\Vault" --sweep

# 6. 语义索引（入库后自动重建，也可手动触发）
python scripts/wiki_index_v2.py --vault "D:\Vault" --rebuild
python scripts/wiki_retrieve.py --vault "D:\Vault" --query "BEV感知" --top-k 5
```

微信抓取依赖上游 [wechat-article-for-ai](https://github.com/bzd6661/wechat-article-for-ai)。GitHub 发布版不再内置这个上游仓库；请按 [references/setup.md](references/setup.md) 的说明安装到 `.tools/wechat-article-for-ai`，或通过 `KWIKI_WECHAT_TOOL_DIR` 指向你已有的克隆目录。

---

## 适合谁

✅ 希望把微信 / 视频 / 网页 / 文件沉淀进 Obsidian，而不只是做一次性摘要
✅ 需要跟踪某个领域的最新进展，形成自己的立场和认知
✅ 经常需要为会议、写作、决策快速组织已有知识
✅ 使用 Claude Code 做日常工作，需要一个可持久化的知识底座
✅ 想在多 vault 场景下自动路由，不同主题知识各归其位

❌ 只需要一次性网页摘要
❌ 不使用 Obsidian
❌ 不接受本地脚本 + 文件系统工作流

---

## 环境要求

- **OS**：Windows（PowerShell），Linux/Mac 非官方支持
- **Python**：3.11+
- **Obsidian Desktop**：本地 vault
- **Claude Code**：推荐（交互式入库质量最高）

核心 Python 依赖为零（全部 stdlib）。各来源类型按需安装，详见 [docs/SPEC.md](docs/SPEC.md)。

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [docs/product-overview.html](docs/product-overview.html) | 产品概述（架构图、核心能力、价值分析，浏览器打开） |
| [docs/SPEC.md](docs/SPEC.md) | 设计哲学、架构、完整功能规格 |
| [references/setup.md](references/setup.md) | 环境配置与依赖安装（含中国镜像指南） |
| [references/workflow.md](references/workflow.md) | 操作模式、pipeline、vault 结构、页面约定 |
| [references/interaction.md](references/interaction.md) | 用户对话路由、入库后引导模板 |
| [references/ingest-guide.md](references/ingest-guide.md) | 入库行为指南（五阶段流水线 + 编译策略） |
| [references/query-guide.md](references/query-guide.md) | 查询行为指南（智能检索 + 综合 + 9 种输出格式） |
| [references/research-guide.md](references/research-guide.md) | 深度研究行为指南（推理驱动 8 阶段 + 横纵双轴分析） |
| [references/maintenance-guide.md](references/maintenance-guide.md) | 维护行为指南（lint / review / archive / graph） |
| [references/deep-research-protocol.md](references/deep-research-protocol.md) | 推理驱动 8 阶段协议 + 横纵双轴分析详情 |

---

## License

MIT
