# Obsidian Wiki Skill

**知识库随意图生长的系统。**

你说为什么关注，系统围绕意图组织认知；新领域反复出现，系统主动感知并提议；查一个库，自动桥接其他库的洞察。

设计思想参考 [Karpathy 的 llm-wiki 方法论](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)：ingest 是编译而不是归档，知识的价值在于围绕意图可积累、可关联、可生长。

> **产品概述**：[docs/product-overview.html](docs/product-overview.html)（浏览器打开）

![产品介绍1](docs/产品介绍1.jpg)
![产品介绍2](docs/产品介绍2.jpg)

---

## 为什么不一样

知识库的根本失败不是维护困难——是**不知道自己为什么存在**。

| 失败模式 | 根因 | 本系统的解法 |
|---------|------|------------|
| 导入几百篇后三个月停更 | 没有意图锚点，积累是噪音，检索再快也是空转 | **Value Point**：表达为什么关注，知识围绕意图组织 |
| 新方向沉默入库，无人感知 | 领域只能预声明，无法从内容中涌现 | **Domain Proposal**：同一领域累积 ≥3 篇来源，系统主动提议 |
| 多个库各自孤立，跨域洞察断裂 | 每个 vault 独立检索，看不到其他库的知识 | **跨 Vault 桥接**：检索时自动从匹配的其他库补充洞察 |

三层架构：

```
意图层   Value Point    — 表达"为什么关注"，不是"关注什么"
涌现层   Domain + Proposal — 领域从内容涌现，≥3 篇触发提案
物理层   Vault          — raw/ 不可变证据 + wiki/ AI 编译知识层
```

---

## 知识随意图生长

V2.1 核心能力——让知识库从被动归档变成主动生长：

- **意图锚定**：在 purpose.md 声明价值锚点，入库时自动匹配意图，知识围绕意图组织而非被动堆叠
- **领域涌现**：compile 产出 domain，不匹配已有锚点时累积；同 domain ≥3 篇来源后系统主动提议——"这个方向反复出现，要成为新锚点吗？"
- **跨库桥接**：查询时，跨域洞察指向其他 vault 的关注领域，自动补充检索 top-3，标记来源和桥接逻辑
- **路由建议**：入库后如果 domain 更匹配另一个 vault，影响报告显示建议；用户可一键迁移

## 入库即编译

V2.0 核心机制——入库不是归档，是认知编译：

- **立场影响检测**：reinforce / contradict / extend，不是只说"写入完成"
- **开放问题推进**：open → partial → resolved，自动关联已有问题
- **跨域联想**：方法论迁移、因果结构类比、抽象模式共享——带 bridge_logic 和迁移结论
- **精读 9 倍**：长文档自动分块 → 逐块提取 → 跨块综合，claim 密度是粗读的 9 倍
- **Schema 自动修正**：编译输出嵌套错误、枚举偏差自动修正

## 基础设施

多源入库、口语化查询、深度研究、维护自动化——稳定可靠，支撑上层价值：

**多源统一入库**

| 来源 | 支持 |
|------|------|
| 微信公众号文章 | ✅ |
| 通用网页 | ✅ |
| YouTube / Bilibili / 抖音 视频（字幕优先，ASR fallback） | ✅ |
| 视频合集/频道（断点续跑 + 冷却保护） | ✅ |
| 本地 Markdown / PDF / HTML / TXT | ✅ |
| DOCX / PPTX / XLSX / EPUB | ✅ |
| 直接粘贴纯文本 | ✅ |

**口语化智能查询**

```
"什么是 BEV 感知？"           → 快速了解：3-5 句要点 + 来源
"准备开会讨论端到端自动驾驶"    → 认知简报：要点 + 反面 + 待讨论问题
"对比 BEV 和纯视觉方案"        → 对比分析：对比表 + 关键差异
"深入研究端到端自动驾驶量产可行性" → 深度研究：9 阶段假说驱动协议
```

**深度调研**：假说驱动 9 阶段协议 + 7 项红线质量门控，所有断言携带证据标签 `[Fact]` / `[Hypothesis X%]` / `[Gap]`

**对话洞见捕获**：LLM 自动识别有价值的问答（10 信号评分），用户说"沉淀"即可入库

**自动维护**：健康评分、Review Sweep、综合刷新、结构化维护建议

**知识图谱**：Mermaid 静态图 + 域子图 + 主图谱降噪

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
python scripts/stale_report.py --vault "D:\Vault" --auto-suggest  # 维护建议
python scripts/review_queue.py --vault "D:\Vault" --sweep  # 自动清理
```

---

## 适合谁

✅ 希望知识库围绕意图生长，而不是被动堆叠文章
✅ 想知道知识库正在往什么方向走——新领域涌现时主动感知
✅ 多个知识库场景下，跨库洞察自动桥接
✅ 需要跟踪某个领域的进展，形成自己的立场和认知
✅ 使用 Claude Code 做日常工作，需要可持久化的知识底座

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
| [docs/product-overview.html](docs/product-overview.html) | 产品概述（价值架构 + 核心能力，浏览器打开） |
| [docs/SPEC.md](docs/SPEC.md) | 设计哲学、架构、完整功能规格 |
| [references/setup.md](references/setup.md) | 环境配置与依赖安装（含中国镜像指南） |
| [references/workflow.md](references/workflow.md) | 操作模式、pipeline、vault 结构、页面约定 |
| [references/interaction.md](references/interaction.md) | 用户对话路由、入库后引导模板 |
| [references/ingest-guide.md](references/ingest-guide.md) | 入库行为指南（五阶段流水线 + 编译策略） |
| [references/query-guide.md](references/query-guide.md) | 查询行为指南（智能检索 + 综合 + 9 种输出格式） |
| [references/research-guide.md](references/research-guide.md) | 深度研究行为指南（9 阶段协议概要） |
| [references/maintenance-guide.md](references/maintenance-guide.md) | 维护行为指南（lint / review / archive / graph） |
| [references/deep-research-protocol.md](references/deep-research-protocol.md) | 9 阶段深度调研协议详情 |

---

## License

MIT
