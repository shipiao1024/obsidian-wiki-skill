# 2026-05-02 Release Notes — V1.2.4

版本：`2026.05.02-compile-redesign-v1.2.4`
基线：`V1.2.3 (V2 Features: Insight Detection + Deep Research Triggers + Auto Maintenance + Smart Retrieval)`

本版解决 V1.2.3 实测中发现的 12 个问题（P0-P3），核心改进是编译模式重设计、PDF 生成修复、JSON 验证门控。

## 核心变更

### 1. 编译模式重设计

**之前**：默认尝试 API 调用 → 无 key 时抛异常 → 自动降级为 prepare-only。每次无 API key 环境都走一遍注定失败的异常流程。

**现在**：三种显式模式，默认 prepare-only，无自动降级。

```
wiki_ingest.py "https://..."                  # 默认 prepare-only
wiki_ingest.py --api-compile "https://..."    # 显式 API 编译
wiki_ingest.py --no-llm-compile "https://..." # 启发式
```

| 模式 | 编译者 | 需要 API key | 适用场景 |
|------|-------|:----------:|---------|
| prepare-only（默认） | LLM agent 在对话中 | 否 | 日常入库 |
| api-compile | 脚本调 API | 是 | 无人值守批量 |
| heuristic | 启发式规则 | 否 | 快速入库 |

### 2. PDF 生成修复

三个问题一次修：
- **封面页**：brief PDF 现在有封面，标题为"{原题目} - 简报"
- **Frontmatter 泄露**：YAML 元数据不再渲染为正文
- **字体过小**：body 10.5→11.5pt，table 9→10pt，code 8.5→9.5pt

### 3. JSON 验证门控

`apply_compiled_brief_source.py` 新增 `--validate-only`：

```powershell
python scripts/apply_compiled_brief_source.py `
  --vault "D:\Vault" `
  --raw "D:\Vault\raw\articles\<slug>.md" `
  --compiled-json "result.json" `
  --validate-only
```

三层验证：结构完整性 → grounding（引用可追溯性）→ 证据密度（成熟度等级）。失败时阻止 apply。

### 4. Windows 编码修复

新增 `pipeline/encoding_fix.py`，5 个主入口脚本集成。Windows 控制台中文输出不再乱码。

### 5. 文档改进

- 新增 `ingest-quickstart.md`：75 行精简版入库指南
- Ingest guide 新增 delta 输出处理流程
- SPEC.md 更新编译模式、模块描述、环境变量说明

## Bug 修复清单

| # | 严重度 | 问题 | 修复 |
|---|--------|------|------|
| 1 | P0 | `detect_domains` 函数删除导致 NameError | 恢复函数到 `llm_compile_ingest.py` |
| 2 | P1 | 无 API key 时 auto-compile 失败 | 重设计：默认 prepare-only，不尝试 API |
| 3 | P1 | guide 中 `--schema-version 2.0` 不存在 | 从示例移除 |
| 4 | P1 | `ingest_report.py` 路径错误 | 修正为 `scripts/pipeline/ingest_report.py` |
| 5 | P1 | `apply` 示例缺 `--raw` 参数 | 补充 |
| 6 | P2 | PDF 路径解析失败 | 多路径候选列表 |
| 7 | P2 | Vault 路径重复发现 | memory 持久化 |
| 8 | P2 | JSON schema 无验证 | `--validate-only` 验证门控 |
| 9 | P3 | Windows 中文乱码 | `encoding_fix.py` |
| 10 | P3 | Ingest guide 369 行过长 | 新增 quickstart |
| 11 | P3 | Delta 输出无指引 | guide 新增处理流程 |
| 12 | P2 | PDF 无封面/frontmatter泄露/字体小 | 三项修复 |

## 改动文件

| 文件 | 改动类型 |
|------|---------|
| `scripts/pipeline/compile.py` | 重写 |
| `scripts/wiki_ingest.py` | 修改 |
| `scripts/pipeline/ingest_orchestrator.py` | 修改 |
| `scripts/pipeline/pdf_utils.py` | 修改 |
| `scripts/apply_compiled_brief_source.py` | 修改 |
| `scripts/pipeline/encoding_fix.py` | 新增 |
| `scripts/llm_compile_ingest.py` | 修改 |
| `scripts/wiki_retrieve.py` | 修改 |
| `scripts/wiki_index_v2.py` | 修改 |
| `references/ingest-quickstart.md` | 新增 |
| `references/ingest-guide.md` | 修改 |
| `SKILL.md` | 修改 |
| `docs/SPEC.md` | 修改 |
| `md-to-pdf-v1.0/scripts/md_to_pdf.py` | 修改 |

## 推荐阅读顺序

1. `README.md`
2. `references/ingest-quickstart.md`（新增，快速上手）
3. `SKILL.md`
4. `docs/2026-05-02-version-lock-v1.2.4.md`
