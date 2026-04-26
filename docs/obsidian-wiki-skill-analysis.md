# Claude-obsidian-wiki-skill 深度分析报告

> 分析时间：2026-04-25  
> 分析对象：`Claude-obsidian-wiki-skill-main`（v2026.04.24-bili-collection-rc2）  
> 分析维度：架构合理性 / 用户价值挖掘 / Skill 框架工程哲学

---

## 总判断

这个 skill 已远超"草稿"水准：12k 行代码、有版本锁定、有回归基线、有清晰的两层知识模型、有 v1/v2 schema 演进、有真实跑通的 cookie/collection 保护机制。

你已经做完了 Karpathy 风格 wiki 的**操作系统层**（raw/wiki 分层、ingest/query/review/lint/delta/archive 五条管道），并在 v2 schema 里把"LLM 编译器内核"也基本接通了。

但当前存在三个隐性裂缝：

1. **工程层**：命名/职责边界已被实际功能演进甩开
2. **产品层**：用户价值停在"信息消化"，没进入"决策辅助/知识杠杆"
3. **框架层**：skill 作为整体太重，没有形成清晰的可复用层次

---

## 一、架构合理性与重构建议

整体设计哲学（host-agent 优先 + raw/wiki 双层 + 五阶段流水线 + v2 知识提案）站得住，不需要推倒。但执行层有六个具体问题。

### 1. 命名债 vs 实际能力的错位

- skill 名是 `wiki`，主脚本是 `wiki_ingest_wechat.py`（2304 行），但实际承担的是"多源统一入口路由器"
- 环境变量统一前缀是 `WECHAT_WIKI_*`，但已经覆盖到视频、PDF、网页
- SKILL.md 里自己也写了"the current default script name still reflects the original project focus"——这是"我知道但还没改"的技术债

**代价**：新用户会被名字骗进错误的心智模型，认为这是个微信归档工具。

**建议**：下一个 minor 版本做 rename（`wiki_ingest.py`、`OBS_WIKI_*` 或 `KWIKI_*`），保留旧名作为 alias 一两个版本。

### 2. 上帝脚本与单文件适配器

| 文件 | 行数 | 问题 |
|---|---|---|
| `wiki_ingest_wechat.py` | 2304 | 承担路由器+orchestrator+内容生成三种角色 |
| `source_adapters.py` | 1229 | 所有 source adapter 堆在一个文件 |
| `test_wiki_ingest_wechat_v2.py` | 1606 | 测试膨胀说明主脚本职责过多 |

五阶段流水线（fetch/ingest/compile/apply/review）在文档里很清晰，但代码组织没有反映这个分层。

**建议**：

- `source_adapters.py` 拆成 `adapters/wechat.py`、`adapters/web.py`、`adapters/video.py`、`adapters/local.py`、`adapters/text.py`，加 `adapters/__init__.py` 用 `source_registry` 做 dispatch
- `wiki_ingest_wechat.py` 拆成薄 orchestrator + `pipeline/fetch.py`、`pipeline/ingest.py`、`pipeline/apply.py`（✅ 已执行；apply.py 后续进一步拆成 page_builders.py + taxonomy.py + ingest_orchestrator.py + index_log.py + shim）
- compile 层（heuristic + LLM）合并成 `pipeline/compile.py`，两种模式共享接口

额外收益：测试从 1606 行巨型黑盒测试变成对单一阶段的单元测试，回归更稳定。

### 3. 五阶段在文档里是 first-class，在代码里是 implicit

每个阶段应该有：
- 一个明确的 CLI 入口（`python -m kwiki.fetch`、`python -m kwiki.compile`...）
- 一个稳定的 JSON 输入/输出契约
- 一个 fixture 化的 mock 模式

这样宿主 Agent 可以按阶段拼装，而不需要理解整个脚本的内部状态。也方便后面把某一阶段单独抽成原子 skill。

### 4. SKILL.md 单文件 595 行——上下文成本过高

每次触发时都要进上下文，595 行已经太重。

**建议**：

- 顶层 SKILL.md 收缩到 100-150 行，只保留 trigger 信号 + 路由规则 + 五阶段心智模型
- "Script Reference"、"Vault Contract"、"Operating Modes" 详细说明全部下沉到 `references/`，按需 view
- 用明确指针：`Read references/X.md when you need Y`，而不是全部塞在 SKILL.md 里以防万一

测试方法：把 SKILL.md 切短后让一个新对话执行典型 ingest 任务，看是否能完成。如果能，短版本就够。

### 5. 知识层的生命周期是单向的，缺少"降级/淘汰"机制

当前流水线只走"成熟化"方向：`raw → source/brief → concepts/entities → domains/syntheses`。

但真实的个人知识库会出现：
- 某个 concept 三个月前很重要，现在不再是焦点
- 某个 synthesis 的核心判断被新证据推翻，但没人去 demote
- 某个 entity 已经淡出（公司倒闭、产品下线）

`stale_report.py` 部分覆盖了这个，但缺少：

- **claim-level supersession**：新 claim 不仅 conflict，还显式 supersede 旧 claim
- **冷启动衰减**：长期未被引用的 concept 自动建议降级
- **领域演化追踪**：domain 关注重心随时间变化的可视化

### 6. 跨平台与可移植性是公开发布的硬限制

Windows 优先、PowerShell 默认、APPDATA 路径，对 skill 的潜在用户群体是个明显限制。

**建议**：保持 Windows 优先的实现路径，但 SKILL.md 不应假设 Windows。adapter 层抽象平台差异，文档里 PowerShell 与 bash 双版本示例。

---

## 二、用户价值挖掘——从"信息消化"到"知识杠杆"

这是最值得花时间的部分。要破当前瓶颈，先要换一个看用户的角度。

### 核心失败模式的诊断

个人知识库赛道有一个**反复出现的失败模式**：用户兴致勃勃地导入几百篇文章，三个月后停止维护，因为系统是"只写不读"的。原因不是 ingest 不够好，而是**写入的成本被看见了，读出的价值没有**。

### 用户痛点的递增曲线

| 层级 | 用户痛点 | 当前 skill 解决度 |
|---|---|---|
| L1 | "我读过这文章但找不回来了" | ✅ 已解决（raw 层） |
| L2 | "我有 200 篇，没时间重读" | ⚡ 部分解决（briefs） |
| L3 | "我想搞懂某主题，但单篇视角太窄" | ⚡ 部分解决（syntheses） |
| L4 | "新材料来了，我的认知应该如何更新？" | 🔶 弱解决（v2 update_proposals） |
| L5 | "我此刻要做决定/写东西，知识库能帮上什么？" | ❌ 几乎未解决 |
| L6 | "我对 X 现在的看法是什么？哪里不确定？" | ❌ 未解决 |
| L7 | "我的知识库中有哪些被忽视的洞察/没回答的问题？" | ❌ 未解决 |

当前核心交付在 L1-L4。真正的产品壁垒在 **L5-L7**——这是从"知识仓库"升级到"会思考的第二大脑"的分水岭。

### 7 个高价值 Feature 方向

#### A. Stance Pages（立场页）—— 最高 ROI 的新页面类型

为每个重要主题维护 `wiki/stances/<topic>.md`：

```markdown
# 我对 X 的当前立场

## 核心判断
（我现在认为...，置信度：high/medium/low）

## 支持证据
（最强的 2-3 条，来自哪些 source）

## 反对证据（steel-man）
（我见过的最强反驳）

## 未解决子问题
（我还不确定的具体点）

## 触发重新思考的条件
（如果看到 X，我会重新评估）
```

关键：它**主动暴露认知状态**，不是被动汇总。每次新 ingest 时 LLM 检查：这篇文章对我现有的 stance 是 reinforce / contradict / extend？这比 syntheses 更接近"知识在我脑子里的样子"。

#### B. Question Ledger（开放问题账本）—— 最容易实现的高价值产物

`wiki/questions/<slug>.md`，每条记录：

- 一个具体问题
- 来自哪里（哪篇 source、哪次 query）
- 当前部分答案 / 已知线索
- 回答这个问题需要什么类型的新材料
- 状态：`open` / `partial` / `resolved` / `dropped`

每次 ingest，LLM 检查"这篇文章有没有回答任何 open question？" → 自动生成 question→source 链接。

这把整个知识库从"已知答案的归档"反转成"未答问题的驱动"——是 Naval/Tiago 一类知识管理系统都没做好的部分。

#### C. 决策辅助型 Query（Briefing on Demand）

把 `wiki_query.py` 升级为多种模式：

| 模式 | 用途 |
|---|---|
| `--mode brief` | 当前的回答模式 |
| `--mode briefing` | 给定上下文（"明天和投资人聊 AIDV"），输出结构化简报：相关 sources、关键 claims、已知争议、open questions、我的 stance |
| `--mode draft-context` | 给定写作主题，输出可直接 paste 到草稿里的素材包（带引用） |
| `--mode contradict` | 给定一个论点，从知识库找最强反驳 |

差异：从"查找信息"变成"为决策/输出 ready 的素材"。

#### D. 类型化的概念关系图

当前 graph 是无类型的链接关系。升级为带 edge type 的关系图：

| 边类型 | 语义 |
|---|---|
| `supports` / `contradicts` | 论证关系 |
| `extends` / `narrows` | 概念范围关系 |
| `example-of` / `instance-of` | 分类关系 |
| `prerequisite` / `applies-in` | 依赖关系 |
| `predicts` / `confirmed-by` / `falsified-by` | 预测追踪 |

v2 compile 输出里已经有 `contradictions / reinforcements`，往前推一步就可以了。可视化上 Obsidian 原生不支持 typed edges，但可以用 mermaid 或独立的 graph view 输出。

实用价值：支持"沿着 contradicts 边走一遍我所有有争议的判断"——这比单纯的知识地图有 10 倍的实用价值。

#### E. 时间维度——知识演化追踪

现在所有页面都是"当前状态快照"。加一个时间维度：

- `wiki/syntheses/X.md` 保留 history snapshot：3 个月前 / 6 个月前的核心判断是什么
- 新 ingest 触发判断变化时，记录"判断从 A 变成 B 是因为 source Z"
- `wiki/concept_genealogy/X.md`：这个概念第一次出现 → 被挑战 → 被扩展 → 当前形态

用户价值：你回头能看到"我对这件事的看法是怎么变的"——是个人知识库少见的真正反思工具。

#### F. 知识缺口/盲点报告

扩展 `stale_report.py`，增加新检测：

- 某个 domain 有 N 篇 source 但没有 synthesis
- 某个 concept 在多个 source 中作为"前提"被用，但没有自己的定义页
- 某个 claim 是单一来源支撑的（potential 风险）
- 某个 question 已 open 6 个月没有新材料涉及
- 某个 stance 距离上次 evidence 更新已经 X 周

输出：`wiki/blind-spots.md`，每周更新一次。把维护从"被动收到 review queue"变成"主动看到我的知识漏洞"。

#### G. 输出导向——把知识库变成产能

最容易被忽视但最具粘性的 feature：**让用户从知识库产出东西**。

- "Generate essay on X"：基于 stance + syntheses + 关键 sources 生成文章草稿（带引用回链）
- "Briefing for [audience]"：根据目标读者自动调节深度
- "Reading list for someone learning Y"：从你的知识库挑出最优 N 篇推荐路径
- "Talk track for meeting on Z"：要点 + 应对反对意见的素材

这个功能直接解决"我知道很多但不会用"——是从 input 系统升级为 output 系统的关键。

### Feature 优先级建议

如果只做 3 个，选：**B（question ledger）+ A（stance pages）+ G（输出导向）**

- **B** 改造成本最低，立刻提升日常使用感（每次 ingest 都有"未答问题被推进"的反馈）
- **A** 是所有高级功能的载体（stance 页一旦存在，typed edges、演化追踪都可以挂上去）
- **G** 是粘性来源（用户每用一次就强化"我的知识库帮我产出了东西"的认知）

D（typed edges）和 E（时间演化）是中期目标，C（briefing on demand）和 F（盲点报告）是这些做完之后水到渠成的。

---

## 三、Skill 框架工程哲学

### 核心结论：分层模块化 ≠ 纯原子化

软件工程里"原子能力解耦"的直觉对，但 skill 有一个传统 library 没有的硬约束：**上下文窗口是真实成本**。每加载一个 skill 都消耗 tokens。100% 原子化反而是反模式——会让组合 skill 时上下文成本爆炸。

正确答案是**三层 skill 架构**：

| 层级 | 类型 | 职责 | 例子 | SKILL.md 大小 |
|---|---|---|---|---|
| **L1 原子能力** | Capability skill | 单一职责，无业务语义 | `pdf-extract`、`vault-discover`、`yt-dlp-wrapper` | < 50 行 |
| **L2 工作流** | Workflow skill | 组合多个 L1 完成一个领域任务 | `multi-source-fetch`、`wiki-maintenance` | 100-200 行 |
| **L3 场景** | Product skill | 用户可见的端到端体验 | `obsidian-second-brain`（当前 skill） | 100-150 行 + 引用 |

### 重构后的目录结构

```
obsidian-second-brain/                    # L3：Product skill
  SKILL.md (~120 行)
  references/
  uses:
    - knowledge-ingest
    - wiki-maintenance
    - knowledge-query

knowledge-ingest/                          # L2：Workflow skill
  uses:
    - vault-discover
    - multi-source-fetch
    - llm-compile
    - markdown-write

wiki-maintenance/                          # L2：Workflow skill
  uses:
    - markdown-lint
    - graph-ops
    - archive-ops

multi-source-fetch/                        # L2：Workflow skill
  uses:
    - wechat-fetch
    - web-fetch
    - video-fetch
    - pdf-extract

vault-discover/                            # L1：Atomic
wechat-fetch/                              # L1：Atomic（有真实 IP，建议开源）
bilibili-collection-fetch/                 # L1：Atomic（保护层是真正的原创贡献）
pdf-extract/                               # L1：Atomic
yt-dlp-wrapper/                            # L1：Atomic
```

当前 skill 实际是 L3，但内部什么都自己做，膨胀到了 L1+L2+L3 一锅炖。

### 开源策略：三类划分

**从社区取（L1 通用能力）**：PDF 提取、网页转 Markdown、yt-dlp 封装、Obsidian vault 操作。这些没差异化，复用成熟方案，自己只做薄包装。

**自己造但应该开源（L1 但有 IP）**：

- wechat-article-for-ai 整合
- **Bilibili collection 保护层**（cooldown / paused / failure-threshold 这套）——社区目前没有等价物
- cookies.txt 自动发现

把它们独立成 L1 skill 开源，社区会反向帮你优化接口，做出更通用的契约。

**绝对自留（L2/L3 业务逻辑）**：Karpathy 风格 wiki schema、claim_inventory、update_proposals 流程、review queue 设计——这是产品壁垒，不是组件。

### 上下文效率的 5 个具体打法

#### 打法 1：SKILL.md 分层 + 懒加载

顶层 SKILL.md 只放：
- 触发条件
- 五阶段心智模型（一句话）
- 路由规则（输入 → 哪个子 skill / 脚本）
- 指针：`需要 X 详情时读 references/x.md`

80% 的当前 SKILL.md 内容下沉。Claude 只在真正需要时 view 那个 reference。

#### 打法 2：跨 skill 通过 JSON 契约通信，不是自然语言

L2 调用 L1 时，L1 返回结构化 JSON（你已经在做：`AdapterResult` TypedDict）。L2 不需要加载 L1 的 SKILL.md 来理解输出，只需要知道 schema。这意味着 L1 的 SKILL.md 在被组合调用时可以**完全不进入上下文**。

#### 打法 3：轻量级 skill 清单

在 L3 顶层放一个 manifest：

```yaml
# manifest.yaml
sub_skills:
  - id: knowledge-ingest
    purpose: 把外部资料编译进 vault
    trigger: 用户给了 URL/文件/文本
    contract: docs/knowledge-ingest.schema.json
  - id: wiki-maintenance
    purpose: 健康检查与降噪
    trigger: 用户说"维护"或定期调度
    contract: docs/wiki-maintenance.schema.json
```

host-agent 先读这个 manifest（几十行）做路由，再决定加载哪个 sub-skill 的 SKILL.md。这就是 skill 版本的 dependency injection。

#### 打法 4：用代码而不是文档承载流程逻辑

很多流程逻辑现在写在 SKILL.md 里（"路由规则 1: WeChat URL → 默认 ingest..."）。这部分应该下沉到 `scripts/route.py` 之类的代码里，配套一个最小的"我会按照这个 router 工作"的提示就够了。代码在 host-agent 调用时执行，不占用上下文；文档每次都占。

#### 打法 5：消除文档重复

SKILL.md / README / workflow.md / interaction.md 里目前有大量重复内容（三种模式、五阶段、路由规则在三个地方都有）。建议：

| 文件 | 职责 | 读者 |
|---|---|---|
| `SKILL.md` | trigger + 路由 + 指向 | host-agent |
| `references/workflow.md` | 技术细节单一来源 | host-agent（懒加载） |
| `references/interaction.md` | 用户对话样例单一来源 | host-agent（懒加载） |
| `README.md` | 仓库门面 | GitHub 访客（不进 skill 上下文） |

### 具体的重构 Roadmap

**阶段 1（2 周内）**：清理技术债，不引入新功能

- `source_adapters.py` 拆成 per-source 目录
- `wiki_ingest_wechat.py` 拆出 fetch / ingest / apply 三个模块
- rename 全部 `WECHAT_WIKI_*` 环境变量
- SKILL.md 收缩到 200 行以内

**阶段 2（1 个月）**：验证三层架构

- 把 wechat / bilibili-collection / pdf-extract 三个稳定 adapter 抽成独立 L1 skill 仓库
- 定义清晰的 JSON 契约
- 验证三层架构是否真的降低了上下文成本

**阶段 3（持续）**：实施高价值 feature

- B（question ledger）→ A（stance pages）→ G（输出导向）
- 这些都是新页面类型，对当前架构是加法不是改写
- D / E / C / F 在 A+B 稳定后依次跟进

---

## 附：新页面类型汇总

| 页面类型 | 路径 | 优先级 | 依赖 |
|---|---|---|---|
| Stance pages | `wiki/stances/` | ⭐⭐⭐ 高 | v2 compile |
| Question ledger | `wiki/questions/` | ⭐⭐⭐ 高 | 现有 ingest |
| Blind-spots report | `wiki/blind-spots.md` | ⭐⭐ 中 | stale_report 扩展 |
| Concept genealogy | `wiki/concept_genealogy/` | ⭐⭐ 中 | stance pages |
| Typed graph view | `wiki/graph-typed.md` | ⭐⭐ 中 | v2 compile edge types |

---

*生成时间：2026-04-25 | 基于 Claude-obsidian-wiki-skill v2026.04.24-bili-collection-rc2 分析*
