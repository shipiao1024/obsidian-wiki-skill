# 2026-04-25-v2 Release Notes

版本建议：`2026.04.25-refactor-v2`

基于 `obsidian-wiki-skill-analysis.md` 的分析建议，完成了 Phase 1（技术债清理）、Phase 2（三层架构验证 + JSON 契约）、Phase 3（高价值特性 + 后续特性）的全面重构。

## 本版包含内容

### Phase 1：技术债清理

- `source_adapters.py`（1229 行单文件）拆成 `adapters/` 包（9 个模块 + dispatch）
- `wiki_ingest_wechat.py`（2304 行 god script）拆成 `pipeline/` 包（11 个模块）+ 薄 orchestrator
- 新增 `python -m kwiki <stage>` 阶段化 CLI（fetch/ingest/compile/apply/review）
- 环境变量 `WECHAT_WIKI_*` → `KWIKI_*` 重命名 + `env_compat.py` 兼容层
- `SKILL.md` 从 595 → 89 行，详情下沉到 `references/`
- 新增 `manifest.yaml` sub skill 路由清单
- 保留 `wiki_ingest_wechat.py` / `source_adapters.py` 作为 shim

### Phase 2：三层架构验证 + JSON 契约

- L1/L2/L3 三层架构明确在 README 中定义
- JSON 契约：`docs/specs/adapter-result.schema.json`、`kwiki-stage-output.schema.json`、`ingest-result.schema.json`
- 上下文成本从 595 行降至 89 行 + 惰加载

### Phase 3：高价值特性

- **Question Ledger**（`wiki/questions/`）— 开放问题账本，每次 ingest 自动检测是否回答 open question
- **Stance Pages**（`wiki/stances/`）— 立场页，每次 ingest 检查 reinforce/contradict/extend
- **Output 多模式**（`wiki_query.py --mode`）— brief/briefing/draft-context/contradict 四种输出模式

### 后续特性

- **知识盲点报告**（`pipeline/blindspots.py` → `wiki/blind-spots.md`）— 孤立页面、缺失交叉链接、无问题/立场的域
- **类型化关系图**（`pipeline/typed_edges.py` → `wiki/typed-graph.md`）— 6 种边类型
- **知识演化追踪**（`pipeline/evolution.py` → `wiki/evolution.md`）— 域积累、立场漂移、问题进展

### README 全面重写

- 系统架构（三层 + ASCII 层级图）
- 软件层级（L1/L2/L3 + infrastructure）
- 能力边界（做什么 / 不做什么）
- 使用方案（三种编译模式 + 四种查询模式）
- 技术栈与环境依赖（13 个 KWIKI_* 环境变量映射表）
- 关键模块一览

## 测试结果

- **97 passed, 0 failed**（之前的 4 个 pre-existing failures 已修复）
- 所有 shim 和向后兼容 import 验证通过
- `python -m kwiki <stage> --help` 五个阶段均可运行
- `env_compat.py` KWIKI_* / WECHAT_WIKI_* 双路径验证通过

## 当前使用约束

- Windows 优先，默认按 PowerShell 工作流编写
- 依赖本地 Obsidian vault
- 依赖本地 adapter 和文件系统
- Bilibili 能力依赖用户自己维护 skill 根目录 `cookies.txt`
- `raw/` 是证据层，`wiki/` 是编译层；精确事实回溯时应优先读 `raw/articles`

## 后续版本建议

- 适配器 L1 skill 仓库独立（wechat-fetch / bilibili-collection-fetch / pdf-extract）
- v2 compile prompt 增加 `open_questions` 和 stance 检查提示
- Concept genealogy（概念谱系追踪）
- Typed edges Obsidian 插件适配