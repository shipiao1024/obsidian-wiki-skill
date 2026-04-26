# Karpathy 风格 LLM 编译器升级设计

日期：2026-04-23

## 背景

当前 [Claude-obsidian-wiki-skill](D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/SKILL.md) 已经具备完整工作流：

- 微信文章抓取进入 `raw/`
- 自动生成 `source / brief / domain / synthesis`
- query 结果写回 `outputs/`
- `delta_compile / apply_approved_delta / review_queue / archive_outputs` 构成审核闭环

这套系统已经是一个可运行的本地知识库操作系统，但它还不是 [llm-wiki.md](D:/AI/Skill/微信文章归档Obsidian/llm-wiki.md) 所描述的 Karpathy 式强版本。

当前 ingest 的核心仍然是启发式抽取：

- `top_lines()`：切句后取前若干条
- `brief_lead()`：拼接前两条
- `extract_entities()`：正则 / 缩写 / 大写词命中
- `extract_concepts()`：seed list + 后缀规则
- `detect_domains()`：关键词打分

这意味着当前系统更接近：

- `schema-first heuristic extraction + human-gated recompilation`

而 Karpathy 原文设想的是：

- `LLM-first semantic compilation`

即：

- ingest 时由 LLM 阅读全文
- 判断哪些知识单位值得独立成页
- 判断要更新哪些旧页
- 主动标记强化、修正、冲突、推翻
- 一次 ingest 可能触达多个现有页面

## 目标

把当前系统从“规则抽取器”升级成“LLM 编译器”，但不丢掉当前已跑通的工程优势：

- Windows 本地流程
- Obsidian vault 自动发现
- `raw/` 不可变证据层
- `review-needed -> approved -> absorbed -> archived` 审核闭环
- 图谱降噪与索引控制

目标不是推倒重来，而是替换 ingest 核心，让后续 `brief/source/concept/entity/domain/synthesis` 的内容生产更接近 Karpathy 原文。

## 现状与原文差异

### 1. 提取逻辑

Karpathy 原文：

- 提取是语义理解后的结果
- LLM 根据全文决定什么是核心判断、什么只是背景叙述

当前实现：

- `source/brief` 主要依赖抽取式切句
- 容易保留叙事噪声、系列导语、样例句

差异：

- 当前没有真正的“全文理解后重写”
- 当前更多是“句子筛选”

### 2. 拆分页策略

Karpathy 原文：

- 拆分是语义驱动
- 是否创建 concept/entity/topic 页面由 LLM 判定

当前实现：

- `concept/entity` 依赖 seed、regex、重复出现阈值
- 已经比最早版本保守，但仍是规则升级

差异：

- 当前能防图谱污染，但表达能力弱
- 无法很好处理“这个词出现了，但不值得成页”与“这个词虽然只出现一次，但对领域结构极关键”的区别

### 3. 旧页更新能力

Karpathy 原文：

- 新来源进入后，旧页被直接重写或增量修订
- `synthesis` 是持续演化的主知识页

当前实现：

- ingest 只生成第一版页或补链
- 真正质量提升依赖后续 `refresh_synthesis.py`、`delta_compile.py`、`apply_approved_delta.py`

差异：

- 当前“持续维护”存在，但主要是二阶段补丁
- 原文设想的是 ingest 当下就完成主要更新

### 4. LLM 角色

Karpathy 原文：

- LLM 是 wiki 的主维护者

当前实现：

- LLM 更多在 query / delta / 审核环节发力
- ingest 主链仍偏规则程序

差异：

- 当前系统里 LLM 还不是 ingest 核心

## 设计原则

升级时遵循以下原则：

1. 不动 `raw/`

- 原文仍是最终证据层
- 无论摘要质量如何，`raw/articles/` 不被覆盖

2. 保留审核门

- LLM 编译结果不能直接覆盖高价值正式页
- 尤其是 `synthesis / source / brief`
- 继续保留 `review-needed -> absorbed`

3. 先替换生成内核，不先扩目录

- 当前目录结构已够用
- 问题不在页类型不足，而在页内容生成方式过弱

4. 优先升级 `brief/source`

- 这是 ingest 的第一层产物
- query、review、synthesis 都依赖它们

5. concept/entity 的创建权提高到 LLM 判定

- 规则阈值退居兜底
- 不再把拆页主决策交给 regex

## 方案选项

### 方案 A：保守增强

做法：

- 保留当前 ingest 骨架
- 只把 `brief/source` 的生成替换成 LLM 提示词重写
- `concept/entity/domain` 仍由规则抽取

优点：

- 侵入小
- 最容易上线

缺点：

- 仍然不是 Karpathy 式语义拆分
- concept/entity 更新质量提升有限

### 方案 B：推荐方案

做法：

- 引入一个 `llm_compile_ingest` 阶段
- LLM 输入：`raw article + 当前相关 wiki 页摘要 + schema rules`
- LLM 输出结构化编译结果：
  - brief
  - source
  - candidate concepts
  - candidate entities
  - affected domains
  - synthesis deltas
  - contradictions / reinforcements
- 规则脚本负责：
  - 预取上下文
  - 校验输出格式
  - 写入草稿页
  - 走审核吸收

优点：

- 最接近 Karpathy 原文
- 兼顾质量与可控性

缺点：

- 需要引入模型调用层
- 需要更严格的 JSON / YAML 输出约束

### 方案 C：完全 LLM 化

做法：

- ingest 期间直接由 LLM 决定所有新建页与更新页
- 脚本只做 orchestration

优点：

- 最贴近原文

缺点：

- 风险最高
- 容易把正式页污染掉
- 在当前 skill 阶段不适合直接上

## 推荐方案

推荐采用方案 B。

原因：

- 它保留当前工程控制面
- 同时把“提取 / 拆分 / 更新”的主判断权交还给 LLM
- 审核闭环还在，避免一步到位造成知识层劣化

## 当前实现进展（2026-04-24）

截至 2026-04-24，仓库内已经落地一条最小 v2 编译链：

- `llm_compile_ingest.py` 支持 `--schema-version 2.0`
- v2 输出已覆盖 `document_outputs / knowledge_proposals / update_proposals / claim_inventory / review_hints`
- `apply_compiled_brief_source.py` 会消费 `document_outputs`，并把 `update_proposals` 落成 `wiki/outputs/*.md` 的 `delta-compile` 草稿
- `wiki_ingest_wechat.py` 在 inline compile 成功时也会直接发出 `delta-compile` 草稿
- `knowledge_proposals.domains` 已参与 domain 路由
- `knowledge_proposals.concepts/entities` 中的 `promote_to_official_candidate` 已参与 taxonomy 建页
- `claim_inventory` 已进入 `delta-compile` 草稿、`review_queue.py` 和 `wiki_lint.py`
- `wiki_lint.py` 已能做 claim 质量检查与 `delta/source/synthesis` 间的保守型 claim 冲突检查

也就是说，当前系统已经从纯 `phase-1 brief/source compile` 前进到：

- `document writeback + review draft emission + claim-aware maintenance`

但还没有走到“ingest 当下直接高质量重写正式 knowledge pages”的阶段。

## 目标架构

### 新 ingest 流程

1. 抓取微信文章，写入 `raw/articles/`
2. 规则脚本抽取最小上下文：
   - 当前 raw 全文
   - 命中的 `source/brief`
   - 相关 `domain/synthesis`
   - 候选 concept/entity 现有页摘要
3. 调用 LLM 编译器
4. LLM 返回结构化结果
5. 写入：
   - `brief/source` 正式候选
   - `delta-source` / `delta-synthesis` 草稿
   - concept/entity 建页建议
6. 人工批准后吸收

### LLM 编译器输入

- 原文标题、作者、日期、来源链接
- 原文正文全文
- 当前命中的 `source/brief`
- 当前主题域 `domain/synthesis`
- schema 约束：
  - 原文是最终证据
  - 不要把推断写成事实
  - 区分“成熟节点”和“候选节点”
  - 输出必须结构化

### LLM 编译器输出

建议统一成结构化对象：

```json
{
  "brief": {
    "one_sentence": "",
    "key_points": [],
    "who_should_read": [],
    "why_revisit": []
  },
  "source": {
    "core_summary": [],
    "candidate_concepts": [],
    "candidate_entities": [],
    "domains": [],
    "knowledge_base_relation": [],
    "contradictions": [],
    "reinforcements": []
  },
  "taxonomy": {
    "concepts_to_create": [],
    "entities_to_create": [],
    "concepts_to_update": [],
    "entities_to_update": []
  },
  "synthesis": {
    "affected_pages": [],
    "delta_judgements": [],
    "delta_sources": []
  }
}
```

## 组件改造

### 1. 新增 `llm_compile_ingest.py`

职责：

- 组织 LLM prompt
- 收集上下文
- 调用模型
- 解析结构化结果

它不直接落正式页，只返回编译结果。

### 2. `wiki_ingest_wechat.py` 改成 orchestrator

当前它直接生产内容。

升级后它负责：

- 抓取
- 写 raw
- 调用 `llm_compile_ingest.py`
- 把编译结果写成候选页或草稿页
- 触发 index/log 更新

### 3. `apply_approved_delta.py` 扩展目标类型

当前主要支持：

- `delta-source -> source/brief`
- `delta-query/output -> synthesis`

升级后要支持：

- `delta-synthesis`
- `delta-taxonomy`

### 4. `review_queue.py` 增加编译草稿分组

按类型显示：

- source rewrite
- synthesis rewrite
- taxonomy decision
- temporary query

## 数据流变化

### 当前

`raw -> heuristic source/brief -> query/delta -> approved absorb`

### 升级后

`raw -> llm compile result -> draft official pages -> approved absorb`

区别是：

- query 不再承担大部分“补质量”工作
- ingest 就能产出更强的一次编译

## 风险

### 1. LLM 过度发挥

风险：

- 把推断写成事实
- 误建 concept/entity 页

控制：

- 强制结构化输出
- 强制保留 candidate / mature 区分
- 不直接覆盖正式页

### 2. token 成本上升

风险：

- 每次 ingest 读全文 + 相关旧页，成本增加

控制：

- 只读取命中域的 `source/synthesis`
- index-first，少量定向上下文
- 先做单文档 ingest，不做大批量

### 3. 审核负担回升

风险：

- 如果每篇都生成太多建议，review_queue 又会膨胀

控制：

- 每次 ingest 只允许少量高置信更新建议
- concept/entity 建页建议必须限额

## 分阶段实施

### 阶段 1

- 实现 `llm_compile_ingest.py`
- 只替换 `brief/source`
- 保留原规则抽取作为 fallback

### 阶段 2

- 让 LLM 输出 taxonomy 建议
- 由审核流决定是否真正建页

### 阶段 3

- 让 ingest 直接生成 `delta-synthesis`
- 把 `refresh_synthesis.py` 从主构建器降为修复器

### 阶段 4

- 引入更强的相关页选择器
- 当规模上升后再考虑本地搜索层

## 成功标准

升级成功的标志不是“脚本更多”，而是：

1. `brief/source` 基本不再依赖抽句拼接
2. `concept/entity` 的创建更少但更准
3. ingest 当下就能对 `synthesis` 产生有价值的增量改写
4. `review_queue` 条目减少，但单条质量提高
5. query 对 `delta_compile` 的依赖下降

## 当前结论

当前系统已经实现了 Karpathy 风格的外层操作系统：

- `raw/wiki/schema`
- `index/log`
- `query/lint/review/apply/archive`

但还没有实现 Karpathy 风格的内核：

- LLM 主导的语义提取
- LLM 主导的知识拆分
- LLM 主导的跨页更新

下一步不应继续加目录或管理脚本，而应进入：

- `llm_compile_ingest.py`

这是把当前 skill 从“可维护的本地知识库流水线”推进到“真正的 LLM Wiki 编译器”的关键步骤。

