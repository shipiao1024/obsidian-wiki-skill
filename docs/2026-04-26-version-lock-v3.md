# 2026-04-26 Version Lock — v3 (lean-compile + trigger-refine + deep-research + kwiki-cleanup)

版本名：`2026.04.26-lean-trigger-v3`
基线版本：`2026.04.26-cross-domain-patch-v2`

## 本版新增内容（相对于上一备份点）

### 1. `--lean` 编译优化

- `llm_compile_ingest.py` 新增 `--lean` 模式（`prepare_compile_payload_v2(lean=True)`）
- 从输出中移除 `system_prompt`、`user_prompt`（宿主 Agent 是 LLM，不需要）
- 移除 `existing_source`、`existing_brief`（v2 apply 会覆盖，不需要旧内容）
- 过滤匹配 ASR 转写噪声模式的 synthesis excerpt（`_SYNTHESIS_NOISE_HEURISTICS` + `_is_noisy_synthesis_excerpt()`）
- 上下文占用从 ~58KB 降至 ~10KB（82% 减少）
- `kwiki/compile.py` 同步支持 `--lean`

### 2. Skill 触发条件重构

- SKILL.md Trigger 从纯语义描述改为三层：
  - **硬触发**：URL pattern（`mp.weixin.qq.com`、`bilibili.com/video` 等）+ 入库关键词（`落盘`、`入库`、`ingest` 等）
  - **软触发**：知识库/维护/autoresearch/deep-research 相关词汇（需 vault 上下文存在）
  - **不触发**：只是总结/翻译/解释，没有入库意图

### 3. 入库后标准引导模板

- interaction.md 新增"入库后标准引导模板"段落
- 分普通入库和高信号入库两种格式
- 固定 3 段结构：入库摘要 → 影响报告 → 下一步建议
- Deep-research 不在入库后主动推荐，仅在追问场景中建议升级

### 4. Deep-research 集成

- SKILL.md Conditional Loading 新增 Deep research 行（`deep-research-protocol.md + workflow.md`）
- interaction.md 路由规则新增 `deep-research` 意图（路由规则第 7 条）
- interaction.md 用户示例新增 13（深度研究主题）和 14（对开放问题做深度研究）
- SPEC.md 新增 4.8 深度调研和 4.9 入库后标准引导功能节
- SPEC.md 文档表新增 `deep-research-protocol.md`
- 模块组织新增 `deep_research.py`、`pipeline/deep_research.py`、`pipeline/dependency_ledger.py`

### 5. kwiki compile 清理

- 删除 `kwiki/compile.py`（v2 路径必崩：缺少 author/date/source_url/slug 必填参数）
- `kwiki/__main__.py` 移除 compile 路由
- helper-scripts.md 移除整个 kwiki CLI 文档段落
- 所有 spec 文档中 `kwiki compile` 引用替换为 `llm_compile_ingest.py`

## 全量改动文件清单

| 文件 | 改动类型 |
|------|---------|
| `scripts/llm_compile_ingest.py` | 新增 `_SYNTHESIS_NOISE_HEURISTICS`、`_is_noisy_synthesis_excerpt()`、`lean` 参数 |
| `scripts/kwiki/compile.py` | **删除** |
| `scripts/kwiki/__main__.py` | 移除 compile 路由 |
| `SKILL.md` | Trigger 重构 + Conditional Loading 新增 Deep research + Script Entrypoints 新增 deep_research.py + References 新增 deep-research-protocol.md |
| `references/interaction.md` | 入库后标准引导模板 + deep-research 路由规则 + 用户示例 13/14 + 不推荐行为补充 |
| `references/helper-scripts.md` | 移除 kwiki CLI 段落 + evolution 调用来源修正 + 描述行简化 |
| `references/workflow.md` | `--lean` 模式说明（上一版本已更新） |
| `references/pipeline-scripts.md` | `--lean` 描述（上一版本已更新） |
| `references/setup.md` | `--lean` 推荐路径（上一版本已更新） |
| `docs/SPEC.md` | 编译模式表修正 + kwiki 模块列表更新 + 新增 4.8/4.9 + deep-research-protocol.md 文档表 + 模块组织新增 3 文件 |

## 未改动但受影响的运行时行为

- `llm_compile_ingest.py --prepare-only --lean` 现在是推荐的交互式编译入口
- `python -m kwiki compile` 不再可用，所有 v2 compile 走 `llm_compile_ingest.py`
- kwiki CLI 剩余 4 个子命令（fetch/ingest/apply/review）仍可用，但大部分是薄桩

## 当前使用约束

- `--lean` 仅在 `--prepare-only` 模式下有效（非 prepare-only 时忽略）
- Deep-research 触发需要宿主 Agent 识别三要素（战略重要性 + 外部验证 + 框架风险）
- 入库后引导模板是规范约束，不是脚本强制——宿主 Agent 应遵循但不由代码校验
- kwiki CLI 的 fetch/ingest/apply 仍为薄桩，review 的 evolution/blind-spots 可实际运行
