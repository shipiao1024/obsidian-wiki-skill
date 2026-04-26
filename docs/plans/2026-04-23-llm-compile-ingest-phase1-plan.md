# LLM Compile Ingest 阶段 1 实施计划

日期：2026-04-23

关联设计：

- [Karpathy 风格 LLM 编译器升级设计](D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/docs/specs/2026-04-23-karpathy-llm-compiler-upgrade-design.md)

## 目标

在不破坏现有 Windows + Obsidian + 审核闭环的前提下，完成第一阶段最小升级：

- 引入 `llm_compile_ingest.py`
- 只替换 `brief/source` 的内容生成内核
- 保留现有 `domain/concept/entity` 规则逻辑作为 fallback
- 不直接覆盖正式页，而是先生成可审查候选

阶段 1 的目标不是“实现完整 Karpathy 版本”，而是验证：

- ingest 是否能由 LLM 生成更高质量的 `brief/source`
- 编译结果是否能稳定结构化
- 审核闭环是否能承接新的编译结果

## 非目标

本阶段不做以下内容：

- 不把 `concept/entity/domain` 的建页主决策完全交给 LLM
- 不新增向量检索
- 不重写 `review_queue.py`
- 不替换 `delta_compile.py`
- 不直接修改 `raw/`
- 不引入复杂 GUI 或后台服务

## 实施范围

### 新增

1. `scripts/llm_compile_ingest.py`

职责：

- 读取单篇 `raw` 文章上下文
- 读取少量相关 wiki 上下文
- 调用 LLM 编译 prompt
- 返回结构化编译结果

2. `references/prompts/ingest_compile_prompt.md`

职责：

- 固化阶段 1 的 LLM 编译提示词
- 避免 prompt 逻辑散在脚本里

3. `docs/plans/` 当前文档

职责：

- 固定实施边界
- 控制范围

### 修改

1. `scripts/wiki_ingest_wechat.py`

改造为 orchestrator：

- 继续负责抓取、写 raw、更新 index/log
- 新增一个“尝试 LLM 编译”的分支
- LLM 编译失败时回退到现有启发式逻辑

2. `references/setup.md`

补充：

- 编译模型配置方式
- API key / 环境变量说明

3. `SKILL.md`

补充：

- 阶段 1 的编译模式与 fallback 行为

## 数据流

### 当前

`fetch -> raw -> heuristic brief/source -> taxonomy/synthesis -> index/log`

### 阶段 1

`fetch -> raw -> llm_compile_ingest -> compiled brief/source`

失败时：

`fetch -> raw -> heuristic brief/source`

后续：

`taxonomy/synthesis -> index/log`

也就是说：

- LLM 编译只替换 `brief/source` 内容生产
- 其余流程先不动

## 输入输出设计

### `llm_compile_ingest.py` 输入

建议 CLI 形态：

```powershell
python Claude-obsidian-wiki-skill\scripts\llm_compile_ingest.py `
  --vault "D:\Obsidian\MyVault" `
  --raw "D:\Obsidian\MyVault\raw\articles\<slug>.md" `
  --title "..." `
  --author "..." `
  --date "..." `
  --source-url "..."
```

最小输入内容：

- raw article markdown
- 当前命中的相关页摘要：
  - 同 slug 的旧 `source` / `brief`（若存在）
  - 命中的 `domain` / `synthesis`
- schema 约束摘要

### `llm_compile_ingest.py` 输出

阶段 1 只需要稳定输出：

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
  }
}
```

注意：

- 先不要让阶段 1 输出 `concepts_to_create`
- 先不要让阶段 1 输出 `delta-synthesis`
- 范围收窄，先把 `brief/source` 做稳

## Prompt 约束

Prompt 必须明确要求：

1. 原文是最终证据
- 不得编造未出现事实

2. 输出必须结构化
- 如果不能确定，留空或输出保守内容

3. `brief` 是快读层
- 可以压缩
- 不要求全面

4. `source` 是较高保真层
- 结论必须可追溯
- 强调判断、定义、关系

5. 候选概念/实体不是正式建页指令
- 只是建议

## 与现有脚本的接缝

### `wiki_ingest_wechat.py`

现有 `ingest_article()`：

- `build_raw_page()`
- `build_brief_page()`
- `build_source_page()`
- `ensure_taxonomy_pages()`
- `ensure_synthesis_pages()`

阶段 1 改法：

1. 继续先写 `raw`
2. 调用 `llm_compile_ingest.py`
3. 如果成功：
   - 用编译结果渲染 `brief/source`
4. 如果失败：
   - 回落到当前 `build_brief_page()` / `build_source_page()`
5. taxonomy/synthesis 暂时仍走现有逻辑

### 新增渲染函数

建议在 `wiki_ingest_wechat.py` 中补：

- `build_brief_page_from_compile()`
- `build_source_page_from_compile()`

这样不会污染现有启发式函数。

## 模型调用策略

阶段 1 不把模型调用写死。

建议环境变量方式：

- `WECHAT_WIKI_COMPILE_PROVIDER`
- `WECHAT_WIKI_COMPILE_MODEL`
- `WECHAT_WIKI_API_KEY`
- `WECHAT_WIKI_API_BASE`

脚本内部先支持一种最小调用模式即可。

推荐：

- 优先支持 OpenAI-compatible chat completion

原因：

- 工程实现最简单
- 便于后续切模型

## 失败与降级

这是阶段 1 的关键。

必须支持以下降级路径：

1. 未配置 API
- 直接回退启发式模式

2. LLM 输出非法 JSON
- 记录错误
- 回退启发式模式

3. LLM 输出结构缺字段
- 做最小容错
- 缺失字段用空数组或默认文案

4. 网络或配额问题
- 回退启发式模式

原则：

- 不能因为编译器失败让 ingest 整体失败

## 验证标准

阶段 1 完成后，至少验证：

1. 同一篇测试微信文章
- 启发式模式能跑
- LLM 编译模式也能跑

2. `brief`
- 不再只是前两句拼接
- 结论更像真正总结

3. `source`
- 核心摘要质量高于 `top_lines()`
- 候选概念/实体更少但更准

4. 降级
- 断开模型配置后仍能正常 ingest

5. 兼容现有审核链
- `review_queue / apply_approved_delta / archive_outputs` 不受破坏

## 实施批次

### 批次 1

- 新建 `llm_compile_ingest.py`
- 新建 prompt 文件
- 跑通本地结构化输出

### 批次 2

- 在 `wiki_ingest_wechat.py` 中接入编译分支
- 实现 fallback

### 批次 3

- 用测试文章对比启发式 vs LLM 编译结果
- 调整 prompt 和渲染模板

### 批次 4

- 更新 `SKILL.md` / `setup.md`
- 增加运行说明

## 风险判断

最大风险不是调用模型本身，而是：

- 结构化输出不稳定
- 摘要看起来更像“流畅废话”
- 候选概念/实体过多

所以阶段 1 成功的关键不是“调用成功”，而是：

- 输出保守
- 结构稳定
- 有 fallback

## 下一步编码建议

进入编码时，第一批只做：

1. `llm_compile_ingest.py`
2. prompt 文件
3. `wiki_ingest_wechat.py` 的最小接缝

先不碰：

- `delta_compile.py`
- `apply_approved_delta.py`
- `review_queue.py`

因为这些属于现有稳定控制面，不应和新编译内核同时改。

