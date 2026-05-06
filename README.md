# Obsidian Wiki Skill

**把外部知识编译进 Obsidian，构建可检索、可推理、可演化的个人知识操作系统。**

不是做一次性摘要——而是把阅读过的一切沉淀成两层：

```
raw/    ← 不可变原始证据（最终事实来源）
wiki/   ← AI 编译知识层（可演化、可检索、可输出）
```

设计思想参考 [Karpathy 的 llm-wiki 方法论](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)：ingest 是编译而不是归档，知识的价值在于可积累、可关联、可演化。

---

## 这个工具解决什么问题

个人知识库的普遍失败模式：导入几百篇文章后三个月就停止维护——因为**写入的成本是可见的，读出的价值却不是**。

Obsidian Wiki Skill 扭转了这个方向。每次入库之后，知识库不只是"多了一篇"，而是：

- **自动检测这篇文章对你现有立场的影响**（reinforce / contradict / extend）
- **自动将内容与已有开放问题关联**（open question 推进 → partial → resolved）
- **口语化查询，系统自动路由**（问什么就用什么格式，零认知成本）
- **入库后展示结构化影响报告**：跨域联想、开放问题、立场影响——而非只说"写入完成"
- **自动检测是否值得启动深度研究**（积累矛盾、跨域碰撞、知识缺口）
- **对话洞见自动捕获**：LLM 自动识别有价值的问答，用户只需说"沉淀"即可入库
- **深度研究智能触发**：vault 信息不足时自动提示升级，用户说"深入研究"即可启动
- **维护流程自动化**：健康评分、审核清理、综合刷新——LLM 自动判断，用户只做确认
- **智能检索**：语义索引 + 评分排序，替代 LLM 逐页 grep，大规模知识库也能快速定位
- **Brief 认知压缩增强**：7 种文章类型自适应分析，隐性假设识别 + 方法论评估 + 逻辑风险标注
- **分块深度精读**：长文档自动分块 → 逐块提取 → 跨块综合，精读版 claim 是粗读版的 9 倍
- **Schema 自动修正**：V2.0 compile JSON 嵌套错误、枚举偏差自动修正，不再需要手动修复
- **PDF 输出**：Brief 和深度研究报告自动生成 PDF，一键直达阅读

---

## 能做什么

### 多源统一入库

| 来源 | 支持 |
|------|------|
| 微信公众号文章 | ✅ |
| 通用网页 | ✅ |
| YouTube / Bilibili / 抖音 视频（字幕优先，ASR fallback） | ✅ |
| 视频合集/频道（断点续跑 + 冷却保护） | ✅ |
| 本地 Markdown / PDF / HTML / TXT | ✅ |
| DOCX / PPTX / XLSX / EPUB | ✅ |
| 直接粘贴纯文本 | ✅ |

入库自动执行**域优先路由**：检测内容主题域，自动匹配各 vault 的 `purpose.md` 关注领域，选最高重叠的 vault 落盘。

### 口语化智能查询

用户说自然语言，LLM 理解意图、调用检索脚本、综合答案、选择输出格式，零认知成本：

```
用户："什么是 BEV 感知？"           → 快速了解：3-5 句要点 + 来源
用户："准备开会讨论端到端自动驾驶"    → 认知简报：要点 + 反面 + 待讨论问题
用户："对比 BEV 和纯视觉方案"        → 对比分析：对比表 + 关键差异
用户："深入研究端到端自动驾驶量产可行性" → 深度研究：9 阶段假说驱动协议
```

查询流程：`wiki_retrieve.py` 从语义索引中评分排序 → 输出结构化上下文包 → LLM 综合回答 → 可选写入 outputs/。脚本做机械检索（索引构建、评分排序、段落提取），LLM 做语义判断（意图理解、综合回答）。

### 深度调研

假说驱动的 9 阶段调研协议，结合知识库存量知识与联网搜索，产出带证据标注的结构化报告（Why/What/How/Trace）。Phase 9.5 自动执行 7 项红线质量门控 + 依赖链审查，结果写入报告附录。报告自动生成 PDF，存储在 `wiki/research/` 目录。所有断言携带证据标签：`[Fact]` / `[Inference]` / `[Assumption]` / `[Hypothesis X%]` / `[Disputed]` / `[Gap]`

**智能触发**：查询过程中，LLM 自动判断 vault 信息是否足够。当遇到外部事实依赖、多源矛盾、高风险决策等情况时，自动在回答末尾提示用户升级到深度研究。

### 对话洞见捕获

LLM 在回答用户问题时自动判断问答价值（10 个信号评分，阈值 ≥ 3 分），有价值的洞见自动写入 `wiki/outputs/`。用户只需说"沉淀"即可升级为正式知识页，无需了解内部机制。

### 自动维护

- **健康评分**：入库后自动检查，评分下降时通知
- **Review Sweep**：自动清理已过时的待处理 output（规则匹配 + LLM 语义判断）
- **综合刷新**：新来源晚于综合页时自动建议刷新
- **维护建议**：`stale_report.py --auto-suggest` 输出结构化建议，按严重程度分级展示

### 知识图谱

- **Mermaid 静态图**：Obsidian 内直接渲染，Louvain 社区分组 + 度数剪枝
- **主图谱视角**：仅 concepts/entities/domains/syntheses，附 Obsidian 过滤建议
- **域子图页面**：按领域筛选的局部视图，解决大图谱噪音问题

---

## 快速上手

```powershell
# 1. 安装依赖（中国用户加 --china）
python scripts/check_deps.py --install

# 2. 初始化 Vault
python scripts/init_vault.py --vault "D:\Obsidian\MyVault"

# 3. 入库（Claude Code 交互式推荐）
# 在 Claude Code 对话里直接给一个 URL，说"入库"即可

# 4. 查询（智能检索 + LLM 综合，口语化沟通即可）
# 用户只需说自然语言："端到端自动驾驶的技术路线是什么？"

# 5. 日常维护
python scripts/wiki_lint.py --vault "D:\Vault"
python scripts/stale_report.py --vault "D:\Vault" --blind-spots
python scripts/stale_report.py --vault "D:\Vault" --auto-suggest  # 维护建议
python scripts/review_queue.py --vault "D:\Vault" --sweep  # 自动清理

# 6. 语义索引（入库后自动重建，也可手动触发）
python scripts/wiki_index_v2.py --vault "D:\Vault" --rebuild
python scripts/wiki_retrieve.py --vault "D:\Vault" --query "BEV感知" --top-k 5
```

---

## 适合谁

✅ 希望把微信/视频/网页/文件沉淀进 Obsidian，而不只是做一次性摘要
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
| [docs/product-overview.html](docs/product-overview.html) | 产品概述（架构图 + 时序图，浏览器打开） |
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
