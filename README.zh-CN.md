# Obsidian Wiki Skill

[English](README.md) | [简体中文](README.zh-CN.md)

**把外部知识编译进 Obsidian，构建可检索、可推理、可演化的个人知识操作系统。**

不是做一次性摘要——而是把阅读过的一切沉淀成两层：

```
raw/    ← 不可变原始证据（最终事实来源）
wiki/   ← AI 编译知识层（可演化、可检索、可输出）
```

通过 Claude Code 对话驱动，Python 脚本处理文件系统，Obsidian 提供浏览和图谱。

设计思想参考 [Karpathy 的 llm-wiki 方法论](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)：ingest 是编译而不是归档，LLM 把原始资料编译为持久 Wiki，prefer 链接而非重复，知识的价值在于可积累、可关联、可演化。

---

## 为什么构建这个

个人知识库有一个普遍失败模式：导入几百篇文章后三个月就停止维护，因为**写入的成本是可见的，读出的价值却不是**。

这个 skill 试图扭转这个方向——每次入库之后，知识库不只是"多了一篇"，而是：

- 自动检测这篇文章对你**现有立场的影响**（reinforce / contradict / extend）
- 自动将内容与**已有开放问题关联**（open question 推进 → partial → resolved）
- 在 8 种查询模式下随时转化为**可直接使用的输出**（简报/会议素材/文章草稿/反驳材料）
- 支持 9 阶段**假说驱动深度调研**，联网验证，产出带证据标注的结构化报告
- 入库后展示**影响报告**：跨域联想、开放问题、立场影响，而非只说"写入完成"

---

## 核心能力

### 📥 多源统一入库

| 来源 | 支持 |
|------|------|
| 微信公众号文章 | ✅ |
| 通用网页 | ✅ |
| YouTube / Bilibili / 抖音 视频（字幕优先，ASR fallback）| ✅ |
| 视频合集/频道（断点续跑 + 冷却保护）| ✅ |
| 本地 Markdown / PDF / HTML / TXT | ✅ |
| 直接粘贴纯文本 | ✅ |

入库自动执行**域优先路由**：检测内容主题域，自动匹配各 vault 的 `purpose.md` 关注领域，选最高重叠的 vault 落盘。不需用户反复选择。

### 🗺️ 知识层结构

```
wiki/
  briefs/       ← 一句话结论 + 核心要点（快速浏览层）
  sources/      ← 核心摘要 + 关联 + 声明（蒸馏层）
  concepts/     ← 概念页（跨来源聚合，≥2 来源提及后才升级为正式节点）
  entities/     ← 实体页（人/公司/产品/方法）
  domains/      ← 域页（主题领域边界与导航）
  syntheses/    ← 综合分析页（跨来源综合）
  questions/    ← 问题追踪（open → partial → resolved → dropped）
  stances/      ← 立场页（我对 X 的当前判断 + 证据）
  comparisons/  ← 结构化对比（A vs B：维度 + 优劣 + 综合判断）
  outputs/      ← 临时工作产物（图谱隐藏，不污染主知识层）
```

**保真度排序**：`raw/articles/` > `wiki/sources/` > `wiki/briefs/`

**页面状态生命周期**：`seed` → `developing`（≥1 引用）→ `mature`（≥3 引用）→ `evergreen`（≥6 引用）。状态在每次 ingest 时自动升级。

### 🔍 8 种查询输出模式

```powershell
python scripts/wiki_query.py "<问题>" --mode <mode> --vault <path>
```

| 模式 | 适用场景 | 输出 |
|------|---------|------|
| `brief` | 快速了解 | 来源摘录 |
| `briefing` | 会议前准备 | 结构化简报：来源 + 主张 + 争议 + 开放问题 + 立场 |
| `draft-context` | 喂给 LLM 做二次分析 | 带 `[[ref]]` 回链的素材包 |
| `contradict` | 找反方论据 | 最强反驳 + steel-man |
| `digest --deep` | 深度研究 | 多源报告：背景 + 观点 + 对比 + 未解问题 |
| `digest --compare` | 技术路线对比 | Markdown 对比表 |
| `digest --timeline` | 追踪发展脉络 | Mermaid 时间线 |
| `essay` | 写文章 | 有论点 + 来源依据的草稿（带 `[[ref]]`）|
| `reading-list` | 系统学习 | 依赖拓扑排序的阅读路径 |
| `talk-track` | 开会 | 核心论点 + 反驳 + 待讨论问题 |

### 📊 知识图谱（三种形态）

| 图谱 | 生成方式 | 使用方式 |
|------|---------|---------|
| `wiki/graph-view.md` | Mermaid 静态图（≤30 节点度数剪枝）| Obsidian 内直接渲染 |
| `wiki/typed-graph.md` | 类型化边（supports/contradicts/answers/evolves）| `--typed-edges` 参数 |
| 交互式 HTML | D3.js + Louvain 社区检测 + 边权重 | 浏览器打开 |

图谱降噪约定：`raw/articles/`、`sources/`、`briefs/`、`outputs/` 不进主图谱；`concepts/entities` 需 ≥2 来源引用才进主图谱。

### 🔬 深度调研（Deep Research）

假说驱动的 9 阶段调研协议，结合知识库存量知识与联网搜索，产出带证据标注的结构化报告。

**触发词**：`深入研究 X` / `deep research X` / `系统分析 X`

```
Phase 0: 上下文收集（hot.md + 已有立场/问题）
Phase 1: 意图扩展（挖掘真实问题）
Phase 2: 假说形成（2-4 个可证伪假说）
Phase 3: Vault 证据分类（F/I/A 节点）
Phase 4: 联网研究（adaptive rounds，证据充分性门控）
Phase 5: 外部事实校准
Phase 6: 根本问题挖掘
Phase 7: 情景压力测试
Phase 8: 预验尸（failure mode analysis）
Phase 9: 收敛 + Why/What/How/Trace 报告
```

所有断言携带证据标签：`[Fact]` / `[Inference]` / `[Assumption]` / `[Hypothesis X%]` / `[Disputed]` / `[Gap]`

### 🔄 入库后影响报告

每次入库完成后，宿主 Agent 必须展示影响报告（而非只返回"写入完成"）：

```
入库完成：{标题} → {vault 名称}
快读入口：[[briefs/{slug}]]
编译质量：{structured | raw-extract}
新增：{N 个概念候选, N 个实体候选, N 个开放问题}
跨域联想：{概念 → 领域映射, bridge_logic}  ← 仅高信号入库
开放问题：{问题列表}                        ← 仅高信号入库
```

---

## 快速上手

### 1. 安装依赖

```powershell
# 检查并安装所有依赖（中国用户加 --china 使用镜像）
python scripts/check_deps.py --install
# 中国镜像
python scripts/check_deps.py --install --china
```

依赖分组：`core` / `wechat` / `video` / `video_asr` / `pdf` / `web`

微信抓取依赖 [wechat-article-for-ai](https://github.com/bzd6661/wechat-article-for-ai)（Camoufox 反检测浏览器）。

### 2. 初始化 Vault

```powershell
python scripts/init_vault.py --vault "D:\Obsidian\MyVault"
```

### 3. 入库

```powershell
# 启发式入库（无需额外 API）
python scripts/wiki_ingest.py --vault "D:\Vault" --no-llm-compile "https://mp.weixin.qq.com/s/..."

# YouTube 视频
python scripts/wiki_ingest.py --vault "D:\Vault" --no-llm-compile "https://www.youtube.com/watch?v=..."

# 本地文件
python scripts/wiki_ingest.py --vault "D:\Vault" --no-llm-compile "D:\notes\article.pdf"
```

**Claude Code 交互式入库（推荐，质量更高）**：

在 Claude Code 对话里直接给一个 URL，说"入库"或"落盘"即可。skill 会自动：
1. 抓取内容 → 写入 `raw/`
2. 生成精简编译上下文（`--prepare-only --lean`，约 10KB，上下文占用减少 ~80%）
3. Claude Code 在对话中生成 v2 结构化 JSON（含 knowledge_proposals / cross_domain_insights / claim_inventory / open_questions）
4. `apply_compiled_brief_source.py` 写入 `wiki/` 全层，刷新 taxonomy/synthesis/delta
5. 展示入库影响报告

### 4. 查询

```powershell
# 会议前准备
python scripts/wiki_query.py "端到端自动驾驶的技术路线" --mode briefing --vault "D:\Vault"

# 写文章用素材
python scripts/wiki_query.py "BEV vs 纯视觉的核心争议" --mode essay --vault "D:\Vault"

# 找最强反驳
python scripts/wiki_query.py "反驳纯视觉方案足够安全" --mode contradict --vault "D:\Vault"
```

### 5. 日常维护

```powershell
# 健康检查
python scripts/wiki_lint.py --vault "D:\Vault"

# 盲区检测（哪些领域缺少问题/立场/综合）
python scripts/stale_report.py --vault "D:\Vault" --blind-spots

# 刷新综合分析页
python scripts/refresh_synthesis.py --vault "D:\Vault"

# 知识图谱（Mermaid + 有类型边）
python scripts/export_main_graph.py --vault "D:\Vault" --typed-edges

# 审核队列
python scripts/review_queue.py --vault "D:\Vault" --write

# 归档重复 output
python scripts/archive_outputs.py --vault "D:\Vault" --apply
```

---

## 架构概览

```
obsidian-wiki-skill/
  SKILL.md              ← 56 行，host-agent 路由表（按任务条件加载 references/）
  manifest.yaml         ← 6 个子 skill 定义（ingest/review/query/helper/video/deep-research）

  scripts/
    wiki_ingest.py      ← 主入口 orchestrator（域优先路由 + 多源适配）
    wiki_query.py       ← 查询入口（8 种输出模式）
    wiki_lint.py        ← 健康检查
    llm_compile_ingest.py ← LLM 编译（--prepare-only --lean 交互模式，~10KB payload）
    apply_compiled_brief_source.py ← 回写宿主 Agent 产出的结构化 JSON

    adapters/           ← 源适配器包（wechat/web/video/local/text/collection/...）
    pipeline/           ← 流水线核心（fetch/ingest/compile/apply/output/...）
    kwiki/              ← CLI 入口（python -m kwiki <stage>）

  references/           ← 分主题文档（按需加载，不全量进上下文）
    workflow.md         ← pipeline + vault 结构 + 页面状态生命周期
    interaction.md      ← 用户对话路由 + 入库后引导模板
    pipeline-scripts.md ← ingest / compile / apply 脚本详情
    deep-research-protocol.md ← 9 阶段调研协议
    stance-schema.md    ← 立场页模板
    question-schema.md  ← 问题追踪模板
    output-modes.md     ← 8 种查询模式说明
    examples/           ← agent_interactive_compiled_result.json 等示例
    ...

  docs/SPEC.md          ← 完整产品与技术规格（不参与运行时）
```

### 执行模式对比

| 模式 | 编译者 | 需要额外 API | 质量 | 适用场景 |
|------|-------|------------|------|---------|
| **Claude Code 交互** | Claude Code 本身 | 否 | 最高 | 日常入库、单篇精读 |
| **脚本直连 API** | 外部 OpenAI 兼容接口 | 是 | 取决于模型 | 批量处理、定时任务 |
| **启发式（no-llm）** | 规则提取 | 否 | 基础 | 快速初抓、离线使用 |

### v2 编译产出字段

交互式入库走 v2 schema，宿主 Agent 产出的 JSON 包含：

| 字段 | 说明 |
|------|------|
| `compile_target` | 编译目标元信息（vault、slug、title、author、date）|
| `document_outputs` | brief（one_sentence + key_points）+ source（core_summary + contradictions + reinforcements）|
| `knowledge_proposals` | domains / concepts / entities 各带 action（link_existing / create_candidate / no_page）和 confidence |
| `update_proposals` | 对已有页面的更新建议（写入 `wiki/outputs/` delta 草稿，不直接覆盖）|
| `claim_inventory` | 核心论断清单，含 claim_type / confidence / verification_needed |
| `open_questions` | 内容衍生的可追踪问题 |
| `cross_domain_insights` | 跨域类比推理（mapped_concept → target_domain + bridge_logic + potential_question）|
| `stance_impacts` | 对已有立场页的影响 |
| `review_hints` | 复核优先级和建议 |

**注意**：v2 JSON 顶层必须带 `"version": "2.0"` key，`apply_compiled_brief_source.py` 据此识别 schema 版本。`core_summary` 必须为字符串列表（list of strings），不能是单个字符串。

---

## 环境要求

- **OS**：Windows（PowerShell），Linux/Mac 非官方支持
- **Python**：3.11+
- **Obsidian Desktop**：本地 vault

核心 Python 依赖为零（全部 stdlib）。各来源类型按需安装：

| 来源 | 额外依赖 |
|------|---------|
| 微信公众号 | `camoufox[geoip]` + `markdownify` + `beautifulsoup4` + `httpx` |
| 视频（字幕）| `yt-dlp` |
| 视频（无字幕 ASR）| `faster-whisper` |
| PDF | `pypdf` |
| 通用网页 | `baoyu-url-to-markdown`（npm） |

### 环境变量

新环境变量使用 `KWIKI_*` 前缀，旧 `WECHAT_WIKI_*` 前缀通过 `env_compat.py` 自动兼容：

| 新名称 | 旧名称 | 说明 |
|--------|--------|------|
| `KWIKI_WEB_ADAPTER_BIN` | `WECHAT_WIKI_WEB_ADAPTER_BIN` | 网页适配器命令 |
| `KWIKI_VIDEO_ADAPTER_BIN` | `WECHAT_WIKI_VIDEO_ADAPTER_BIN` | 视频适配器命令 |
| `KWIKI_API_KEY` | `WECHAT_WIKI_API_KEY` | LLM API 密钥 |
| `KWIKI_COMPILE_MODEL` | `WECHAT_WIKI_COMPILE_MODEL` | LLM 编译模型 |
| `KWIKI_WECHAT_TOOL_DIR` | `WECHAT_ARTICLE_FOR_AI_DIR` | wechat-article-for-ai 路径 |
| `KWIKI_DEPS_DIR` | `WECHAT_ARTICLE_PYTHONPATH` | Python 依赖路径 |

完整环境变量列表见 [references/setup.md](references/setup.md)。

---

## 常见故障

| 问题 | 排查 |
|------|------|
| 微信 URL 失败 | 检查 `.tools\wechat-article-for-ai` 存在，`KWIKI_WECHAT_TOOL_DIR` 已设置 |
| 网页 URL 失败 | 检查 `baoyu-url-to-markdown` 在 PATH，区分为 `browser_not_ready` 或 `network_failed` |
| Bilibili HTTP 412 | 登录态问题，检查 `cookies.txt` |
| 合集反复失败 | 查看 `wiki/import-jobs/*.md` 的 `cooldown_until` |
| v2 JSON apply 报错 | 检查顶层是否有 `"version": "2.0"`，`core_summary` 是否为列表 |

---

## 测试

```powershell
python -m pytest tests/ -q
```

93 passed，4 个预存在失败（因 wechat-article-for-ai 未安装）。

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [docs/SPEC.md](docs/SPEC.md) | 完整产品与技术规格 |
| [references/setup.md](references/setup.md) | 环境配置与依赖安装（含中国镜像指南）|
| [references/workflow.md](references/workflow.md) | 操作模式、pipeline、vault 结构、页面约定、状态生命周期 |
| [references/interaction.md](references/interaction.md) | 用户对话路由、入库后引导模板、状态词汇 |
| [references/pipeline-scripts.md](references/pipeline-scripts.md) | ingest / compile / apply 脚本详情 |
| [references/deep-research-protocol.md](references/deep-research-protocol.md) | 9 阶段深度调研协议 |
| [references/output-modes.md](references/output-modes.md) | 8 种查询模式详解 |
| [references/stance-schema.md](references/stance-schema.md) | 立场页模板与状态机 |
| [references/question-schema.md](references/question-schema.md) | 问题追踪模板 |
| [references/video-rules.md](references/video-rules.md) | 视频处理与合集保护规则 |
| [references/cross-project-access.md](references/cross-project-access.md) | 跨项目只读 vault 访问 |

---

## 设计原则

**两层证据原则**：`raw/` 是最终证据层，永久不可变；`wiki/` 是可演化的编译层，可迭代维护。精确数字/日期/原文引用必须回看 `raw/`，理解与分析看 `wiki/`。

**host-agent 优先**：Claude Code 是主入口，脚本是支撑。AI 做语义理解，脚本做文件操作。用户体验是对话，不是命令行序列。

**概念成熟度门槛**：concept/entity 不会因"提到一次就建页"，必须 ≥2 来源稳定引用才升级为正式图谱节点，避免污染知识图谱。

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

## License

MIT
