# 2026-05-02 Version Lock — V1.2.4 (Compile Mode Redesign + PDF Fix + Validation Gate)

版本名：`2026.05.02-compile-redesign-v1.2.4`
基线版本：`V1.2.3 (V2 Features: Insight Detection + Deep Research Triggers + Auto Maintenance + Smart Retrieval)`

## 本版核心变更

### 1. 编译模式重设计

**问题**：默认行为是"先尝试 API 调用 → 失败 → 降级 prepare-only"，每次无 API key 环境都走一遍注定失败的异常流程。

**解决方案**：三种显式编译模式，默认 prepare-only，无自动降级。

| 模式 | 标志 | 行为 |
|------|------|------|
| `prepare-only` | **默认**（无需参数） | `prepare_compile_payload_v2()` 直接生成 payload |
| `api-compile` | `--api-compile` | `compile_article_v2()` 调 API，无 key 则报错 |
| `heuristic` | `--no-llm-compile` | 启发式提取，不走 LLM |

**改动文件**：
- `scripts/pipeline/compile.py`：`try_llm_compile()` 和 `try_llm_compile_two_step()` 重写为三模式 `if/elif/else` 分支，移除 RuntimeError 降级逻辑
- `scripts/wiki_ingest.py`：新增 `--api-compile` 参数，`main()` 中确定 `compile_mode` 并传递
- `scripts/pipeline/ingest_orchestrator.py`：`ingest_article()` 新增 `compile_mode` 参数（默认 `"prepare-only"`）

**设计原则**：默认路径不依赖外部 API key。`api-compile` 是 opt-in，仅在无人值守批量处理时启用。

### 2. PDF 生成修复

**三个问题**：
1. 首页无标题（`no_cover=True` 导致无封面页）
2. Frontmatter 元数据泄露为正文（`---\ntitle: "..."` 被 markdown 库渲染）
3. 正文字体过小（body 10.5pt）

**修复**：
- `scripts/pipeline/pdf_utils.py`：`clean_obsidian_syntax()` 新增 YAML frontmatter 剥离（`re.sub(r"\A---\s*\n.*?\n---\s*\n?", ...)`）；`brief_to_pdf()` 从 `no_cover=True` 改为 `no_cover=False`
- `D:\AI\Skill\md-to-pdf-v1.0\scripts\md_to_pdf.py`：CSS 字体全面调大（body 10.5→11.5pt, h2 14→15pt, h3 12→13pt, h4 11→12pt, table 9→10pt, code 8.5→9.5pt）

**封面标题**：由 `ingest_orchestrator.py` 传入 `f"{article.title} - 简报"`，封面页正确显示。

### 3. JSON Schema 验证门控

**问题**：`apply_compiled_brief_source.py` 直接加载 JSON 并应用，无任何验证。LLM 在对话中生成的 v2.0 schema JSON（~200 行）容易出错。

**解决方案**：
- `scripts/apply_compiled_brief_source.py`：新增 `--validate-only` 标志，apply 前自动执行三层验证：
  - 结构完整性（`validate_compile_result`）：schema_version、必填字段、枚举值
  - Grounding（`grounding_validate`）：引用是否可在原文找到
  - 证据密度（`density_check`）：成熟度等级（grounded/compiled/raw）
- 验证失败时拒绝应用，输出失败原因

### 4. Windows 控制台编码修复

**问题**：Windows 终端默认 GBK 编码，`json.dumps(..., ensure_ascii=False)` 输出中文时乱码。

**解决方案**：
- 新增 `scripts/pipeline/encoding_fix.py`：`fix_windows_encoding()` 函数，`sys.stdout.reconfigure(encoding="utf-8")`
- 5 个主入口脚本集成：`wiki_ingest.py`、`llm_compile_ingest.py`、`apply_compiled_brief_source.py`、`wiki_retrieve.py`、`wiki_index_v2.py`

### 5. 文档改进

- 新增 `references/ingest-quickstart.md`：精简版入库指南（~75 行），覆盖核心流程
- 修改 `references/ingest-guide.md`：新增 delta 输出处理流程章节；编译模式表更新为新设计
- 修改 `SKILL.md`：任务路由新增 quickstart 引用
- 修改 `docs/SPEC.md`：§2.6 重写为编译模式、§4.1/§4.2 更新模块描述、§10 环境变量说明

### 6. Bug 修复（从 V1.2.3 遗留）

| Bug | 严重度 | 修复 |
|-----|--------|------|
| `detect_domains` 函数被删除导致 NameError | P0 | 在 `llm_compile_ingest.py` 恢复函数，从 `pipeline.types` 导入域配置 |
| `--schema-version 2.0` 参数不存在 | P1 | 从 ingest-guide 示例中移除 |
| `ingest_report.py` 路径错误 | P1 | 修正为 `scripts/pipeline/ingest_report.py` |
| `apply_compiled_brief_source.py` 示例缺 `--raw` | P1 | 补充参数 |
| `pdf_utils.py` 路径解析失败 | P2 | 改用多路径候选列表 |
| Vault 路径重复发现 | P2 | 写入 memory 持久化 |

## 全量改动文件清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `scripts/pipeline/compile.py` | **重写** | 三模式显式分支，移除降级逻辑 |
| `scripts/wiki_ingest.py` | 修改 | 新增 `--api-compile`，编码修复 |
| `scripts/pipeline/ingest_orchestrator.py` | 修改 | 新增 `compile_mode` 参数 |
| `scripts/pipeline/pdf_utils.py` | 修改 | frontmatter 剥离 + 封面页 |
| `scripts/apply_compiled_brief_source.py` | 修改 | `--validate-only` 验证门控 + 编码修复 |
| `scripts/pipeline/encoding_fix.py` | **新增** | Windows UTF-8 编码修复 |
| `scripts/llm_compile_ingest.py` | 修改 | `detect_domains` 恢复 + 编码修复 |
| `scripts/wiki_retrieve.py` | 修改 | 编码修复 |
| `scripts/wiki_index_v2.py` | 修改 | 编码修复 |
| `references/ingest-quickstart.md` | **新增** | 精简版入库指南 |
| `references/ingest-guide.md` | 修改 | 编译模式更新 + delta 指引 |
| `SKILL.md` | 修改 | quickstart 引用 |
| `docs/SPEC.md` | 修改 | 编译模式 + 模块描述 + 环境变量 |
| `D:\AI\Skill\md-to-pdf-v1.0\scripts\md_to_pdf.py` | 修改 | CSS 字体调大 |

## 验收标准

- [x] 无 API key 时 `wiki_ingest.py` 直接走 prepare-only，无异常流程
- [x] `--api-compile` 显式启用 API 编译
- [x] Brief PDF 有封面页，标题为"{原题目} - 简报"
- [x] PDF 无 frontmatter 泄露
- [x] PDF 正文字体可读（body 11.5pt）
- [x] `--validate-only` 输出结构/grounding/密度三层验证
- [x] `--validate-only` 失败时阻止 apply
- [x] Windows 控制台中文输出正常
- [x] ingest-guide 编译模式描述与代码一致
- [x] SPEC.md 与实际设计一致

## 与上一版本的兼容性

- `--no-llm-compile` 保留，行为不变（等同于 `mode="heuristic"`）
- `llm_compile_ingest.py --prepare-only --lean` 保留，可独立使用
- `try_llm_compile()` 的 `disabled` 参数保留向后兼容（映射到 `mode="heuristic"`）
- 所有现有脚本参数不变，`--api-compile` 为新增 opt-in
